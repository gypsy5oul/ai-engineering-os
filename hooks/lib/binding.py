"""Match a Claude Code native task to the organizational task it is executing.

Two events need this answer and used to derive it separately. `TaskCompleted`
worked it out from a subject line at the very end, which is the latest possible
moment: everything between creation and completion ran with the association
unrecorded, so `SubagentStart` briefed from a re-derivation of the same prose and
a crash in between lost the link entirely.

`TaskCreated` is the earliest moment the platform offers, and it is where the
binding belongs. This module is the single resolution rule both events use, so
the two cannot answer differently -- which is how the durable graph came to
disagree with the gate the first time.

`SubagentStart` is not one of them: it carries `agent_id` and `agent_type` and no
task id, so the briefing claims a task by agent and has nothing to resolve.

What the platform gives us, verified against Claude Code 2.1.250 by reading the
binary rather than the documentation:

    hook_event_name: "TaskCreated"
    task_id, task_subject, task_description?, teammate_name?, team_name?

`team_name` is marked `@deprecated` in the payload schema. There is no
`hookSpecificOutput` variant for either task event, so neither can inject context
or rewrite a field: the binding has to be *written down* in the graph and read
back later. And there are no dependency edges in the payload -- the native
engine keeps `blocks`/`blockedBy` internally, but does not send them -- which is
why the task graph is this plugin's own artifact and not a mirror of Claude's
list.
"""
import re

# Whole tokens, never substrings. `T-001` is inside `T-0010`, and the schema
# permits both, so substring matching binds and later closes the wrong task.
TASK_MARKER = re.compile(r"\bT-[0-9]{3,}\b")


def markers(data):
    """Every graph task id the native task's own text names."""
    blob = "%s %s" % (data.get("task_subject") or "", data.get("task_description") or "")
    return set(TASK_MARKER.findall(blob))


def resolve(graph, data):
    """Return (task, how) for the graph task this native task is executing.

    `how` is one of:
      bound     -- an earlier event already recorded the association. Trusted
                   over the prose, because prose can be edited after the fact.
      marker    -- the subject or description names exactly one graph task id.
      unknown   -- nothing here identifies a graph task. Not an error: most
                   native tasks in a session are not organizational tasks, and a
                   hook that treated silence as a problem would fire constantly.
      missing   -- the text names a task id that does not exist in this graph.
      ambiguous -- the text names more than one existing graph task.

    `missing` and `ambiguous` are returned rather than swallowed. The completion
    gate treated both as "not ours" and exited quietly, so a task referring to an
    invented id was indistinguishable from an ordinary unrelated task.
    """
    tasks = graph.get("tasks", []) or []
    native = data.get("task_id")

    if native:
        held = next((t for t in tasks if t.get("native_task") == native), None)
        if held is not None:
            return held, "bound"

    named = markers(data)
    if not named:
        return None, "unknown"

    known = [t for t in tasks if t["id"] in named]
    if len(known) == 1:
        return known[0], "marker"
    if len(known) > 1:
        return None, "ambiguous"
    return None, "missing"


def contradicts_binding(graph, task, data):
    """A different existing graph task that this payload's own text names.

    `resolve` trusts a recorded binding over prose, which is right at completion:
    a subject line can be rewritten and the recorded id cannot. But at *creation*
    a native id that is already bound, whose text names a different task, is not
    an edited subject -- it is a contradiction between what the platform is
    creating and what the organization already recorded. Returning it lets the
    caller say so instead of quietly binding to the older answer.
    """
    others = [t for t in graph.get("tasks", []) or []
              if t["id"] in markers(data) and t["id"] != task["id"]]
    return others[0] if others else None


def double_bound(graph, task, native):
    """The graph task this native id is already bound to, if it is another one.

    One native task belongs to one graph task. `workitem.bind_native_task`
    refuses the rebind and returns None, which reads identically to "the graph
    was not loadable" at the call site -- so the caller has to ask this first if
    it wants to say anything useful about why.
    """
    if not native:
        return None
    for t in graph.get("tasks", []) or []:
        if t.get("native_task") == native and t["id"] != task["id"]:
            return t
    return None


def as_teammate(data):
    """Whether the platform says this task runs as a teammate.

    `teammate_name` is the only assignee signal the payload carries, and it
    carries no role: a teammate name is a display name, not a registry entry. So
    this answers "is it a teammate", never "which role is it".
    """
    return bool(data.get("teammate_name"))
