#!/usr/bin/env python3
"""Measure what an execution actually cost, from transcripts rather than from claims.

A certification says whether the lifecycle *can* be completed. It says nothing
about what completing it cost, and cost is where an engineering OS is actually
judged: an organization whose agents reach the right answer after forty turns of
re-reading the same files has a working process and an unusable one.

Everything here is counted from durable evidence -- the work item history, and
the subagent transcripts the `SubagentStop` hook records the path to. Nothing is
inferred from a session's own account of itself, because an agent's summary of
its run is the least reliable record of it.

Two rules shape what is and is not reported.

**Nothing is fabricated.** A metric with no evidence is reported as
`not-measured` with the reason, never as zero. Zero and unmeasured look identical
in a dashboard and mean opposite things, and the difference is exactly the one a
reader needs.

**Nothing is judged.** "Unnecessary" is a judgement, so it is given a definition
that a machine can apply without one: a turn is unnecessary if its only tool
calls repeat a call already made with the same input, or were refused by the
platform in a way no retry could have changed. That undercounts. A turn that was
merely wasteful and unique is not caught, and no number here should be read as
the whole of the friction -- only as the part that can be counted.

    measure_friction.py --project <dir>
    measure_friction.py --project <dir> --json
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402

# A refusal by the platform, not a mistake by the agent. The distinction matters:
# the first is the organization's cost, the second is the model's.
PERMISSION_REFUSAL = re.compile(
    r"requires approval|was blocked|requested permissions|permission to|"
    r"only (?:list|search|read) files in|not allowed", re.I)

# Looking for the rules rather than doing the work.
#
# Only outside the project. The first version matched any path under `docs/`,
# which counted a product manager writing `docs/requirements/GOLD-REQ-001.md`
# as friction -- that is the REQ stage's actual work, and the metric reported
# 59% of a run as overhead when much of it was the deliverable. What is friction
# is reading the *organization's own rules* to find out what is being asked, and
# those live outside the project tree.
DOC_LOOKUP = re.compile(r"/(?:policies|schemas|sdlc|skills|agents)/|"
                        r"ai-engineering-plugin|CLAUDE\.md", re.I)

DISCOVERY = re.compile(r"^\s*(find|ls|tree|grep|rg)\b")


def _messages(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    return out


def _blocks(entry, kind):
    msg = entry.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind]


def _call_key(block):
    """What makes two tool calls the same call."""
    payload = block.get("input") or {}
    if block.get("name") == "Bash":
        return ("Bash", (payload.get("command") or "").strip())
    return (block.get("name"), json.dumps(payload, sort_keys=True))


def _outside(target, project):
    """Is this path outside the project being worked on?"""
    if not project or not target:
        return True
    try:
        return not os.path.abspath(str(target)).startswith(os.path.abspath(project) + os.sep)
    except (TypeError, ValueError):
        return True


def analyse_transcript(path, project=None):
    """Countable friction in one agent's run."""
    entries = _messages(path)
    if not entries:
        return None

    results = {}
    for e in entries:
        for b in _blocks(e, "tool_result"):
            results[b.get("tool_use_id")] = b

    seen = set()
    stats = {
        "turns": 0, "tool_calls": 0, "failed_tool_calls": 0,
        "permission_refusals": 0, "agent_errors": 0,
        "repeated_calls": 0, "discovery_calls": 0, "documentation_lookups": 0,
        "clarification_requests": 0, "unnecessary_turns": 0,
    }

    for e in entries:
        if e.get("type") != "assistant":
            continue
        stats["turns"] += 1
        calls = _blocks(e, "tool_use")
        texts = [b.get("text") or "" for b in _blocks(e, "text")]

        # In `-p` there is nobody to answer. A question is a stall.
        if not calls and any(t.rstrip().endswith("?") for t in texts):
            stats["clarification_requests"] += 1

        wasted = bool(calls)
        for b in calls:
            stats["tool_calls"] += 1
            key = _call_key(b)
            repeat = key in seen
            seen.add(key)
            if repeat:
                stats["repeated_calls"] += 1

            payload = b.get("input") or {}
            target = (payload.get("command") or payload.get("file_path")
                      or payload.get("pattern") or payload.get("path") or "")
            if b.get("name") == "Bash" and DISCOVERY.search(target):
                stats["discovery_calls"] += 1
            # A Bash command names many paths; a Read names one. Either way the
            # question is whether the agent went outside the project to find out
            # what the organization wanted.
            probe_path = payload.get("file_path") or payload.get("path") or ""
            if DOC_LOOKUP.search(str(target)) and (
                    not probe_path or _outside(probe_path, project)):
                stats["documentation_lookups"] += 1

            res = results.get(b.get("id")) or {}
            failed = bool(res.get("is_error"))
            refused = failed and bool(PERMISSION_REFUSAL.search(str(res.get("content"))))
            if failed:
                stats["failed_tool_calls"] += 1
                if refused:
                    stats["permission_refusals"] += 1
                else:
                    stats["agent_errors"] += 1

            # The defined sense of "unnecessary": this call taught the run
            # nothing it did not already have, or could never have succeeded.
            if not (repeat or refused):
                wasted = False
        if wasted:
            stats["unnecessary_turns"] += 1

    return stats


def _rate(num, den):
    return None if not den else round(float(num) / den, 4)


def measure(project, wid=None):
    wid = wid or W.current(project)
    if not wid:
        return {"work_item": None, "measured": False,
                "why": "no active work item, so there is no history to read"}

    entries = []
    path = os.path.join(project, ".ai-engineering", "work", wid, "history.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            entries = [json.loads(l) for l in fh if l.strip()]

    transcripts = [h["transcript"] for h in entries
                   if h.get("kind", "").startswith("subagent_stopped") and h.get("transcript")]

    per_agent, totals = [], {}
    for t in transcripts:
        stats = analyse_transcript(t, project)
        if stats is None:
            per_agent.append({"transcript": t, "measured": False,
                              "why": "the transcript named by the hook is not readable"})
            continue
        per_agent.append(dict(stats, transcript=t, measured=True))
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v

    graph = W.load_graph(project, wid) or {}
    tasks = graph.get("tasks", [])
    verdicted = [t for t in tasks if t.get("state") in ("accepted", "rejected", "rework")]
    first_pass = [t for t in verdicted
                  if t.get("state") == "accepted" and int(t.get("attempts") or 1) <= 1]

    # A recorded `execution_diverged` is not a failure awaiting recovery. It is
    # the OS noticing that what ran was not what was resolved, which is the
    # designed response and the only reason divergence is visible at all.
    # Counting it in the denominator reported the detector working as a 0%
    # recovery rate, which is the opposite of what happened.
    divergences = [h for h in entries if "diverged" in (h.get("kind") or "")]
    # Same class as a divergence, and it cost the same mistake twice. A
    # `subagent_stopped_unattributed` is the OS noticing that an agent ran
    # without holding a lease -- a detection. In the mechanism sessions that is
    # the expected shape, because no task was delegated to them, and counting
    # four of them as unrecovered failures reported a 0% recovery rate for a run
    # in which nothing had failed.
    detections = divergences + [h for h in entries
                                if "unattributed" in (h.get("kind") or "")]
    # Governance, counted and kept out of the friction numbers. A human approving
    # an architecture or a release is the organization working, not the
    # organization costing something -- the brief's line, and the reason
    # human_intervention_rate stays unmeasured even on a run where a human acted.
    approvals = [h for h in entries if h.get("kind") == "human_approval_recorded"]
    needed_recovery = [h for h in entries
                       if any(k in (h.get("kind") or "")
                              for k in ("blocked", "failed"))]
    recovered = [h for h in entries
                 if any(k in (h.get("kind") or "")
                        for k in ("released", "recovered", "reworked", "replanned"))]

    measured = bool(per_agent) and any(a.get("measured") for a in per_agent)
    return {
        "work_item": wid,
        "measured": measured,
        "why": None if measured else
               "no subagent transcript was recorded, so nothing was executed to measure",
        "agents_measured": len([a for a in per_agent if a.get("measured")]),
        "execution_divergences": len(divergences),
        "detections_recorded": len(detections),
        "human_approvals_recorded": len(approvals),
        "approvals": [{"policy_ref": a.get("policy_ref"),
                       "approver_id": a.get("approver_id"),
                       "approver_role": a.get("approver_role")}
                      for a in approvals],
        "totals": totals,
        "per_agent": per_agent,
        "rates": {
            "unnecessary_turn_rate": _rate(totals.get("unnecessary_turns", 0),
                                           totals.get("turns", 0)),
            "command_failure_rate": _rate(totals.get("failed_tool_calls", 0),
                                          totals.get("tool_calls", 0)),
            "permission_refusal_share": _rate(totals.get("permission_refusals", 0),
                                              totals.get("failed_tool_calls", 0)),
            "first_pass_acceptance_rate": _rate(len(first_pass), len(verdicted)),
            "workflow_recovery_rate": _rate(len(recovered), len(needed_recovery)),
            # Deliberately not a number. An unattended `claude -p` certification
            # has no human in it, so counting zero interventions and reporting a
            # rate of 0.0 would say the organization needed no help when what
            # happened is that no help was available. Measuring this needs a run
            # a person actually sat through.
            "human_intervention_rate": None,
        },
        "not_measured": {
            # Every rate that can come back None needs a reason here. A `None`
            # with no explanation is the same defect this file exists to avoid,
            # one level along: the reader sees a blank and supplies their own
            # story for it.
            "unnecessary_turn_rate":
                None if totals.get("turns") else
                "no transcript recorded a turn, so there is nothing to divide",
            "command_failure_rate":
                None if totals.get("tool_calls") else
                "no transcript recorded a tool call, so there is nothing to divide",
            "permission_refusal_share":
                None if totals.get("failed_tool_calls") else
                "nothing failed, so there is no share of failures to attribute",
            "human_intervention_rate":
                ("unattended run: no human was present, so zero interventions is an "
                 "artefact of the harness and not a property of the organization"
                 if not approvals else
                 "the %d human act(s) in this run were approvals the organization "
                 "requires, which is governance rather than friction; nothing was a "
                 "human repairing what an agent should have done"
                 % len(approvals)),
            "first_pass_acceptance_rate":
                None if verdicted else
                "no task reached a verdict, so there is no first pass to measure",
            "workflow_recovery_rate":
                None if needed_recovery else
                "nothing entered a state needing recovery; %d drift detection(s) "
                "were recorded -- %d execution divergence(s) and %d unattributed "
                "subagent stop(s) -- which is the designed response rather than a "
                "failure" % (len(detections), len(divergences),
                             len(detections) - len(divergences)),
        },
    }


def report(data):
    if not data.get("measured"):
        print("friction: not measured — %s" % data.get("why"))
        return 0
    t = data["totals"]
    print("work item %s — %d agent run(s) measured" % (data["work_item"], data["agents_measured"]))
    print("  turns %d · tool calls %d · failed %d (%d refused by the platform, "
          "%d agent errors)" % (t.get("turns", 0), t.get("tool_calls", 0),
                                t.get("failed_tool_calls", 0),
                                t.get("permission_refusals", 0), t.get("agent_errors", 0)))
    print("  repeated calls %d · discovery %d · documentation lookups %d · "
          "clarifications %d" % (t.get("repeated_calls", 0), t.get("discovery_calls", 0),
                                 t.get("documentation_lookups", 0),
                                 t.get("clarification_requests", 0)))
    print("  execution divergences detected and recorded: %d"
          % data.get("execution_divergences", 0))
    if data.get("human_approvals_recorded"):
        print("  human approvals recorded: %d (governance, not friction) — %s"
              % (data["human_approvals_recorded"],
                 ", ".join("%s by %s" % (a["policy_ref"], a["approver_id"])
                           for a in data.get("approvals") or [])))
    print()
    for name, value in sorted(data["rates"].items()):
        if value is None:
            why = (data["not_measured"].get(name)
                   or "no evidence, so no number")
            print("  %-28s not-measured — %s" % (name, why))
        else:
            print("  %-28s %.1f%%" % (name, value * 100))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--work-item")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = measure(os.path.abspath(args.project), args.work_item)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    return report(data)


if __name__ == "__main__":
    sys.exit(main())
