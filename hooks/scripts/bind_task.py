#!/usr/bin/env python3
"""TaskCreated: bind the native task to the organizational one, and check it may exist.

The lifecycle the organization wants is:

    TaskCreated -> validate -> bind -> SubagentStart -> execution -> SubagentStop
    -> TaskCompleted -> definition of done

Until now it started at `SubagentStart`, and the binding was not established at
all until `TaskCompleted` worked it out from a subject line -- the last possible
moment. Everything in between ran with the association unrecorded, and a crash
before completion lost the link outright. `TaskCreated` is the earliest point the
platform offers, so the association is written here: the completion gate then
matches on an id rather than on prose, the history says when the binding was made
and on what evidence, and the checks below run *before* the work is done instead
of after it.

It does not help `SubagentStart`. That event carries `agent_id` and `agent_type`
and no task id at all, so the briefing still claims a task by agent. The gain
here is durability and an earlier refusal, not a shorter briefing path.

**This does not duplicate the native task engine.** It creates no task, orders no
work and rewrites no field of Claude's list -- it could not if it wanted to,
because `TaskCreated` has no `hookSpecificOutput` variant. It establishes and
validates *organizational* metadata: which work item and graph task this is, whose
role owns it, whether its dependencies are met, and whether it is permitted to
start at all.

Blocking is deliberately narrow, for the same reason the completion gate's is.
Exit 2 here does not warn -- verified against 2.1.250, the CLI deletes the task
and strips its id out of every other task's edges -- so it fires only where the
organization can say the task is *wrong*, never where evidence is merely absent:

  * the text names a graph task that does not exist (an invented id),
  * the text names several, so binding would be a guess,
  * the graph task's dependencies are not accepted yet,
  * the graph task is already finished or abandoned,
  * the native id is already bound to a different graph task,
  * the role that owns it is not in the registry.

A task with no work item, no marker and no graph is not an error. Most native
tasks in a session are not organizational tasks, and a hook that treated silence
as a problem would fire constantly and be turned off.
"""
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402
import binding as B  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))

# States in which the work is over. Creating a native task for one of these means
# something is about to redo accepted work, or resurrect work that was dropped.
TERMINAL = ("accepted", "abandoned")


def registry_roles():
    reg = H.load_json(os.path.join(H.PLUGIN_ROOT, "policies", "agent-registry.json")) or {}
    return {a.get("name") for a in reg.get("agents") or []}


def refuse(project, wid, native, reason, detail, **fields):
    try:
        import workitem as W
        W.record(project, wid, "task_creation_blocked", native_task=native,
                 reason=reason, **fields)
    except Exception:
        pass
    H.audit({"type": "task_creation_blocked", "native_task": native, "reason": reason})
    sys.stderr.write("[ai-engineering-os] This task cannot be created.\n  %s\n" % detail)
    sys.exit(2)


def main():
    data = H.read_input()
    native = data.get("task_id")
    risk = "MEDIUM"
    if not native:
        sys.exit(0)

    try:
        import workitem as W
        project = H.PROJECT_DIR
        wid = W.active_item(project, data.get("session_id"), H.plugin_data_dir())
        if not wid:
            sys.exit(0)
        graph = W.load_graph(project, wid)
        if not graph:
            sys.exit(0)

        held, how = B.resolve(graph, data)

        if how == "unknown":
            # An ordinary task that is not part of the work item. Nothing to bind
            # and nothing to say.
            sys.exit(0)

        if how == "missing":
            named = ", ".join(sorted(B.markers(data)))
            refuse(project, wid, native, "unknown_task",
                   "It names %s, which is not a task in %s. Either the id is wrong, or the "
                   "work was never planned. Run `control_loop.py plan --item %s` to see the "
                   "graph, or drop the marker if this is not organizational work."
                   % (named, wid, wid), named=sorted(B.markers(data)), item=wid)

        if how == "ambiguous":
            named = ", ".join(sorted(B.markers(data)))
            refuse(project, wid, native, "ambiguous_task",
                   "It names several graph tasks (%s), so binding it to one would be a guess. "
                   "One native task executes one graph task. Split it, or name only the task "
                   "this one is." % named, named=sorted(B.markers(data)), item=wid)

        risk = held.get("risk") or (W.load_item(project, wid) or {}).get("risk") or "MEDIUM"

        # Two ways one native task ends up claiming two graph tasks: the id is
        # already recorded against another task, or it is recorded against this
        # one while the text names another. Both are the same defect and both
        # end with a completion closing work it was never about.
        clash = B.double_bound(graph, held, native)
        if clash is None and how == "bound":
            clash = B.contradicts_binding(graph, held, data)
            if clash is not None:
                refuse(project, wid, native, "double_binding",
                       "Native task %s is already bound to %s, but this names %s. The recorded "
                       "binding and the task's own text disagree, so one of them is about work "
                       "this task is not doing." % (native, held["id"], clash["id"]),
                       task=held["id"], names=clash["id"], item=wid, risk=risk)
        if clash is not None:
            refuse(project, wid, native, "double_binding",
                   "Native task %s is already bound to %s, and this would bind it to %s as "
                   "well. One native task belongs to one graph task, or a completion closes "
                   "work it was never about." % (native, clash["id"], held["id"]),
                   task=held["id"], already=clash["id"], item=wid)

        if held.get("state") in TERMINAL:
            refuse(project, wid, native, "terminal_task",
                   "%s is already %s. Starting it again would redo work the organization has "
                   "accepted, or resurrect work it dropped. If this is new work, it needs its "
                   "own task: `control_loop.py plan` or a task-synthesis proposal."
                   % (held["id"], held["state"]),
                   task=held["id"], state=held.get("state"), item=wid, risk=risk)

        if not W.dependencies_met(graph, held):
            open_deps = [d for d in held.get("depends_on") or []
                         if (W.task(graph, d) or {}).get("state") != "accepted"]
            refuse(project, wid, native, "dependencies_unmet",
                   "%s depends on %s, which %s not accepted yet. The graph exists to stop work "
                   "starting on an input that is still moving; the dependency is what makes the "
                   "artifact it produces trustworthy."
                   % (held["id"], ", ".join(open_deps),
                      "is" if len(open_deps) == 1 else "are"),
                   task=held["id"], depends_on=open_deps, item=wid, risk=risk)

        roles = registry_roles()
        if roles and held.get("role") not in roles:
            refuse(project, wid, native, "unknown_role",
                   "%s is assigned to role %r, which is not in policies/agent-registry.json. A "
                   "task nobody in the organization can perform is not a task."
                   % (held["id"], held.get("role")),
                   task=held["id"], role=held.get("role"), item=wid, risk=risk)

        # Everything organizational checks out. Establish the association now, so
        # the completion gate matches on an id and the link survives anything that
        # happens between here and there.
        bound = how == "bound"
        if not bound:
            bound = W.bind_native_task(project, wid, held["id"], native) is not None

        W.record(project, wid, "task_created", task=held["id"], native_task=native,
                 bound=bool(bound), resolved_by=how, role=held.get("role"),
                 state=held.get("state"), risk=risk,
                 execution=W.effective_execution(held),
                 teammate=data.get("teammate_name") or None,
                 subject=(data.get("task_subject") or "")[:200])

        if not bound:
            # The bind lost a race or the graph moved underneath it. Not worth
            # refusing a legitimate task over -- the completion gate can still
            # resolve from the marker -- but it is worth saying, because the
            # thing this hook exists to guarantee did not happen.
            sys.stderr.write(
                "[ai-engineering-os] %s could not be bound to native task %s. It will still be "
                "matched by its marker, but the association is not recorded. Check "
                "`control_loop.py status --item %s`.\n" % (held["id"], native, wid))
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as exc:
        fail_open(risk, exc, native)


def fail_open(risk, exc, native):
    """What to do when the check itself breaks, by the risk of the work.

    Same tiering as the completion gate and for the same reason: turning "the
    check could not run" into "the check passed" is the failure mode this
    repository is arranged against. But the asymmetry matters here. Refusing a
    completion leaves finished work needing a second look; refusing a *creation*
    deletes the task, so the cost of a false positive is higher and the tier that
    blocks is correspondingly narrower -- CRITICAL only.
    """
    try:
        H.audit({"type": "task_binding_failed", "risk": risk, "native_task": native,
                 "error": repr(exc)[:200]})
    except Exception:
        pass
    if str(risk).upper() == "CRITICAL":
        sys.stderr.write(
            "[ai-engineering-os] The task-binding check could not run for this CRITICAL task: "
            "%r\nIt is not being treated as valid. Fix the check, or plan the task explicitly "
            "with `control_loop.py plan`.\n" % (exc,))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
