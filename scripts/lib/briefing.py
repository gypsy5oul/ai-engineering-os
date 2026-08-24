"""The task briefing, in one place, because it has two delivery routes.

`SubagentStart` injects it as `additionalContext`. An isolated spawn does not
receive that -- verified against Claude Code 2.1.241 and recorded in
policies/platform-capabilities.json -- so for those the briefing has to travel in
the spawn prompt instead.

Two routes and one text. Written twice, they would drift, and the isolated route
is the one nobody would notice drifting: the agent still gets *a* briefing, just
not the one the hook would have given it.
"""


def render(item, task=None, graph=None):
    """The briefing for this work item, and this task if one is claimed."""
    graph = graph or {"tasks": []}
    lines = ["## Your work item", "",
             "%s (%s, %s risk, stage %s)" % (item["id"], item["type"], item["risk"],
                                             item.get("stage", "?")),
             "",
             "**Intent, in the requester's words:** %s" % item["intent"],
             "**Objective, as the organization understood it:** %s" % item["objective"],
             ""]

    if task is not None:
        lines += ["## Your task", "", "**%s — %s**" % (task["id"], task["title"])]
        if task.get("role"):
            lines.append("- You are acting as: %s" % task["role"])
        if task.get("produces"):
            lines.append("- Must produce: %s" % ", ".join(task["produces"]))
        if task.get("definition_of_done"):
            lines.append("- Definition of done: %s" % "; ".join(task["definition_of_done"]))
        if task.get("reviewer"):
            lines.append("- Reviewed by: %s" % task["reviewer"])
        if task.get("owns_paths"):
            lines.append("- Owns these paths, and only these: %s"
                         % ", ".join(task["owns_paths"]))
        if task.get("coupled_surface"):
            lines.append("- Touches the **%s** surface. It has an owner; if the contract is "
                         "wrong, raise it rather than changing it." % task["coupled_surface"])
        ex = task.get("execution") if isinstance(task.get("execution"), dict) else {}
        if ex.get("resolved") and ex["resolved"] != ex.get("declared"):
            lines.append("- Execution: declared `%s`, resolved to `%s` — %s"
                         % (ex.get("declared"), ex["resolved"],
                            (ex.get("resolution_reason") or "")[:120]))
        attempts = task.get("attempts", 0)
        if attempts:
            lines.append("- Attempt %d of %d. Previously: %s"
                         % (attempts + 1, task.get("max_attempts", 3),
                            task.get("result") or "no detail recorded"))
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
