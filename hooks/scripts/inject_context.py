#!/usr/bin/env python3
"""SubagentStart: give the agent its work, and only its work.

`additionalContext` is a declared field of the SubagentStart hook output schema,
and it reaches the subagent -- confirmed both in the CLI's own zod contract and on
the wire. That is what lets the organization keep its agent definitions small.

The agent is briefed on exactly one task, claimed against its `agent_id`. Matching
on role alone briefed an agent on every task its role owned, and briefed two
concurrent agents on the same one.

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


def build(project, agent_type, agent_id=None, session=None):
    import workitem as W
    wid = W.active_item(project, session, H.plugin_data_dir())
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

    # Claim exactly one task for this agent. Matching on role alone briefed an
    # agent on every task its role owned, and two agents on the same one.
    claimed = W.claim(project, wid, agent_type, agent_id, session) if agent_id else None
    if claimed is not None:
        resolve_and_record(project, wid, claimed)
    mine = [claimed] if claimed else []
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
            ex = t.get("execution") if isinstance(t.get("execution"), dict) else {}
            if ex.get("resolved") and ex["resolved"] != ex.get("declared"):
                lines.append("- Execution: declared `%s`, resolved to `%s` — %s"
                             % (ex.get("declared"), ex["resolved"],
                                (ex.get("resolution_reason") or "")[:120]))
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


def resolve_and_record(project, wid, task):
    """Resolve how this task should run, and write the answer onto the task.

    The resolver was correct and standalone: execution-policy.json named it as its
    enforcement, and nothing on the spawn path called it. A stage could declare
    `team`, the resolver could say `subagent`, and the spawn could do a third
    thing with nothing recording that the three disagreed. This is the claim path,
    which is the only moment where the situation is known and the spawn has not
    happened yet.
    """
    try:
        # workitem is imported inside build(), not at module scope, so this needs
        # its own import rather than the caller's name.
        sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts"))
        sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))
        import resolve_execution
        import workitem as W
        graph = W.load_graph(project, wid)
        live = W.task(graph, task["id"])
        result = resolve_execution.record_resolution(project, wid, live, graph)
        if result is None:
            return None
        W.save_graph(project, graph)
        task["execution"] = live["execution"]
        mode, why = result
        if mode != W.declared_execution(live):
            W.record(project, wid, "execution_resolved", task=task["id"],
                     declared=W.declared_execution(live), resolved=mode, why=why)
        return result
    except Exception as exc:
        # A resolver that breaks a spawn is worse than a spawn that runs as
        # declared. The declaration is a considered default, not a guess. It is
        # still recorded: a resolver that silently never runs is the defect this
        # whole path exists to close.
        if os.environ.get("AIEOS_DEBUG"):
            sys.stderr.write("resolve_and_record failed: %r\n" % (exc,))
        try:
            H.audit({"type": "execution_resolution_failed", "task": task.get("id"),
                     "work_item": wid, "error": repr(exc)[:200]})
        except Exception:
            pass
        return None


def main():
    data = H.read_input()
    agent_type = (data.get("agent_type") or "").split(":")[-1]
    if not agent_type:
        sys.exit(0)
    try:
        context = build(H.PROJECT_DIR, agent_type, data.get("agent_id"),
                        data.get("session_id"))
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
