"""How much organization a task gets, and the two ways that can go wrong.

The department cycle is correct and it is not free. Every task walked all of it,
so a two-predicate intake step with no reviewer, no gate and no artifact paid for
a peer review and a lead review.

Intensity selects a path through the cycle that already exists. The two failure
modes are opposite and both are here: a level that quietly removes independent
review from work that needs it, and a level nothing can ever reach, which is
ceremony about ceremony. The first run of the resolver had the second — every one
of a feature's fifteen tasks came out at STANDARD or above.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import resolve_intensity as I  # noqa: E402
import workitem as W  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def task(**over):
    """A task nothing objects to: LOW, routine, no reviewer, no gate, no artifact."""
    t = {"id": "T-001", "title": "t", "role": "backend-developer", "state": "queued",
         "risk": "LOW", "complexity": "routine", "stage": "IDEA",
         "definition_of_done": ["config_valid()"]}
    t.update(over)
    return t


class TestEveryLevelIsReachable(unittest.TestCase):
    """A level nothing can reach is not a level."""

    def test_micro_is_reachable(self):
        level, why = I.resolve(task())
        self.assertEqual(level, "MICRO", why)

    def test_standard_is_reachable(self):
        level, _ = I.resolve(task(risk="MEDIUM"))
        self.assertEqual(level, "STANDARD")

    def test_complex_is_reachable(self):
        level, _ = I.resolve(task(risk="HIGH"))
        self.assertEqual(level, "COMPLEX")

    def test_critical_is_reachable(self):
        level, _ = I.resolve(task(risk="CRITICAL"))
        self.assertEqual(level, "CRITICAL")

    def test_a_real_feature_graph_reaches_more_than_one_level(self):
        """Measured against the shipped workflow, not against a fixture. A model
        that puts every task at the same level has not reduced anything."""
        levels = {u["intensity"] for u in planned_feature()}
        self.assertGreater(len(levels), 1, "every task resolved to the same level")
        self.assertIn("MICRO", levels)


def planned_feature():
    project = tempfile.mkdtemp(prefix="aieos-int-")
    try:
        os.makedirs(os.path.join(project, ".ai-engineering"))
        with open(os.path.join(ROOT, "templates", "project", "project.yaml"),
                  encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for sub, extra in (("open", ["--type", "feature", "--intent", "measure intensity"]),
                           ("plan", ["--item", "SFTP-FEAT-001"])):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                            sub, "--project", project] + extra,
                           capture_output=True, timeout=120)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "resolve_intensity.py"),
             "--project", project, "--item", "SFTP-FEAT-001", "--all", "--json"],
            capture_output=True, text=True, timeout=120)
        return json.loads(proc.stdout)
    finally:
        shutil.rmtree(project, True)


class TestItNeverWeakensIndependentReview(unittest.TestCase):
    """The failure mode that matters. Every one of these is a task the organization
    has already said it wants a second pair of eyes on."""

    def test_a_task_needing_a_verdict_cannot_be_micro(self):
        """The mechanical one: a path where nobody produces a verdict cannot satisfy
        a predicate that demands one, so the checker refuses it whatever the policy
        says."""
        level, _ = I.resolve(task(definition_of_done=["agent_verdict(code-reviewer, pass)"]))
        self.assertNotEqual(level, "MICRO")

    def test_a_task_with_a_named_reviewer_cannot_be_micro(self):
        level, _ = I.resolve(task(reviewer="code-reviewer"))
        self.assertNotEqual(level, "MICRO")

    def test_a_task_needing_a_human_approval_is_at_least_complex(self):
        level, _ = I.resolve(task(definition_of_done=["human_approval_recorded(AP-02)"]))
        self.assertEqual(level, "COMPLEX")

    def test_a_coupled_surface_is_at_least_complex(self):
        """The review that matters is the one that sees the consumers."""
        level, why = I.resolve(task(coupled_surface="api-contract"))
        self.assertEqual(level, "COMPLEX")
        self.assertIn("api-contract", why)

    def test_critical_risk_always_wins(self):
        """Whatever else is true, including a declaration to the contrary."""
        for over in ({}, {"complexity": "routine"}, {"intensity": "MICRO"},
                     {"definition_of_done": []}):
            over = dict(over, risk="CRITICAL")
            with self.subTest(over=over):
                self.assertEqual(I.resolve(task(**over))[0], "CRITICAL")

    def test_an_irreversible_stage_is_critical(self):
        for stage in ("DEPLOY", "AUTHORIZE", "EXECUTE", "RELEASE"):
            with self.subTest(stage=stage):
                self.assertEqual(I.resolve(task(stage=stage))[0], "CRITICAL")

    def test_declaring_a_lower_level_does_not_lower_it(self):
        """A model choosing how much review its own work gets is the failure this
        would otherwise introduce."""
        level, _ = I.resolve(task(intensity="MICRO", risk="HIGH"))
        self.assertEqual(level, "COMPLEX")

    def test_a_heavy_change_type_is_at_least_complex(self):
        for wtype in ("incident", "release", "migration"):
            with self.subTest(type=wtype):
                level, _ = I.resolve(task(), item={"type": wtype})
                self.assertEqual(level, "COMPLEX")


class TestMicroIsNarrow(unittest.TestCase):
    """Each of these on its own is enough to take a task out of MICRO. The test is a
    conjunction of negatives because a positive test for triviality would be a
    judgement, and this has to be something the graph can answer."""

    DISQUALIFIERS = [
        {"risk": "MEDIUM"},
        {"complexity": "complex"},
        {"complexity": "novel"},
        {"reviewer": "code-reviewer"},
        {"coupled_surface": "database-schema"},
        {"produces": ["REQ"]},
        {"definition_of_done": ["agent_verdict(qa-lead, pass)"]},
        {"definition_of_done": ["human_approval_recorded(AP-12)"]},
        {"definition_of_done": ["a()", "b()", "c()", "d()", "e()", "f()", "g()"]},
    ]

    def test_each_disqualifier_alone_removes_micro(self):
        self.assertEqual(I.resolve(task())[0], "MICRO", "the baseline must be MICRO")
        for over in self.DISQUALIFIERS:
            with self.subTest(over=over):
                level, why = I.resolve(task(**over))
                self.assertNotEqual(level, "MICRO", why)

    def test_producing_an_artifact_another_stage_consumes_removes_micro(self):
        ok, why = I.qualifies_for_micro(task(produces=["ARCH"]))
        self.assertFalse(ok)
        self.assertIn("consumes", why)

    def test_the_reason_is_always_specific(self):
        """A refusal that does not say what disqualified it gets argued with."""
        for over in self.DISQUALIFIERS:
            with self.subTest(over=over):
                _level, why = I.resolve(task(**over))
                self.assertGreater(len(why), 20, why)
                self.assertNotEqual(why, "no signal raised it above STANDARD")


class TestItChangesWhoLooksNeverWhatIsSatisfied(unittest.TestCase):
    def setUp(self):
        self.policy = load("policies/workflow-intensity.json")

    def test_no_level_declares_a_different_definition_of_done(self):
        """Stated as an invariant, and true of the levels themselves. A level that
        could name its own predicates would be deciding what the work has to
        satisfy, which is the one thing intensity must never touch."""
        invariants = " ".join(self.policy["invariants"])
        self.assertIn("No level removes a definition-of-done predicate", invariants)
        for name, level in self.policy["levels"].items():
            with self.subTest(level=name):
                self.assertNotIn("definition_of_done", level)
                self.assertNotIn("acceptance", level)

    def test_only_the_two_review_states_are_skippable(self):
        cycle = load("policies/department-cycle.json")["intensity"]
        self.assertEqual(set(cycle["skippable"]), {"PEER_REVIEW", "LEAD_REVIEW"})
        for state in ("SELF_VALIDATION", "ACCEPTANCE_REQUESTED", "ACCEPTED"):
            self.assertIn(state, cycle["never_skippable"])

    def test_every_level_path_ends_in_acceptance(self):
        for name, level in self.policy["levels"].items():
            with self.subTest(level=name):
                self.assertEqual(level["path"][-1], "ACCEPTED")
                self.assertIn("SELF_VALIDATION", level["path"])

    def test_a_level_skips_exactly_what_its_path_omits(self):
        full = set(self.policy["levels"]["COMPLEX"]["path"])
        for name, level in self.policy["levels"].items():
            with self.subTest(level=name):
                self.assertEqual(set(level.get("skips") or []),
                                 full - set(level["path"]))

    def test_the_cycle_acceptance_conditions_are_untouched_by_intensity(self):
        """The honest resolution of 'do not weaken independent review': intensity
        reduces per-task ceremony, and the department's own output still gets an
        independent verdict before the cycle is accepted."""
        import glob
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        reviewed = 0
        for path in sorted(glob.glob(os.path.join(ROOT, "sdlc", "cycles", "*.yaml"))):
            cycle = parse_file(path)
            conditions = " ".join((cycle.get("acceptance") or {}).get("conditions") or [])
            self.assertNotIn("intensity", conditions,
                             "%s makes its acceptance depend on intensity" % cycle["id"])
            if "agent_verdict" in conditions:
                reviewed += 1
        self.assertGreater(reviewed, 0,
                           "no cycle requires an independent verdict at acceptance, so nothing "
                           "compensates for a skipped per-task review")


class TestOrderingIsTotal(unittest.TestCase):
    def test_the_levels_are_ordered_and_the_order_is_shared(self):
        policy = load("policies/workflow-intensity.json")
        self.assertEqual(policy["order"], I.ORDER)
        self.assertEqual(set(policy["levels"]), set(I.ORDER))

    def test_the_default_is_standard(self):
        """MICRO by default makes every unconsidered task unreviewed; COMPLEX by
        default pays for a lead on work nobody has to integrate."""
        self.assertEqual(load("policies/workflow-intensity.json")["default"], "STANDARD")
        self.assertEqual(I.resolve(task(risk="MEDIUM"))[0], "STANDARD")

    def test_raising_is_monotonic(self):
        for i, low in enumerate(I.ORDER):
            for high in I.ORDER[i:]:
                self.assertEqual(I._raise_to(low, high, "r", []), high)
                self.assertEqual(I._raise_to(high, low, "r", []), high)


class TestItIsRecordedNotAssumed(unittest.TestCase):
    def test_the_resolution_is_written_onto_the_task_with_its_reason(self):
        t = task(risk="HIGH")
        level, why = I.record(t)
        self.assertEqual(t["intensity"]["resolved"], level)
        self.assertEqual(t["intensity"]["resolution_reason"], why)
        self.assertTrue(t["intensity"]["resolved_at"])

    def test_the_declaration_survives_the_resolution(self):
        """So a level the organization chose and a level the facts forced stay
        distinguishable, the same way declared and resolved execution do."""
        t = task(intensity="MICRO", risk="HIGH")
        I.record(t)
        self.assertEqual(t["intensity"]["declared"], "MICRO")
        self.assertEqual(t["intensity"]["resolved"], "COMPLEX")

    def test_planning_resolves_every_task(self):
        for unit in planned_feature():
            with self.subTest(task=unit["task"]):
                self.assertIn(unit["intensity"], I.ORDER)

    def test_the_graph_records_it_after_plan(self):
        project = tempfile.mkdtemp(prefix="aieos-int-")
        self.addCleanup(shutil.rmtree, project, True)
        os.makedirs(os.path.join(project, ".ai-engineering"))
        with open(os.path.join(ROOT, "templates", "project", "project.yaml"),
                  encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for sub, extra in (("open", ["--type", "feature", "--intent", "record intensity"]),
                           ("plan", ["--item", "SFTP-FEAT-001"])):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                            sub, "--project", project] + extra,
                           capture_output=True, timeout=120)
        graph = W.load_graph(project, "SFTP-FEAT-001")
        for t in graph["tasks"]:
            with self.subTest(task=t["id"]):
                self.assertIn("intensity", t, "plan did not resolve %s" % t["id"])
                self.assertIn(t["intensity"]["resolved"], I.ORDER)


class TestItSaysWhatItCannotDo(unittest.TestCase):
    def test_the_policy_admits_the_proxies_it_uses(self):
        policy = load("policies/workflow-intensity.json")
        blob = " ".join(policy["not_enforceable"])
        self.assertIn("proxy", blob)
        self.assertIn("Nothing makes an agent actually perform the review", blob)

    def test_the_size_signal_says_it_is_a_proxy(self):
        signal = next(s for s in load("policies/workflow-intensity.json")["signals"]
                      if s["id"] == "IN-06")
        self.assertIn("proxy", signal["why"])


if __name__ == "__main__":
    unittest.main()
