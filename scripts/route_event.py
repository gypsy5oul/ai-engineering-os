#!/usr/bin/env python3
"""The notification policy engine. Deterministic, and deliberately not a model.

Answers, for one event: should anyone be notified, who, on which channel, in
which thread, how urgently, and with which template. The notification agent
receives that decision and turns it into a readable message. It cannot change
the decision, and it cannot decide that nothing is sent.

It also answers the audit question the routing decision cannot: what happened to
one change, in what order, and what caused what.

  echo '<event json>' | python3 scripts/route_event.py
  python3 scripts/route_event.py --event-file e.json --project /path/to/project
  python3 scripts/route_event.py --explain FEATURE_CREATED
  python3 scripts/route_event.py --trace SFTP-FEAT-103 --project /path/to/project
  python3 scripts/route_event.py --verify-chains --project /path/to/project
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
    decision = {"event_id": event.get("id"), "event": event.get("type"),
                "subject": event.get("subject")}
    try:
        pol, cat, chans = policy(), catalogue(), channels()
    except Exception as exc:
        # A routing configuration that cannot be read is a refusal, not a crash
        # and never a send. The traceback was technically loud, but a stack trace
        # is not a decision anyone can act on, and a caller that ignores exit
        # codes would have seen nothing at all.
        decision.update({"send": False, "severity": "policy-error",
                         "reason": "notification configuration is unreadable: %s" % exc})
        return decision

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

    # The thread key groups messages in the space. "subject" threads one
    # artifact; "correlation" threads one change, which is the wider grouping
    # the event log itself uses. Neither is derived from the other: an event's
    # correlation_id can differ from its subject, and a policy has to say which
    # grouping the space is for.
    thread = rule.get("thread", pol["defaults"]["thread_strategy"])
    if thread == "correlation":
        thread_key = event.get("correlation_id") or event.get("subject")
    elif thread == "subject":
        thread_key = event.get("subject")
    else:
        thread_key = None

    decision.update(
        send=True,
        mode=rule["notify"],
        priority=rule["priority"],
        channels=[{"name": c, "webhook_env": chans[c]["webhook_env"]} for c in targets],
        recipients=rule.get("recipients", []),
        thread_key=thread_key,
        correlation_id=event.get("correlation_id"),
        causation_id=event.get("causation_id"),
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


# ------------------------------------------------------------------ tracing
#
# correlation_id gathers one change's events into a set. causation_id orders
# them. Both are needed: `at` has one-second resolution, so several events in
# the same second are indistinguishable by time, and a set with no order cannot
# answer "what caused this".

CHAIN_REQUIRED = ("correlation_id", "actor", "actor_type", "severity", "artifact",
                  "schema_version")


def read_log(project):
    """Every event recorded for a project, in the order the log was written."""
    log_dir = os.path.join(project or ".", ".ai-engineering", "events")
    if not os.path.isdir(log_dir):
        return []
    out = []
    for name in sorted(os.listdir(log_dir)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def chain(events):
    """Order one correlation thread by causation, and report where it breaks.

    Returns (ordered, problems). `ordered` is the thread walked from its root
    through causation_id, deepest-first for each branch. `problems` lists every
    reason the walk could not account for an event.
    """
    order = {e["id"]: i for i, e in enumerate(events) if e.get("id")}
    by_id = {e["id"]: e for e in events if e.get("id")}
    children, roots, problems = {}, [], []

    for e in events:
        eid = e.get("id")
        if eid is None:
            problems.append("an event in this thread has no id")
            continue
        cause = e.get("causation_id")
        if cause is None:
            roots.append(eid)
            continue
        if cause not in by_id:
            problems.append("%s (%s) is caused by %s, which is not in this thread"
                            % (eid, e["type"], cause))
            roots.append(eid)
            continue
        if order[cause] >= order[eid]:
            problems.append("%s (%s) is caused by %s, which the log records after it"
                            % (eid, e["type"], cause))
        children.setdefault(cause, []).append(eid)

    if len(roots) > 1:
        problems.append("the thread has %d starting points (%s); every event after the first "
                        "should name what caused it" % (len(roots), ", ".join(sorted(roots))))
    if events and not roots:
        problems.append("the thread has no starting point: causation is circular")

    ordered, seen = [], set()
    stack = list(reversed(sorted(roots, key=lambda i: order[i])))
    while stack:
        eid = stack.pop()
        if eid in seen:
            continue
        seen.add(eid)
        ordered.append(by_id[eid])
        stack += list(reversed(sorted(children.get(eid, []), key=lambda i: order[i])))

    for e in events:
        if e.get("id") and e["id"] not in seen:
            problems.append("%s (%s) is not reachable from the start of the thread"
                            % (e["id"], e["type"]))
            ordered.append(e)
    return ordered, problems


def threads(project):
    """The project's event log grouped by correlation_id, in first-seen order."""
    grouped = {}
    for e in read_log(project):
        grouped.setdefault(e.get("correlation_id") or "(uncorrelated)", []).append(e)
    return grouped


def trace(correlation_id, project):
    events = threads(project).get(correlation_id, [])
    if not events:
        print("no events recorded for correlation id %r in %s"
              % (correlation_id, os.path.join(project or ".", ".ai-engineering", "events")))
        return 2

    ordered, problems = chain(events)
    position = {e["id"]: i for i, e in enumerate(ordered, 1) if e.get("id")}

    print("%s  ·  %d events  ·  %s .. %s"
          % (correlation_id, len(events), ordered[0].get("at", "?"), ordered[-1].get("at", "?")))
    print("%-4s %-8s %-24s %-22s %-22s %-22s %s"
          % ("#", "CAUSE", "EVENT", "SUBJECT", "WHERE", "ACTOR", "STATUS"))
    for i, e in enumerate(ordered, 1):
        where = e.get("workflow") or e.get("cycle") or e.get("source", {}).get("kind", "-")
        if e.get("stage"):
            where += "/" + e["stage"]
        cause = e.get("causation_id")
        if cause is None:
            ref = "start"
        elif cause in position:
            ref = "#%d" % position[cause]
        else:
            ref = "?%s" % cause[-4:]
        print("%-4d %-8s %-24s %-22s %-22s %-22s %s"
              % (i, ref, e.get("type", "?")[:24], (e.get("subject") or "-")[:22], where[:22],
                 (e.get("actor") or "-")[:22],
                 "%s/%s" % (e.get("status", "-"), e.get("severity", "-"))))

    legacy = [e for e in events if e.get("schema_version") is None]
    if legacy:
        print("\n%d event(s) predate the correlated event model (no schema_version) and carry no "
              "causation. They are listed in log order, not causal order." % len(legacy))
    if problems:
        print("\nBROKEN")
        for p in problems:
            print("  · %s" % p)
        return 1
    return 0


def verify_chains(project, strict=False):
    """Every thread in the log must be one walkable chain. Non-zero if not."""
    grouped = threads(project)
    if not grouped:
        print("no events recorded in %s"
              % os.path.join(project or ".", ".ai-engineering", "events"))
        return 0

    failures = 0
    for correlation_id in sorted(grouped):
        events = grouped[correlation_id]
        current = [e for e in events if e.get("schema_version") is not None]
        legacy = len(events) - len(current)

        problems = []
        for e in current:
            missing = [f for f in CHAIN_REQUIRED if not e.get(f)]
            if missing:
                problems.append("%s (%s) is missing %s"
                                % (e.get("id", "?"), e.get("type", "?"), ", ".join(missing)))
        if correlation_id == "(uncorrelated)" and current:
            problems.append("%d event(s) carry no correlation_id and belong to no change"
                            % len(current))
        _, walk_problems = chain(current)
        problems += walk_problems
        if legacy and strict:
            problems.append("%d event(s) predate the correlated event model" % legacy)

        status = "BROKEN" if problems else "ok"
        note = "" if not legacy else "  (%d legacy)" % legacy
        print("%-8s %-30s %3d events%s" % (status, correlation_id[:30], len(events), note))
        for p in problems:
            print("         · %s" % p)
        failures += 1 if problems else 0

    print("\n%d thread(s), %d broken" % (len(grouped), failures))
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-file")
    ap.add_argument("--project")
    ap.add_argument("--explain")
    ap.add_argument("--table", action="store_true", help="print the whole routing table")
    ap.add_argument("--trace", metavar="CORRELATION_ID",
                    help="walk one change's events in causal order")
    ap.add_argument("--verify-chains", action="store_true",
                    help="check every correlation thread in the log is one walkable chain")
    ap.add_argument("--strict", action="store_true",
                    help="with --verify-chains, also fail on events that predate the model")
    args = ap.parse_args()

    if args.trace:
        return trace(args.trace, args.project)

    if args.verify_chains:
        return verify_chains(args.project, args.strict)

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
    decision = route(event, args.project)
    print(json.dumps(decision, indent=2))
    return 1 if decision.get("severity") == "policy-error" else 0


if __name__ == "__main__":
    sys.exit(main())
