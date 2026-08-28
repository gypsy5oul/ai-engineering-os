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
