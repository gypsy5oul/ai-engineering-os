#!/usr/bin/env python3
"""The invariants a task graph must satisfy that its schema cannot express.

JSON Schema validates shape. It cannot say that a parent exists, that one agent
holds one task, that an accepted task satisfied its contract, or that a derived
dependency points at something real. Those checks existed -- scattered across
workitem.py, control_loop.py, the hooks and the tests -- which means the next
field added to the graph will be missed by whichever of those five places nobody
thought about.

One place, so a new mutation has one thing to answer to.

    validate_graph_semantics.py --project . --item ACME-FEAT-001
    validate_graph_semantics.py --project .            # every work item
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import workitem as W  # noqa: E402
import check_dod  # noqa: E402

TERMINAL_OK_LEASE = ("working", "review", "assigned", "rework")


def invariants(project, item_id, graph, item):
    """Every violation, as (severity, invariant, message)."""
    return structural(graph) + contractual(project, item_id, graph)


def structural(graph):
    """The invariants that need only the graph.

    Separated from the contractual ones because these are cheap -- no artifact is
    read and no predicate is evaluated -- which is what makes it possible to run
    them on every write rather than in the gate afterwards. A validator that only
    runs later tells you an invalid state was created; one that runs on the write
    stops it being created.
    """
    out = []
    tasks = {t["id"]: t for t in graph.get("tasks", [])}

    def bad(name, message, severity="ERROR"):
        out.append((severity, name, message))

    leases = {}
    natives = {}
    for tid, t in sorted(tasks.items()):
        # --- structure
        parent = t.get("parent")
        if parent is not None:
            if parent == tid:
                bad("parent_is_not_self", "%s is its own parent" % tid)
            elif parent not in tasks:
                bad("parent_exists", "%s names parent %s, which is not in this graph"
                    % (tid, parent))
            elif tasks[parent].get("parent"):
                bad("one_level_of_decomposition",
                    "%s is a child of %s, which is itself a child. The synthesis policy permits "
                    "one level." % (tid, parent))
        for dep in t.get("depends_on") or []:
            if dep not in tasks:
                bad("dependency_exists", "%s depends on %s, which is not in this graph"
                    % (tid, dep))
            elif dep == tid:
                bad("no_self_dependency", "%s depends on itself" % tid)
        for d in t.get("derived_depends_on") or []:
            if d["task"] not in tasks:
                bad("derived_dependency_exists",
                    "%s has a derived dependency on %s, which is not in this graph"
                    % (tid, d["task"]))
            elif d["task"] not in (t.get("depends_on") or []):
                bad("derived_dependency_is_applied",
                    "%s records a derived dependency on %s and does not depend on it. The "
                    "evidence was kept and the edge was not." % (tid, d["task"]))

        # --- runtime ownership
        owner = t.get("owner_agent")
        if owner:
            if owner in leases:
                bad("one_agent_one_task",
                    "agent %s holds both %s and %s. A lease is what attributes a result to a "
                    "task; two of them attribute it to neither." % (owner, leases[owner], tid))
            leases[owner] = tid
            if t["state"] in W.TERMINAL:
                bad("terminal_tasks_hold_no_lease",
                    "%s is %s and still leased to %s" % (tid, t["state"], owner))
            elif t["state"] not in TERMINAL_OK_LEASE:
                bad("a_lease_implies_work_in_progress",
                    "%s is leased to %s while in state %s" % (tid, owner, t["state"]),
                    severity="WARN")
            if W.lease_expired(t):
                bad("no_authoritative_expired_lease",
                    "%s has been held by %s since %s, past the lease TTL. It should have been "
                    "reclaimed." % (tid, owner, t.get("last_activity")), severity="WARN")
        elif t.get("owner_session"):
            bad("no_session_without_an_agent",
                "%s records owner_session %s and no owner_agent" % (tid, t["owner_session"]))

        native = t.get("native_task")
        if native:
            if native in natives:
                bad("one_native_task_one_graph_task",
                    "native task %s is bound to both %s and %s" % (native, natives[native], tid))
            natives[native] = tid

        # --- execution truthfulness
        ex = t.get("execution")
        if isinstance(ex, dict):
            if ex.get("actual") and not ex.get("actual_evidence"):
                bad("actual_requires_evidence",
                    "%s claims actual execution %r with no evidence. Without it, `actual` is a "
                    "copy of `resolved` wearing another name." % (tid, ex["actual"]))
            if ex.get("actual_undetermined") and not ex.get("actual_evidence"):
                # "I do not know" is still a claim about the runtime, and it is
                # only worth anything if something was actually observed. The
                # invariant was one-sided: not knowing needed no observation.
                bad("undetermined_requires_evidence",
                    "%s records actual_undetermined with no evidence. Not knowing what ran is a "
                    "conclusion from an observation, not a substitute for one." % tid)
            if ex.get("actual") and ex.get("actual_undetermined"):
                bad("actual_is_not_both_known_and_unknown",
                    "%s records both actual=%r and actual_undetermined" % (tid, ex["actual"]))
            if ex.get("resolved") and not ex.get("resolution_reason"):
                bad("a_resolution_says_why",
                    "%s resolved to %r with no reason recorded" % (tid, ex["resolved"]),
                    severity="WARN")

        # --- acceptance
        if t["state"] == "accepted":
            kids = [c["id"] for c in W.children_of(graph, tid) if c["state"] != "accepted"]
            if kids:
                bad("accepted_parent_has_accepted_children",
                    "%s is accepted and %d of its tasks are not: %s. The stage stands for its "
                    "pieces." % (tid, len(kids), ", ".join(kids)))
            unmet = [d for d in (t.get("depends_on") or [])
                     if d in tasks and tasks[d]["state"] != "accepted"]
            if unmet:
                bad("accepted_after_its_dependencies",
                    "%s is accepted while it still waits on %s" % (tid, ", ".join(unmet)),
                    severity="WARN")

    for cycle in cycles(tasks):
        bad("acyclic", "these tasks wait on each other: %s" % " -> ".join(cycle))
    return out


def contractual(project, item_id, graph):
    """The invariants that need the artifacts on disk.

    Every one of these reads the project and evaluates predicates, so they run in
    the gate and from the CLI, not on every write.
    """
    out = []
    tasks = {t["id"]: t for t in graph.get("tasks", [])}

    def bad(name, message, severity="ERROR"):
        out.append((severity, name, message))

    accepted = [t for t in tasks.values()
                if t["state"] == "accepted" and t.get("definition_of_done")]
    if accepted:
        artifacts = check_dod.scope_to_change(check_dod.load_artifacts(project), item_id)
        for t in accepted:
            result = check_dod.acceptance(project, t, change=item_id, artifacts=artifacts)
            if result["failing"]:
                bad("accepted_means_the_contract_was_met",
                    "%s is accepted and %d predicate(s) of its definition of done fail: %s"
                    % (t["id"], len(result["failing"]), "; ".join(result["failing"][:2])))
            if result["unsupported"] and str(t.get("risk", "")).upper() in ("HIGH", "CRITICAL"):
                bad("unanswerable_is_not_satisfied",
                    "%s is accepted %s-risk work with %d predicate(s) nothing can answer: %s"
                    % (t["id"], t.get("risk"), len(result["unsupported"]),
                       "; ".join(result["unsupported"][:2])))

    # CRITICAL work is not sent where nobody is watching. This used to live in
    # resolve_execution as `declared == "background" -> subagent`, a branch that
    # could never fire: no stage may declare `background`, because the workflow
    # schema has only ever allowed inline, subagent and team. The rule was real
    # and its implementation was unreachable, so it moved here -- to the runtime
    # property that actually records detachment, checked against what happened
    # rather than against what was asked for.
    for t in tasks.values():
        execution = t.get("execution")
        runtime = (execution or {}).get("runtime") if isinstance(execution, dict) else None
        if not isinstance(runtime, dict):
            continue
        if runtime.get("background") and str(t.get("risk", "")).upper() == "CRITICAL":
            bad("critical_work_is_watched",
                "%s is CRITICAL and its runtime records background execution. Detaching "
                "CRITICAL work sends it where nobody is watching; the risk class is the "
                "reason, and the mode it declared is not." % t["id"])
    return out


def cycles(tasks):
    found, state = [], {}

    def walk(tid, trail):
        if state.get(tid) == "done":
            return
        if state.get(tid) == "open":
            found.append(trail[trail.index(tid):] + [tid])
            return
        state[tid] = "open"
        for dep in tasks.get(tid, {}).get("depends_on") or []:
            if dep in tasks:
                walk(dep, trail + [tid])
        state[tid] = "done"

    for tid in sorted(tasks):
        walk(tid, [])
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", help="one work item; every one when omitted")
    ap.add_argument("--warnings-are-errors", action="store_true")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    items = ([args.item] if args.item
             else [i["id"] for i in W.list_items(project)])
    if not items:
        print("No work items under %s. Nothing to check." % project)
        return 0

    errors = warnings = 0
    for wid in items:
        graph = W.load_graph(project, wid)
        item = W.load_item(project, wid)
        if graph is None or item is None:
            print("ERROR %s has no work item or graph" % wid)
            errors += 1
            continue
        found = invariants(project, wid, graph, item)
        print("%s: %d task(s), %d finding(s)" % (wid, len(graph.get("tasks", [])), len(found)))
        for severity, name, message in found:
            print("  %-5s %-42s %s" % (severity, name, message))
            if severity == "ERROR":
                errors += 1
            else:
                warnings += 1

    print("\n%d error(s), %d warning(s)" % (errors, warnings))
    if errors or (warnings and args.warnings_are_errors):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
