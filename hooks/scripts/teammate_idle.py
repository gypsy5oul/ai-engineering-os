#!/usr/bin/env python3
"""TeammateIdle: an agent that stopped talking has not necessarily finished.

A teammate going idle means it stopped producing turns. The organization's
question is different -- does it still hold a task nobody has accepted -- and
those two came apart with nothing watching the gap.

The correlation available here is weak and this hook is built around that.
TeammateIdle carries `teammate_name` and a deprecated `team_name`; it does NOT
carry `agent_id`, which is what a task lease is keyed by. So the teammate can
only be matched to a lease by name, and this blocks only when exactly one lease
matches unambiguously. Where the name matches nothing, or several tasks, it says
nothing at all: nagging on a guess teaches people to ignore the hook, which costs
more than the case it would have caught.
"""
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402

DONE = ("accepted", "abandoned", "rejected")


def held_by(graph, name):
    """Tasks this teammate plausibly holds, matched by name against the lease.

    Both the agent id and the role are compared, because which of the two a
    teammate is named after is not something this can know from the payload.
    """
    if not name:
        return []
    want = str(name).split(":")[-1].strip().lower()
    out = []
    for t in graph.get("tasks", []):
        if t["state"] in DONE:
            continue
        owner = str(t.get("owner_agent") or "").split(":")[-1].strip().lower()
        role = str(t.get("role") or "").strip().lower()
        if want and want in (owner, role):
            out.append(t)
    return out


def main():
    data = H.read_input()
    name = data.get("teammate_name")
    project = H.PROJECT_DIR
    wid = W.active_item(project, data.get("session_id"), H.plugin_data_dir())
    if not wid:
        sys.exit(0)
    graph = W.load_graph(project, wid)
    if not graph:
        sys.exit(0)

    mine = held_by(graph, name)
    if len(mine) != 1:
        # No match, or an ambiguous one. Both are silence: this hook can block a
        # teammate from going idle, and doing that on a guess is worse than
        # missing the case.
        if mine:
            W.record(project, wid, "teammate_idle_ambiguous", teammate=name,
                     candidates=[t["id"] for t in mine],
                     why="TeammateIdle carries no agent_id, so the lease could not be identified")
        sys.exit(0)

    t = mine[0]
    W.record(project, wid, "teammate_idle_with_open_task", teammate=name, task=t["id"],
             state=t["state"])
    sys.stderr.write(
        "[ai-engineering-os] %s still holds %s (%s), which nobody has accepted.\n"
        "Finish it, or record what happened with `control_loop.py observe --item %s --task %s "
        "--outcome failed|blocked` so the loop can decide. Going idle is not an outcome.\n"
        % (name, t["id"], t["state"], wid, t["id"]))
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Never strand a teammate on this hook's own failure.
        sys.exit(0)
