"""Reviewing a decomposition, without pretending to score one.

`policies/task-synthesis.json` rejects a split that is incoherent with the graph.
It cannot reject one that is merely poor, and it said so — deferring to "the
reviewer on the stage". That reviewer did not exist for this: every stage gate
reviews the stage's *artifact* (testability of stories, coverage of scenarios),
not the split, and the stages most likely to synthesize have no gate at all.

So there are two classes of test here. One holds the review that now happens. The
other holds the line the brief drew: **do not build a fake heuristic that claims
to know whether an engineering decomposition is good.** A number for cohesion
would be defensible-looking, arguable, and wrong often enough that a split which
scored well would stop being read.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import synthesize_tasks as S  # noqa: E402
from minyaml import parse_file  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


POLICY = load("policies/decomposition-review.json")
DIMS = [d["dimension"] for d in POLICY["dimensions"]]
ANSWERED = {d: "a real answer" for d in DIMS}


def parent(**over):
    p = {"id": "T-004", "title": "a stage", "role": "solution-architect",
         "state": "queued", "risk": "HIGH"}
    p.update(over)
    return p


def proposal(review=None, **over):
    p = {"parent": "T-004", "rationale": "split for the purposes of this test",
         "children": [{"key": "a", "title": "the first piece", "role": "solution-architect"},
                      {"key": "b", "title": "the second piece", "role": "solution-architect"}]}
    if review is not None:
        p["review"] = review
    p.update(over)
    return p


def check(prop, par):
    errors = []
    S.check_review(prop, par, errors)
    return [e for e in errors if e.startswith("DQ")]


class TestTheReviewIsRequiredWhereItMatters(unittest.TestCase):
    """Narrow on purpose. Demanding a second reader for a three-way split of a
    LOW-risk documentation stage would make synthesis expensive enough that stages
    stop being decomposed at all, which is worse than an imperfect split."""

    def test_high_risk_needs_one(self):
        self.assertTrue(check(proposal(), parent(risk="HIGH")))

    def test_critical_risk_needs_one(self):
        self.assertTrue(check(proposal(), parent(risk="CRITICAL")))

    def test_a_coupled_surface_needs_one(self):
        errs = check(proposal(), parent(risk="LOW", coupled_surface="api-contract"))
        self.assertTrue(errs)
        self.assertIn("api-contract", errs[0])

    def test_a_low_risk_stage_does_not(self):
        self.assertEqual(check(proposal(), parent(risk="LOW")), [])

    def test_a_medium_risk_stage_does_not(self):
        self.assertEqual(check(proposal(), parent(risk="MEDIUM")), [])

    def test_the_policy_says_why_it_is_not_always_required(self):
        self.assertIn("stop being decomposed at all", POLICY["when_it_is_required"]["otherwise"])


class TestWhatTheCheckerRefuses(unittest.TestCase):
    """Provenance and completeness. Never quality."""

    def test_a_proposer_cannot_review_its_own_split(self):
        """The only part of this a machine can check, and the same separation
        review-routing applies everywhere else."""
        errs = check(proposal(review={"reviewer": "solution-architect", "verdict": "sound",
                                      "dimensions": ANSWERED}), parent())
        self.assertTrue(errs)
        self.assertIn("reviewed its own decomposition", errs[0])

    def test_an_independent_reviewer_is_accepted(self):
        self.assertEqual(check(proposal(review={"reviewer": "engineering-director",
                                                "verdict": "sound",
                                                "dimensions": ANSWERED}), parent()), [])

    def test_a_blank_dimension_is_refused(self):
        for dim in DIMS:
            with self.subTest(dimension=dim):
                errs = check(proposal(review={
                    "reviewer": "engineering-director", "verdict": "sound",
                    "dimensions": dict(ANSWERED, **{dim: "   "})}), parent())
                self.assertTrue(errs)
                self.assertIn(dim, errs[0])

    def test_a_missing_dimension_is_refused(self):
        partial = {d: "answered" for d in DIMS[:-1]}
        errs = check(proposal(review={"reviewer": "engineering-director", "verdict": "sound",
                                      "dimensions": partial}), parent())
        self.assertTrue(errs)
        self.assertIn(DIMS[-1], errs[0])

    def test_resplit_does_not_graft(self):
        errs = check(proposal(review={"reviewer": "engineering-director", "verdict": "resplit",
                                      "dimensions": ANSWERED,
                                      "findings": ["b is the whole stage renamed"]}), parent())
        self.assertTrue(errs)
        self.assertIn("b is the whole stage renamed", errs[0])

    def test_resplit_with_no_findings_says_it_is_unactionable(self):
        errs = check(proposal(review={"reviewer": "engineering-director", "verdict": "resplit",
                                      "dimensions": ANSWERED}), parent())
        self.assertIn("unactionable", errs[0])

    def test_do_not_split_is_a_real_answer_and_grafts_nothing(self):
        """Rejecting the decomposition entirely is under-used, so it is a first-class
        verdict rather than a variant of resplit."""
        errs = check(proposal(review={"reviewer": "engineering-director",
                                      "verdict": "do-not-split",
                                      "dimensions": ANSWERED}), parent())
        self.assertTrue(errs)
        self.assertIn("one task", errs[0])

    def test_sound_with_findings_still_grafts(self):
        """Blocking a workable, imperfect split is how a review becomes something
        people route around."""
        self.assertEqual(check(proposal(review={
            "reviewer": "engineering-director", "verdict": "sound-with-findings",
            "dimensions": ANSWERED,
            "findings": ["handoff between a and b is heavier than it looks"]}), parent()), [])


class TestThereIsNoHeuristic(unittest.TestCase):
    """The line the brief drew, held mechanically. A scoring function would be the
    single easiest thing to add here and the whole reason not to."""

    def test_the_policy_says_there_is_no_score(self):
        self.assertIn("no metric here and there will not be one",
                      POLICY["not_a_score"]["statement"])

    def test_the_policy_says_what_is_checked_instead(self):
        instead = POLICY["not_a_score"]["what_is_checked_instead"]
        self.assertIn("Provenance and completeness, never quality", instead)

    def test_no_dimension_carries_a_weight_or_a_threshold(self):
        for d in POLICY["dimensions"]:
            with self.subTest(dimension=d["dimension"]):
                for banned in ("weight", "score", "threshold", "max", "min"):
                    self.assertNotIn(banned, d)

    def test_the_checker_computes_no_number(self):
        """The code, not the commentary. The docstring says the word `scored` while
        explaining why nothing is, which is exactly the sentence that should stay."""
        import ast
        with open(os.path.join(ROOT, "scripts", "synthesize_tasks.py"), encoding="utf-8") as fh:
            source = fh.read()
        fn = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name == "check_review")
        body = list(fn.body)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)):
            body = body[1:]                      # drop the docstring
        code = "\n".join(ast.dump(n) for n in body).lower()
        for banned in ("score", "weight", "threshold", "mean", "average"):
            self.assertNotIn(banned, code,
                             "check_review computes %r; the review is prose, not a number"
                             % banned)
        # No arithmetic at all on the answers.
        for node in ast.walk(fn):
            self.assertNotIsInstance(node, ast.BinOp if False else ast.Div,
                                     "check_review divides something")

    def test_every_dimension_is_a_question(self):
        for d in POLICY["dimensions"]:
            with self.subTest(dimension=d["dimension"]):
                self.assertTrue(d["asks"].endswith("?"))
                self.assertTrue(d["looks_like_a_problem_when"])
                self.assertGreater(len(d["why_it_matters"]), 40)

    def test_the_schema_takes_prose_for_every_dimension(self):
        schema = load("schemas/task-proposal.schema.json")
        props = schema["properties"]["review"]["properties"]["dimensions"]["properties"]
        self.assertEqual(sorted(props), sorted(DIMS))
        for dim, spec in props.items():
            with self.subTest(dimension=dim):
                self.assertEqual(spec["type"], "string")


class TestItCoversTheDimensionsTheBriefNamed(unittest.TestCase):
    def test_all_seven_are_present(self):
        self.assertEqual(sorted(DIMS), sorted([
            "cohesion", "coupling", "parallelizability", "task_size",
            "ownership", "handoff_cost", "integration_cost"]))

    def test_the_skill_documents_each_one(self):
        with open(os.path.join(ROOT, "skills", "task-synthesis", "SKILL.md"),
                  encoding="utf-8") as fh:
            body = fh.read()
        for dim in DIMS:
            with self.subTest(dimension=dim):
                self.assertIn(dim.replace("_", " "), body)


class TestTheClaimThatWasNotTrue(unittest.TestCase):
    """task-synthesis.json deferred to "the reviewer on the stage". No stage gate
    reviews the split, and the stages most likely to synthesize have no gate."""

    def test_the_old_claim_is_gone(self):
        blob = " ".join(load("policies/task-synthesis.json")["not_enforceable"])
        self.assertNotIn("That is what the reviewer on the stage is for.", blob)
        self.assertIn("decomposition-review.json", blob)

    def test_it_records_why_the_claim_was_wrong(self):
        gap = POLICY["why_this_exists"]["the_gap"]
        self.assertIn("not one of them mentions the decomposition", gap)

    def test_no_stage_gate_actually_reviews_a_decomposition(self):
        """The finding, asserted rather than remembered. If a gate is ever added
        that does review the split, this test is how somebody notices that the
        policy's history needs updating."""
        purposes = []
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            for stage in parse_file(os.path.join(base, name))["stages"]:
                gate = stage.get("agent_gate") or {}
                if gate.get("purpose"):
                    purposes.append(gate["purpose"].lower())
        self.assertTrue(purposes)
        for p in purposes:
            self.assertNotIn("decomposition", p)

    def test_the_synthesizing_roles_are_all_leads(self):
        """Which is why the fallback reviewer matters: the default is the stage's
        gate reviewer, and these three often have none."""
        from frontmatter import read as read_fm
        can = set()
        for name in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            if not name.endswith(".md"):
                continue
            fm, _ = read_fm(os.path.join(ROOT, "agents", name))
            if "task-synthesis" in (fm.get("skills") or []):
                can.add(name[:-3])
        self.assertEqual(can, {"development-lead", "qa-lead", "solution-architect"})
        self.assertIn("All three are leads", POLICY["who_reviews"]["note"])


class TestItSaysWhatItCannotDo(unittest.TestCase):
    def test_it_admits_a_lazy_answer_passes(self):
        limits = " ".join(POLICY["not_enforceable"])
        self.assertIn("What the checker refuses is a blank", limits)

    def test_it_admits_it_cannot_find_a_missing_split(self):
        """A stage that should have been decomposed and was not produces no
        proposal, so there is nothing to review."""
        self.assertIn("never missing ones", " ".join(POLICY["not_enforceable"]))

    def test_it_admits_nothing_correlates_a_review_with_the_graph(self):
        self.assertIn("actually looked at the graph", " ".join(POLICY["not_enforceable"]))


if __name__ == "__main__":
    unittest.main()
