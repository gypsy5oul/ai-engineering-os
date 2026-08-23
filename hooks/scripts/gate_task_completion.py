#!/usr/bin/env python3
"""TaskCompleted: refuse to let a task be marked done when its work is not.

The earlier reading of this hook was that it cannot steer, so it was left unused.
That was too broad. It is true that TaskCreated and TaskCompleted carry no
dependency information and offer no `hookSpecificOutput`, so they cannot drive a
control loop. But they can do the one thing the loop most needs and cannot do for
itself: **exit 2 blocks the completion**.

That turns the definition of done from something the organization evaluates when
asked into something that has to be true before a task can close. Everywhere else
in this repository, a definition of done is checked because an agent chose to run
the checker. Here it is checked because the platform will not let the task finish
otherwise.

Deliberately narrow. It blocks only when a task is bound to a graph task whose
definition of done has a predicate that actually **fails** -- not when evidence is
merely missing, because "not yet provable" is a different thing from "wrong", and
a gate that cannot be satisfied offline would just teach people to turn it off.
"""
import json
import os
import subprocess
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))


def failing_predicates(project, task):
    """Predicates of this task's definition of done that FAIL right now.

    Evidence that cannot be seen from here is not a failure. A GitLab pipeline
    result is unknowable offline, and blocking on it would make the gate
    unusable rather than strict.
    """
    dod = task.get("definition_of_done") or []
    if not dod:
        return []
    sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts"))
    import check_dod
    artifacts = check_dod.load_artifacts(project)
    out = []
    for entry in dod:
        fn, args = check_dod.parse_predicate(entry)
        if fn is None:
            continue
        try:
            status, detail = check_dod.evaluate(fn, args, artifacts, project)
        except Exception:
            continue
        if status == "FAIL":
            out.append("%s -- %s" % (entry, detail[:80]))
    return out


def main():
    data = H.read_input()
    task_id = data.get("task_id")
    if not task_id:
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

        # The native task carries our graph task id in its subject or description,
        # which is how the two are bound. A native task with no binding is somebody
        # else's bookkeeping and none of this hook's business.
        blob = "%s %s" % (data.get("task_subject") or "", data.get("task_description") or "")
        held = next((t for t in graph.get("tasks", []) if t["id"] in blob), None)
        if held is None:
            sys.exit(0)

        failing = failing_predicates(project, held)
        if not failing:
            W.record(project, wid, "task_completion_allowed", task=held["id"],
                     native_task=task_id)
            sys.exit(0)

        W.record(project, wid, "task_completion_blocked", task=held["id"],
                 native_task=task_id, failing=failing)
        sys.stderr.write(
            "[ai-engineering-os] %s cannot be completed: %d predicate(s) of its definition "
            "of done fail.\n  - %s\n"
            "Fix these, or record the outcome with `control_loop.py observe --outcome failed` "
            "so the loop can decide whether to retry, rework or escalate.\n"
            % (held["id"], len(failing), "\n  - ".join(failing)))
        sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        # A gate that breaks a session is worse than one that misses a case.
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
