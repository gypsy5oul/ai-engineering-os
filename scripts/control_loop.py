#!/usr/bin/env python3
"""The control loop: turn intent into a durable work item, a task graph, and a
decision about what happens next.

The separation this whole design rests on:

    the declarative workflow   says WHAT MUST BE TRUE
    the task graph             says HOW THIS CHANGE GETS THERE
    Claude Code                says HOW EXECUTION ACTUALLY HAPPENS

This script owns the middle one. It does not schedule agents, run them, or hold
a conversation -- Claude Code does all of that, and reproducing it here would be
a second runtime competing with the one underneath. What this owns is the state:
which tasks exist, which may run now, what happened to them, and whether the
answer to a failure is retry, rework, replan or escalate.

    control_loop.py open    --project . --type feature --intent "..."
    control_loop.py plan    --project . --item ACME-FEAT-001
    control_loop.py next    --project . --item ACME-FEAT-001
    control_loop.py observe --project . --item ACME-FEAT-001 --task T-003 --outcome failed --detail "..."
    control_loop.py decide  --project . --item ACME-FEAT-001 --task T-003
    control_loop.py replan  --project . --item ACME-FEAT-001 --reason "..."
    control_loop.py status  --project . --item ACME-FEAT-001

Exit codes: 0 proceed, 1 blocked or refused, 2 could not run.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file          # noqa: E402
import workitem as W                    # noqa: E402
import failure as F                     # noqa: E402

# The work-item vocabulary. One entry per way work enters the organization, and
# `--type` is exactly these keys, so the CLI cannot offer a word this map does not
# define. Three workflows used to be unreachable from here: a dependency upgrade,
# a change to this repository's own agents and a project onboarding are three of
# the nine workflows, and none of them could be opened as a work item at all, so
# the control loop could not drive them. The skill documented all three anyway,
# which is how the gap stayed invisible -- the documentation described the
# intention and nothing compared it to the parser.
TYPE_WORKFLOW = {
    "feature": "WF-FEATURE", "defect": "WF-DEFECT", "incident": "WF-INCIDENT",
    "release": "WF-RELEASE", "change-request": "WF-CHANGE", "migration": "WF-MIGRATION",
    "dependency": "WF-DEPENDENCY", "agent-change": "WF-AGENT-CHANGE",
    "onboarding": "WF-ONBOARDING",
    # Operational work follows the feature lifecycle rather than one of its own.
    # Deliberate: it is a delivery route, not a separate discipline, and giving it
    # a workflow would have meant a tenth lifecycle nobody maintains.
    "operations": "WF-FEATURE",
}
# The identifier segment, per type. Not the artifact codes in
# policies/artifact-model.json -- a different namespace, and shorter, because it
# reads in every traceability identifier the project produces.
TYPE_CODE = {
    "feature": "FEAT", "defect": "DEF", "incident": "INC", "release": "REL",
    "change-request": "CHG", "migration": "MIG", "operations": "OPS",
    "dependency": "DEP", "agent-change": "AGT", "onboarding": "ONB",
}


def policy(name):
    with open(os.path.join(ROOT, "policies", name), encoding="utf-8") as fh:
        return json.load(fh)


def workflow(wid):
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            wf = parse_file(os.path.join(base, name))
            if wf["id"] == wid:
                return wf
    return None


def project_config(project):
    for name in ("project.yaml", "project.json"):
        path = os.path.join(project, ".ai-engineering", name)
        if os.path.exists(path):
            if name.endswith(".json"):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            return parse_file(path)
    return {}


def prefix(project):
    """The project's traceability prefix.

    Two fields carry it: `project.key`, whose schema description is "Short
    uppercase prefix for traceability identifiers, e.g. SFTP -> SFTP-REQ-001",
    and `knowledge.id_prefix`. This read only the second, and the shipped
    template sets both to the same value -- so a project that filled in the one
    the schema describes got work items called PROJ-FEAT-001. Found the first
    time a real project was configured by hand.

    `project.key` wins because it is the one the schema explains.
    """
    cfg = project_config(project)
    key = ((cfg.get("project") or {}).get("key")
           or (cfg.get("knowledge") or {}).get("id_prefix"))
    return key or "PROJ"


def next_id(project, wtype):
    code = TYPE_CODE[wtype]
    base = os.path.join(project, W.WORK_DIR)
    n = 1
    if os.path.isdir(base):
        used = [x for x in os.listdir(base) if "-%s-" % code in x]
        n = len(used) + 1
    return "%s-%s-%03d" % (prefix(project), code, n)


# ------------------------------------------------------------------- open

def cmd_open(args):
    wtype = args.type
    wid = args.id or next_id(args.project, wtype)
    item = {
        "id": wid, "type": wtype,
        "intent": args.intent,
        "objective": args.objective or args.intent,
        "owner": args.owner or "engineering-director",
        "risk": args.risk, "workflow": TYPE_WORKFLOW[wtype],
        "stage": "intake", "status": "planning",
        "created_at": W.now(), "updated_at": W.now(),
        "replans": 0,
    }
    if args.human_owner:
        item["human_owner"] = args.human_owner
    W.save_item(args.project, item)
    W.set_current(args.project, wid)
    # And bind the session, which is the identity active_item() actually prefers.
    # Nothing wrote it before, so every lookup fell through to CURRENT -- fine for
    # one engineer in one checkout, and wrong the moment two sessions are open on
    # the same project.
    session = getattr(args, "session", None) or os.environ.get("CLAUDE_SESSION_ID")
    if session:
        W.bind_session(W.plugin_data_dir(), session, wid)
    W.record(args.project, wid, "opened", type=wtype, intent=args.intent, risk=args.risk)
    print("%s opened (%s, %s risk)" % (wid, wtype, args.risk))
    print("The intent is preserved verbatim; the objective is what the organization "
          "understood. Acceptance is judged against the objective, so they are kept "
          "separately and can be compared when a plan solves the wrong problem.")
    return 0


# ------------------------------------------------------------------- plan

def applicable_stages(wf, cfg, wtype, risk="MEDIUM"):
    """Which stages this change actually needs.

    A workflow lists every stage a change of this kind could need. Forcing all of
    them on every change is how a process becomes ceremony, so a stage that
    declares optional_when is dropped -- and the drop is recorded rather than
    silent.

    The exception is risk. `optional_when` is prose, and no planner can evaluate
    "the change ships no running service" from a sentence of intent. On a LOW or
    MEDIUM change, guessing wrong costs a stage nobody needed. On a HIGH or
    CRITICAL one it costs the observability design for a service going to
    production, so there the default inverts: optional stages are kept unless the
    project has explicitly listed them as skippable. Dropping a stage on a
    high-risk change becomes a decision someone made rather than a default nobody
    saw.
    """
    stages, skipped = [], []
    sdlc = cfg.get("sdlc") or {}
    required = set(sdlc.get("required_stages") or [])
    skippable = set(sdlc.get("skippable_stages") or [])
    cautious = risk in ("HIGH", "CRITICAL")
    for s in wf["stages"]:
        if not s.get("optional_when") or s["id"] in required:
            stages.append(s)
            continue
        if cautious and s["id"] not in skippable:
            stages.append(s)
            continue
        stages.append(s) if False else skipped.append(
            (s["id"], s["optional_when"][0] if s["optional_when"] else ""))
    return stages, skipped


ARTIFACT_IN_PREDICATE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\b")


def artifacts_needed(stage):
    """Artifact codes a stage depends on, read from its own definition of done.

    The dependency has to come from somewhere real. `inputs` is prose, but the
    definition of done names artifact codes precisely, because a machine has to
    evaluate it: `every_linked(REQ, ARCH)` says this stage cannot finish without a
    REQ, which means it cannot start before whatever produces one.
    """
    produced = set(stage.get("produces") or [])
    needed = set()
    for entry in stage.get("definition_of_done") or []:
        for code in ARTIFACT_IN_PREDICATE.findall(entry):
            if code not in produced and not code.startswith(("CYCLE", "AP")):
                needed.add(code)
    return needed


def build_graph(project, item, generation=1, reason=None, carry=None):
    """Generate the graph for this change.

    Dependencies are derived from artifact flow rather than from stage order, so
    work that genuinely does not depend on other work can run at the same time.
    The previous version made every task depend on the one before it, which is a
    pipeline wearing a graph's schema: `runnable()` could only ever return one
    task, and the coupled-surface exclusion it enforces had nothing to exclude.

    Ordering is not abandoned, though. Three things still sequence:
      - a stage that consumes an artifact waits for whatever produces it,
      - a stage behind a human gate waits for everything before that gate, because
        an approval is a point the whole change passes through,
      - two stages touching the same coupled surface are sequenced, since that
        surface has one owner and parallel edits to it are the thing the coupling
        policy exists to prevent.
    """
    wf = workflow(item["workflow"])
    if wf is None:
        raise SystemExit("ERROR unknown workflow %s" % item["workflow"])
    cfg = project_config(project)
    stages, skipped = applicable_stages(wf, cfg, item["type"], item.get("risk", "MEDIUM"))
    carry = carry or {}
    cap = loop_bound(policy("control-loop-policy.json"))

    tasks, by_stage, producer, surface_last = [], {}, {}, {}
    gate_barrier = None          # the last human gate every later task must clear
    ordered = []

    for i, s in enumerate(stages, start=1):
        tid = "T-%03d" % i
        done = carry.get(s["id"])
        t = {
            "id": tid, "title": s.get("name") or s["id"], "role": s["owner"],
            "stage": s["id"],
            "state": "accepted" if done else "queued",
            "execution": s.get("execution", "subagent"),
            "risk": s.get("risk", "MEDIUM"),
            "attempts": 0, "max_attempts": cap,
            "depends_on": [],
            "definition_of_done": list(s.get("definition_of_done") or []),
        }
        if s.get("produces"):
            t["produces"] = list(s["produces"])
        if (s.get("agent_gate") or {}).get("reviewer"):
            t["reviewer"] = s["agent_gate"]["reviewer"]
        if s.get("coupled_artifacts"):
            t["coupled_surface"] = s["coupled_artifacts"][0]
        if done:
            t["result"] = "carried forward from generation %d" % (generation - 1)

        deps = set()
        for code in artifacts_needed(s):
            if code in producer:
                deps.add(producer[code])
        if gate_barrier:
            deps.add(gate_barrier)
        surface = t.get("coupled_surface")
        if surface and surface in surface_last:
            deps.add(surface_last[surface])
        # A stage that needs nothing yet produced still cannot be a second root:
        # the change has one entry point, and everything else follows it.
        if not deps and ordered:
            deps.add(ordered[0])
        t["depends_on"] = sorted(deps - {tid})

        for code in (s.get("produces") or []):
            producer.setdefault(code, tid)
        if surface:
            surface_last[surface] = tid
        if s.get("human_gate"):
            gate_barrier = tid

        tasks.append(t)
        by_stage[s["id"]] = tid
        ordered.append(tid)

    graph = {"work_item": item["id"], "generated_at": W.now(),
             "generation": generation, "tasks": tasks}
    if reason:
        graph["replan_reason"] = reason
    return graph, skipped


def cmd_plan(args):
    item = W.load_item(args.project, args.item)
    if item is None:
        print("ERROR no such work item: %s" % args.item)
        return 2
    # A graph that will not parse is the case --force exists for, and reading it
    # is how you find that out. Letting the parse error escape meant the repair
    # tool could not repair its primary case: an agent result containing a
    # newline made the file unreadable, and `plan --force` then died on the same
    # line as everything else.
    unreadable = None
    try:
        existing = W.load_graph(args.project, args.item)
    except Exception as exc:
        if not args.force:
            print("ERROR %s has a graph that cannot be read: %s" % (args.item, exc))
            print("Run `plan --force` to rebuild it. Accepted work in it is lost, because "
                  "nothing can read what it said.")
            return 2
        unreadable, existing = exc, None

    if existing and not args.force:
        print("ERROR %s already has a graph. Use `replan --reason` to rebuild it: a plan "
              "replaced without a recorded reason is indistinguishable from thrashing."
              % args.item)
        return 1
    if unreadable is not None:
        W.record(args.project, args.item, "graph_repaired",
                 why="the previous graph could not be parsed: %s" % str(unreadable)[:200])
        print("Repairing an unreadable graph for %s." % args.item)
        print("  it would not parse: %s" % str(unreadable)[:120])
    elif existing and args.force:
        # --force is a repair tool, not a second replan. It used to rebuild any
        # graph: it reset the generation to 1, discarded accepted work the replan
        # rule says to carry forward, and never touched item['replans'] -- so it
        # was an unrecorded, unlimited way around a cap that refuses at two.
        if W.is_valid(existing, "task-graph.schema.json"):
            print("REFUSED: %s has a valid graph, so there is nothing to repair.\n"
                  "--force exists for a graph that will not parse or validate. To replace one "
                  "that works, use `replan --reason`: it counts against the replan limit, "
                  "records why, and carries accepted work forward." % args.item)
            return 1
        W.record(args.project, args.item, "graph_repaired",
                 why="the previous graph did not validate")
        print("Repairing an invalid graph for %s." % args.item)
    graph, skipped = build_graph(args.project, item)
    W.save_graph(args.project, graph)
    item["status"] = "in-progress"
    W.save_item(args.project, item)
    W.record(args.project, args.item, "planned", generation=1,
             tasks=len(graph["tasks"]), skipped=[s for s, _ in skipped])
    print("%s planned: %d task(s) from %s" % (args.item, len(graph["tasks"]), item["workflow"]))
    for sid, why in skipped:
        print("  skipped %-14s %s" % (sid, why[:90]))
    return 0


# ------------------------------------------------------------------- next

def cmd_next(args):
    graph = W.load_graph(args.project, args.item)
    if graph is None:
        print("ERROR %s has no graph. Run `plan` first." % args.item)
        return 2
    ready = W.runnable(graph)
    stuck = W.unreachable(graph)
    prog = W.progress(graph)

    if args.json:
        print(json.dumps({"runnable": ready, "unreachable": stuck, "progress": prog}, indent=2))
        return 0 if ready else 1

    if prog["complete"]:
        print("%s: every task accepted." % args.item)
        return 0
    if not ready:
        print("%s: nothing runnable." % args.item)
        for t in graph["tasks"]:
            if t["state"] not in W.TERMINAL:
                held = W.blocked_on(graph, t)
                if held:
                    print("  %-6s %-28s waiting on %s" % (t["id"], t["title"][:28], ", ".join(held)))
                elif t.get("attempts", 0) >= t.get("max_attempts", 3):
                    print("  %-6s %-28s attempts exhausted -> escalate" % (t["id"], t["title"][:28]))
                elif t.get("owner_agent"):
                    print("  %-6s %-28s held by %s since %s"
                          % (t["id"], t["title"][:28], t["owner_agent"],
                             t.get("last_activity") or "unknown"))
        if stuck:
            print("\nUnreachable, because something they need was abandoned: %s" % ", ".join(stuck))
            print("A graph where work waits on an abandoned task looks busy and is finished.")
        return 1

    print("%s: %d runnable" % (args.item, len(ready)))
    needs_briefing = []
    for t in ready:
        ex = t.get("execution") if isinstance(t.get("execution"), dict) else {}
        mode = W.effective_execution(t)
        isolation = W.effective_isolation(t)
        # Both, always. One column is how `worktree` came to be an execution mode
        # in the first place: there was nowhere to print the other answer.
        print("  %-6s %-28s %-20s %-10s %s"
              % (t["id"], t["title"][:28], t["role"], mode,
                 "" if isolation == "shared-checkout" else isolation))
        if ex.get("briefing_required"):
            needs_briefing.append(t["id"])
    if needs_briefing:
        # The resolver has been setting this flag since 0.23 and nothing read it.
        # An isolated spawn receives no additionalContext, so without this the
        # worker runs on its role definition and never learns what it was for.
        print("\nThese resolve to an isolated spawn, which receives no injected context. "
              "Put the briefing in the prompt:")
        for tid in needs_briefing:
            print("  python3 scripts/control_loop.py brief --project . --item %s --task %s"
                  % (args.item, tid))
    if stuck:
        print("\nUnreachable: %s" % ", ".join(stuck))
    return 0


def refuse_unearned_acceptance(args, t):
    """None when this task may be accepted, or an exit code when it may not.

    Uses the same evaluation as the completion gate, from the same function, so
    the two cannot reach different conclusions about the same task.
    """
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import check_dod
    try:
        result = check_dod.acceptance(args.project, t, change=args.item)
    except Exception as exc:
        # The checker breaking is not evidence that the work is done. Tiered the
        # same way every other guard here is.
        risk = str(t.get("risk", "MEDIUM")).upper()
        if risk in ("HIGH", "CRITICAL"):
            print("REFUSED: the acceptance check could not run for this %s-risk task (%r), and "
                  "that is not the same as passing." % (risk, exc))
            return 1
        print("WARNING: the acceptance check could not run (%r). Accepting anyway because this "
              "is %s-risk work; the failure is in the audit log." % (exc, risk))
        return None

    risk = str(t.get("risk", "MEDIUM")).upper()
    # From policies/control-loop-policy.json, so the gate and the loop cannot
    # drift apart on how serious each kind of unanswered predicate is.
    high = check_dod.refuses("unsupported", risk)
    blocking = list(result["failing"]) if check_dod.refuses("failing", risk) else []
    if result["unsupported"] and high:
        blocking += result["unsupported"]
    if result["unverifiable"] and check_dod.refuses("unverifiable", risk):
        blocking += result["unverifiable"]

    if blocking:
        print("REFUSED: %s has not satisfied its definition of done." % t["id"])
        for line in result["failing"]:
            print("  fails      %s" % line)
        if result["unsupported"] and high:
            for line in result["unsupported"]:
                print("  unanswered %s" % line)
            print("\n  An unanswerable predicate is not a satisfied one, and this is %s-risk "
                  "work." % risk)
        print("\nRecord what actually happened instead -- `--outcome failed`, `rejected` or "
              "`blocked` -- and let `decide` choose between retry, rework, replan and escalate.")
        W.record(args.project, args.item, "acceptance_refused", task=t["id"],
                 failing=result["failing"], unsupported=result["unsupported"], risk=risk)
        return 1

    # A parent stands for its children. Accepting it while they are unfinished
    # would close a stage over work that has not happened.
    graph = W.load_graph(args.project, args.item)
    open_children = [c["id"] for c in W.children_of(graph, t["id"])
                     if c["state"] != "accepted"]
    if open_children:
        print("REFUSED: %s was decomposed, and %d of its tasks have not been accepted: %s"
              % (t["id"], len(open_children), ", ".join(open_children)))
        print("The stage stands for its pieces. Accept them first.")
        W.record(args.project, args.item, "acceptance_refused", task=t["id"],
                 open_children=open_children)
        return 1

    if result["unsupported"]:
        print("  %d predicate(s) could not be answered at all: %s"
              % (len(result["unsupported"]), "; ".join(result["unsupported"])))
        print("  Accepted because this is %s-risk work. Fix them; an unanswerable predicate is "
              "not a satisfied one." % risk)
    if result["unverifiable"]:
        print("  %d predicate(s) rest on evidence outside the repository: %s"
              % (len(result["unverifiable"]),
                 "; ".join(e.split(" -- ")[0] for e in result["unverifiable"])))
    W.record(args.project, args.item, "acceptance_checked", task=t["id"],
             passing=result["passing"], unsupported=result["unsupported"],
             unverifiable=result["unverifiable"], risk=risk)
    return None


def cmd_brief(args):
    """Print the briefing for a task, for a spawn that will not be injected into.

    `SubagentStart` delivers this as additionalContext. An isolated spawn does not
    receive that, so the briefing has to travel in the prompt -- and until this
    existed, `briefing_required` was set by the resolver and read by nobody, which
    meant an isolated worker silently ran on its role definition alone.
    """
    item = W.load_item(args.project, args.item)
    graph = W.load_graph(args.project, args.item)
    if item is None or graph is None:
        print("ERROR %s has no work item or graph." % args.item)
        return 2
    task = W.task(graph, args.task) if args.task else None
    if args.task and task is None:
        print("ERROR no task %s" % args.task)
        return 2
    sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
    import briefing
    print(briefing.render(item, task, graph))
    return 0


# ---------------------------------------------------------------- observe

def cmd_observe(args):
    graph = W.load_graph(args.project, args.item)
    if graph is None:
        print("ERROR %s has no graph." % args.item)
        return 2
    t = W.task(graph, args.task)
    if t is None:
        print("ERROR no task %s in %s" % (args.task, args.item))
        return 2

    state = {"accepted": "accepted", "failed": "rework", "rejected": "rework",
             "blocked": "blocked", "escalated": "escalated"}[args.outcome]

    # Acceptance is the one outcome that is not merely an observation. There were
    # two authorities on it: the TaskCompleted gate evaluated the definition of
    # done, and this set the state without evaluating anything -- so the durable
    # graph could say a task was accepted while its own predicates were failing,
    # and the gate could not object because the mutation never went near it.
    if args.outcome == "accepted":
        verdict = refuse_unearned_acceptance(args, t)
        if verdict is not None:
            return verdict

    if args.outcome in ("failed", "rejected"):
        t["attempts"] = t.get("attempts", 0) + 1
    route = W.path_to(t["state"], state)
    if route is None:
        print("ERROR %s cannot reach %s from %s. Legal next: %s"
              % (args.task, state, t["state"], ", ".join(W.TRANSITIONS.get(t["state"], ())) or "nothing; it is terminal"))
        return 1
    if len(route) > 2:
        print("  (via %s)" % " -> ".join(route[1:-1]))
    t["state"] = state
    t["last_activity"] = W.now()
    if args.detail:
        t["result"] = args.detail
    if args.outcome == "blocked" and args.detail:
        t["blocked_reason"] = args.detail
    entry = {"task": args.task, "outcome": args.outcome,
             "attempts": t.get("attempts", 0), "detail": args.detail or ""}
    if args.outcome in ("failed", "rejected"):
        cls, sig = F.identity(args.failure_class, args.signature, args.detail)
        entry["failure_class"], entry["failure_signature"] = cls, sig
        if args.evidence:
            entry["evidence"] = args.evidence
            t.setdefault("evidence", []).extend(args.evidence)
        t["failure_class"], t["failure_signature"] = cls, sig
    W.save_graph(args.project, graph)
    W.record(args.project, args.item, "observed", **entry)
    print("%s %s -> %s (attempt %d of %d)"
          % (args.item, args.task, state, t.get("attempts", 0), t.get("max_attempts", 3)))
    if entry.get("failure_signature"):
        print("  failure: %s" % F.describe((entry["failure_class"], entry["failure_signature"])))
        if entry["failure_signature"] == F.NO_SIGNATURE:
            print("  Nothing identifying in the detail, so this will not be read as a repeat of "
                  "anything. Pass --signature to make it comparable.")
    return 0


# ----------------------------------------------------------------- decide


def loop_bound(pol, loop="implement"):
    """The attempt cap, from the policy rather than from a constant here.

    A bound written in a policy file and a different bound hardcoded in the code
    that enforces it is the failure this repository keeps finding in itself: the
    policy reads like the authority and is decoration.
    """
    return int(((pol.get("loops") or {}).get(loop) or {}).get("max_iterations", 3))


def _repeated_failure(hist):
    """Whether the last two failures were the same one, by identity not by wording."""
    ids = [(h.get("failure_class"), h.get("failure_signature"))
           for h in hist if h.get("outcome") in ("failed", "rejected")]
    ids = [i for i in ids if i[1]]
    if len(ids) < 2:
        return False, ids
    return F.same(ids[-1], ids[-2]), ids


# How a rule name in policies/control-loop-policy.json becomes a question about
# this task. Every rule the policy declares must appear here, and a rule with no
# predicate is a rule that can never fire -- which check_control_loop_policy()
# in validate_plugin.py turns into a build failure rather than a silent no-op.
RULE_PREDICATES = {
    "task_accepted":            lambda t, h, p: t["state"] == "accepted",
    "attempts_exhausted":       lambda t, h, p: t.get("attempts", 0) >= t.get("max_attempts", loop_bound(p)),
    "same_failure_repeated":    lambda t, h, p: _repeated_failure(h)[0],
    "review_rejected":          lambda t, h, p: t["state"] in ("rework", "rejected"),
    "dependency_invalidated":   lambda t, h, p: t.get("blocked_reason", "").startswith("dependency:"),
    "architecture_contradicted": lambda t, h, p: "architecture" in (t.get("blocked_reason") or "").lower(),
    "missing_information":      lambda t, h, p: "missing information" in (t.get("blocked_reason") or "").lower(),
    "approval_missing":         lambda t, h, p: "approval" in (t.get("blocked_reason") or "").lower(),
    "transient_failure":        lambda t, h, p: t["state"] in ("rework", "rejected", "blocked"),
}


def evaluate_rules(pol, t, hist):
    """First matching rule wins, in the order the policy declares them.

    The order is the policy's to decide, which is why it is read rather than
    reproduced: `attempts_exhausted` sits above `transient_failure` on purpose,
    so an exhausted task cannot be retried once more by a rule further down.
    """
    for rule in ((pol.get("decide") or {}).get("rules") or []):
        name = rule.get("when")
        pred = RULE_PREDICATES.get(name)
        if pred is None or not pred(t, hist, pol):
            continue
        why = rule.get("why") or name
        if name == "same_failure_repeated":
            why = "%s Seen twice as %s." % (why, F.describe(_repeated_failure(hist)[1][-1]))
        elif name == "attempts_exhausted":
            why = "%s (%d of %d)" % (why, t.get("attempts", 0),
                                     t.get("max_attempts", loop_bound(pol)))
        return rule.get("action", "continue"), why
    return "continue", "no rule in the policy objects"


def cmd_decide(args):
    graph = W.load_graph(args.project, args.item)
    item = W.load_item(args.project, args.item)
    if graph is None or item is None:
        print("ERROR %s has no work item or graph." % args.item)
        return 2
    t = W.task(graph, args.task)
    if t is None:
        print("ERROR no task %s" % args.task)
        return 2

    pol = policy("control-loop-policy.json")
    hist = [h for h in W.history(args.project, args.item)
            if h.get("kind") == "observed" and h.get("task") == args.task]
    action, why = evaluate_rules(pol, t, hist)

    if args.json:
        print(json.dumps({"task": args.task, "state": t["state"],
                          "attempts": t.get("attempts", 0),
                          "max_attempts": t.get("max_attempts", loop_bound(pol)),
                          "action": action, "why": why}, indent=2))
    else:
        print("%s %s: %s" % (args.item, args.task, action.upper()))
        print("  %s" % why)
        if action == "escalate":
            print("  ladder: %s" % " -> ".join((pol.get("escalation") or {}).get("ladder", [])))
    ladder = (pol.get("escalation") or {}).get("ladder") or []
    # Who the escalation actually reaches. Telemetry counted a human intervention
    # from replan_refused alone, so a real escalation to the human owner reported
    # none: the loudest event in the system was invisible in the one number that
    # is supposed to summarise it.
    target = (t.get("escalation_target") or (ladder[-1] if ladder else "human_owner"))
    W.record(args.project, args.item, "decided", task=args.task, action=action, why=why)
    if action == "escalate":
        W.record(args.project, args.item, "escalated", task=args.task, to=target, why=why)
    return 1 if action == "escalate" else 0


# ----------------------------------------------------------------- replan

def cmd_replan(args):
    item = W.load_item(args.project, args.item)
    graph = W.load_graph(args.project, args.item)
    if item is None or graph is None:
        print("ERROR %s has no work item or graph." % args.item)
        return 2
    pol = policy("control-loop-policy.json")
    cap = (pol.get("replan") or {}).get("max_per_work_item", 2)
    done = item.get("replans", 0)
    if done >= cap:
        print("REFUSED: %s has already been replanned %d time(s), and the limit is %d."
              % (args.item, done, cap))
        print("Two replans means the intake was wrong. A third plan is a new work item, "
              "not a better plan. Escalate to the human owner.")
        W.record(args.project, args.item, "replan_refused", replans=done, reason=args.reason)
        return 1

    # Every task of the stage, not any one of them. A decomposed stage has
    # several, and carrying it forward because one child finished would mark the
    # whole stage done and drop the rest of the work silently.
    by_stage = {}
    for t in graph["tasks"]:
        if t.get("stage"):
            by_stage.setdefault(t["stage"], []).append(t["state"])
    carry = ({sid: True for sid, states in by_stage.items()
              if all(st == "accepted" for st in states)} if not args.redo_all else {})
    new, skipped = build_graph(args.project, item, generation=graph["generation"] + 1,
                               reason=args.reason, carry=carry)
    W.record(args.project, args.item, "replanned",
             generation=new["generation"], reason=args.reason,
             superseded=graph["generation"], carried=sorted(carry))
    W.save_graph(args.project, new)
    item["replans"] = done + 1
    W.save_item(args.project, item)
    print("%s replanned: generation %d -> %d" % (args.item, graph["generation"], new["generation"]))
    print("  reason: %s" % args.reason)
    print("  carried forward: %s" % (", ".join(sorted(carry)) or "nothing"))
    print("  The superseded generation stays in history.jsonl. What the organization used "
          "to believe is evidence about how it plans.")
    return 0


# ----------------------------------------------------------------- status

def cmd_status(args):
    if args.item:
        items = [W.load_item(args.project, args.item)]
        if items[0] is None:
            print("ERROR no such work item: %s" % args.item)
            return 2
    else:
        items = W.list_items(args.project)
    if not items:
        print("No work items under %s" % os.path.join(args.project, W.WORK_DIR))
        return 0

    for item in items:
        graph = W.load_graph(args.project, item["id"])
        prog = W.progress(graph) if graph else {"total": 0, "accepted": 0, "by_state": {}}
        print("%-18s %-14s %-11s risk=%-8s %d/%d task(s)"
              % (item["id"], item["type"], item["status"], item["risk"],
                 prog["accepted"], prog["total"]))
        if args.item:
            print("  intent:    %s" % item["intent"][:100])
            print("  objective: %s" % item["objective"][:100])
            if item.get("replans"):
                print("  replans:   %d" % item["replans"])
            if graph:
                print("  generation %d" % graph["generation"])
                # Children are listed under the stage they came out of, because
                # a flat list of twenty-two tasks does not say which four of them
                # are one stage.
                kids = {}
                for t in graph["tasks"]:
                    if t.get("parent"):
                        kids.setdefault(t["parent"], []).append(t)

                def show(t, indent=""):
                    mark = {"accepted": "ok ", "rework": "RWK", "blocked": "BLK",
                            "escalated": "ESC", "abandoned": "---"}.get(t["state"], "   ")
                    print("    %s %s%-6s %-*s %-20s %s"
                          % (mark, indent, t["id"], 30 - len(indent),
                             t["title"][:30 - len(indent)], t["role"], t["state"]))

                for t in graph["tasks"]:
                    if t.get("parent"):
                        continue
                    show(t)
                    for child in kids.get(t["id"], []):
                        show(child, indent="  ")
    return 0


def build_parser():
    """The parser, separately, so validate_plugin can check that every invocation
    the documentation shows is one argparse would actually accept. Running the
    commands to find out is not an option: most of them write."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--project", default=".")
        return p

    o = common(sub.add_parser("open"))
    o.add_argument("--session", help="bind this work item to a session id, so two sessions on "
                                     "one project do not brief each other's agents "
                                     "(defaults to $CLAUDE_SESSION_ID)")
    o.add_argument("--type", required=True, choices=sorted(TYPE_WORKFLOW))
    o.add_argument("--intent", required=True)
    o.add_argument("--objective")
    o.add_argument("--risk", default="MEDIUM", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    o.add_argument("--owner")
    o.add_argument("--human-owner")
    o.add_argument("--id")
    o.set_defaults(fn=cmd_open)

    p = common(sub.add_parser("plan"))
    p.add_argument("--item", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_plan)

    n = common(sub.add_parser("next"))
    n.add_argument("--item", required=True)
    n.add_argument("--json", action="store_true")
    n.set_defaults(fn=cmd_next)

    ob = common(sub.add_parser("observe"))
    ob.add_argument("--item", required=True)
    ob.add_argument("--task", required=True)
    ob.add_argument("--outcome", required=True,
                    choices=["accepted", "failed", "rejected", "blocked", "escalated"])
    ob.add_argument("--detail")
    ob.add_argument("--failure-class", choices=list(F.CLASSES),
                    help="the kind of failure. With --signature this is how the loop tells a "
                         "repeat from progress.")
    ob.add_argument("--signature",
                    help="a stable identity for this failure, not a description. Derived from "
                         "--detail when omitted, conservatively: prose is discarded and only "
                         "identifying tokens are kept.")
    ob.add_argument("--evidence", action="append",
                    help="where to look: a test path, a log line, an artifact id. Repeatable.")
    ob.set_defaults(fn=cmd_observe)

    d = common(sub.add_parser("decide"))
    d.add_argument("--item", required=True)
    d.add_argument("--task", required=True)
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_decide)

    r = common(sub.add_parser("replan"))
    r.add_argument("--item", required=True)
    r.add_argument("--reason", required=True)
    r.add_argument("--redo-all", action="store_true")
    r.set_defaults(fn=cmd_replan)

    b = common(sub.add_parser("brief"))
    b.add_argument("--item", required=True)
    b.add_argument("--task", help="include this task's contract, as SubagentStart would")
    b.set_defaults(fn=cmd_brief)

    s = common(sub.add_parser("status"))
    s.add_argument("--item")
    s.set_defaults(fn=cmd_status)

    return ap


def main():
    args = build_parser().parse_args()
    args.project = os.path.abspath(args.project)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
