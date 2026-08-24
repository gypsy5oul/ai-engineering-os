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
        wid = W.active_item(project, data.get("session_id"), H.plugin_data_dir())
        if not wid:
            sys.exit(0)
        graph = W.load_graph(project, wid)
        if not graph:
            sys.exit(0)

        # Resolve the lease this agent took at SubagentStart. Never infer from
        # role: with two tasks sharing a role, one agent's output was written to
        # both, and the graph then claimed work nobody had done.
        agent_id = data.get("agent_id")
        held = W.resolve(project, wid, agent_id) if agent_id else None
        if held is None:
            W.record(project, wid, "subagent_stopped_unattributed", agent=agent_type,
                     agent_id=agent_id,
                     why="no task was leased to this agent, so its result belongs to nothing")
            sys.exit(0)

        message = (data.get("last_assistant_message") or "").strip()
        thin = message.lower() in EMPTY or len(message) < 40
        # One transaction. This used to resolve, then load the graph a second
        # time, edit, save, and release -- three separate lock scopes, so a
        # concurrent claim landing between them was overwritten. That is the same
        # lost update the lease exists to prevent, arriving one door further along.
        # `actual` is NOT set from here. It used to be set to
        # W.effective_execution(held) -- the resolution this hook had just read
        # back -- so the field recorded that the graph agreed with itself and
        # proved nothing about what ran. It is written at SubagentStart, from the
        # event that is actual evidence a spawn happened.
        t = W.complete_lease(
            project, wid, agent_id,
            result=message[:400] or "(the agent stopped without a result)")
        if t is None:
            W.record(project, wid, "subagent_stopped_unattributed", agent=agent_type,
                     agent_id=agent_id,
                     why="the lease was gone by the time the result arrived")
            sys.exit(0)
        W.record(project, wid, "subagent_stopped", agent=agent_type,
                 agent_id=agent_id, task=t["id"],
                 execution=W.effective_execution(t),
                 thin_result=thin, transcript=data.get("agent_transcript_path"))
        mine = [t]

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
