#!/usr/bin/env python3
"""Emit one SDLC event into the project's append-only event log.

The event log is the source the notification subsystem and the digests read. It
is append-only for the same reason an incident record is: an event stream that
can be rewritten cannot reconstruct what happened.

  python3 scripts/emit_event.py --type DEFECT_CREATED --subject SFTP-DEF-421 \
      --project . --payload severity=high defect_id=SFTP-DEF-421
"""
import argparse
import json
import os
import random
import string
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from jsonschema_mini import validate  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def new_id(now):
    tail = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return "EVT-%s-%s" % (now.strftime("%Y%m%d-%H%M%S"), tail)


def build(args, now):
    cat = {e["type"]: e for e in load("notification/event-catalogue.json")["events"]}
    spec = cat.get(args.type)
    if spec is None:
        raise SystemExit("ERROR unknown event type %r. Add it to notification/event-catalogue.json "
                         "first; an event nothing declares cannot be routed." % args.type)

    payload = {}
    for item in args.payload or []:
        if "=" not in item:
            raise SystemExit("ERROR payload item %r is not key=value" % item)
        k, v = item.split("=", 1)
        payload[k] = v

    missing = [f for f in spec["payload_fields"] if f not in payload]

    source = {"kind": args.source_kind}
    for k in ("workflow", "stage", "cycle", "agent"):
        v = getattr(args, k)
        if v:
            source[k] = v

    event = {
        "id": new_id(now),
        "type": args.type,
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": args.project_key or os.path.basename(os.path.abspath(args.project)),
        "source": source,
        "level": args.level or spec["level"],
        "subject": args.subject,
        "category": spec["category"],
        "actor_type": args.actor_type,
        "correlation_id": args.correlation_id or args.subject,
        "severity": args.severity or spec.get("default_severity", "normal"),
    }
    if spec.get("default_status") or args.status:
        event["status"] = args.status or spec["default_status"]
    if args.actor:
        event["actor"] = args.actor
    if args.artifact:
        event["artifact"] = args.artifact
    if args.stage:
        event["stage"] = args.stage
    if args.cycle:
        event["cycle"] = args.cycle
    if args.correlates:
        event["correlates"] = args.correlates
    if payload:
        event["payload"] = payload
    return event, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--project", default=".")
    ap.add_argument("--project-key")
    ap.add_argument("--level")
    ap.add_argument("--source-kind", default="workflow-stage",
                    choices=["workflow-stage", "department-cycle", "gitlab", "guard", "human", "schedule"])
    ap.add_argument("--workflow")
    ap.add_argument("--stage")
    ap.add_argument("--cycle")
    ap.add_argument("--agent")
    ap.add_argument("--correlates", nargs="*")
    ap.add_argument("--correlation-id", help="Ties every event about one change together. "
                                             "Defaults to the subject.")
    ap.add_argument("--actor")
    ap.add_argument("--actor-type", default="agent", choices=["agent", "human", "system"])
    ap.add_argument("--severity", choices=["info", "low", "normal", "high", "critical"])
    ap.add_argument("--status", choices=["started", "in-progress", "passed", "failed", "blocked",
                                         "approved", "rejected", "completed", "escalated"])
    ap.add_argument("--artifact")
    ap.add_argument("--payload", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.utcnow()
    event, missing = build(args, now)

    errors = validate(event, load("schemas/notification-event.schema.json"))
    if errors:
        for e in errors:
            print("ERROR %s" % e)
        return 1
    if missing:
        print("WARN  payload is missing declared field(s): %s" % ", ".join(missing))

    if args.dry_run:
        print(json.dumps(event, indent=2))
        return 0

    log_dir = os.path.join(args.project, ".ai-engineering", "events")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, now.strftime("%Y-%m") + ".jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    print("%s  %s  %s  -> %s" % (event["id"], event["type"], event["subject"],
                                 os.path.relpath(path, args.project)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
