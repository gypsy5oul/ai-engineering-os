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
import re
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))


def contract(project, task, change=None):
    """Ask the one acceptance authority whether this task's contract is met.

    This used to evaluate the definition of done itself and drop three things on
    the floor: an unparseable entry, a predicate the model does not define, and an
    evaluator that raised. All three were `continue`, so the gate saw no failure
    and allowed the completion -- an unknown predicate was a definition of done
    that always passed. Same evaluation as `observe --outcome accepted`, because
    two acceptance authorities is how the durable graph came to disagree with the
    gate in the first place.
    """
    sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts"))
    sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))
    import check_dod
    return check_dod.acceptance(project, task, change=change)


TASK_MARKER = re.compile(r"\bT-[0-9]{3,}\b")


def main():
    data = H.read_input()
    task_id = data.get("task_id")
    risk = "MEDIUM"
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

        # The native task is bound to a graph task by the marker the spawner
        # writes into its subject or description. Matched as whole tokens, not as
        # a substring: `T-001 in "T-0010 done"` is true, and the schema permits
        # both ids, so substring matching could close the wrong task.
        blob = "%s %s" % (data.get("task_subject") or "", data.get("task_description") or "")
        mentioned = set(TASK_MARKER.findall(blob))
        held = next((t for t in graph.get("tasks", []) if t.get("native_task") == task_id), None)
        if held is None:
            held = next((t for t in graph.get("tasks", []) if t["id"] in mentioned), None)
        if held is None:
            sys.exit(0)
        risk = held.get("risk") or (W.load_item(project, wid) or {}).get("risk") or "MEDIUM"

        # Bind the two ids now that they are known, so the next event does not
        # have to re-derive the association from prose.
        if task_id and held.get("native_task") != task_id:
            try:
                W.bind_native_task(project, wid, held["id"], task_id)
            except Exception:
                pass

        result = contract(project, held, change=wid)
        failing, unsupported = result["failing"], result["unsupported"]
        high = str(risk).upper() in ("HIGH", "CRITICAL")

        # An entry the checker cannot answer is not a satisfied one. On HIGH and
        # CRITICAL work that difference is the whole point of having a gate; below
        # it, refusing every session over a broken predicate would make the gate
        # unusable, so it is allowed and recorded.
        blocking = list(failing)
        if unsupported and high:
            blocking += unsupported

        if not blocking:
            W.record(project, wid, "task_completion_allowed", task=held["id"],
                     native_task=task_id, unsupported=unsupported,
                     unverifiable=result["unverifiable"])
            if unsupported:
                sys.stderr.write(
                    "[ai-engineering-os] %s completed with %d predicate(s) its definition of "
                    "done could not answer:\n  - %s\nThese were not checked. Fix them; an "
                    "unanswerable predicate is not a satisfied one.\n"
                    % (held["id"], len(unsupported), "\n  - ".join(unsupported)))
            sys.exit(0)

        W.record(project, wid, "task_completion_blocked", task=held["id"],
                 native_task=task_id, failing=failing, unsupported=unsupported, risk=risk)
        sys.stderr.write(
            "[ai-engineering-os] %s cannot be completed.\n%s%s"
            "Fix these, or record the outcome with `control_loop.py observe --outcome failed` "
            "so the loop can decide whether to retry, rework or escalate.\n"
            % (held["id"],
               ("  %d predicate(s) of its definition of done fail:\n  - %s\n"
                % (len(failing), "\n  - ".join(failing))) if failing else "",
               ("  %d predicate(s) could not be answered at all, and this is %s-risk work:\n"
                "  - %s\n" % (len(unsupported), risk, "\n  - ".join(unsupported)))
               if unsupported and high else ""))
        sys.exit(2)
    except SystemExit:
        raise
    except Exception as exc:
        # A gate that breaks a session is worse than one that misses a case --
        # but this gate is the only place the platform will actually refuse, and
        # turning "the check could not run" into "the check passed" is the
        # failure mode the whole repository is arranged against. So it is
        # risk-tiered, the same way every other guard here is.
        fail_open(risk, exc, task_id)


def fail_open(risk, exc, task_id):
    """What to do when the gate itself breaks, by the risk of the work."""
    try:
        H.audit({"type": "task_gate_failed", "risk": risk, "native_task": task_id,
                 "error": repr(exc)[:200]})
    except Exception:
        pass
    if str(risk).upper() in ("HIGH", "CRITICAL"):
        sys.stderr.write(
            "[ai-engineering-os] The definition-of-done gate could not run for this %s-risk "
            "task: %r\nIt is not being treated as satisfied. Re-run the check, or record the "
            "outcome with `control_loop.py observe` and let the loop decide.\n"
            % (risk, exc))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
