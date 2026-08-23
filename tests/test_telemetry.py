"""What the organization can say about itself.

The tests that matter here are the ones about honesty. A metric computed from the
wrong source flatters, and a flattering metric is worse than no metric: it gets
quoted in decisions.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))


def cl(project, sub, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), sub,
         "--project", project] + list(args), capture_output=True, text=True, timeout=120)


def telemetry(project):
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "telemetry.py"),
         "--project", project, "--json"], capture_output=True, text=True, timeout=120)
    return json.loads(proc.stdout)


class Measured(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-tele-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        with open(os.path.join(ROOT, "templates", "project", "project.yaml")) as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w") as fh:
            fh.write(cfg)

    def item(self, wtype="feature", risk="MEDIUM", intent="A change that needs doing properly"):
        out = cl(self.project, "open", "--type", wtype, "--risk", risk, "--intent", intent)
        wid = out.stdout.split()[0]
        cl(self.project, "plan", "--item", wid)
        return wid


class TestRewordSurvivesAReplan(Measured):
    """The trap this fell into once: computing rework from the current graph.

    A replan rebuilds the graph and resets attempts to zero, so a change that
    fought hard and was then replanned reported as having gone smoothly. That is
    flattering and exactly backwards, and it is why the history is append-only.
    """

    def test_rework_before_a_replan_is_still_counted(self):
        wid = self.item()
        cl(self.project, "observe", "--item", wid, "--task", "T-002", "--outcome", "failed",
           "--failure-class", "test_failure", "--signature", "X-1", "--detail", "first")
        before = telemetry(self.project)["derived"]["rework_rate"]
        self.assertGreater(before, 0)
        cl(self.project, "replan", "--item", wid, "--reason", "the plan was wrong")
        after = telemetry(self.project)["derived"]["rework_rate"]
        self.assertGreater(after, 0,
                           "a replan erased the record that this change ever struggled")

    def test_the_denominator_is_work_attempted_not_work_planned(self):
        """A graph of forty tasks with three attempted is not a 7% rework rate."""
        wid = self.item()
        cl(self.project, "observe", "--item", wid, "--task", "T-001", "--outcome", "accepted")
        cl(self.project, "observe", "--item", wid, "--task", "T-002", "--outcome", "failed",
           "--signature", "X-1", "--detail", "no")
        t = telemetry(self.project)
        self.assertEqual(t["counts"]["tasks_observed"], 2)
        self.assertLess(t["counts"]["tasks_observed"], t["counts"]["tasks"])
        self.assertAlmostEqual(t["derived"]["rework_rate"], 0.5)


class TestHumanIntervention(Measured):
    def test_a_replan_counts_as_intervention(self):
        """The plan a human accepted turned out to be wrong."""
        wid = self.item()
        base = telemetry(self.project)["counts"]["replans"]
        cl(self.project, "replan", "--item", wid, "--reason", "the design assumed telemetry we lack")
        self.assertEqual(telemetry(self.project)["counts"]["replans"], base + 1)

    def test_running_out_of_plans_reaches_a_human(self):
        wid = self.item()
        for reason in ("one", "two", "three"):
            cl(self.project, "replan", "--item", wid, "--reason", reason)
        self.assertGreater(telemetry(self.project)["counts"]["human_escalations"], 0,
                           "a refused replan is the organization saying it is out of ideas")

    def test_the_rate_is_per_work_item(self):
        for _ in range(2):
            self.item()
        t = telemetry(self.project)
        self.assertEqual(t["counts"]["work_items"], 2)
        self.assertIsNotNone(t["derived"]["human_intervention_rate"])

    def test_an_agent_verdict_is_not_a_human_intervention(self):
        """The organization reviewing itself is not a person being interrupted."""
        wid = self.item()
        cl(self.project, "observe", "--item", wid, "--task", "T-001", "--outcome", "accepted")
        self.assertEqual(telemetry(self.project)["counts"]["approvals"], 0)


class TestHonesty(Measured):
    def test_what_cannot_be_computed_is_named_rather_than_estimated(self):
        self.item()
        t = telemetry(self.project)
        self.assertIn("token_cost", t["not_measured"])
        for name, why in t["not_measured"].items():
            with self.subTest(metric=name):
                self.assertGreater(len(why), 30,
                                   "%s is listed unmeasured with no reason" % name)

    def test_no_unmeasured_metric_appears_in_the_derived_numbers(self):
        """Reporting an estimate for something the record cannot support teaches
        people not to trust the rest of the numbers."""
        self.item()
        t = telemetry(self.project)
        for name in t["not_measured"]:
            with self.subTest(metric=name):
                self.assertNotIn(name, t["derived"])

    def test_an_empty_project_says_so_rather_than_reporting_zeros(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "telemetry.py"),
             "--project", self.project], capture_output=True, text=True, timeout=120)
        self.assertIn("Nothing to measure yet", proc.stdout)

    def test_rates_are_none_rather_than_zero_when_there_is_no_denominator(self):
        """0% and "we have not seen one yet" are different claims."""
        self.item()
        d = telemetry(self.project)["derived"]
        self.assertIsNone(d["escalation_rate"])
        self.assertIsNone(d["median_cycle_time_hours"])
