"""The Golden Project, and the line between synthetic validation and real evidence.

The deterministic suite proves the organization is coherent with itself. It does
not prove Claude Code ever calls any of it. Those are different claims, and the
one thing certification must never do is let the first stand in for the second.

So most of these tests are about the verdict refusing to overclaim: a run with a
perfect synthetic result and no session is not certified, and no arrangement of
synthetic units can make it so.
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
import certify  # noqa: E402
from jsonschema_mini import validate as jsvalidate  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def unit(stage="REQ", evidence="synthetic", dod_result="pass", unsupported=0):
    return {"stage": stage, "work_item": "GOLD-FEAT-001", "task": "T-001",
            "role": "product-manager", "evidence": evidence, "outcome": "accepted",
            "dod": {"pass": 3, "fail": 0, "unsupported": unsupported,
                    "requires_evidence": 0, "result": dod_result, "failing": []}}


def probe(pid="p", result="pass"):
    return {"id": pid, "asks": "does the thing happen in a real session?",
            "result": result, "evidence_source": "the audit log",
            "observed": None, "why_not_run": None}


class TestTheVerdictRefusesToOverclaim(unittest.TestCase):
    """The single rule the whole file exists to enforce."""

    def test_a_perfect_synthetic_run_with_no_session_is_not_certified(self):
        units = [unit(s) for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(result="not-run")], "synthetic")
        self.assertEqual(v["synthetic"], "pass")
        self.assertEqual(v["real_agent"], "not-run")
        self.assertFalse(v["certified"])

    def test_no_number_of_synthetic_units_produces_real_agent_evidence(self):
        """The overclaim this guards against is arithmetic: enough green synthetic
        stages starting to look like a certified system."""
        units = [unit(s) for s in certify.REQUIRED_STAGES] * 50
        v = certify.build_verdict(units, [], "synthetic")
        self.assertEqual(v["real_agent"], "not-run")
        self.assertFalse(v["certified"])

    def test_live_mode_alone_does_not_make_a_run_real(self):
        """Asking for a live run is not the same as getting one. A live-mode run
        whose sessions never started produced no evidence."""
        v = certify.build_verdict([unit()], [probe(result="not-run")], "live")
        self.assertEqual(v["real_agent"], "not-run")
        self.assertFalse(v["certified"])

    def test_passing_probes_without_stage_coverage_is_partial_not_pass(self):
        v = certify.build_verdict([unit(evidence="real-agent", stage="REQ")],
                                  [probe()], "live")
        self.assertEqual(v["real_agent"], "partial")
        self.assertFalse(v["certified"])
        for stage in certify.REQUIRED_STAGES[1:]:
            self.assertIn(stage, v["coverage"]["synthetic_only"])

    def test_a_failing_probe_refuses_certification_outright(self):
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(result="fail")], "live")
        self.assertEqual(v["real_agent"], "fail")
        self.assertFalse(v["certified"])

    def test_full_real_coverage_with_passing_probes_certifies(self):
        """The positive case, so the refusals above are refusing something real."""
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe()], "live")
        self.assertEqual(v["real_agent"], "pass")
        self.assertTrue(v["certified"])

    def test_a_probe_that_never_ran_blocks_certification(self):
        """`not-run` is not a quiet `pass`. A probe that never fired measured
        nothing, and the mechanism it asks about is exactly the one that breaks
        in a pilot -- the live baseline for v0.44.0 had every stage's probe green
        and `task-binding-recorded` never fired at all, because no session ever
        created a native task."""
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(), probe(pid="never-fired",
                                                         result="not-run")], "live")
        self.assertEqual(v["real_agent"], "partial")
        self.assertFalse(v["certified"])
        self.assertIn("never-fired", v["probes"]["unmeasured"])

    def test_the_reason_names_the_probes_that_did_not_run(self):
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(), probe(pid="never-fired",
                                                         result="not-run")], "live")
        self.assertIn("never-fired", v["why"])
        self.assertIn("unmeasured", v["why"])

    def test_a_run_where_no_probe_fired_at_all_is_not_run_not_partial(self):
        """Stronger than partial, and the distinction is real: partial means some
        mechanisms were measured, not-run means none were."""
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(result="not-run")], "live")
        self.assertEqual(v["real_agent"], "not-run")
        self.assertFalse(v["certified"])

    def test_the_verdict_counts_its_probes(self):
        units = [unit(s, evidence="real-agent") for s in certify.REQUIRED_STAGES]
        v = certify.build_verdict(units, [probe(), probe(pid="b", result="fail"),
                                          probe(pid="c", result="not-run")], "live")
        self.assertEqual(v["probes"]["total"], 3)
        self.assertEqual(v["probes"]["failed"], 1)
        self.assertEqual(v["probes"]["not_run"], 1)

    def test_the_walk_never_overwrites_what_an_agent_reported(self):
        """`observe --detail` writes straight over `task["result"]`, which is
        where the agent's own words live and the only evidence one probe has to
        read. The first full walk passed a helpful-looking note and overwrote
        them; the probe correctly reported that the evidence was gone. A harness
        that narrates over what it is measuring is measuring itself."""
        import ast
        with open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "drive_lifecycle")
        literals = {n.value for n in ast.walk(fn)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn("observe", literals, "the fixture no longer describes the walk")
        self.assertNotIn("--detail", literals,
                         "the walk writes over the agent's own result")

    def test_the_verdict_always_says_why(self):
        for units, probes, mode in [([unit()], [], "synthetic"),
                                    ([unit(evidence="real-agent")], [probe()], "live"),
                                    ([unit()], [probe(result="fail")], "live")]:
            v = certify.build_verdict(units, probes, mode)
            self.assertGreater(len(v["why"]), 40, v)

    def test_an_unsupported_predicate_fails_the_synthetic_path(self):
        """A stage whose contract has no evaluator could never be satisfied, however
        well an agent did the work."""
        v = certify.build_verdict([unit(unsupported=1)], [], "synthetic")
        self.assertEqual(v["synthetic"], "fail")


class TestAProbeReportsWhatHappenedAndNotWhatItAssumed(unittest.TestCase):
    """Two probes overclaimed in opposite directions, and both were caught by a
    real run rather than by reading the code.

    The background probe called `state: working` "the platform never ran it"
    while the same record said the artifact had been produced -- the poll had
    simply caught the job before it finished, and a state cannot turn work that
    demonstrably happened into work that did not.

    The worktree probe accepted a modified file in the main checkout as evidence
    of integration. That is exactly the trace an agent leaves when it ignores the
    worktree and edits the main checkout directly, which is the opposite of the
    behaviour being certified. It would have passed on that evidence had a
    removal also been recorded.
    """

    def background(self, state, produced):
        fn = next(p["fn"] for p in certify.PROBES
                  if p["id"] == "background-execution-was-actually-dispatched")
        return fn({"mechanisms": [{"mechanism": "background", "id": "j1",
                                   "produced": produced,
                                   "listing": {"kind": "background", "state": state}}]})

    def test_a_finished_job_that_wrote_its_artifact_passes(self):
        self.assertIs(self.background("done", True)[0], True)

    def test_a_finished_job_that_produced_nothing_fails(self):
        """It ran and did not do the work. That is a real failure."""
        self.assertIs(self.background("done", False)[0], False)

    def test_a_running_job_that_already_wrote_its_artifact_passes(self):
        ok, why = self.background("working", True)
        self.assertIs(ok, True)
        self.assertIn("poll being early", why)

    def test_a_running_job_with_nothing_produced_is_undetermined(self):
        self.assertIsNone(self.background("working", False)[0])

    def test_a_blocked_job_is_unexercised_rather_than_broken(self):
        """A dispatch the platform never started leaves the mechanism unmeasured.
        Both refuse certification; only one of them is a defect here."""
        self.assertIsNone(self.background("blocked", False)[0])

    def test_a_dirty_working_tree_is_not_integration_evidence(self):
        source = open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8").read()
        self.assertIn("editing the main checkout directly looks like", source)
        self.assertIn("commits touch", source,
                      "integration must be evidenced by a commit, not by a modified file")


class TestTheHarnessCanReachTheTaskLifecycle(unittest.TestCase):
    """TaskCreated and TaskCompleted were recorded as unreachable for two releases.

    The harness listed a headless session's tools, found nothing that creates a
    task, and concluded that `-p` was the limit. The list was right and the
    inference was wrong: 2.1.252 turned the task tools off for current models
    regardless of execution mode, and CLAUDE_CODE_ENABLE_TODO_TOOLS=1 restores
    them -- headless included. An interactive session on the same model had no
    more access, which is why driving one by hand produced no native task either.

    Verified end to end against live hooks: TaskCreate produced `task_created`
    with the native task bound to T-001 by its subject marker, and TaskUpdate
    produced `task_completion_allowed` with the completion gate evaluating the
    definition of done.
    """

    def test_the_harness_enables_the_task_tools(self):
        import ast
        with open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("CLAUDE_CODE_ENABLE_TODO_TOOLS", source,
                      "without this the two task probes can never run")
        fn = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_session")
        # It is passed as a keyword to dict(os.environ, ...), so it is an argument
        # name rather than a string constant.
        names = {kw.arg for n in ast.walk(fn) if isinstance(n, ast.Call)
                 for kw in n.keywords if kw.arg}
        self.assertIn("CLAUDE_CODE_ENABLE_TODO_TOOLS", names,
                      "the variable must be set on the session's environment, not "
                      "merely mentioned in a comment")

    def test_the_mechanism_prompt_names_the_binding_marker(self):
        """bind_task.py binds on a graph task id in the subject. A prompt that asks
        for a task without one produces a native task the organization cannot
        attribute -- which is `unknown`, not a failure, so it would fail silently."""
        source = open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8").read()
        prompts = source.split("MECHANISM_PROMPTS")[1].split("def ")[0]
        self.assertIn("TaskCreate", prompts)
        self.assertIn("T-001", prompts)

    def test_the_capability_model_records_the_corrected_cause(self):
        caps = load("policies/platform-capabilities.json")["capabilities"]
        entry = caps["headless.native_task_tools"]
        self.assertTrue(entry["available"],
                        "the tools are reachable; the earlier entry blamed headless mode")
        self.assertIn("CLAUDE_CODE_ENABLE_TODO_TOOLS", entry["note"])
        self.assertIn("model that gates them, not the execution mode", entry["note"])


class TestALiveRunMeasuresTheOrganizationAndNotTheMachine(unittest.TestCase):
    """A certification that inherits the operator's settings measures the operator.

    The harness writes this plugin's hooks into a throwaway project and then asks
    whether they behave correctly. Without --setting-sources it also loaded the
    operator's own ~/.claude settings and auto-memory, so a personal permission
    rule or a remembered preference could change the result and nothing would say
    that it had.

    --max-turns is the other half. The agent loop runs until the model stops
    calling tools, and the organization's retry bound applies only between
    attempts -- a session that never returns is invisible to it until the process
    exits.
    """

    def session_flags(self):
        import ast
        with open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_session")
        return {n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}

    def test_the_session_loads_only_the_project_s_settings(self):
        flags = self.session_flags()
        self.assertIn("--setting-sources", flags)
        self.assertIn("project", flags)

    def test_the_session_is_bounded(self):
        self.assertIn("--max-turns", self.session_flags())

    def test_the_reason_is_written_down(self):
        source = open(os.path.join(ROOT, "scripts", "certify.py"), encoding="utf-8").read()
        self.assertIn("measuring the machine", source)


class TestASyntheticUnitCannotLookReal(unittest.TestCase):
    def test_a_synthetic_unit_names_no_model(self):
        """Naming a model on a unit nothing ran is the conflation in miniature."""
        project = self.golden_copy()
        units, wid, failure = certify.synthetic_units(project)
        self.assertIsNone(failure, failure)
        self.assertTrue(units)
        for u in units:
            self.assertEqual(u["evidence"], "synthetic")
            self.assertIsNone(u["model"])

    def test_a_synthetic_unit_is_incomplete_never_passing(self):
        """A stage nobody executed has not failed and has not passed."""
        project = self.golden_copy()
        units, _, _ = certify.synthetic_units(project)
        for u in units:
            self.assertIn(u["dod"]["result"], ("incomplete", "fail"))
            self.assertEqual(u["outcome"], "not-run")

    def golden_copy(self):
        tmp = tempfile.mkdtemp(prefix="aieos-cert-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        return certify.materialise(os.path.join(tmp, "p"))


class TestTheGoldenProjectIsReal(unittest.TestCase):
    """A fixture that gestures at a project proves less than no fixture, because it
    reads as evidence."""

    def test_its_configuration_validates_with_no_warnings(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate_project_config.py"),
             os.path.join(GOLDEN, ".ai-engineering", "project.yaml")],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 error(s), 0 warning(s)", proc.stdout)

    def test_its_own_tests_pass(self):
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=GOLDEN, capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_it_has_working_code_and_not_a_placeholder(self):
        sys.path.insert(0, os.path.join(GOLDEN, "src"))
        import datetime
        from retention import Record, RetentionPolicy, decide
        created = datetime.date(2026, 1, 1)
        held = decide(Record("r", created, on_legal_hold=True), RetentionPolicy(30),
                      created + datetime.timedelta(days=999))
        self.assertFalse(held.deletable)
        self.assertEqual(held.rule, "legal-hold")

    def test_it_introduces_no_component_its_requirements_do_not_ask_for(self):
        """It is the project certification runs against, so it has to be the kind of
        project this organization says to build."""
        with open(os.path.join(GOLDEN, ".ai-engineering", "project.yaml"),
                  encoding="utf-8") as fh:
            cfg = fh.read()
        for absent in ("postgresql", "kafka", "redis", "rabbitmq", "elasticsearch"):
            self.assertNotIn(absent, cfg.lower())


class TestTheRunRecord(unittest.TestCase):
    def test_the_kept_run_validates_against_its_schema(self):
        schema = load("schemas/certification-run.schema.json")
        errors = list(jsvalidate(load("golden/certification-run.json"), schema))
        self.assertEqual(errors, [], errors[:4])

    def test_the_kept_run_is_not_claimed_as_certified(self):
        """It is kept so the documentation's claims can be checked rather than
        believed, which only works while it is honest about what it did not do."""
        rec = load("golden/certification-run.json")
        self.assertFalse(rec["verdict"]["certified"])
        self.assertIn(rec["verdict"]["real_agent"], ("partial", "not-run", "fail"))

    def test_the_kept_run_carries_real_agent_evidence(self):
        """And honest about what it did. A record with no real units would make the
        certification path indistinguishable from the simulation."""
        rec = load("golden/certification-run.json")
        real = [u for u in rec["units"] if u["evidence"] == "real-agent"]
        self.assertTrue(real, "no real-agent unit in the kept run")
        self.assertTrue(any(p["result"] == "pass" for p in rec["probes"]))

    def test_the_kept_run_names_the_versions_it_ran_against(self):
        rec = load("golden/certification-run.json")
        self.assertTrue(rec["claude_code_version"])
        self.assertTrue(rec["plugin_version"])

    def test_execution_actual_was_observed_to_differ_from_resolved(self):
        """`actual` is only worth recording if it can disagree with `resolved`. A run
        where they always match is consistent with actual being copied and never
        observed."""
        rec = load("golden/certification-run.json")
        real = [u for u in rec["units"] if u["evidence"] == "real-agent"]
        diverged = [u for u in real
                    if (u.get("execution") or {}).get("actual")
                    and u["execution"]["actual"] != u["execution"].get("resolved")]
        self.assertTrue(diverged, "no real unit recorded an actual that differs from resolved")

    def test_no_probe_accepts_a_session_s_own_account_as_evidence(self):
        """Except one, which is allowed because it tests for a value the prompt never
        contained -- a model cannot report a string it was never given."""
        rec = load("golden/certification-run.json")
        for p in rec["probes"]:
            with self.subTest(probe=p["id"]):
                if p["id"] == "the-agent-knew-what-was-not-in-its-prompt":
                    continue
                self.assertNotIn("self-report", p["evidence_source"])
                self.assertNotIn("the session said", p["evidence_source"])


class TestTheSyntheticPathRunsOffline(unittest.TestCase):
    def test_it_completes_and_refuses_to_certify(self):
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "certify.py")],
                              capture_output=True, text=True, cwd=ROOT, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("CERTIFIED  : no", proc.stdout)
        self.assertIn("real-agent : not-run", proc.stdout)

    def test_it_is_in_the_check_suite(self):
        with open(os.path.join(ROOT, "scripts", "check_all.sh"), encoding="utf-8") as fh:
            self.assertIn("certify.py", fh.read())


if __name__ == "__main__":
    unittest.main()
