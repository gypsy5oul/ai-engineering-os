#!/usr/bin/env python3
"""SubagentStart: give the agent its work, and only its work.

Verified empirically against Claude Code 2.1.237: SubagentStart fires with
`agent_type` and `agent_id`, and an `additionalContext` returned here reaches the
subagent. That is what lets the organization keep its agent definitions small.

The alternative -- baking the project's configuration, the current stage, the
risk and the constraints into thirty agent files -- was the shape this repository
started with, and it has two costs. Every spawn pays for context the role will
never use, and the moment anything changes, thirty files disagree with reality
until someone remembers them all.

So the durable work item on disk is the source, and each agent gets the slice
that applies to it: what is being built, which task is theirs, what it must
produce, and what has already gone wrong. Nothing else.

Silent on purpose when there is no active work item. A session doing something
other than a tracked change is a normal session, not an error.
"""
import json
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))


def build(project, agent_type):
    import workitem as W
    wid = W.current(project)
    if not wid:
        return None
    item = W.load_item(project, wid)
    if not item:
        return None
    graph = W.load_graph(project, wid) or {"tasks": []}

    lines = ["## Your work item", "",
             "%s (%s, %s risk, stage %s)" % (item["id"], item["type"], item["risk"],
                                             item.get("stage", "?")),
             "",
             "**Intent, in the requester's words:** %s" % item["intent"],
             "**Objective, as the organization understood it:** %s" % item["objective"],
             ""]

    mine = [t for t in graph.get("tasks", [])
            if t.get("role") == agent_type and t["state"] not in W.TERMINAL]
    if mine:
        lines.append("## Your task")
        lines.append("")
        for t in mine:
            lines.append("**%s — %s**" % (t["id"], t["title"]))
            if t.get("produces"):
                lines.append("- Must produce: %s" % ", ".join(t["produces"]))
            if t.get("definition_of_done"):
                lines.append("- Definition of done: %s" % "; ".join(t["definition_of_done"]))
            if t.get("reviewer"):
                lines.append("- Reviewed by: %s" % t["reviewer"])
            if t.get("coupled_surface"):
                lines.append("- Touches the **%s** surface. It has an owner; if the contract is "
                             "wrong, raise it rather than changing it." % t["coupled_surface"])
            attempts = t.get("attempts", 0)
            if attempts:
                lines.append("- Attempt %d of %d. Previously: %s"
                             % (attempts + 1, t.get("max_attempts", 3),
                                t.get("result") or "no detail recorded"))
            lines.append("")

    blocked = [t for t in graph.get("tasks", []) if t["state"] in ("blocked", "escalated")]
    if blocked:
        lines.append("## Blocked elsewhere in this change")
        for t in blocked:
            lines.append("- %s (%s): %s" % (t["id"], t["state"],
                                            t.get("blocked_reason") or "no reason recorded"))
        lines.append("")

    if item.get("replans"):
        lines.append("This work has been replanned %d time(s). The history is in "
                     "`.ai-engineering/work/%s/history.jsonl`, and the reasons matter: "
                     "repeating a superseded approach is the failure mode here."
                     % (item["replans"], item["id"]))
    return "\n".join(lines).strip()


def main():
    data = H.read_input()
    agent_type = (data.get("agent_type") or "").split(":")[-1]
    if not agent_type:
        sys.exit(0)
    try:
        context = build(H.PROJECT_DIR, agent_type)
    except Exception:
        # A context injector that breaks a spawn is worse than one that stays
        # quiet. The agent definition alone is a workable, if larger, fallback.
        sys.exit(0)
    if not context:
        sys.exit(0)
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SubagentStart",
                               "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
