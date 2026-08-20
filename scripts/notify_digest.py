#!/usr/bin/env python3
"""Build a daily or weekly digest from the project's event log.

Counts are computed from the log, never recalled by a model. The notification
agent turns this structure into prose using notification/templates/; it does not
decide what the numbers are.

  python3 scripts/notify_digest.py --project . --period daily
  python3 scripts/notify_digest.py --project . --period weekly --json
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_log(project, since):
    log_dir = os.path.join(project, ".ai-engineering", "events")
    if not os.path.isdir(log_dir):
        return []
    out = []
    for name in sorted(os.listdir(log_dir)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                    when = datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    continue
                if when >= since:
                    e["_at"] = when
                    out.append(e)
    return out


def threads(events):
    """How many distinct changes the period covers, and which moved most.

    A count of events answers "how busy was it". A count of correlation threads
    answers "how many changes were in flight", which is the number a lead is
    actually asking for. Events with no correlation_id are counted separately
    rather than folded in: they are a defect in the emitter, not a change.
    """
    by_thread = defaultdict(list)
    uncorrelated = 0
    for e in events:
        cid = e.get("correlation_id")
        if not cid:
            uncorrelated += 1
            continue
        by_thread[cid].append(e)

    busiest = sorted(((cid, es) for cid, es in by_thread.items()),
                     key=lambda pair: (-len(pair[1]), pair[0]))[:5]
    return {
        "count": len(by_thread),
        "uncorrelated_events": uncorrelated,
        "busiest": [{"correlation_id": cid,
                     "events": len(es),
                     "last": max(e["at"] for e in es),
                     "starting_points": sum(1 for e in es
                                            if e.get("schema_version")
                                            and not e.get("causation_id"))}
                    for cid, es in busiest],
    }


def digest(events, period):
    by_type = Counter(e["type"] for e in events)
    subjects = defaultdict(set)
    for e in events:
        subjects[e["type"]].add(e["subject"])

    def n(*types):
        return sum(by_type.get(t, 0) for t in types)

    def subj(*types):
        s = set()
        for t in types:
            s |= subjects.get(t, set())
        return sorted(s)

    blockers = []
    for e in events:
        if e["type"] == "DECISION_OPENED":
            p = e.get("payload") or {}
            age = (datetime.utcnow() - e["_at"]).days
            blockers.append({"id": p.get("decision_id", e["subject"]),
                             "what": p.get("question", "(no question recorded)"),
                             "owner": p.get("owner", "unassigned"),
                             "age_days": age,
                             "blocks": p.get("blocks", "")})
        elif e["type"] == "TASK_BLOCKED":
            p = e.get("payload") or {}
            blockers.append({"id": e["subject"], "what": p.get("reason", ""),
                             "owner": p.get("blocked_by", "unassigned"),
                             "age_days": (datetime.utcnow() - e["_at"]).days, "blocks": ""})

    resolved = {e["subject"] for e in events if e["type"] == "DECISION_RESOLVED"}
    blockers = [b for b in blockers if b["id"] not in resolved]

    d = {
        "period": period,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events_considered": len(events),
        "features": {"created": n("FEATURE_CREATED"),
                     "requirements_approved": n("REQUIREMENT_APPROVED"),
                     "architecture_approved": n("ARCHITECTURE_APPROVED"),
                     "awaiting_architecture": len(subj("ARCHITECTURE_STARTED")) - n("ARCHITECTURE_APPROVED"),
                     "active_subjects": subj("FEATURE_CREATED", "DEVELOPMENT_ROLLUP")},
        "development": {"started": n("DEVELOPMENT_STARTED"),
                        "completed": n("DEVELOPMENT_COMPLETED"),
                        "rollups": n("DEVELOPMENT_ROLLUP"),
                        "blocked": n("TASK_BLOCKED"),
                        "escalations": n("ESCALATED"),
                        "changes_requested": n("CHANGES_REQUESTED")},
        "qa": {"plans_approved": n("QA_PLAN_APPROVED"),
               "completed": n("QA_COMPLETED"),
               "defects_created": n("DEFECT_CREATED"),
               "defects_fixed": n("DEFECT_FIXED"),
               "defects_reopened": n("DEFECT_REOPENED"),
               "ci_failures": n("CI_FAILED")},
        "security": {"findings": n("SECURITY_FINDING"),
                     "blocked": n("SECURITY_BLOCKED"),
                     "exceptions_granted": n("SECURITY_EXCEPTION_GRANTED"),
                     "advisories": n("DEPENDENCY_ADVISORY")},
        "release": {"planned": n("RELEASE_PLANNED"), "approved": n("RELEASE_APPROVED"),
                    "authorized": n("DEPLOYMENT_AUTHORIZED"),
                    "deployed": n("DEPLOYMENT_COMPLETED"),
                    "failed": n("DEPLOYMENT_FAILED")},
        "incidents": {"created": n("INCIDENT_CREATED"), "mitigated": n("INCIDENT_MITIGATED"),
                      "resolved": n("INCIDENT_RESOLVED"), "rcas": n("RCA_COMPLETED"),
                      "active": n("INCIDENT_CREATED") - n("INCIDENT_RESOLVED")},
        "blockers": sorted(blockers, key=lambda b: -b["age_days"]),
        "threads": threads(events),
    }

    if period == "weekly":
        created, fixed = n("DEFECT_CREATED"), n("DEFECT_FIXED")
        d["trends"] = []
        if n("DEFECT_REOPENED") and fixed:
            rate = n("DEFECT_REOPENED") / float(fixed)
            if rate > 0.15:
                d["trends"].append("Reopen rate %.0f%%: fixes are being accepted that should not be."
                                   % (rate * 100))
        if d["development"]["changes_requested"] > 3 * max(d["development"]["completed"], 1):
            d["trends"].append("Rework is high relative to completion. The acceptance criteria or "
                               "the design is likely the problem, not the implementation.")
        stale = [b for b in d["blockers"] if b["age_days"] >= 7]
        if stale:
            d["trends"].append("%d blocker(s) open a week or more: %s. Somebody is working around "
                               "them instead of closing them."
                               % (len(stale), ", ".join(b["id"] for b in stale)))
        if d["incidents"]["created"] and not d["incidents"]["rcas"]:
            d["trends"].append("Incidents occurred with no RCA published.")
        if d["threads"]["uncorrelated_events"]:
            d["trends"].append("%d event(s) carry no correlation_id and belong to no change. "
                               "Those are invisible to a trace and to an audit."
                               % d["threads"]["uncorrelated_events"])
        split = [t for t in d["threads"]["busiest"] if t["starting_points"] > 1]
        if split:
            d["trends"].append("%s has more than one starting point: something emitted an event "
                               "without naming what caused it, so the chain cannot be walked "
                               "end to end. Check with route_event.py --verify-chains."
                               % ", ".join(t["correlation_id"] for t in split))
        if not d["trends"]:
            d["trends"].append("Nothing anomalous in the shape of the week.")
    return d


def render(d):
    lines = []
    title = "Daily" if d["period"] == "daily" else "Weekly"
    lines.append("Engineering %s Summary  ·  %s" % (title, d["generated_at"][:10]))
    lines.append("")
    f, dev, qa, sec, rel, inc = (d["features"], d["development"], d["qa"], d["security"],
                                 d["release"], d["incidents"])
    lines.append("🚀 FEATURES     %d created · %d requirements approved · %d architecture approved"
                 % (f["created"], f["requirements_approved"], f["architecture_approved"]))
    lines.append("💻 DEVELOPMENT  %d started · %d completed · %d blocked · %d escalations"
                 % (dev["started"], dev["completed"], dev["blocked"], dev["escalations"]))
    lines.append("🧪 QA           %d defects created · %d fixed · %d reopened · %d CI failures"
                 % (qa["defects_created"], qa["defects_fixed"], qa["defects_reopened"],
                    qa["ci_failures"]))
    lines.append("🔐 SECURITY     %d findings · %d blocking · %d exceptions granted"
                 % (sec["findings"], sec["blocked"], sec["exceptions_granted"]))
    lines.append("🚢 RELEASE      %d approved · %d authorized · %d deployed · %d failed"
                 % (rel["approved"], rel["authorized"], rel["deployed"], rel["failed"]))
    lines.append("🚨 INCIDENTS    %s"
                 % ("No active incidents" if inc["active"] <= 0
                    else "%d active · %d resolved · %d RCAs" % (inc["active"], inc["resolved"], inc["rcas"])))
    th = d["threads"]
    lines.append("🧵 CHANGES      %d in flight%s%s"
                 % (th["count"],
                    "" if not th["busiest"] else "  ·  busiest: " +
                    ", ".join("%s (%d)" % (t["correlation_id"], t["events"])
                              for t in th["busiest"][:3]),
                    "" if not th["uncorrelated_events"]
                    else "  ·  %d event(s) with no correlation_id" % th["uncorrelated_events"]))
    lines.append("")
    lines.append("⛔ BLOCKERS")
    if not d["blockers"]:
        lines.append("   None.")
    for b in d["blockers"][:8]:
        age = "%dd" % b["age_days"] if b["age_days"] else "today"
        lines.append("   %-12s %-46s %-18s %s" % (b["id"], b["what"][:46], b["owner"], age))
    if d.get("trends"):
        lines.append("")
        lines.append("TRENDS WORTH WATCHING")
        for t in d["trends"]:
            lines.append("   · %s" % t)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--period", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    days = 1 if args.period == "daily" else 7
    events = read_log(args.project, datetime.utcnow() - timedelta(days=days))
    d = digest(events, args.period)
    print(json.dumps(d, indent=2) if args.json else render(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
