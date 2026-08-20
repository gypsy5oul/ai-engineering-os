"""Time-based liveness: what happens when nothing happens.

Every state machine here answers "what may happen next". None answers "what if
nothing does". A workflow can be perfectly correct and stall forever, so these
tests are about the one failure the state machines cannot see.

The false-positive cases matter as much as the detections. A staleness report
that fires on work in progress is one people learn to ignore, and then it is
worse than not having it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADER = """---
id: {id}
type: {type}
title: {title}
status: {status}
owner: development-lead
version: 1
created_at: '2026-08-01'
updated_at: '{updated}'
source: agent
links: {{}}
{extra}---
"""


class Project:
    def __init__(self, case):
        self.dir = tempfile.mkdtemp(prefix="aieos-live-")
        case.addCleanup(__import__("shutil").rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, "docs"), exist_ok=True)

    def add(self, aid, atype, status, updated, extra="", title="An item"):
        path = os.path.join(self.dir, "docs", aid + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(HEADER.format(id=aid, type=atype, title=title, status=status,
                                   updated=updated, extra=extra))
        return self

    def check(self, now="2026-08-20T12:00:00"):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "check_liveness.py"),
             "--project", self.dir, "--now", now, "--json"],
            capture_output=True, text=True, timeout=120)
        return json.loads(proc.stdout)["findings"], proc.returncode


class TestStaleDetection(unittest.TestCase):
    def test_a_review_nobody_picked_up_is_reported(self):
        findings, code = Project(self).add(
            "ACME-STORY-001", "story", "in-review", "2026-08-19T09:00:00").check()
        self.assertEqual(code, 1)
        self.assertEqual(findings[0]["id"], "ACME-STORY-001")
        self.assertEqual(findings[0]["kind"], "artifact_status")

    def test_the_ladder_escalates_with_age(self):
        """A review stuck one working day is the lead's. Stuck a day longer it is not."""
        near, _ = Project(self).add("A-STORY-001", "story", "in-review",
                                    "2026-08-20T02:00:00").check()
        far, _ = Project(self).add("A-STORY-002", "story", "in-review",
                                   "2026-08-19T09:00:00").check()
        self.assertEqual(near[0]["notify"], "lead")
        self.assertEqual(far[0]["notify"], "head")

    def test_a_stalled_cycle_state_is_reported(self):
        rollup = ("rollup:\n  cycle: CYCLE-DEV\n  status: IN_PROGRESS\n"
                  "  produced_by: development-lead\n  at: '2026-08-18'\n")
        findings, _ = Project(self).add("A-STORY-003", "story", "done",
                                        "2026-08-18T09:00:00", extra=rollup).check()
        states = [f for f in findings if f["kind"] == "cycle_state"]
        self.assertTrue(states, "a cycle sitting in IN_PROGRESS for two days went unreported")
        self.assertEqual(states[0]["cycle"], "CYCLE-DEV")

    def test_a_blocking_decision_is_measured_on_a_shorter_clock(self):
        """Work is stopped behind it, which is different from a question that can wait.

        At the same age both are reported; what differs is how far up the ladder
        each has travelled. The blocking one has already reached a human.
        """
        blocking, _ = Project(self).add("A-DEC-001", "open-decision", "open",
                                        "2026-08-18T12:00:00", extra="blocking: true\n").check()
        ordinary, _ = Project(self).add("A-DEC-002", "open-decision", "open",
                                        "2026-08-18T12:00:00").check()
        self.assertEqual(blocking[0]["notify"], "human_owner")
        self.assertEqual(ordinary[0]["notify"], "lead")
        self.assertLess(blocking[0]["threshold"], blocking[0]["stated_threshold"],
                        "the reported threshold must be the one that actually applied")

    def test_a_young_blocking_decision_is_still_quiet(self):
        findings, _ = Project(self).add("A-DEC-003", "open-decision", "open",
                                        "2026-08-20T06:00:00", extra="blocking: true\n").check()
        self.assertEqual(findings, [], "fired at 6h; even halved the first threshold is 12h")

    def test_an_unanswered_escalation_reaches_a_human(self):
        rollup = ("rollup:\n  cycle: CYCLE-DEV\n  status: ESCALATED\n"
                  "  produced_by: development-lead\n  at: '2026-08-17'\n")
        findings, _ = Project(self).add("A-STORY-004", "story", "done",
                                        "2026-08-17T09:00:00", extra=rollup).check()
        cyc = [f for f in findings if f["kind"] == "cycle_state"]
        self.assertEqual(cyc[0]["notify"], "human_owner")


class TestNoFalsePositives(unittest.TestCase):
    """A report that fires on healthy work is one people stop reading."""

    def test_work_that_just_moved_is_not_stale(self):
        findings, code = Project(self).add(
            "A-STORY-010", "story", "in-review", "2026-08-20T11:00:00").check()
        self.assertEqual(findings, [])
        self.assertEqual(code, 0)

    def test_finished_work_is_never_stale(self):
        rollup = ("rollup:\n  cycle: CYCLE-DEV\n  status: ACCEPTED\n"
                  "  produced_by: development-lead\n  at: '2026-06-01'\n")
        findings, _ = Project(self).add("A-STORY-011", "story", "done",
                                        "2026-06-01T09:00:00", extra=rollup).check()
        self.assertEqual(findings, [], "an accepted item from months ago was reported as stuck")

    def test_a_resolved_decision_is_not_chased(self):
        findings, _ = Project(self).add("A-DEC-010", "open-decision", "resolved",
                                        "2026-06-01T09:00:00").check()
        self.assertEqual(findings, [])

    def test_an_empty_project_is_quiet(self):
        findings, code = Project(self).check()
        self.assertEqual((findings, code), ([], 0))


class TestLivenessIsHonestAboutItself(unittest.TestCase):
    def test_it_does_not_claim_to_be_a_scheduler(self):
        """Claude Code has no persistent background process this plugin can rely on.
        A watchdog that does not watch is worse than none."""
        with open(os.path.join(ROOT, "policies", "sla-policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        self.assertIn("not_a_scheduler",
                      {"not_a_scheduler": True} if "what_this_is_not" in policy else {})
        self.assertIn("Not a scheduler", policy["what_this_is_not"])

    def test_every_threshold_names_who_to_tell(self):
        with open(os.path.join(ROOT, "policies", "sla-policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        ladder = {s["step"] for s in policy["ladder"]}
        groups = [policy["open_decision"]]
        groups += list(policy["artifact_status"].values())
        groups += list(policy["cycle_state"].values())
        for steps in groups:
            for step in steps:
                with self.subTest(step=step):
                    self.assertIn(step["notify"], ladder)
                    self.assertGreater(step["after_hours"], 0)
