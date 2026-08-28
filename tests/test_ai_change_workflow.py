"""WF-AI-CHANGE and the evaluation model it rests on.

An AI change is the one kind where "it looks better" is a sentence somebody will
actually say and mean. The workflow exists to make that sentence into a
comparison, and these tests hold the two properties that make the comparison
worth anything: a baseline before the work, and one variable moved.

The second class of test is about not building a parallel lifecycle. The brief
that asked for this said so explicitly, and it is the easy mistake: an AI change
feels different enough to deserve its own artifacts, its own reviewers and its own
notion of done. It does not. Same work item, same task graph, same cycles, same
approvals.
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import check_dod as C  # noqa: E402
from minyaml import parse_file  # noqa: E402

WF = parse_file(os.path.join(ROOT, "sdlc", "workflows", "ai-change.yaml"))
STAGES = {s["id"]: s for s in WF["stages"]}

VERSIONS = {"prompt_version": "p1", "model_version": "m1",
            "retrieval_index_version": "i1", "dataset_version": "d1"}


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def run(role, ident=1, **over):
    r = dict({"id": "GOLD-EVALRUN-%03d" % ident, "type": "evaluation-run", "role": role},
             **VERSIONS)
    r.update(over)
    return r


class TestTheComparisonIsTheResult(unittest.TestCase):
    """An absolute number answers almost nothing. 87% correct is good or
    catastrophic depending entirely on what it was before."""

    def ev(self, fn, artifacts, args=None):
        return C.evaluate(fn, args or [], artifacts, ROOT)

    def test_a_change_with_no_baseline_cannot_be_assessed(self):
        status, why = self.ev("baseline_recorded", [run("candidate")])
        self.assertEqual(status, "FAIL")
        self.assertIn("baseline", why)

    def test_a_baseline_that_does_not_name_its_versions_is_not_a_baseline(self):
        """Four versions change independently and each changes behaviour. A result
        naming fewer has a provenance that is a guess."""
        for missing in ("prompt_version", "model_version",
                        "retrieval_index_version", "dataset_version"):
            with self.subTest(missing=missing):
                status, _ = self.ev("baseline_recorded", [run("baseline", **{missing: ""})])
                self.assertEqual(status, "FAIL")

    def test_a_complete_baseline_passes(self):
        self.assertEqual(self.ev("baseline_recorded", [run("baseline")])[0], "PASS")

    def test_two_variables_moving_together_cannot_be_attributed(self):
        status, why = self.ev("one_variable_changed",
                              [run("baseline", 1),
                               run("candidate", 2, prompt_version="p2", model_version="m2")])
        self.assertEqual(status, "FAIL")
        self.assertIn("attributed", why)

    def test_one_variable_moving_is_the_whole_point(self):
        status, why = self.ev("one_variable_changed",
                              [run("baseline", 1), run("candidate", 2, prompt_version="p2")])
        self.assertEqual(status, "PASS")
        self.assertIn("prompt_version", why)

    def test_a_run_that_moved_nothing_is_a_noise_check(self):
        """Two runs of the same configuration differ. Knowing by how much is what
        makes a small delta believable or not."""
        status, why = self.ev("one_variable_changed", [run("baseline", 1), run("candidate", 2)])
        self.assertEqual(status, "PASS")
        self.assertIn("noise", why)


class TestARegressionIsNotAllowedToBeSilent(unittest.TestCase):
    """An improvement in the targeted dimension alongside a quiet loss elsewhere is
    the normal shape of a bad AI change."""

    def ev(self, artifacts):
        return C.evaluate("no_unexplained_regression", [], artifacts, ROOT)

    def test_an_absent_list_is_not_an_answer(self):
        """Empty says the comparison was made and found nothing. Absent says nobody
        looked, and the two must not read the same."""
        status, why = self.ev([run("candidate")])
        self.assertEqual(status, "FAIL")
        self.assertIn("An empty list is an answer", why)

    def test_an_empty_list_is_an_answer(self):
        self.assertEqual(self.ev([run("candidate", regressions=[])])[0], "PASS")

    def test_a_regression_without_an_explanation_fails(self):
        status, why = self.ev([run("candidate", regressions=[{"dimension": "cost"}])])
        self.assertEqual(status, "FAIL")
        self.assertIn("cost", why)

    def test_an_explained_regression_passes(self):
        """An accepted regression is a legitimate outcome. What is refused is one
        nobody noticed."""
        status, _ = self.ev([run("candidate", regressions=[
            {"dimension": "cost", "explanation": "accepted: +25% on a 0.4-cent call"}])])
        self.assertEqual(status, "PASS")


class TestAMetricNamesTheRunThatProducedIt(unittest.TestCase):
    """Do not fabricate metrics. The predicate cannot re-execute a run, so what it
    checks is provenance -- and a bare number has none."""

    def ev(self, artifacts):
        return C.evaluate("metrics_have_evidence", ["EVALRUN"], artifacts, ROOT)

    def test_a_bare_number_is_not_evidence(self):
        status, why = self.ev([run("candidate", deterministic_metrics={"correctness": 0.87})])
        self.assertEqual(status, "FAIL")
        self.assertIn("bare value", why)

    def test_a_metric_naming_its_run_is(self):
        status, _ = self.ev([run("candidate", deterministic_metrics={
            "correctness": {"value": 0.87, "run": "GOLD-EVALRUN-002"}})])
        self.assertEqual(status, "PASS")

    def test_deterministic_and_judged_are_separate_fields(self):
        """Merging them is how a suite stops meaning anything: the deterministic
        part stops being reproducible and the judged part stops being visible."""
        model = load("policies/artifact-model.json")
        evalrun = next(a for a in model["artifact_types"] if a["code"] == "EVALRUN")
        self.assertIn("deterministic_metrics", evalrun["required_fields"])
        self.assertIn("judged_metrics", evalrun["required_fields"])


class TestItIsNotAParallelLifecycle(unittest.TestCase):
    """The brief said not to build one, and it is the easy mistake: an AI change
    feels different enough to deserve its own everything."""

    def test_it_uses_the_department_cycles_that_already_exist(self):
        used = {s.get("department_cycle") for s in WF["stages"] if s.get("department_cycle")}
        self.assertTrue(used)
        known = set()
        base = os.path.join(ROOT, "sdlc", "cycles")
        for name in sorted(os.listdir(base)):
            if name.endswith(".yaml"):
                known.add(parse_file(os.path.join(base, name))["id"])
        self.assertTrue(used <= known, "invented a cycle: %s" % (used - known))

    def test_it_uses_the_approval_categories_that_already_exist(self):
        approvals = {(s.get("human_gate") or {}).get("policy_ref")
                     for s in WF["stages"] if s.get("human_gate")}
        approvals.discard(None)
        known = {i["id"] for i in load("policies/approval-policy.json")["human_approval_required"]}
        self.assertTrue(approvals <= known, "invented an approval: %s" % (approvals - known))

    def test_it_is_opened_as_an_ordinary_work_item(self):
        import control_loop as CL
        self.assertEqual(CL.TYPE_WORKFLOW["ai-change"], "WF-AI-CHANGE")
        self.assertEqual(CL.TYPE_CODE["ai-change"], "AIC")

    def test_its_reviewers_are_roles_that_already_existed(self):
        registry = {a["name"] for a in load("policies/agent-registry.json")["agents"]}
        for stage in WF["stages"]:
            with self.subTest(stage=stage["id"]):
                self.assertIn(stage["owner"], registry)
                reviewer = (stage.get("agent_gate") or {}).get("reviewer")
                if reviewer:
                    self.assertIn(reviewer, registry)

    def test_no_new_agent_was_added_for_it(self):
        self.assertEqual(len(load("policies/agent-registry.json")["agents"]), 30)


class TestTheLifecycleTheBriefAskedFor(unittest.TestCase):
    def test_every_named_stage_exists(self):
        for stage in ("INTENT", "CONTRACT", "BASELINE", "DESIGN", "IMPLEMENT",
                      "OFFLINE-EVAL", "REGRESSION", "REVIEW", "SHADOW", "PRODUCTION",
                      "POST-DEPLOY"):
            with self.subTest(stage=stage):
                self.assertIn(stage, STAGES)

    def test_the_baseline_comes_before_the_work(self):
        """Establishing it is a stage rather than a preparation for one. A change
        with no baseline produces a number rather than a finding."""
        order = [s["id"] for s in WF["stages"]]
        self.assertLess(order.index("BASELINE"), order.index("IMPLEMENT"))
        self.assertLess(order.index("CONTRACT"), order.index("BASELINE"))

    def test_the_contract_comes_before_anything_is_measured(self):
        """A contract written afterwards describes what was built, which is the one
        thing an evaluation cannot check."""
        order = [s["id"] for s in WF["stages"]]
        self.assertLess(order.index("CONTRACT"), order.index("BASELINE"))

    def test_the_workflow_gates_on_the_comparison(self):
        dod = WF["definition_of_done"]
        for predicate in ("baseline_recorded()", "one_variable_changed()",
                          "no_unexplained_regression()", "metrics_have_evidence(EVALRUN)"):
            self.assertIn(predicate, dod)

    def test_production_needs_a_named_human(self):
        gate = STAGES["PRODUCTION"]["human_gate"]
        self.assertEqual(gate["policy_ref"], "AP-01")
        self.assertEqual(STAGES["PRODUCTION"]["risk"], "CRITICAL")

    def test_shadow_may_be_skipped_only_for_the_lowest_autonomy(self):
        skip = " ".join(STAGES["SHADOW"]["optional_when"])
        self.assertIn("suggests-to-a-human", skip)


class TestTheWorkflowCanActuallyBeCompleted(unittest.TestCase):
    def test_the_simulation_runs_it_end_to_end(self):
        """Every other workflow earned its place this way. Without it, WF-AI-CHANGE
        would be the only one never shown to be completable, and the four new
        predicates would never meet a real artifact."""
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "simulate_sdlc.py"),
             "--scenario", "ai-change"],
            capture_output=True, text=True, cwd=ROOT, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2500:])
        self.assertIn("every definition of done satisfied", proc.stdout)


class TestTheTwoEvaluationSubjectsStayApart(unittest.TestCase):
    """policies/evaluation-policy.json evaluates this organization's agents.
    policies/ai-evaluation-model.json evaluates the product. Same discipline,
    different subject, and a suite that mixes them measures neither."""

    def test_the_ai_model_says_which_subject_it_is(self):
        policy = load("policies/ai-evaluation-model.json")
        self.assertIn("about the product", policy["description"])
        self.assertIn("evaluation-policy.json", policy["description"])

    def test_the_ai_model_does_not_redefine_the_agent_suite(self):
        """It borrows the discipline and none of the machinery. `adversarial` is
        deliberately not checked here: it appears in the robustness metric, about
        adversarial input to the product, which is a different use of the word from
        the agent suite's adversarial cases."""
        policy = json.dumps(load("policies/ai-evaluation-model.json"))
        for token in ("agent-registry", "evaluation_suite", "EVAL-", "suites"):
            self.assertNotIn(token, policy)

    def test_both_refuse_to_auto_pass_a_judged_case(self):
        agent = json.dumps(load("policies/evaluation-policy.json"))
        product = load("policies/ai-evaluation-model.json")
        self.assertIn("never", agent.lower())
        self.assertTrue(any("Never auto-passed" in r
                            for r in product["modes"]["model-judged"]["rules"]))

    def test_the_product_model_admits_what_it_cannot_check(self):
        limits = " ".join(load("policies/ai-evaluation-model.json")["enforcement"]["not_enforceable"])
        self.assertIn("representative", limits)
        self.assertIn("cannot re-execute", limits)


class TestTheSchemasAgreeAboutWhatAWorkItemIs(unittest.TestCase):
    """They drifted twice. The second time was v0.35.0 adding three work-item types
    to one pattern and not the other, so an artifact belonging to a dependency,
    agent-change or onboarding item could not satisfy its own header schema."""

    def test_the_change_pattern_equals_the_work_item_id_pattern(self):
        item = load("schemas/work-item.schema.json")["properties"]["id"]["pattern"]
        change = load("schemas/artifact-header.schema.json")["properties"]["change"]["pattern"]
        self.assertEqual(item, change)

    def test_every_work_item_code_is_accepted_by_both(self):
        import re
        import control_loop as CL
        item = load("schemas/work-item.schema.json")["properties"]["id"]["pattern"]
        change = load("schemas/artifact-header.schema.json")["properties"]["change"]["pattern"]
        for code in sorted(set(CL.TYPE_CODE.values())):
            with self.subTest(code=code):
                self.assertRegex("ACME-%s-001" % code, item)
                self.assertRegex("ACME-%s-001" % code, change)

    def test_the_validator_would_catch_the_drift(self):
        with open(os.path.join(ROOT, "scripts", "validate_plugin.py"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("def check_work_item_id_patterns_agree(", body)
        self.assertIn("check_work_item_id_patterns_agree()", body)


if __name__ == "__main__":
    unittest.main()
