"""Event correlation and causation.

A field is decoration until something depends on it. These tests emit a real
change's worth of events through `scripts/emit_event.py` and then reconstruct
the change from the log alone - requirement, architecture, story, merge request,
QA, defect, release, incident, RCA - using nothing but `correlation_id` and
`causation_id`. If the chain cannot be walked, the fields are not doing their
job and these fail.

The reconstruction here is deliberately independent of `route_event.chain()`:
the point is that the log is walkable by anything, not that our own walker
agrees with itself.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from jsonschema_mini import validate  # noqa: E402
from route_event import route, verify_chains  # noqa: E402

EMIT = os.path.join(ROOT, "scripts", "emit_event.py")
ROUTE = os.path.join(ROOT, "scripts", "route_event.py")

# One change, end to end. The order here is the order a reviewer asked to be
# able to reconstruct, and nothing in the log records it except causation.
LIFECYCLE = [
    ("FEATURE_CREATED", "SFTP-FEAT-103", ["title=Enterprise SFTP", "requester=partner-ops"]),
    ("REQUIREMENT_APPROVED", "SFTP-REQ-001", ["requirement_count=14", "open_decisions=1"]),
    ("ARCHITECTURE_APPROVED", "SFTP-ADR-001", ["adr_count=5", "risks=2"]),
    ("STORY_CREATED", "SFTP-FEAT-103", ["story_count=14", "epics=3"]),
    ("CODE_REVIEW_COMPLETED", "SFTP-MR-88", ["verdict=pass", "findings=0"]),
    ("QA_COMPLETED", "SFTP-QA-01",
     ["verdict=conditional", "passed=40", "failed=1", "residual_risk=low"]),
    ("DEFECT_CREATED", "SFTP-DEF-421",
     ["defect_id=SFTP-DEF-421", "severity=high", "summary=session drop on key rotation"]),
    ("DEFECT_FIXED", "SFTP-DEF-421", ["defect_id=SFTP-DEF-421"]),
    ("RELEASE_APPROVED", "REL-1.4.0", ["release_id=REL-1.4.0", "approver_role=release-approver"]),
    ("DEPLOYMENT_COMPLETED", "REL-1.4.0",
     ["release_id=REL-1.4.0", "duration=4m12s", "verification=passed"]),
    ("INCIDENT_CREATED", "SFTP-INC-007",
     ["incident_id=SFTP-INC-007", "severity=1", "symptom=partner sessions timing out"]),
    ("INCIDENT_RESOLVED", "SFTP-INC-007", ["incident_id=SFTP-INC-007", "duration=41m"]),
    ("RCA_COMPLETED", "SFTP-INC-007",
     ["incident_id=SFTP-INC-007", "root_cause=key rotation drops the session", "action_count=3"]),
]

CORRELATION = "SFTP-FEAT-103"


def emit(project, etype, subject, payload, correlation=CORRELATION, **flags):
    cmd = [sys.executable, EMIT, "--type", etype, "--subject", subject,
           "--project", project, "--project-key", "SFTP", "--correlation-id", correlation]
    for key, value in flags.items():
        cmd.append("--" + key.replace("_", "-"))
        if value is not True:
            cmd.append(value)
    if payload:
        cmd += ["--payload"] + list(payload)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError("emit %s failed: %s%s" % (etype, r.stdout, r.stderr))
    return r.stdout


def read_log(project):
    log_dir = os.path.join(project, ".ai-engineering", "events")
    events = []
    for name in sorted(os.listdir(log_dir)):
        with open(os.path.join(log_dir, name), encoding="utf-8") as fh:
            events += [json.loads(line) for line in fh if line.strip()]
    return events


def walk(events, correlation_id):
    """Reconstruct one change's order from causation alone.

    Not from log order, not from `at` - `at` has one-second resolution and a
    burst of events shares a timestamp. Start at the single event with no
    causation and follow whatever names it.
    """
    thread = [e for e in events if e.get("correlation_id") == correlation_id]
    caused_by = {}
    for e in thread:
        caused_by.setdefault(e.get("causation_id"), []).append(e)

    roots = caused_by.get(None, [])
    if len(roots) != 1:
        raise AssertionError("expected exactly one starting point, found %d" % len(roots))

    order, frontier = [], list(roots)
    while frontier:
        event = frontier.pop(0)
        order.append(event)
        frontier += caused_by.get(event["id"], [])
    return order


class TestOneChangeIsReconstructable(unittest.TestCase):
    """Given FEATURE-103, the whole change can be walked out of the log."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = cls._tmp.name
        for etype, subject, payload in LIFECYCLE:
            emit(cls.project, etype, subject, payload)
        # A second, unrelated change interleaved into the same log. A thread
        # that only reconstructs when nothing else is happening is not a thread.
        emit(cls.project, "FEATURE_CREATED", "AUDIT-FEAT-200",
             ["title=Audit export", "requester=compliance"], correlation="AUDIT-FEAT-200")
        emit(cls.project, "REQUIREMENT_APPROVED", "AUDIT-REQ-001",
             ["requirement_count=3", "open_decisions=0"], correlation="AUDIT-FEAT-200")
        cls.events = read_log(cls.project)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_change_walks_out_in_the_order_it_happened(self):
        order = walk(self.events, CORRELATION)
        self.assertEqual([e["type"] for e in order], [t for t, _, _ in LIFECYCLE])

    def test_requirement_to_rca_is_one_unbroken_chain(self):
        order = walk(self.events, CORRELATION)
        by_id = {e["id"]: e for e in order}
        for previous, event in zip(order, order[1:]):
            self.assertEqual(event["causation_id"], previous["id"],
                             "%s does not name %s as its cause" % (event["type"], previous["type"]))
            self.assertIn(event["causation_id"], by_id)
        self.assertEqual(order[0]["type"], "FEATURE_CREATED")
        self.assertEqual(order[-1]["type"], "RCA_COMPLETED")

    def test_ordering_does_not_depend_on_the_timestamp(self):
        """`at` is second-resolution, so the burst shares timestamps."""
        order = walk(self.events, CORRELATION)
        stamps = [e["at"] for e in order]
        if len(set(stamps)) == len(stamps):
            self.skipTest("this run emitted slowly enough that no two events share a second; "
                          "the claim is untested rather than false")
        # Sorting by timestamp cannot recover the order; causation can.
        self.assertEqual([e["type"] for e in order], [t for t, _, _ in LIFECYCLE])

    def test_two_changes_in_one_log_do_not_mix(self):
        feature = walk(self.events, CORRELATION)
        audit = walk(self.events, "AUDIT-FEAT-200")
        self.assertEqual(len(feature), len(LIFECYCLE))
        self.assertEqual(len(audit), 2)
        self.assertFalse({e["id"] for e in feature} & {e["id"] for e in audit})
        self.assertIsNone(audit[0].get("causation_id"))

    def test_every_event_carries_what_an_audit_query_needs(self):
        for event in self.events:
            with self.subTest(event=event["type"]):
                for field in ("schema_version", "correlation_id", "actor", "actor_type",
                              "severity", "artifact", "category", "level", "project"):
                    self.assertTrue(event.get(field), "%s has no %s" % (event["type"], field))

    def test_workflow_stage_and_cycle_come_from_the_catalogue(self):
        """No emitter passed these. They are derived, so they are always there."""
        by_type = {e["type"]: e for e in self.events}
        self.assertEqual(by_type["REQUIREMENT_APPROVED"]["workflow"], "WF-FEATURE")
        self.assertEqual(by_type["REQUIREMENT_APPROVED"]["stage"], "REQ")
        self.assertEqual(by_type["DEFECT_CREATED"]["cycle"], "CYCLE-QA")
        self.assertEqual(by_type["DEFECT_CREATED"]["source"]["kind"], "department-cycle")
        self.assertNotIn("workflow", by_type["DEFECT_CREATED"])

    def test_severity_never_contradicts_the_payload(self):
        by_type = {e["type"]: e for e in self.events}
        defect = by_type["DEFECT_CREATED"]
        self.assertEqual(defect["severity"], defect["payload"]["severity"])

    def test_the_shipped_verifier_agrees_the_log_is_intact(self):
        self.assertEqual(verify_chains(self.project), 0)

    def test_the_trace_command_prints_the_whole_change(self):
        r = subprocess.run([sys.executable, ROUTE, "--trace", CORRELATION,
                            "--project", self.project],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for etype, _, _ in LIFECYCLE:
            self.assertIn(etype, r.stdout)
        self.assertNotIn("AUDIT-REQ-001", r.stdout)


class TestTheChainIsEnforced(unittest.TestCase):
    def schema(self):
        with open(os.path.join(ROOT, "schemas", "notification-event.schema.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def one_event(self, project):
        return read_log(project)[0]

    def test_an_event_without_a_correlation_id_is_invalid(self):
        with tempfile.TemporaryDirectory() as project:
            emit(project, "DEFECT_FIXED", "X-1", ["defect_id=X-1"])
            event = self.one_event(project)
            self.assertFalse(validate(event, self.schema()))
            del event["correlation_id"]
            self.assertTrue(validate(event, self.schema()),
                            "correlation_id is required, so removing it must be an error")

    def test_the_required_fields_are_actually_required(self):
        with tempfile.TemporaryDirectory() as project:
            emit(project, "DEFECT_FIXED", "X-1", ["defect_id=X-1"])
            event = self.one_event(project)
            for field in ("schema_version", "actor", "actor_type", "severity", "artifact"):
                with self.subTest(field=field):
                    broken = dict(event)
                    del broken[field]
                    self.assertTrue(validate(broken, self.schema()))

    def test_a_causation_id_that_names_nothing_is_reported(self):
        with tempfile.TemporaryDirectory() as project:
            emit(project, "FEATURE_CREATED", "X-1", ["title=X", "requester=y"])
            path = os.path.join(project, ".ai-engineering", "events",
                                os.listdir(os.path.join(project, ".ai-engineering",
                                                        "events"))[0])
            orphan = dict(read_log(project)[0])
            orphan["id"] = "EVT-20250101-000000-zzzz"
            orphan["causation_id"] = "EVT-20250101-000000-nope"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(orphan) + "\n")
            self.assertEqual(verify_chains(project), 1)

    def test_causation_that_points_forwards_is_reported(self):
        """An event cannot be caused by something the log records after it."""
        with tempfile.TemporaryDirectory() as project:
            emit(project, "FEATURE_CREATED", "X-1", ["title=X", "requester=y"])
            emit(project, "DEFECT_FIXED", "X-1", ["defect_id=X-1"])
            log_dir = os.path.join(project, ".ai-engineering", "events")
            path = os.path.join(log_dir, os.listdir(log_dir)[0])
            first, second = read_log(project)
            first["causation_id"] = second["id"]
            second.pop("causation_id", None)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(first) + "\n" + json.dumps(second) + "\n")
            self.assertEqual(verify_chains(project), 1)

    def test_an_explicit_cause_beats_the_derived_one(self):
        """A stage that knows the real cause is not overruled by log order."""
        with tempfile.TemporaryDirectory() as project:
            emit(project, "FEATURE_CREATED", "X-1", ["title=X", "requester=y"])
            root = read_log(project)[0]["id"]
            emit(project, "DEFECT_FIXED", "X-1", ["defect_id=X-1"])
            emit(project, "DEFECT_REOPENED", "X-1",
                 ["defect_id=X-1", "reason=regression"], causation_id=root)
            self.assertEqual(read_log(project)[2]["causation_id"], root)

    def test_root_forces_a_new_thread_start(self):
        with tempfile.TemporaryDirectory() as project:
            emit(project, "FEATURE_CREATED", "X-1", ["title=X", "requester=y"])
            emit(project, "DEFECT_FIXED", "X-1", ["defect_id=X-1"], root=True)
            second = read_log(project)[1]
            self.assertNotIn("causation_id", second)
            # Two starting points in one thread is exactly what the verifier
            # exists to catch.
            self.assertEqual(verify_chains(project), 1)


class TestNothingExistingBroke(unittest.TestCase):
    def catalogue(self):
        with open(os.path.join(ROOT, "notification", "event-catalogue.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)["events"]

    def test_the_routing_table_still_resolves_every_event(self):
        r = subprocess.run([sys.executable, ROUTE, "--table"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for spec in self.catalogue():
            self.assertIn(spec["type"], r.stdout)

    def test_every_emitted_event_still_routes(self):
        """Routing reads the event, and the event grew fields. It must not care."""
        with tempfile.TemporaryDirectory() as project:
            for etype, subject, payload in LIFECYCLE:
                emit(project, etype, subject, payload)
            for event in read_log(project):
                with self.subTest(event=event["type"]):
                    decision = route(event, project)
                    self.assertNotEqual(decision.get("severity"), "policy-error",
                                        decision.get("reason"))

    def test_an_event_from_before_this_model_still_routes_and_is_tolerated(self):
        """Logs written by an older version are still valid history."""
        legacy = {"id": "EVT-20250101-000000-aaaa", "type": "DEFECT_CREATED",
                  "at": "2025-01-01T00:00:00Z", "project": "SFTP",
                  "source": {"kind": "workflow-stage"}, "level": "team",
                  "subject": "SFTP-DEF-1", "correlation_id": "SFTP-FEAT-103",
                  "payload": {"severity": "high"}}
        decision = route(legacy)
        self.assertTrue(decision["send"])
        with tempfile.TemporaryDirectory() as project:
            log_dir = os.path.join(project, ".ai-engineering", "events")
            os.makedirs(log_dir)
            with open(os.path.join(log_dir, "2025-01.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps(legacy) + "\n")
            self.assertEqual(verify_chains(project), 0)
            self.assertEqual(verify_chains(project, strict=True), 1)


if __name__ == "__main__":
    unittest.main()
