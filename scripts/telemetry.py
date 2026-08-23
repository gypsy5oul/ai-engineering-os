#!/usr/bin/env python3
"""What the organization can say about itself, from the record it already keeps.

The question this exists to answer is whether working this way is better than the
alternative. Architecture does not answer that; a trend does.

Everything here is derived from the work items on disk. Nothing is instrumented
specially, because a measurement needing its own bookkeeping is one that stops
being kept the first busy week.

    telemetry.py --project .
    telemetry.py --project . --json
    telemetry.py --project . --item ACME-FEAT-001

The section that matters most is the last one. A metric that cannot be computed
from the durable record is listed as unmeasured with the reason, never estimated:
an organization that reports a number it cannot derive teaches its own people not
to trust the rest of them.
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402


def policy():
    with open(os.path.join(ROOT, "policies", "telemetry-policy.json"), encoding="utf-8") as fh:
        return json.load(fh)


def parse_when(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def collect(project, only=None):
    items = W.list_items(project)
    if only:
        items = [i for i in items if i["id"] == only]

    m = {
        "work_items": len(items), "accepted": 0, "in_progress": 0, "escalated": 0,
        "cancelled": 0, "tasks": 0, "tasks_accepted": 0, "tasks_escalated": 0,
        "tasks_reworked": 0, "attempts_total": 0, "replans": 0, "replans_refused": 0,
        "decisions": 0, "decisions_escalated": 0, "repeated_failures": 0,
        "subagent_stops": 0, "thin_results": 0, "unattributed_results": 0,
        "tasks_observed": 0,
        "completions_blocked": 0, "completions_allowed": 0,
        "approvals": 0, "human_escalations": 0, "open_decisions": 0,
        "cycle_times_hours": [], "per_item": [],
    }

    for item in items:
        m[{"accepted": "accepted", "in-progress": "in_progress", "escalated": "escalated",
           "cancelled": "cancelled"}.get(item.get("status"), "in_progress")] += 1
        m["replans"] += int(item.get("replans") or 0)
        m["approvals"] += len(item.get("approvals") or [])
        m["open_decisions"] += len(item.get("decisions") or [])

        if item.get("status") == "accepted":
            a, b = parse_when(item.get("created_at")), parse_when(item.get("updated_at"))
            if a and b and b >= a:
                m["cycle_times_hours"].append((b - a).total_seconds() / 3600.0)

        graph = W.load_graph(project, item["id"])
        item_tasks = (graph or {}).get("tasks", [])
        m["tasks"] += len(item_tasks)
        for t in item_tasks:
            if t["state"] == "accepted":
                m["tasks_accepted"] += 1
            if t["state"] == "escalated":
                m["tasks_escalated"] += 1

        # Rework comes from the history, not from the graph. A replan rebuilds the
        # graph and resets attempts to zero, so a change that fought hard and was
        # then replanned would report as having gone smoothly -- flattering, and
        # exactly backwards. The append-only history is what survives a replan,
        # which is the reason it is append-only.
        seen, failed = set(), set()
        for h in W.history(project, item["id"]):
            kind = h.get("kind")
            if kind == "observed":
                key = (item["id"], h.get("task"))
                seen.add(key)
                if h.get("outcome") in ("failed", "rejected"):
                    failed.add(key)
                    m["attempts_total"] += 1
        m["tasks_reworked"] += len(failed)
        m["tasks_observed"] = m.get("tasks_observed", 0) + len(seen)

        for h in W.history(project, item["id"]):
            kind = h.get("kind")
            if kind == "decided":
                m["decisions"] += 1
                if h.get("action") == "escalate":
                    m["decisions_escalated"] += 1
                    if "same failure" in (h.get("why") or ""):
                        m["repeated_failures"] += 1
            elif kind == "escalated":
                # Only an escalation that reaches outside the organization is a
                # human intervention. One that stops at the lead is the ladder
                # working.
                if (h.get("to") or "").startswith("human"):
                    m["human_escalations"] += 1
            elif kind == "replan_refused":
                m["replans_refused"] += 1
                # A refused replan is the organization telling a human it is out of
                # ideas, which is an intervention whether or not one happens.
                m["human_escalations"] += 1
            elif kind == "subagent_stopped":
                m["subagent_stops"] += 1
                if h.get("thin_result"):
                    m["thin_results"] += 1
            elif kind == "subagent_stopped_unattributed":
                m["unattributed_results"] += 1
            elif kind == "task_completion_blocked":
                m["completions_blocked"] += 1
            elif kind == "task_completion_allowed":
                m["completions_allowed"] += 1

        m["per_item"].append({"id": item["id"], "status": item.get("status"),
                              "tasks": len(item_tasks), "replans": item.get("replans", 0)})
    return m


def rate(numerator, denominator):
    return None if not denominator else numerator / float(denominator)


def derive(m):
    """The numbers worth reading, and the human intervention rate."""
    # Two of the four terms this used to sum -- approvals and open_decisions --
    # are read off work-item fields that nothing writes, so they were structurally
    # zero and made the rate look better the more it was trusted. They are named
    # in `not_measured` now rather than silently added.
    interventions = m["human_escalations"] + m["replans"]
    return {
        # Denominator is tasks anyone actually worked, not tasks planned. A graph
        # of forty tasks with three attempted is not a 7% rework rate.
        "rework_rate": rate(m["tasks_reworked"], m["tasks_observed"]),
        "escalation_rate": rate(m["decisions_escalated"], m["decisions"]),
        "repeated_failure_rate": rate(m["repeated_failures"], m["decisions_escalated"]),
        "thin_result_rate": rate(m["thin_results"], m["subagent_stops"]),
        "attempts_per_task": rate(m["attempts_total"], m["tasks_observed"]),
        "replans_per_work_item": rate(m["replans"], m["work_items"]),
        "completion_block_rate": rate(m["completions_blocked"],
                                      m["completions_blocked"] + m["completions_allowed"]),
        "median_cycle_time_hours": (sorted(m["cycle_times_hours"])[len(m["cycle_times_hours"]) // 2]
                                    if m["cycle_times_hours"] else None),
        "human_interventions": interventions,
        "human_intervention_rate": rate(interventions, m["work_items"]),
    }


def pct(value):
    return "  n/a" if value is None else "%5.0f%%" % (value * 100)


def num(value, fmt="%5.1f"):
    return "  n/a" if value is None else fmt % value


def report(m, d, pol):
    print("WORK")
    print("  %d work item(s): %d accepted, %d in progress, %d escalated, %d cancelled"
          % (m["work_items"], m["accepted"], m["in_progress"], m["escalated"], m["cancelled"]))
    print("  %d task(s), %d accepted" % (m["tasks"], m["tasks_accepted"]))
    print("  median cycle time      %s h" % num(d["median_cycle_time_hours"]))
    print()
    print("QUALITY")
    print("  rework rate            %s   of the %d task(s) anyone actually worked"
          % (pct(d["rework_rate"]), m["tasks_observed"]))
    print("  attempts per task      %s" % num(d["attempts_per_task"], "%5.2f"))
    print("  escalation rate        %s   of decisions" % pct(d["escalation_rate"]))
    print("  repeated failure       %s   of escalations were the same failure twice"
          % pct(d["repeated_failure_rate"]))
    print("  thin results           %s   agents that stopped saying nothing useful"
          % pct(d["thin_result_rate"]))
    if m["unattributed_results"]:
        print("  unattributed           %5d   results that resolved to no task"
              % m["unattributed_results"])
    print()
    print("ENFORCEMENT")
    print("  completions blocked    %s   by a failing definition of done"
          % pct(d["completion_block_rate"]))
    print()
    print("HUMAN INTERVENTION")
    print("  %s per work item" % num(d["human_intervention_rate"], "%5.2f"))
    print("    reached a human      %5d   an escalation the ladder could not absorb"
          % m["human_escalations"])
    print("    replans              %5d   the plan a human accepted was wrong" % m["replans"])
    print("  The goal is not zero. A system that never asks has either solved engineering")
    print("  or stopped noticing when it should ask, and the second is far more likely.")
    print()
    print("NOT MEASURED")
    for name, why in (pol.get("not_measured") or {}).items():
        print("  %-22s %s" % (name, why[:88]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--item")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    m = collect(project, args.item)
    if not m["work_items"]:
        print("No work items under %s. Nothing to measure yet."
              % os.path.join(project, W.WORK_DIR))
        return 0
    d = derive(m)
    if args.json:
        print(json.dumps({"counts": m, "derived": d,
                          "not_measured": policy().get("not_measured", {})}, indent=2))
    else:
        report(m, d, policy())
    return 0


if __name__ == "__main__":
    sys.exit(main())
