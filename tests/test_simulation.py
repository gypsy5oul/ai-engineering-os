"""End-to-end SDLC simulation.

Every other test checks that a document is well-formed. These check that the
organization can actually be operated: each scenario creates real artifacts,
emits real events, produces real rollups, and then evaluates each stage's
machine-checkable definition of done at the moment that stage completes.

A workflow that reads well but cannot be completed is a contradiction, and this
is where it surfaces. Three real defects were found this way:

  - required_fields_present treated an empty list as a missing field
  - every_linked only looked forward, which no author can satisfy at the time
    the upstream artifact is written
  - cycle_accepted was required at stages where the department's work had only
    just started
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import simulate_sdlc as sim  # noqa: E402


class TestScenarios(unittest.TestCase):
    """One test per loop, so a failure names the loop that broke."""

    def _run(self, name):
        failures, details = sim.run(name, keep=False, verbose=False)
        self.assertEqual(failures, 0,
                         "\n  " + "\n  ".join("%s %s: %s" % d for d in details))

    def test_feature_delivery(self):
        self._run("feature")

    def test_defect_loop(self):
        self._run("defect")

    def test_incident_and_rca_loop(self):
        self._run("incident")

    def test_security_block_loop(self):
        self._run("security-block")

    def test_release_and_rollback_loop(self):
        self._run("release-rollback")

    def test_agent_change_loop(self):
        self._run("agent-change")

    def test_onboarding_loop(self):
        self._run("onboarding")


class TestSimulationCoverage(unittest.TestCase):
    def test_every_workflow_is_exercised(self):
        """A workflow nobody simulates is a workflow nobody has run."""
        import glob
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        defined = set()
        for f in glob.glob(os.path.join(ROOT, "sdlc", "workflows", "*.yaml")):
            defined.add(parse_file(f)["id"])
        exercised = set()
        for name in sim.SCENARIOS:
            import tempfile, shutil
            project = tempfile.mkdtemp(prefix="aieos-cov-")
            try:
                sim.COUNTER.clear()
                sim.make_project(project)
                for workflow, stage, work in sim.SCENARIOS[name](project, lambda *_: None):
                    exercised.add(workflow)
            finally:
                shutil.rmtree(project, ignore_errors=True)
        missing = defined - exercised
        self.assertEqual(missing, set(),
                         "workflows with no simulation: %s" % sorted(missing))

    def test_every_completing_stage_is_reached_by_some_scenario(self):
        import glob, tempfile, shutil
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        completing = set()
        for f in glob.glob(os.path.join(ROOT, "sdlc", "workflows", "*.yaml")):
            wf = parse_file(f)
            for s in wf["stages"]:
                if s.get("cycle_role") == "completes":
                    completing.add((wf["id"], s["id"]))
        reached = set()
        for name in sim.SCENARIOS:
            project = tempfile.mkdtemp(prefix="aieos-cov-")
            try:
                sim.COUNTER.clear()
                sim.make_project(project)
                for workflow, stage, work in sim.SCENARIOS[name](project, lambda *_: None):
                    reached.add((workflow, stage))
            finally:
                shutil.rmtree(project, ignore_errors=True)
        gap = sorted(completing - reached)
        self.assertEqual(gap, [],
                         "department cycles that are never completed in simulation: %s" % gap)


if __name__ == "__main__":
    unittest.main()


class TestTheSimulationValidatesWhatItWrites(unittest.TestCase):
    """A proof that does not check its own output is measuring the checker.

    The simulation wrote 37 of its 49 artifacts in a shape the header schema
    rejects, while reporting every definition of done satisfied. Three separate
    drifts caused it -- the change-id pattern, seven statuses and six link kinds --
    and none was visible because nothing validated the artifacts.
    """

    def scenarios_output(self):
        import tempfile, shutil, json
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import simulate_sdlc as S
        import check_dod as C
        from jsonschema_mini import validate as jsvalidate
        root = tempfile.mkdtemp(prefix="aieos-simval-")
        self.addCleanup(shutil.rmtree, root, True)
        for name, fn in S.SCENARIOS.items():
            d = os.path.join(root, name)
            S.make_project(d)
            for _, _, work in fn(d, lambda *a, **k: None):
                work()
        with open(os.path.join(ROOT, "schemas", "artifact-header.schema.json"),
                  encoding="utf-8") as fh:
            schema = json.load(fh)
        out = []
        for base, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".md"):
                    continue
                try:
                    fm, _ = C.read_fm(os.path.join(base, f))
                except Exception:
                    continue
                if isinstance(fm, dict) and fm.get("id") and fm.get("type"):
                    out.append((fm["id"], [str(e) for e in jsvalidate(fm, schema)]))
        return out

    def test_every_artifact_the_simulation_writes_is_valid(self):
        results = self.scenarios_output()
        self.assertGreater(len(results), 20, "the simulation wrote almost nothing")
        bad = ["%s: %s" % (aid, "; ".join(errs[:2])) for aid, errs in results if errs]
        self.assertEqual(bad, [], "%d invalid artifact(s):\n  %s"
                         % (len(bad), "\n  ".join(bad[:6])))

    def test_writing_an_invalid_artifact_stops_the_simulation(self):
        """The guard, not just the current state. Without this the schema could be
        loosened and nothing would notice."""
        import tempfile, shutil, subprocess
        tmp = tempfile.mkdtemp(prefix="aieos-simmut-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = os.path.join(tmp, "plugin")
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        path = os.path.join(dst, "scripts", "simulate_sdlc.py")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body.replace('    body += ["---", "", "Simulated artifact."]',
                                  '    header["status"] = "nearly-done"\n'
                                  '    body += ["---", "", "Simulated artifact."]', 1))
        proc = subprocess.run(
            [sys.executable, os.path.join(dst, "scripts", "simulate_sdlc.py"),
             "--scenario", "feature"], cwd=dst, capture_output=True, text=True, timeout=300)
        self.assertTrue(proc.returncode != 0 or "does not satisfy" in proc.stdout + proc.stderr,
                        "an artifact with an invalid status was written without complaint")

