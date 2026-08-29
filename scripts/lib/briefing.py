"""The task briefing, in one place, because it has two delivery routes.

`SubagentStart` injects it as `additionalContext`. An isolated spawn does not
receive that -- verified against Claude Code 2.1.241 and recorded in
policies/platform-capabilities.json -- so for those the briefing has to travel in
the spawn prompt instead.

Two routes and one text. Written twice, they would drift, and the isolated route
is the one nobody would notice drifting: the agent still gets *a* briefing, just
not the one the hook would have given it.

A definition of done arrives as predicate identifiers -- `every_skip_recorded();
config_valid()` -- and for two releases that is all it arrived as. Watched live,
an agent given exactly that spent six blocked commands trying to read the
plugin's own source to find out what the identifiers meant, because the meanings
live here and the plugin is outside an agent's read scope. It guessed correctly
in the end. Guessing correctly is not the same as being told.

So each predicate is glossed from `policies/artifact-model.json`, which is where
the evaluator reads it from too. A gloss written out here instead would be a
second copy of a definition, and the copy is always the one that goes stale.
"""
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GLOSS = None


def _glossary():
    """`predicate name -> one sentence`, read from the artifact model.

    Cached, because a briefing is rendered on every SubagentStart and the file is
    large. Failure is silent and returns an empty glossary: a briefing with bare
    predicate names is what this used to be, and is much better than a hook that
    raises during a spawn.
    """
    global _GLOSS
    if _GLOSS is not None:
        return _GLOSS
    _GLOSS = {}
    try:
        with open(os.path.join(_ROOT, "policies", "artifact-model.json"),
                  encoding="utf-8") as fh:
            model = json.load(fh)
    except (OSError, ValueError):
        return _GLOSS

    def walk(node):
        if not isinstance(node, dict):
            return None
        if "every_skip_recorded" in node:
            return node
        for value in node.values():
            found = walk(value)
            if found is not None:
                return found
        return None

    registry = walk(model) or {}
    for name, spec in registry.items():
        means = (spec or {}).get("means") or ""
        if not means:
            continue
        # The first sentence is the definition. What follows is usually the
        # history of why the predicate is shaped the way it is, which the
        # evaluator's reader needs and the agent doing the work does not.
        _GLOSS[name] = (re.split(r"(?<=[.])\s+", means.strip())[0],
                        (spec or {}).get("evidence") or "")
    return _GLOSS


def _dod_lines(predicates):
    """Each predicate as written, what it means, and where the evidence lives.

    The second half was the missing one. Told `cycle_rollup_reported(CYCLE-PROD)`
    and its meaning -- "the lead produced the rollup for the head" -- a real
    product-manager was called in three times and never produced one, because
    nothing said a rollup is a `rollup:` mapping in an artifact's frontmatter
    rather than a document to write. A predicate an agent cannot locate is a
    predicate no agent can satisfy.
    """
    gloss = _glossary()
    out = ["- Definition of done:"]
    for pred in predicates:
        name = pred.split("(")[0].strip()
        entry = gloss.get(name)
        if not entry:
            out.append("  - `%s`" % pred)
            continue
        meaning, evidence = entry
        out.append("  - `%s` — %s" % (pred, meaning))
        if evidence:
            out.append("    Satisfied by: %s" % evidence)
    return out


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
            lines += _dod_lines(task["definition_of_done"])
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
