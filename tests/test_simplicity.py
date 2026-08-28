"""Simplicity by default: the principle, the predicate that reads its ledger, and
the guarantee that the control never becomes a ban list.

Every guard here is tested four ways, because a control is only worth what its
failure cases prove: the positive case (a justified introduction passes), the
negative case (an unjustified one fails), the false-positive case (a design that
introduces nothing is not punished for it), and the failure-of-the-control case
(a ledger that is present but hollow does not pass on presence alone).
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

import check_dod  # noqa: E402
from frontmatter import read as read_fm  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


JUSTIFIED = {
    "component": "message-broker",
    "driver": "NFR-004",
    "simpler_alternative": "Poll the existing PostgreSQL table with SELECT ... FOR UPDATE "
                           "SKIP LOCKED.",
    "why_rejected": "Measured at 40 jobs/s against a stated requirement of 500 jobs/s.",
    "evidence": "measurement",
    "evidence_ref": "docs/architecture/load-test.md",
    "operational_cost": "One more component to run, monitor, patch and carry on-call.",
    "reversible": "Yes at moderate cost while the producer interface is unchanged.",
}


def arch(**over):
    a = {"id": "ACME-ARCH-001", "type": "architecture", "status": "approved"}
    a.update(over)
    return [a]


def evaluate(artifacts):
    return check_dod.evaluate("complexity_justified", ["ARCH"], artifacts, ROOT)


class TestComplexityJustifiedPredicate(unittest.TestCase):
    """The predicate checks that the justification exists and is complete. It never
    checks whether the judgement was right: that is architecture-reviewer's finding
    and the human's decision under AP-02."""

    def test_positive_justified_introduction_passes(self):
        status, detail = evaluate(arch(complexity=[JUSTIFIED]))
        self.assertEqual(status, "PASS", detail)

    def test_negative_absent_ledger_fails(self):
        status, detail = evaluate(arch())
        self.assertEqual(status, "FAIL", detail)
        self.assertIn("no complexity ledger", detail)

    def test_false_positive_empty_ledger_passes(self):
        """A change that introduces no complexity is the common case and the one the
        principle wants. Failing it would make the honest answer the expensive one and
        teach every architect to invent an entry."""
        status, detail = evaluate(arch(complexity=[]))
        self.assertEqual(status, "PASS", detail)
        self.assertIn("introduce none", detail)

    def test_control_failure_hollow_entry_does_not_pass_on_presence(self):
        """The way this control fails quietly is by accepting any list at all. An entry
        that names the component and nothing else is the form filled in to get past the
        gate, and it must not."""
        hollow = {"component": "message-broker"}
        status, detail = evaluate(arch(complexity=[hollow]))
        self.assertEqual(status, "FAIL", detail)
        for field in ("driver", "simpler_alternative", "why_rejected", "evidence"):
            self.assertIn(field, detail)

    def test_control_failure_unnamed_alternative_does_not_pass(self):
        """Rejecting an alternative nobody named is not a comparison."""
        item = dict(JUSTIFIED, simpler_alternative="   ")
        status, detail = evaluate(arch(complexity=[item]))
        self.assertEqual(status, "FAIL", detail)
        self.assertIn("simpler_alternative", detail)

    def test_evidence_kind_must_be_one_the_policy_recognises(self):
        """'We might need to scale' is the standard non-evidence. It cannot be laundered
        into the ledger by putting it in the evidence field."""
        item = dict(JUSTIFIED, evidence="expected growth")
        status, detail = evaluate(arch(complexity=[item]))
        self.assertEqual(status, "FAIL", detail)
        self.assertIn("evidence", detail)

    def test_missing_artifact_fails_rather_than_passing_vacuously(self):
        status, detail = evaluate([])
        self.assertEqual(status, "FAIL", detail)

    def test_malformed_ledger_fails_rather_than_raising(self):
        status, detail = evaluate(arch(complexity="we thought about it"))
        self.assertEqual(status, "FAIL", detail)

    def test_required_fields_come_from_the_policy(self):
        """The predicate and the document agents follow read one list. Hard-coding the
        fields here is how the check and the instruction drift apart."""
        policy = load("policies/simplicity-policy.json")
        self.assertEqual(check_dod._simplicity_required_fields(),
                         policy["required_justification_fields"])

    def test_predicate_is_declared_in_the_artifact_model(self):
        model = load("policies/artifact-model.json")
        self.assertIn("complexity_justified", model["dod_predicates"])
        self.assertEqual(model["dod_predicates"]["complexity_justified"]["args"],
                         ["artifact_code"])


class TestSimplicityPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = load("policies/simplicity-policy.json")

    def test_principle_is_not_choose_the_smallest(self):
        """The abuse this principle attracts is dropping a stated requirement and
        calling the result simple. The policy has to rule that out in its own text,
        because the text is what an agent reads."""
        principle = self.policy["principle"].lower()
        for word in ("functional", "reliability", "security", "operational"):
            self.assertIn(word, principle)
        self.assertTrue(any("smallest" in c for c in self.policy["not_the_principle"]))

    def test_every_trigger_offers_a_simpler_alternative_prompt(self):
        """A trigger that only says 'this is complex' produces an argument. One that
        asks a specific question produces an answer."""
        for t in self.policy["complexity_triggers"]:
            self.assertTrue(t.get("simpler_alternative_prompt", "").strip(),
                            "%s has no simpler-alternative prompt" % t["id"])
            self.assertTrue(t.get("category", "").strip(), "%s has no category" % t["id"])

    def test_trigger_ids_are_unique_and_sequential(self):
        ids = [t["id"] for t in self.policy["complexity_triggers"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["CX-%02d" % (i + 1) for i in range(len(ids))])

    def test_the_categories_the_brief_named_are_all_covered(self):
        cats = {t["category"] for t in self.policy["complexity_triggers"]}
        self.assertEqual(cats, {"infrastructure", "structure", "code", "dependency",
                                "capacity"})

    def test_required_fields_are_a_subset_of_the_documented_fields(self):
        fields = set(self.policy["justification_fields"])
        self.assertTrue(set(self.policy["required_justification_fields"]) <= fields)

    def test_evidence_kinds_exclude_prediction(self):
        self.assertEqual(set(self.policy["evidence_kinds"]),
                         {"requirement", "measurement", "constraint"})
        self.assertTrue(any("Unquantified growth" in n for n in self.policy["not_evidence"]))

    def test_it_prohibits_nothing(self):
        """The failure mode of a simplicity rule is becoming a ban list: it blocks the
        project that genuinely needs a queue, and the organization routes around it."""
        text = json.dumps(self.policy).lower()
        for banned in ("must not use", "is forbidden", "is prohibited", "never use "):
            self.assertNotIn(banned, text)
        self.assertIn("legitimate engineering decision",
                      self.policy["enforcement"]["deliberate_non_prohibition"])

    def test_it_does_not_claim_enforcement_it_does_not_have(self):
        enf = self.policy["enforcement"]
        self.assertEqual(enf["mechanism"], "review dimension and definition-of-done predicate")
        self.assertTrue(enf["not_enforced_by_hook"])
        self.assertEqual(enf["predicate"], "complexity_justified(artifact_code)")

    def test_no_hook_enforces_it(self):
        base = os.path.join(ROOT, "hooks", "scripts")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                self.assertNotIn("simplicity", fh.read(),
                                 "hooks/scripts/%s decides on simplicity; a guard cannot tell a "
                                 "justified queue from an unjustified one" % name)

    def test_preference_order_is_ranked_and_starts_with_doing_nothing(self):
        order = self.policy["preference_order"]
        self.assertEqual([o["rank"] for o in order], list(range(1, len(order) + 1)))
        self.assertEqual(order[0]["option"], "do-nothing")
        self.assertEqual(order[-1]["option"], "build-new")

    def test_every_stage_the_brief_named_is_covered(self):
        stages = {a["stage"] for a in self.policy["applies_at"]}
        self.assertEqual(stages, {"requirements", "architecture", "technology-selection",
                                  "story-decomposition", "development", "infrastructure",
                                  "performance", "release"})
        for entry in self.policy["applies_at"]:
            self.assertTrue(entry["how"].strip(), entry["stage"])


class TestSimplicityIsReachable(unittest.TestCase):
    """A principle nobody loads is documentation. None of the agents holds the Skill
    tool, so frontmatter is the only route into a role's context."""

    DECIDERS = ["solution-architect", "development-lead", "backend-developer",
                "devops-engineer", "release-manager", "requirements-analyst"]
    REVIEWERS = ["architecture-reviewer", "code-reviewer", "performance-reviewer",
                 "dependency-reviewer"]

    def preloads(self, agent):
        fm, _ = read_fm(os.path.join(ROOT, "agents", "%s.md" % agent))
        return set(fm.get("skills") or [])

    def test_the_roles_that_buy_complexity_load_the_skill(self):
        for a in self.DECIDERS:
            self.assertIn("engineering-simplicity", self.preloads(a), a)

    def test_the_roles_that_review_it_load_the_same_skill(self):
        """Author and reviewer must hold the same standard, or the review is an opinion
        against a rule the author never saw."""
        for a in self.REVIEWERS:
            self.assertIn("engineering-simplicity", self.preloads(a), a)

    def test_the_skill_exists_and_names_the_policy(self):
        path = os.path.join(ROOT, "skills", "engineering-simplicity", "SKILL.md")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("simplicity-policy.json", body)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", body)


class TestSimplicityIsWiredIntoTheLifecycle(unittest.TestCase):
    def setUp(self):
        self.workflows = check_dod.workflows()

    def stage(self, wid, sid):
        return next(s for s in self.workflows[wid]["stages"] if s["id"] == sid)

    def test_architecture_gates_on_the_ledger(self):
        self.assertIn("complexity_justified(ARCH)",
                      self.stage("WF-FEATURE", "ARCH")["definition_of_done"])

    def test_the_skill_is_available_at_every_stage_that_decides_complexity(self):
        for wid, sid in [("WF-FEATURE", "REQ"), ("WF-FEATURE", "FEAS"),
                         ("WF-FEATURE", "ARCH"), ("WF-FEATURE", "STORY"),
                         ("WF-FEATURE", "DEV"), ("WF-FEATURE", "QA"),
                         ("WF-FEATURE", "RELEASE"), ("WF-CHANGE", "ASSESS"),
                         ("WF-MIGRATION", "DESIGN"), ("WF-DEPENDENCY", "IMPACT")]:
            self.assertIn("engineering-simplicity", self.stage(wid, sid).get("skills") or [],
                          "%s/%s" % (wid, sid))

    def test_a_stage_that_offers_the_skill_has_an_owner_that_preloads_it(self):
        """Otherwise the stage names a capability its owner cannot reach."""
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                if "engineering-simplicity" not in (s.get("skills") or []):
                    continue
                fm, _ = read_fm(os.path.join(ROOT, "agents", "%s.md" % s["owner"]))
                self.assertIn("engineering-simplicity", fm.get("skills") or [],
                              "%s/%s is owned by %s, which does not preload it"
                              % (wid, s["id"], s["owner"]))

    def test_a_change_introducing_a_component_reaches_an_independent_reviewer(self):
        routes = {r["id"]: r for r in load("policies/review-routing.json")["routes"]}
        self.assertIn("RR-11", routes)
        self.assertEqual(routes["RR-11"]["gate"], "blocking")
        self.assertEqual(routes["RR-11"]["reviewers"], ["architecture-reviewer"])
        self.assertEqual(routes["RR-11"]["dimension"], "simplicity")

    def test_the_route_does_not_authorise_a_taste_veto(self):
        routes = {r["id"]: r for r in load("policies/review-routing.json")["routes"]}
        self.assertIn("never returns 'too complex' as a verdict on its own",
                      routes["RR-11"]["notes"])


class TestSimplicityEvaluationSuite(unittest.TestCase):
    def cases(self):
        base = os.path.join(ROOT, "evaluations", "simplicity-evaluation")
        return [load("evaluations/simplicity-evaluation/%s" % f)
                for f in sorted(os.listdir(base)) if f.endswith(".json")]

    def test_the_suite_has_both_deterministic_and_judged_cases(self):
        modes = [c["mode"] for c in self.cases()]
        self.assertTrue(any(m == "deterministic" for m in modes))
        self.assertTrue(any(m == "llm-judged" for m in modes))

    def test_the_suite_tries_to_break_its_own_control(self):
        """Every suite must attempt to make its subject exceed its authority. Here the
        subject includes the policy itself: the adversarial cases are the ones that try
        to use simplicity to drop a requirement, and to turn it into a ban list."""
        self.assertTrue(any(c.get("adversarial") for c in self.cases()))

    def test_the_brief_case_is_present(self):
        """'Given two solutions that both satisfy the requirements, prefer the simpler
        one unless there is concrete evidence that the additional complexity is
        necessary.'"""
        inputs = " ".join(str(c.get("input") or "") for c in self.cases())
        self.assertIn("prefer the simpler one", inputs)

    def test_a_case_covers_justified_complexity_being_accepted(self):
        """Without this the suite only ever rewards the smaller design, which is the
        misreading the principle is most vulnerable to."""
        subjects = [c for c in self.cases() if c["subject"] == "architecture-reviewer"]
        self.assertTrue(subjects)
        self.assertTrue(any("justif" in b.lower()
                            for c in subjects for b in c["expected_behaviors"]))

    def test_judged_cases_carry_a_rubric_and_are_never_auto_passed(self):
        for c in self.cases():
            if c["mode"] == "llm-judged":
                self.assertTrue(c.get("rubric"), c["id"])
            else:
                self.assertTrue(c.get("checks"), c["id"])


if __name__ == "__main__":
    unittest.main()
