#!/usr/bin/env python3
"""Emit one SDLC event into the project's append-only event log.

The event log is the source the notification subsystem and the digests read. It
is append-only for the same reason an incident record is: an event stream that
can be rewritten cannot reconstruct what happened.

Two fields make the log traceable rather than merely searchable:

  correlation_id  every event about one change carries the same value, so the
                  whole change is one query. It is required, and it defaults to
                  the subject - correct for the event that opens a thread, wrong
                  for everything downstream, so pass it explicitly.
  causation_id    the id of the event that caused this one. Set explicitly with
                  --causation-id, otherwise derived as the most recent event
                  already recorded under the same correlation_id. That is what
                  turns a set of events into an ordered chain that can be walked
                  backwards from any point.

Everything else the catalogue already knows - workflow, stage, cycle, the
implied source kind - is derived from the event's `emitted_by`, so an emitter
that passes nothing still produces a fully attributed event.

  python3 scripts/emit_event.py --type DEFECT_CREATED --subject SFTP-DEF-421 \
      --project . --correlation-id SFTP-FEAT-103 \
      --payload severity=high defect_id=SFTP-DEF-421

  python3 scripts/route_event.py --trace SFTP-FEAT-103 --project .
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

SCHEMA_VERSION = "2"

SEVERITIES = ("info", "low", "normal", "high", "critical")


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def new_id(now):
    tail = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return "EVT-%s-%s" % (now.strftime("%Y%m%d-%H%M%S"), tail)


def origin(spec):
    """What the catalogue already knows about where this event comes from.

    `emitted_by` is one of `WF-<id>/<STAGE>`, `CYCLE-<id>`, `guard` or
    `liveness`. Denormalising it onto the event means workflow, stage and cycle
    are populated on every event without every emitter having to remember them,
    and an emitter that does know better still overrides it.
    """
    emitted_by = spec.get("emitted_by", "")
    if "/" in emitted_by:
        workflow, stage = emitted_by.split("/", 1)
        return {"kind": "workflow-stage", "workflow": workflow, "stage": stage}
    if emitted_by.startswith("CYCLE-"):
        return {"kind": "department-cycle", "cycle": emitted_by}
    if emitted_by == "guard":
        return {"kind": "guard"}
    if emitted_by == "liveness":
        return {"kind": "schedule"}
    return {"kind": "workflow-stage"}


def log_path(project, now):
    return os.path.join(project, ".ai-engineering", "events",
                        now.strftime("%Y-%m") + ".jsonl")


def read_log(project):
    """Every event recorded for this project, in the order it was written."""
    log_dir = os.path.join(project, ".ai-engineering", "events")
    if not os.path.isdir(log_dir):
        return []
    out = []
    for name in sorted(os.listdir(log_dir)):
        if not name.endswith(".jsonl"):
            continue
        try:
            with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            continue
    return out


def last_in_thread(project, correlation_id):
    """The most recent event already recorded under this correlation_id.

    Log order, not timestamp order: `at` has one-second resolution, so several
    events in the same second are indistinguishable by time. The log is
    append-only, so its order is the order things happened.
    """
    prior = None
    for event in read_log(project):
        if event.get("correlation_id") == correlation_id and event.get("id"):
            prior = event
    return prior


def build(args, now, prior=None):
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
    implied = origin(spec)

    workflow = args.workflow or implied.get("workflow")
    stage = args.stage or implied.get("stage")
    cycle = args.cycle or implied.get("cycle")

    source = {"kind": args.source_kind or implied["kind"]}
    for key, value in (("workflow", workflow), ("stage", stage), ("cycle", cycle),
                       ("agent", args.agent)):
        if value:
            source[key] = value

    # An event's own severity. A declared payload severity is the same fact
    # stated once already, so it wins over the catalogue default rather than
    # contradicting it; an explicit --severity wins over both.
    severity = args.severity
    if not severity and payload.get("severity") in SEVERITIES:
        severity = payload["severity"]
    if not severity:
        severity = spec.get("default_severity", "normal")

    # Who caused it. An emitter that knows the role passes it; one that does not
    # falls back to the emitting stage or cycle, which is real attribution at
    # stage granularity rather than an empty field.
    actor = args.actor or args.agent or spec.get("emitted_by") or "unknown"
    actor_type = args.actor_type
    if actor_type is None:
        actor_type = "system" if source["kind"] in ("guard", "schedule") else "agent"

    event = {
        "schema_version": SCHEMA_VERSION,
        "id": new_id(now),
        "type": args.type,
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": args.project_key or os.path.basename(os.path.abspath(args.project)),
        "source": source,
        "level": args.level or spec["level"],
        "subject": args.subject,
        "category": spec["category"],
        "actor": actor,
        "actor_type": actor_type,
        "severity": severity,
        "artifact": args.artifact or args.subject,
        "correlation_id": args.correlation_id or args.subject,
    }

    causation_id = args.causation_id
    if causation_id is None and not args.root and prior is not None:
        causation_id = prior.get("id")
    if causation_id:
        event["causation_id"] = causation_id

    if spec.get("default_status") or args.status:
        event["status"] = args.status or spec["default_status"]
    if workflow:
        event["workflow"] = workflow
    if stage:
        event["stage"] = stage
    if cycle:
        event["cycle"] = cycle
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
    ap.add_argument("--source-kind",
                    choices=["workflow-stage", "department-cycle", "gitlab", "guard", "human",
                             "schedule"],
                    help="Defaults to the kind implied by the catalogue's emitted_by.")
    ap.add_argument("--workflow")
    ap.add_argument("--stage")
    ap.add_argument("--cycle")
    ap.add_argument("--agent")
    ap.add_argument("--correlates", nargs="*")
    ap.add_argument("--correlation-id", help="Ties every event about one change together. "
                                             "Defaults to the subject, which is only right for "
                                             "the event that opens the thread.")
    ap.add_argument("--causation-id", help="The event that caused this one. Defaults to the most "
                                           "recent event already recorded under the same "
                                           "correlation id.")
    ap.add_argument("--root", action="store_true",
                    help="This event opens its correlation thread: record no causation_id even "
                         "if earlier events share the correlation id.")
    ap.add_argument("--actor", help="The agent or human role that caused it. Defaults to --agent, "
                                    "then to the emitting stage or cycle.")
    ap.add_argument("--actor-type", choices=["agent", "human", "system"],
                    help="Defaults to 'system' for guard- and schedule-sourced events, "
                         "'agent' otherwise.")
    ap.add_argument("--severity", choices=list(SEVERITIES))
    ap.add_argument("--status", choices=["started", "in-progress", "passed", "failed", "blocked",
                                         "approved", "rejected", "completed", "escalated"])
    ap.add_argument("--artifact")
    ap.add_argument("--payload", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.utcnow()
    correlation_id = args.correlation_id or args.subject
    prior = last_in_thread(args.project, correlation_id)
    event, missing = build(args, now, prior)

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

    path = log_path(args.project, now)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    print("%s  %s  %s  corr=%s  caused-by=%s  -> %s"
          % (event["id"], event["type"], event["subject"], event["correlation_id"],
             event.get("causation_id", "(root)"), os.path.relpath(path, args.project)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
