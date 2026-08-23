#!/usr/bin/env python3
"""Choose how a task runs, at the moment it runs.

A stage declares an execution mode when the workflow is written, which is before
the situation exists. `execution: team` is good advice and a bad instruction in a
headless session, where teammates do not spawn at all; `worktree` is prudent for a
writer and pure cost for a reviewer that holds no write tools.

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
    reg = policy("agent-registry.json")
    profiles = policy("tool-permissions.json").get("profiles", {})
    entries = reg.get("agents") or []
    if isinstance(entries, dict):
        entries = [dict(v, name=k) for k, v in entries.items()]
    for e in entries:
        if (e.get("name") or e.get("id")) == role:
            tools = (profiles.get(e.get("tool_profile"), {}) or {}).get("tools", [])
            return any(t in tools for t in WRITE_TOOLS)
    return True          # unknown role: assume it writes, which is the cautious answer


def teams_available(project):
    """Whether a team could actually spawn here.

    Both halves matter: the environment variable, and an interactive session. A
    project that declares teams available in a headless run is declaring something
    the platform will not do.
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


def resolve(project, graph, task):
    """(mode, why). The first fact that overrules the declaration wins."""
    declared = task.get("execution", "subagent")
    risk = task.get("risk", "MEDIUM")
    role = task.get("role", "")
    surface = task.get("coupled_surface")

    siblings = [t for t in graph.get("tasks", []) if t["id"] != task["id"]]
    running = [t for t in siblings if t["state"] in ("assigned", "working", "review")]
    surface_clash = [t for t in running if surface and t.get("coupled_surface") == surface]

    if declared == "team":
        ok, why = teams_available(project)
        if not ok:
            return "subagent", ("declared team, resolved to subagent: %s. Nothing in the "
                                "lifecycle may depend on an experimental, interactive-only "
                                "feature." % why)

    if declared == "worktree" and not role_can_write(role):
        return "subagent", ("declared worktree, resolved to subagent: %s holds no write tools, "
                            "so there is nothing to isolate." % role)

    if declared == "background" and risk == "CRITICAL":
        return "subagent", ("declared background, resolved to subagent: CRITICAL work is not "
                            "sent where nobody is watching.")

    if surface_clash:
        return "worktree", ("a sibling holds the %s surface (%s), so this is isolated rather "
                            "than sequenced -- the parallelism survives and the integration "
                            "becomes an explicit step."
                            % (surface, ", ".join(t["id"] for t in surface_clash)))

    if declared in ("inline", "subagent") and running and role_can_write(role):
        return "worktree", ("%d task(s) already running and %s writes files. Parallel writers in "
                            "one checkout produce a build output nobody owns."
                            % (len(running), role))

    return declared, "no fact overruled the stage's recommendation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", required=True)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
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
        mode, why = resolve(project, graph, t)
        out.append({"task": t["id"], "declared": t.get("execution", "subagent"),
                    "resolved": mode, "changed": mode != t.get("execution", "subagent"),
                    "why": why})

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print("%-7s %-14s %-14s %s" % ("TASK", "DECLARED", "RESOLVED", "WHY"))
        for r in out:
            mark = "->" if r["changed"] else "  "
            print("%-7s %-14s %s %-12s %s"
                  % (r["task"], r["declared"], mark, r["resolved"], r["why"][:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
