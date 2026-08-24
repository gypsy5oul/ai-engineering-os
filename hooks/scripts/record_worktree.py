#!/usr/bin/env python3
"""WorktreeCreate / WorktreeRemove: record that isolation happened.

The execution resolver can resolve a task to `worktree`, and until this existed
nothing observed whether one was ever created. What can honestly be recorded is
limited by the payload: WorktreeCreate carries `name` and WorktreeRemove carries
`worktree_path`, and neither carries a task or an agent. So these events are
written to the work item's history as evidence that isolation occurred during
this change, and explicitly NOT bound to a task -- a correlation by timing would
look like knowledge and be a guess.
"""
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402


def main():
    data = H.read_input()
    event = data.get("hook_event_name") or "Worktree"
    project = H.PROJECT_DIR
    wid = W.active_item(project, data.get("session_id"), H.plugin_data_dir())
    if not wid:
        sys.exit(0)
    W.record(project, wid, "worktree_" + ("created" if event == "WorktreeCreate" else "removed"),
             name=data.get("name"), path=data.get("worktree_path"),
             bound_to_task=None,
             why="the payload carries no task or agent, so this is evidence that isolation "
                 "happened during this change and not evidence about which task used it")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
