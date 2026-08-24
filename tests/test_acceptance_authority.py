"""Acceptance must mean the contract was met.

There were two authorities on it. The TaskCompleted gate evaluated the definition
of done; `observe --outcome accepted` set the state without evaluating anything.
So the durable graph could say a task was accepted while two of its own
predicates were failing, and the gate could not object because the mutation never
went near it.

The second theme here is that an unanswerable predicate is not a satisfied one.
An unparseable entry, a predicate the model does not define and an evaluator that
raised were all `continue` -- so an unknown predicate was a definition of done
that always passed.
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
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_dod  # noqa: E402
import workitem as W  # noqa: E402


class Accepting(unittest.TestCase):
    ITEM = "SFTP-FEAT-001"

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-acc-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Acceptance must mean the contract was met"],
                     ["plan", "--item", self.ITEM]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)

    def accept(self, tid):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), "observe",
             "--project", self.project, "--item", self.ITEM, "--task", tid,
             "--outcome", "accepted"], capture_output=True, text=True, timeout=120)

    def state(self, tid):
        return W.task(W.load_graph(self.project, self.ITEM), tid)["state"]

    def set_task(self, tid, **fields):
        graph = W.load_graph(self.project, self.ITEM)
        W.task(graph, tid).update(fields)
        W.save_graph(self.project, graph)

    def a_failing_task(self):
        graph = W.load_graph(self.project, self.ITEM)
        for t in graph["tasks"]:
            if not t.get("definition_of_done"):
                continue
            result = check_dod.acceptance(self.project, t, change=self.ITEM)
            if result["failing"]:
                return t["id"]
        raise unittest.SkipTest("no task in the fixture has a failing predicate")


class TestAcceptanceRunsTheGate(Accepting):
    def test_a_task_whose_contract_fails_cannot_be_declared_accepted(self):
        tid = self.a_failing_task()
        proc = self.accept(tid)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("REFUSED", proc.stdout)
        self.assertEqual(self.state(tid), "queued",
                         "the durable graph was mutated by a refused acceptance")

    def test_the_refusal_names_the_predicates(self):
        proc = self.accept(self.a_failing_task())
        self.assertIn("fails", proc.stdout)

    def test_the_refusal_is_recorded(self):
        tid = self.a_failing_task()
        self.accept(tid)
        refusals = [h for h in W.history(self.project, self.ITEM)
                    if h["kind"] == "acceptance_refused"]
        self.assertTrue(refusals)
        self.assertEqual(refusals[0]["task"], tid)

    def test_a_satisfied_task_still_accepts(self):
        graph = W.load_graph(self.project, self.ITEM)
        ok = next(t["id"] for t in graph["tasks"]
                  if not check_dod.acceptance(self.project, t, change=self.ITEM)["failing"]
                  and t["state"] == "queued")
        self.assertEqual(self.accept(ok).returncode, 0)
        self.assertEqual(self.state(ok), "accepted")

    def test_other_outcomes_are_observations_and_are_not_gated(self):
        """Recording that something failed must never be refused: that is the
        loop's own input."""
        tid = self.a_failing_task()
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), "observe",
             "--project", self.project, "--item", self.ITEM, "--task", tid,
             "--outcome", "failed", "--detail", "the endpoint still rejects valid credentials"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestUnanswerableIsNotSatisfied(Accepting):
    UNKNOWN = ["looks_fine(REQ)"]
    UNPARSEABLE = ["just some prose about being done"]
    WRONG_ARITY = ["artifact_exists(REQ, extra)"]

    def test_classify_separates_a_broken_contract_from_missing_evidence(self):
        self.assertIsNone(check_dod.classify("artifact_exists(REQ)")[2])
        for entry in self.UNKNOWN + self.UNPARSEABLE + self.WRONG_ARITY:
            self.assertIsNotNone(check_dod.classify(entry)[2], entry)

    def test_an_unknown_predicate_blocks_high_risk_acceptance(self):
        for dod in (self.UNKNOWN, self.UNPARSEABLE, self.WRONG_ARITY):
            with self.subTest(dod=dod):
                self.set_task("T-002", definition_of_done=list(dod), risk="HIGH",
                              depends_on=[], state="queued")
                proc = self.accept("T-002")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("unanswered", proc.stdout)
                self.assertEqual(self.state("T-002"), "queued")

    def test_the_same_predicate_is_allowed_and_reported_on_low_risk_work(self):
        self.set_task("T-002", definition_of_done=list(self.UNKNOWN), risk="LOW",
                      depends_on=[], state="queued")
        proc = self.accept("T-002")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("could not be answered", proc.stdout)
        self.assertEqual(self.state("T-002"), "accepted")

    def test_evidence_outside_the_repository_is_not_the_same_as_unanswerable(self):
        """`pipeline_passed` is a real predicate whose evidence lives in GitLab.
        Conflating it with an unknown one is what made an invented predicate look
        like a legitimate absence."""
        result = check_dod.acceptance(
            self.project, {"id": "X", "definition_of_done": ["pipeline_passed(required)",
                                                             "looks_fine(REQ)"]},
            change=self.ITEM)
        self.assertEqual(len(result["unverifiable"]), 1)
        self.assertEqual(len(result["unsupported"]), 1)
        self.assertIn("pipeline_passed", result["unverifiable"][0])
        self.assertIn("looks_fine", result["unsupported"][0])

    def test_an_evaluator_that_raises_is_unsupported_not_passed(self):
        broken = {"id": "X", "definition_of_done": ["artifact_exists(REQ)"]}
        real = check_dod.evaluate

        def explode(*a, **k):
            raise RuntimeError("the evaluator is broken")

        check_dod.evaluate = explode
        try:
            result = check_dod.acceptance(self.project, broken, change=self.ITEM)
        finally:
            check_dod.evaluate = real
        self.assertEqual(result["passing"], [])
        self.assertEqual(len(result["unsupported"]), 1)


class TestAParentStandsForItsPieces(Accepting):
    def test_a_decomposed_stage_is_not_accepted_over_open_children(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
                        "--project", self.project, "--item", self.ITEM, "--task", "T-008",
                        "--derive", "--no-infer"], capture_output=True, timeout=180)
        graph = W.load_graph(self.project, self.ITEM)
        kids = W.children_of(graph, "T-008")
        self.assertTrue(kids, "the fixture did not decompose")
        self.set_task("T-008", definition_of_done=[], depends_on=[c["id"] for c in kids])
        proc = self.accept("T-008")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("have not been accepted", proc.stdout)

    def test_it_accepts_once_the_pieces_are_done(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
                        "--project", self.project, "--item", self.ITEM, "--task", "T-008",
                        "--derive", "--no-infer"], capture_output=True, timeout=180)
        graph = W.load_graph(self.project, self.ITEM)
        kids = W.children_of(graph, "T-008")
        for c in kids:
            W.task(graph, c["id"])["state"] = "accepted"
        W.task(graph, "T-008")["definition_of_done"] = []
        W.task(graph, "T-008")["depends_on"] = [c["id"] for c in kids]
        W.save_graph(self.project, graph)
        self.assertEqual(self.accept("T-008").returncode, 0)


class TestBothPathsAgree(Accepting):
    """One acceptance authority means the gate and the loop cannot disagree
    about the same task."""

    def gate(self, tid):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=self.project)
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "hooks", "scripts", "gate_task_completion.py")],
            input=json.dumps({"hook_event_name": "TaskCompleted", "task_id": "n-" + tid,
                              "task_subject": "%s done" % tid}),
            capture_output=True, text=True, env=env, timeout=60)

    def test_a_failing_task_is_refused_by_both(self):
        tid = self.a_failing_task()
        self.assertEqual(self.accept(tid).returncode, 1)
        self.assertEqual(self.gate(tid).returncode, 2)

    def test_an_unknown_predicate_is_refused_by_both_on_high_risk(self):
        self.set_task("T-002", definition_of_done=["looks_fine(REQ)"], risk="HIGH",
                      depends_on=[], state="queued")
        self.assertEqual(self.accept("T-002").returncode, 1)
        self.assertEqual(self.gate("T-002").returncode, 2)

    def test_both_allow_the_same_low_risk_case(self):
        self.set_task("T-002", definition_of_done=["looks_fine(REQ)"], risk="LOW",
                      depends_on=[], state="queued")
        self.assertEqual(self.gate("T-002").returncode, 0)
        self.assertEqual(self.accept("T-002").returncode, 0)


if __name__ == "__main__":
    unittest.main()


class TestAPredicateTheModelDeclaresAndNothingEvaluates(Accepting):
    """The subtlest of the three. `classify` accepts it -- the model does define
    it -- so only the evaluator's own fallthrough can catch it, and that used to
    answer REQUIRES-EVIDENCE, which the gate read as "not a failure".
    """

    NAME = "declared_but_unimplemented"

    def with_declared_predicate(self, fn):
        real = check_dod.model
        model = dict(real())
        preds = dict(model["dod_predicates"])
        preds[self.NAME] = {"args": ["artifact_code"], "checkable": "project",
                            "means": "declared in the model and implemented nowhere"}
        model["dod_predicates"] = preds
        check_dod.model = lambda: model
        try:
            return fn()
        finally:
            check_dod.model = real

    def test_classify_accepts_it_because_the_model_defines_it(self):
        problem = self.with_declared_predicate(
            lambda: check_dod.classify("%s(REQ)" % self.NAME)[2])
        self.assertIsNone(problem, "the model does declare it; classify is not the check here")

    def test_acceptance_reports_it_as_unsupported_not_as_missing_evidence(self):
        result = self.with_declared_predicate(lambda: check_dod.acceptance(
            self.project, {"id": "X", "definition_of_done": ["%s(REQ)" % self.NAME]},
            change=self.ITEM))
        self.assertEqual(result["unverifiable"], [],
                         "a checker gap was reported as evidence living elsewhere")
        self.assertEqual(len(result["unsupported"]), 1)
        self.assertEqual(result["passing"], [])

    def test_it_blocks_high_risk_acceptance(self):
        self.set_task("T-002", definition_of_done=["%s(REQ)" % self.NAME], risk="HIGH",
                      depends_on=[], state="queued")
        # Evaluated in the subprocess against the real model, where the name is
        # unknown; the point of this class is the in-process path above. Here we
        # only confirm the end-to-end refusal still happens for a name nothing
        # can answer, by either route.
        self.assertEqual(self.accept("T-002").returncode, 1)
