#!/usr/bin/env python3
"""Choose how a task runs, at the moment it runs.

A stage declares an execution mode when the workflow is written, which is before
the situation exists. `execution: team` is good advice and a bad instruction in a
headless session, where teammates do not spawn at all; `worktree` is prudent for a
writer and pure cost for a reviewer, which writes nothing another role touches.

So the declaration is a starting point and the runtime overrules it on facts:
whether teams are actually available, whether the role can write, what the risk
is, and whether a sibling task would collide.

    resolve_execution.py --project . --item ACME-FEAT-001 --task T-004
    resolve_execution.py --project . --item ACME-FEAT-001 --all --json

This resolves and records. It does not compel: nothing makes an agent honour the
answer, because a PreToolUse hook can refuse a spawn but cannot rewrite one. That
limit is stated in the policy rather than implied.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")


def policy(name):
    with open(os.path.join(ROOT, "policies", name), encoding="utf-8") as fh:
        return json.load(fh)


def role_can_write(role):
    """Whether this role writes anything a worktree would protect.

    Not just "holds a write tool". A reviewer holds one so it can record its own
    verdict, and its scope is docs/reviews/** and nothing else -- isolating that
    protects nobody from anything, because no other role writes there and the
    reviewer writes nowhere else.
    """
    reg = policy("agent-registry.json")
    profiles = policy("tool-permissions.json").get("profiles", {})
    scope = (policy("write-scope.json").get("roles") or {}).get(role)
    entries = reg.get("agents") or []
    if isinstance(entries, dict):
        entries = [dict(v, name=k) for k, v in entries.items()]
    for e in entries:
        if (e.get("name") or e.get("id")) == role:
            tools = (profiles.get(e.get("tool_profile"), {}) or {}).get("tools", [])
            if not any(t in tools for t in WRITE_TOOLS):
                return False
            if scope and scope.get("mode") == "allow":
                elsewhere = [p for p in (scope.get("allow") or [])
                             if not p.startswith("docs/reviews/")]
                return bool(elsewhere)
            return True
    return True          # unknown role: assume it writes, which is the cautious answer


def teams_available(project):
    """Whether a team could actually spawn here.

    Only one half is checkable. Spawning a teammate also requires an interactive
    session -- under -p a named spawn runs as an ordinary subagent -- and no
    environment variable distinguishes the two: CLAUDE_CODE_ENTRYPOINT is "cli"
    in both. So this checks the flag and the project's declaration, and the
    undetectable half is covered downstream instead: a team that silently became
    a subagent is recorded in execution.actual and the divergence goes to the
    work item history.
    """
    if os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") != "1":
        return False, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not set"
    cfg = {}
    for name in ("project.yaml", "project.json"):
        path = os.path.join(project, ".ai-engineering", name)
        if os.path.exists(path):
            if name.endswith(".json"):
                with open(path, encoding="utf-8") as fh:
                    cfg = json.load(fh)
            else:
                sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
                from minyaml import parse_file
                cfg = parse_file(path)
            break
    if (cfg.get("ai") or {}).get("agent_teams_available") is False:
        return False, "the project records agent teams as unavailable"
    return True, "teams are enabled"


def project_override(project, stage):
    """A mode the project pinned for this stage, or None.

    `ai.execution_overrides` sat in the template and the schema for eight versions
    reading like configuration and consumed by nothing -- a team could write
    `ARCH: subagent` there and get a four-way architecture team anyway.
    """
    if not stage:
        return None
    cfg = {}
    for name in ("project.yaml", "project.json"):
        path = os.path.join(project, ".ai-engineering", name)
        if not os.path.exists(path):
            continue
        if name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        else:
            sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
            from minyaml import parse_file
            cfg = parse_file(path)
        break
    return ((cfg.get("ai") or {}).get("execution_overrides") or {}).get(stage)


def overlapping_paths(task, siblings):
    """A description of the first file overlap with a live sibling, or None.

    Only what the tasks have declared. A task that names no paths cannot be
    checked, and this says nothing rather than assuming disjointness -- the
    absence of a declaration is not evidence of separation.
    """
    mine = set(task.get("owns_paths") or [])
    if not mine:
        return None
    for other in siblings:
        if other["state"] not in ("assigned", "working", "review"):
            continue
        shared = mine & set(other.get("owns_paths") or [])
        if shared:
            return "%s also edits %s" % (other["id"], ", ".join(sorted(shared)[:3]))
    return None


def resolve_execution(project, graph, task, declared, running):
    """(mode, why) for how the task runs. Nothing here decides *where*.

    Two facts overrule the declaration, and both are about whether the mode is
    achievable at all rather than about collisions with other work: teams that
    the platform will not spawn, and CRITICAL work sent where nobody is watching.
    """
    risk = task.get("risk", "MEDIUM")

    if declared == "team":
        ok, why = teams_available(project)
        if not ok:
            return "subagent", ("declared team, resolved to subagent: %s. Nothing in the "
                                "lifecycle may depend on an experimental, interactive-only "
                                "feature." % why)

    siblings = [t for t in graph.get("tasks", []) if t["id"] != task["id"]]
    if declared == "team" and overlapping_paths(task, siblings):
        # A worktree around a team isolates nothing. Teammates are separate Claude
        # instances sharing one checkout and one task list; putting the task in a
        # worktree moves all of them into that worktree together, so two teammates
        # editing one file still overwrite each other -- in a different directory.
        # The isolation resolver used to answer this with `worktree`, and its own
        # comment said teammates are not worktree-isolated while it did so.
        #
        # A collision means the work was not partitioned, and the honest answer is
        # that it is not team-shaped: subagents can each hold their own worktree,
        # which is real isolation, and the lead owns the merge.
        return "subagent", ("declared team, resolved to subagent: %s. Teammates share one "
                            "checkout, so a team cannot be isolated from itself -- a worktree "
                            "would hold the whole team. Subagents can each take their own "
                            "worktree and the lead owns the integration."
                            % overlapping_paths(task, siblings))

    if declared == "background" and risk == "CRITICAL":
        return "subagent", ("declared background, resolved to subagent: CRITICAL work is not "
                            "sent where nobody is watching.")

    return declared, None


def resolve_isolation(project, graph, task, execution, declared_iso, running):
    """(isolation, why) for where the task runs. Nothing here changes the mode.

    Every rule that used to return "worktree" lived in the execution resolver and
    threw the mode away on the way past: a team that needed its own checkout came
    back as "worktree", and nothing downstream could still tell it was a team.
    They are the same rules, on the axis they were always about.
    """
    role = task.get("role", "")
    surface = task.get("coupled_surface")
    siblings = [t for t in graph.get("tasks", []) if t["id"] != task["id"]]
    surface_clash = [t for t in running if surface and t.get("coupled_surface") == surface]

    # A worktree protects files from another writer. A role that writes nothing
    # another role touches is protected from nobody, and the isolation is pure
    # cost -- including the briefing that an isolated spawn does not receive.
    if declared_iso == "worktree" and not role_can_write(role):
        return "shared-checkout", ("declared worktree, resolved to shared-checkout: %s writes "
                                   "nothing a worktree would protect, so there is nothing to "
                                   "isolate." % role)

    if execution == "team":
        # Nothing to decide. Teammates are not worktree-isolated: they are separate
        # instances sharing one checkout, so any worktree here would contain the
        # whole team and isolate none of them from each other. A team whose members
        # collide is handled where it belongs -- resolve_mode degrades it to
        # subagent, and the subagent rules below can then give each worker a real
        # worktree.
        return declared_iso, None

    if surface_clash:
        return "worktree", ("a sibling holds the %s surface (%s), so this is isolated rather "
                            "than sequenced -- the parallelism survives and the integration "
                            "becomes an explicit step."
                            % (surface, ", ".join(t["id"] for t in surface_clash)))

    if execution in ("inline", "subagent") and running and role_can_write(role):
        return "worktree", ("%d task(s) already running and %s writes files. Parallel writers in "
                            "one checkout produce a build output nobody owns."
                            % (len(running), role))

    return declared_iso, None


def resolve(project, graph, task):
    """(execution, isolation, why). Two dimensions, resolved separately.

    The signature used to be (mode, why) with `worktree` among the modes, which
    is why three rules could isolate a task and silently demote it to a subagent
    at the same time.
    """
    # Through the accessor, not the raw field. Since v0.23 `execution` is an
    # object on any task that came from a decomposition, and reading it directly
    # made `declared` a dict: no rule matched, the dict was returned as the mode,
    # and writing it back failed schema validation inside a try/except -- so
    # execution resolution silently did not apply to decomposed tasks at all.
    declared = W.declared_execution(task)
    declared_iso = W.declared_isolation(task)
    pinned = project_override(project, task.get("stage"))
    if pinned and pinned != declared:
        # The project knows things the workflow author did not: how big the team
        # is, what the change actually costs. A pin is a decision, so it is taken
        # before the runtime facts and then still subject to them.
        declared = pinned

    running = [t for t in graph.get("tasks", [])
               if t["id"] != task["id"] and t["state"] in ("assigned", "working", "review")]

    execution, exec_why = resolve_execution(project, graph, task, declared, running)
    isolation, iso_why = resolve_isolation(project, graph, task, execution, declared_iso, running)

    reasons = [r for r in (exec_why, iso_why) if r]
    if not reasons:
        if pinned and pinned == declared:
            reasons = ["the project pinned %s for stage %s in ai.execution_overrides"
                       % (declared, task.get("stage"))]
        else:
            reasons = ["no fact overruled the stage's recommendation"]
    return execution, isolation, "; ".join(reasons)


# An isolated spawn does not receive SubagentStart's additionalContext -- verified
# against 2.1.241 and recorded in platform-capabilities.json. The briefing this
# plugin exists to deliver silently does not arrive, so the resolver has to say
# that the briefing must travel in the spawn prompt instead.
#
# These are isolation values now, not execution modes. `remote` is listed because
# a remote environment is at least as isolated as a worktree; nothing here has
# ever run one, and the capability model says so.
ISOLATING = ("worktree", "remote")


def record_resolution(project, wid, task, graph=None):
    """Resolve this task's execution and persist the decision on the task.

    This is the difference between a resolver and an advisory CLI. The policy
    named `resolve_execution.py` as its enforcement for two versions while nothing
    on the spawn path called it and nothing wrote its answer down, so a stage
    could declare `team`, the resolver could say `subagent`, and the spawn could
    do a third thing with no record that the three ever disagreed.
    """
    graph = graph if graph is not None else W.load_graph(project, wid)
    if graph is None:
        return None
    mode, isolation, why = resolve(project, graph, task)
    W.set_execution(task, resolved=mode, resolution_reason=why, resolved_at=W.now(),
                    briefing_required=isolation in ISOLATING)
    W.set_isolation(task, resolved=isolation, resolution_reason=why, resolved_at=W.now())
    return mode, isolation, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", required=True)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="persist the resolution onto the task, as the claim path does")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    graph = W.load_graph(project, args.item)
    if graph is None:
        print("ERROR %s has no graph" % args.item)
        return 2

    tasks = graph["tasks"] if args.all else [W.task(graph, args.task)]
    if tasks == [None]:
        print("ERROR no task %s" % args.task)
        return 2

    out = []
    for t in tasks:
        declared, declared_iso = W.declared_execution(t), W.declared_isolation(t)
        if args.record:
            mode, isolation, why = record_resolution(project, args.item, t, graph)
        else:
            mode, isolation, why = resolve(project, graph, t)
        out.append({"task": t["id"],
                    "execution": {"declared": declared, "resolved": mode},
                    "isolation": {"declared": declared_iso, "resolved": isolation},
                    "changed": mode != declared or isolation != declared_iso,
                    "why": why})

    if args.record:
        W.save_graph(project, graph)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        # Two columns, because one column is how `worktree` came to be an
        # execution mode: there was nowhere to print the other answer.
        print("%-7s %-22s %-26s %s" % ("TASK", "EXECUTION", "ISOLATION", "WHY"))
        for r in out:
            ex, iso = r["execution"], r["isolation"]
            exs = ("%s -> %s" % (ex["declared"], ex["resolved"])
                   if ex["declared"] != ex["resolved"] else ex["declared"])
            isos = ("%s -> %s" % (iso["declared"], iso["resolved"])
                    if iso["declared"] != iso["resolved"] else iso["declared"])
            print("%-7s %-22s %-26s %s" % (r["task"], exs, isos, r["why"][:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
