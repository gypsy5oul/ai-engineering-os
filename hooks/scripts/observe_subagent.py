#!/usr/bin/env python3
"""SubagentStop: record what the agent actually produced, against its task.

Verified against Claude Code 2.1.237: SubagentStop carries `agent_type`,
`agent_id`, `last_assistant_message` and `agent_transcript_path`. That is enough
to attribute a result to a task without the agent having to report it.

Why that matters: an agent reporting its own completion is the weakest possible
evidence, and it is the point where an organization stops being able to tell
finished from abandoned. A subagent that stops without saying anything useful
looks identical to one that succeeded, unless something outside it is watching.

This observes; it does not judge. Whether the result is good enough is the
definition of done's question, and the control loop's `decide` answers what to do
about it. Recording is enough of a job.
"""
import json
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))

# A stop with nothing behind it. Distinguished from a real result because
# "the agent ran and produced nothing" is a finding, not a success.
EMPTY = ("", "none", "no output", "done", "ok")


def main():
    data = H.read_input()
    if data.get("stop_hook_active"):
        sys.exit(0)
    agent_type = (data.get("agent_type") or "").split(":")[-1]
    if not agent_type:
        sys.exit(0)

    try:
        import workitem as W
        project = H.PROJECT_DIR
        wid = W.current(project)
        if not wid:
            sys.exit(0)
        graph = W.load_graph(project, wid)
        if not graph:
            sys.exit(0)

        mine = [t for t in graph.get("tasks", [])
                if t.get("role") == agent_type and t["state"] not in W.TERMINAL]
        if not mine:
            sys.exit(0)

        message = (data.get("last_assistant_message") or "").strip()
        thin = message.lower() in EMPTY or len(message) < 40
        for t in mine:
            t["last_activity"] = W.now()
            if not t.get("result"):
                t["result"] = message[:400] or "(the agent stopped without a result)"
        W.save_graph(project, graph)
        W.record(project, wid, "subagent_stopped", agent=agent_type,
                 agent_id=data.get("agent_id"), tasks=[t["id"] for t in mine],
                 thin_result=thin, transcript=data.get("agent_transcript_path"))

        if thin:
            # Say so rather than blocking. The agent has already stopped, and a
            # thin result is a thing for the loop to notice, not an error to raise.
            sys.stdout.write(json.dumps({"systemMessage":
                "[ai-engineering-os] %s stopped with little or no result against %s. "
                "Record the outcome with `control_loop.py observe` before continuing: an "
                "unobserved task is indistinguishable from an abandoned one."
                % (agent_type, ", ".join(t["id"] for t in mine))}))
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
