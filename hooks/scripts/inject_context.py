#!/usr/bin/env python3
"""SubagentStart: give the agent its work, and only its work.

`additionalContext` is a declared field of the SubagentStart hook output schema,
and it reaches the subagent -- confirmed both in the CLI's own zod contract and on
the wire. That is what lets the organization keep its agent definitions small.

The agent is briefed on exactly one task, claimed against its `agent_id`. Matching
on role alone briefed an agent on every task its role owned, and briefed two
concurrent agents on the same one.

The alternative -- baking the project's configuration, the current stage, the
risk and the constraints into thirty agent files -- was the shape this repository
started with, and it has two costs. Every spawn pays for context the role will
never use, and the moment anything changes, thirty files disagree with reality
until someone remembers them all.

So the durable work item on disk is the source, and each agent gets the slice
that applies to it: what is being built, which task is theirs, what it must
produce, and what has already gone wrong. Nothing else.

Silent on purpose when there is no active work item. A session doing something
other than a tracked change is a normal session, not an error.
"""
import json
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts"))
import briefing  # noqa: E402
import workitem as W  # noqa: E402


def build(project, agent_type, agent_id=None, session=None):
    wid = W.active_item(project, session, H.plugin_data_dir())
    if not wid:
        return None
    item = W.load_item(project, wid)
    if not item:
        return None
    graph = W.load_graph(project, wid) or {"tasks": []}

    # Claim exactly one task for this agent. Matching on role alone briefed an
    # agent on every task its role owned, and two agents on the same one.
    claimed = W.claim(project, wid, agent_type, agent_id, session) if agent_id else None
    if claimed is None:
        return briefing.render(item, None, graph, project)

    # Everything after the claim can fail, and until this existed a failure left
    # the task leased to an agent that had received nothing: the organization
    # recorded that T-007 was being worked on by someone who had never heard of
    # it, and SubagentStop then attributed whatever that agent did to T-007.
    # SubagentStart cannot refuse a spawn -- it is not in the CLI's blocking set
    # -- so the agent runs regardless. What can be fixed is the lie.
    try:
        resolve_and_record(project, wid, claimed, agent_id)
        graph = W.load_graph(project, wid) or graph
        claimed = W.task(graph, claimed["id"])
        return briefing.render(item, claimed, graph, project)
    except Exception as exc:
        return abandon_claim(project, wid, item, claimed, agent_id, exc)


def abandon_claim(project, wid, item, claimed, agent_id, exc):
    """Give the task back, and tell the agent it is running without its contract.

    Releasing is the honest half: an unattributed result is a gap in the record,
    while a result attributed to a task the agent never saw is a false entry in
    it, and only one of those can be noticed later.
    """
    # The higher of the two. A LOW task inside a CRITICAL change is still work
    # nobody should do blind, and taking only the task's risk here would let the
    # finer-grained number talk the coarser one down.
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    levels = [str((claimed or {}).get("risk") or "MEDIUM").upper(),
              str(item.get("risk") or "MEDIUM").upper()]
    risk = max(levels, key=lambda r: order.get(r, 1))
    released = None
    try:
        released = W.release(project, wid, agent_id)
    except Exception as release_failed:
        # The release failing is the serious half of this: the alternative to a
        # released lease is a task the organization believes is being worked on
        # by an agent that never heard of it.
        try:
            H.audit({"type": "lease_release_failed", "work_item": wid,
                     "task": (claimed or {}).get("id"), "agent": agent_id,
                     "error": repr(release_failed)[:200]})
        except Exception:
            pass
        if os.environ.get("AIEOS_DEBUG"):
            sys.stderr.write("release failed: %r\n" % (release_failed,))
    try:
        H.audit({"type": "briefing_failed", "work_item": wid,
                 "task": (claimed or {}).get("id"), "agent": agent_id,
                 "risk": risk, "error": repr(exc)[:200]})
        W.record(project, wid, "briefing_failed", task=(claimed or {}).get("id"),
                 agent_id=agent_id, risk=risk, error=repr(exc)[:200],
                 why="the lease was released; an unbriefed agent must not own a task")
    except Exception:
        pass

    warning = [
        "## This session has no organizational context",
        "",
        "The work item briefing could not be built (%s). The task that had been "
        "assigned to you has been released, so nothing is recorded as belonging to "
        "you." % repr(exc)[:120],
        "",
    ]
    if risk in ("HIGH", "CRITICAL"):
        warning += [
            "This is %s-risk work. Do not proceed on assumption. Report that the briefing "
            "failed and stop; the organization cannot tell whether what you produce belongs "
            "to this change." % risk,
        ]
    else:
        warning += [
            "Say so before doing anything whose correctness depends on the requirement, the "
            "architecture or the definition of done, none of which reached you.",
        ]
    return "\n".join(warning)


def observe_actual(project, wid, task, agent_id):
    """Record what the runtime actually did, or why that cannot be determined."""
    # The environment alone, not resolve_execution.teams_available(), which also
    # asks whether the project expects teams. That is the right question when
    # deciding what to spawn and the wrong one here: if the flag is on, a named
    # spawn becomes a teammate whatever project.yaml says, so a spawn observed in
    # that environment could be either.
    teams_on = os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1"
    evidence = "SubagentStart fired for %s" % (agent_id or "an unnamed agent")
    if teams_on:
        # A teammate spawn and a subagent spawn look the same from here.
        W.set_execution(task, actual_evidence=evidence,
                        actual_undetermined="agent teams are enabled in this environment and "
                                            "SubagentStart does not distinguish a teammate from "
                                            "a subagent")
    else:
        W.set_execution(task, actual="subagent", actual_evidence=evidence)
    resolved = (task.get("execution") or {}).get("resolved")
    actual = (task.get("execution") or {}).get("actual")
    if actual and resolved and actual != resolved:
        # The resolver records and does not compel, so this is the only place the
        # difference between what was decided and what happened becomes visible.
        W.record(project, wid, "execution_diverged", task=task["id"],
                 resolved=resolved, actual=actual, evidence=evidence,
                 why="the spawn did not use the mode the resolver decided")


def resolve_and_record(project, wid, task, agent_id=None):
    """Resolve how this task should run, and write the answer onto the task.

    The resolver was correct and standalone: execution-policy.json named it as its
    enforcement, and nothing on the spawn path called it. A stage could declare
    `team`, the resolver could say `subagent`, and the spawn could do a third
    thing with nothing recording that the three disagreed. This is the claim path,
    which is the only moment where the situation is known and the spawn has not
    happened yet.
    """
    try:
        # workitem is imported inside build(), not at module scope, so this needs
        # its own import rather than the caller's name.
        import resolve_execution
        graph = W.load_graph(project, wid)
        live = W.task(graph, task["id"])
        result = resolve_execution.record_resolution(project, wid, live, graph)
        if result is None:
            return None
        # SubagentStart firing is evidence that this task ran as a hook-visible
        # spawn. It is not evidence of which kind: the payload carries agent_id
        # and agent_type and nothing else -- no teammate marker, no isolation
        # flag -- so the mode is claimed only where the environment makes it
        # unambiguous, and the reason is recorded where it does not.
        observe_actual(project, wid, live, agent_id)
        W.save_graph(project, graph)
        task["execution"] = live["execution"]
        if live.get("isolation") is not None:
            task["isolation"] = live["isolation"]

        mode, isolation, why = result
        # Two dimensions, so two things can have been overruled. Recording only
        # the mode was how a task isolated into its own checkout left no trace of
        # having been isolated -- the reason went into the execution record and
        # the decision itself went nowhere.
        if mode != W.declared_execution(live) or isolation != W.declared_isolation(live):
            W.record(project, wid, "execution_resolved", task=task["id"],
                     declared=W.declared_execution(live), resolved=mode,
                     declared_isolation=W.declared_isolation(live),
                     resolved_isolation=isolation, why=why)
        return result
    except Exception as exc:
        # A resolver that breaks a spawn is worse than a spawn that runs as
        # declared. The declaration is a considered default, not a guess. It is
        # still recorded: a resolver that silently never runs is the defect this
        # whole path exists to close.
        if os.environ.get("AIEOS_DEBUG"):
            sys.stderr.write("resolve_and_record failed: %r\n" % (exc,))
        try:
            H.audit({"type": "execution_resolution_failed", "task": task.get("id"),
                     "work_item": wid, "error": repr(exc)[:200]})
        except Exception:
            pass
        return None


def main():
    data = H.read_input()
    agent_type = (data.get("agent_type") or "").split(":")[-1]
    if not agent_type:
        sys.exit(0)
    try:
        context = build(H.PROJECT_DIR, agent_type, data.get("agent_id"),
                        data.get("session_id"))
    except Exception:
        # A context injector that breaks a spawn is worse than one that stays
        # quiet. The agent definition alone is a workable, if larger, fallback.
        sys.exit(0)
    if not context:
        sys.exit(0)
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SubagentStart",
                               "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
