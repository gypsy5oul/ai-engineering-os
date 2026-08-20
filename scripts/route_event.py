#!/usr/bin/env python3
"""The notification policy engine. Deterministic, and deliberately not a model.

Answers, for one event: should anyone be notified, who, on which channel, in
which thread, how urgently, and with which template. The notification agent
receives that decision and turns it into a readable message. It cannot change
the decision, and it cannot decide that nothing is sent.

  echo '<event json>' | python3 scripts/route_event.py
  python3 scripts/route_event.py --event-file e.json --project /path/to/project
  python3 scripts/route_event.py --explain FEATURE_CREATED
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def catalogue():
    return {e["type"]: e for e in load("notification/event-catalogue.json")["events"]}


def policy():
    return load("notification/notification-policy.json")


def channels():
    return load("notification/channels.json")["channels"]


def _matches(rule, event):
    """A rule's optional `when` narrows it by payload fields."""
    for field, allowed in (rule.get("when") or {}).items():
        value = (event.get("payload") or {}).get(field)
        if value not in allowed:
            return False
    return True


def _recent_events(project, minutes):
    """Events already recorded inside the suppression window."""
    if not project:
        return []
    log_dir = os.path.join(project, ".ai-engineering", "events")
    if not os.path.isdir(log_dir):
        return []
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    out = []
    for name in sorted(os.listdir(log_dir))[-2:]:
        try:
            with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        e = json.loads(line)
                        when = datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        continue
                    if when >= cutoff:
                        out.append(e)
        except OSError:
            continue
    return out


def _key(event, fields):
    parts = []
    for f in fields:
        if f.startswith("payload."):
            parts.append(str((event.get("payload") or {}).get(f.split(".", 1)[1])))
        else:
            parts.append(str(event.get(f)))
    return "|".join(parts)


def route(event, project=None):
    pol, cat, chans = policy(), catalogue(), channels()
    decision = {"event_id": event.get("id"), "event": event.get("type"),
                "subject": event.get("subject")}

    spec = cat.get(event["type"])
    if spec is None:
        decision.update(send=False, reason="unknown event type; not in the catalogue",
                        severity="policy-error")
        return decision

    level = event.get("level") or spec["level"]
    decision["level"] = level

    # A rule may narrow by payload; the first matching rule wins, so the
    # narrowest rule for an event type must be listed first.
    rule = next((r for r in pol["rules"] if r["event"] == event["type"] and _matches(r, event)), None)
    if rule is None:
        level_default = pol["levels"].get(level, {})
        rule = {"event": event["type"], "notify": level_default.get("notify", "never"),
                "channel": pol["defaults"]["channel"], "priority": "low",
                "thread": pol["defaults"]["thread_strategy"]}
        decision["rule_source"] = "level default (%s)" % level
    else:
        decision["rule_source"] = "explicit rule"

    if rule["notify"] == "never":
        decision.update(send=False,
                        reason="%s events are recorded, not notified: %s"
                               % (level, pol["levels"].get(level, {}).get("rationale", "")))
        return decision

    # Duplicate suppression.
    window = pol["suppression"]["duplicate_window_minutes"]
    key_fields = pol["suppression"]["identical_event_key"]
    if project:
        this_key = _key(event, key_fields)
        for prior in _recent_events(project, window):
            if prior.get("id") == event.get("id"):
                continue
            if _key(prior, key_fields) == this_key:
                decision.update(send=False,
                                reason="duplicate of %s inside the %d minute window"
                                       % (prior.get("id"), window))
                return decision

    targets = [rule["channel"]] + list(rule.get("also_channels") or [])
    unknown = [c for c in targets if c not in chans]
    if unknown:
        decision.update(send=False, severity="policy-error",
                        reason="unknown channel(s) %s" % unknown)
        return decision

    thread = rule.get("thread", pol["defaults"]["thread_strategy"])
    decision.update(
        send=True,
        mode=rule["notify"],
        priority=rule["priority"],
        channels=[{"name": c, "webhook_env": chans[c]["webhook_env"]} for c in targets],
        recipients=rule.get("recipients", []),
        thread_key=event.get("subject") if thread == "subject" else None,
        template=rule.get("template"),
        suppress_if=rule.get("suppress_if"),
        aggregate_window_minutes=(pol["defaults"]["aggregate_window_minutes"]
                                  if rule["notify"] == "aggregate" else 0),
    )
    if rule["notify"] == "aggregate":
        decision["note"] = ("Hold and combine with other events for this subject. Emit when the "
                            "aggregate state has meaningfully changed: " +
                            "; ".join(pol["suppression"]["aggregation"]["meaningful_change"]))
    return decision


def explain(event_type):
    pol, cat = policy(), catalogue()
    spec = cat.get(event_type)
    if spec is None:
        print("unknown event type. known: %s" % ", ".join(sorted(cat)))
        return 2
    print("%s\n  level      %s\n  emitted by %s\n  meaning    %s\n  payload    %s"
          % (event_type, spec["level"], spec["emitted_by"], spec["meaning"],
             ", ".join(spec["payload_fields"])))
    rules = [r for r in pol["rules"] if r["event"] == event_type]
    if not rules:
        d = pol["levels"].get(spec["level"], {})
        print("  routing    level default: %s (%s)" % (d.get("notify"), d.get("rationale")))
        return 0
    for r in rules:
        print("  routing    %s -> %s%s  priority=%s%s"
              % (r["notify"], r["channel"],
                 " (+%s)" % ",".join(r["also_channels"]) if r.get("also_channels") else "",
                 r["priority"],
                 "  when %s" % r["when"] if r.get("when") else ""))
        if r.get("recipients"):
            print("             recipients: %s" % ", ".join(r["recipients"]))
        if r.get("suppress_if"):
            print("             suppress if: %s" % r["suppress_if"])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-file")
    ap.add_argument("--project")
    ap.add_argument("--explain")
    ap.add_argument("--table", action="store_true", help="print the whole routing table")
    args = ap.parse_args()

    if args.explain:
        return explain(args.explain)

    if args.table:
        pol, cat = policy(), catalogue()
        print("%-30s %-13s %-10s %-26s %s" % ("EVENT", "LEVEL", "NOTIFY", "CHANNEL", "PRIORITY"))
        for e in load("notification/event-catalogue.json")["events"]:
            rs = [r for r in pol["rules"] if r["event"] == e["type"]] or [None]
            for r in rs:
                if r is None:
                    d = pol["levels"][e["level"]]
                    print("%-30s %-13s %-10s %-26s %s" % (e["type"], e["level"], d["notify"], "-", "-"))
                else:
                    ch = r["channel"] + ("+%d" % len(r["also_channels"]) if r.get("also_channels") else "")
                    print("%-30s %-13s %-10s %-26s %s" % (e["type"], e["level"], r["notify"], ch, r["priority"]))
        return 0

    raw = open(args.event_file, encoding="utf-8").read() if args.event_file else sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"send": False, "severity": "policy-error",
                          "reason": "unparseable event: %s" % exc}))
        return 1
    print(json.dumps(route(event, args.project), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
