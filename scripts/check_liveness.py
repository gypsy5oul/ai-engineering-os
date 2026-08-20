#!/usr/bin/env python3
"""What is stuck? Reports work that has sat in one state past its threshold.

Every state machine in this repository answers "what may happen next". None of
them answers "what if nothing happens". A workflow can be perfectly correct and
still stall forever: a review nobody picks up, an escalation nobody answers, a
decision nobody makes. Correctness does not imply progress.

**This is not a scheduler.** Claude Code has no persistent background process this
plugin can rely on, so nothing here fires by itself. It answers the question when
it is run -- from a session, from CI, or from whatever timer the project already
has. A watchdog that does not watch would be worse than none, so it does not claim
to be one.

    python3 scripts/check_liveness.py --project .
    python3 scripts/check_liveness.py --project . --emit     # write events
    python3 scripts/check_liveness.py --project . --json

Exit codes: 0 nothing stale, 1 something is stale, 2 could not run.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from frontmatter import read as read_fm   # noqa: E402
from minyaml import parse_file            # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def project_config(project):
    for name in ("project.json", "project.yaml"):
        path = os.path.join(project, ".ai-engineering", name)
        if not os.path.exists(path):
            continue
        if name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return parse_file(path)
    return {}


def parse_when(value):
    """An artifact timestamp, as an aware or naive datetime, or None."""
    if not value:
        return None
    text = str(value).strip().strip("'\"")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text[:len(fmt) + 2].rstrip("Z"), fmt)
        except ValueError:
            continue
    return None


def artifacts(project):
    out = []
    for dirpath, dirnames, files in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                fm, _ = read_fm(os.path.join(dirpath, name))
            except Exception:
                continue
            if isinstance(fm, dict) and fm.get("id") and fm.get("type"):
                fm["_path"] = os.path.relpath(os.path.join(dirpath, name), project)
                out.append(fm)
    return out


def thresholds_for(policy, kind, key):
    table = policy.get(kind) or {}
    return table.get(key) or []


def breach(steps, hours, multiplier=1.0):
    """The most severe threshold this age has passed, or None."""
    passed = [s for s in steps if hours >= s["after_hours"] * multiplier]
    return max(passed, key=lambda s: s["after_hours"]) if passed else None


def scan(project, now, policy):
    findings = []
    cfg = project_config(project)
    overrides = cfg.get("sla") if isinstance(cfg, dict) else None
    if isinstance(overrides, dict):
        merged = dict(policy)
        merged.update(overrides)
        policy = merged
    blocking_mult = policy.get("blocking_decision_multiplier", 0.5)

    for a in artifacts(project):
        when = parse_when(a.get("updated_at"))
        if when is None:
            continue
        hours = (now - when).total_seconds() / 3600.0

        # A decision that is blocking work is measured on a shorter clock.
        if a.get("type") == "open-decision" and str(a.get("status")) not in ("resolved", "closed"):
            is_blocking = bool(a.get("blocking"))
            mult = blocking_mult if is_blocking else 1.0
            hit = breach(policy.get("open_decision") or [], hours, mult)
            if hit:
                # Report the threshold that actually applied. A blocking decision
                # fires at half the stated hours, and printing the stated number
                # would look like the checker had misfired.
                findings.append({"id": a["id"], "path": a["_path"], "kind": "open_decision",
                                 "state": str(a.get("status")), "hours": round(hours, 1),
                                 "threshold": round(hit["after_hours"] * mult, 1),
                                 "stated_threshold": hit["after_hours"],
                                 "notify": hit["notify"], "blocking": is_blocking,
                                 "event": "DECISION_STALE"})
            continue

        hit = breach(thresholds_for(policy, "artifact_status", str(a.get("status"))), hours)
        if hit:
            findings.append({"id": a["id"], "path": a["_path"], "kind": "artifact_status",
                             "state": str(a.get("status")), "hours": round(hours, 1),
                             "threshold": hit["after_hours"], "notify": hit["notify"],
                             "event": "WORK_STALE"})

        rollup = a.get("rollup")
        if isinstance(rollup, dict):
            state = str(rollup.get("status"))
            hit = breach(thresholds_for(policy, "cycle_state", state), hours)
            if hit:
                findings.append({"id": a["id"], "path": a["_path"], "kind": "cycle_state",
                                 "state": state, "cycle": rollup.get("cycle"),
                                 "hours": round(hours, 1), "threshold": hit["after_hours"],
                                 "notify": hit["notify"], "event": "WORK_STALE"})
    findings.sort(key=lambda f: -f["hours"])
    return findings


def emit(project, finding):
    # emit_event takes --payload as a single list. Repeating the flag would keep
    # only the last pair, which silently drops most of the finding.
    payload = ["hours=%s" % finding["hours"],
               "threshold=%s" % finding["threshold"],
               "notify=%s" % finding["notify"]]
    if finding["event"] == "WORK_STALE":
        payload.append("state=%s" % finding["state"])
    else:
        payload.append("blocking=%s" % str(finding.get("blocking", False)).lower())
    args = [sys.executable, os.path.join(ROOT, "scripts", "emit_event.py"),
            "--type", finding["event"], "--subject", finding["id"], "--project", project,
            "--payload"] + payload
    return subprocess.run(args, capture_output=True, text=True).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--emit", action="store_true", help="write an event for each finding")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", help="override the clock, as YYYY-MM-DDTHH:MM:SS (for tests)")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("ERROR no such project: %s" % project)
        return 2
    now = parse_when(args.now) or datetime.datetime.now()
    policy = load("policies/sla-policy.json")
    findings = scan(project, now, policy)

    if args.json:
        print(json.dumps({"at": now.isoformat(), "findings": findings}, indent=2))
    elif not findings:
        print("Nothing is stale. Every item has moved inside its threshold.")
    else:
        print("%-22s %-18s %-8s %-11s %s" % ("ITEM", "STATE", "AGE", "THRESHOLD", "TELL"))
        for f in findings:
            note = " (blocking)" if f.get("blocking") else ""
            print("%-22s %-18s %6.1fh %8.1fh%-2s %s"
                  % (f["id"], f["state"], f["hours"], f["threshold"], note and "*", f["notify"]))
        if any(f.get("blocking") for f in findings):
            print("\n* a blocking decision is measured on half the stated threshold: work is "
                  "stopped behind it.")
        print("\n%d item(s) past a threshold. Nothing here failed; nothing happened, which is "
              "the one thing a state machine cannot notice by itself." % len(findings))

    if args.emit:
        sent = sum(1 for f in findings if emit(project, f))
        print("emitted %d/%d event(s)" % (sent, len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
