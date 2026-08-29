"""Decomposing a stage into the tasks it actually is.

The judgement is an agent's; the rules, the graph and the refusal are the
organization's. These tests are mostly about the refusals, because a
decomposition that is grafted in when it should not be is a stage nobody owes.
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
import workitem as W  # noqa: E402


def synth(project, item, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
         "--project", project, "--item", item] + list(args),
        capture_output=True, text=True, timeout=120)


class Synthesis(unittest.TestCase):
    ITEM = "SFTP-FEAT-001"

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-syn-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Build a SIM activation service"],
                     ["plan", "--item", self.ITEM]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)

    def graph(self):
        return W.load_graph(self.project, self.ITEM)

    def a_stage_producing(self, *codes):
        """A queued stage task that owes exactly these artifacts."""
        for t in self.graph()["tasks"]:
            if set(t.get("produces") or []) == set(codes):
                return t
        raise unittest.SkipTest("no stage in the fixture produces %s" % (codes,))

    # A decomposition review that satisfies policies/decomposition-review.json, so a
    # test about a structural rule reaches that rule rather than stopping at the
    # review gate. The answers are deliberately thin: what the checker verifies is
    # that every dimension was answered and that the reviewer is not the proposer,
    # and a test that supplied thoughtful prose would be testing nothing extra.
    REVIEW = {
        "reviewer": "engineering-director",
        "verdict": "sound",
        "dimensions": {
            "cohesion": "each child produces one artifact",
            "coupling": "the two followers read the contract and nothing else",
            "parallelizability": "adr and sec run together once api lands",
            "task_size": "one sitting each",
            "ownership": "the roles that own these artifacts",
            "handoff_cost": "one contract, handed over once",
            "integration_cost": "the parent is the checkpoint; nothing to merge",
        },
    }

    # A decomposition review, for proposals whose parent needs one. These tests
    # predate the review and exercise the structural rules; attaching a default
    # keeps each of them testing what it was written to test. The review's own
    # behaviour -- absent, incomplete, self-reviewed -- is in
    # tests/test_decomposition_review.py.
    REVIEW = {
        "reviewer": "engineering-director",
        "verdict": "sound",
        "dimensions": {d: "answered for the purposes of this fixture" for d in
                       ("cohesion", "coupling", "parallelizability", "task_size",
                        "ownership", "handoff_cost", "integration_cost")},
    }

    def propose(self, payload, *extra, **kw):
        if kw.get("review", True) and "review" not in payload:
            payload = dict(payload, review=self.REVIEW)
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
             "--project", self.project, "--item", self.ITEM, "--from", "-"] + list(extra),
            input=json.dumps(payload), capture_output=True, text=True, timeout=120)


class TestDerivedSynthesis(Synthesis):
    """Reading the artifact model is not the same as guessing a split."""

    def test_a_stage_owned_by_two_roles_splits_along_that(self):
        t = self.a_stage_producing("TP", "TEST")
        proc = synth(self.project, self.ITEM, "--task", t["id"], "--derive")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        kids = W.children_of(self.graph(), t["id"])
        self.assertEqual(len(kids), 2)
        self.assertEqual(sorted(c["role"] for c in kids), ["qa-engineer", "qa-lead"])

    def test_it_refuses_rather_than_inventing_a_split(self):
        """One role owning everything the stage produces is not a split the
        artifact model contains."""
        single = next(t for t in self.graph()["tasks"]
                      if len(t.get("produces") or []) == 1 and t["state"] == "queued")
        proc = synth(self.project, self.ITEM, "--task", single["id"], "--derive")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no split to derive", proc.stdout)

    def test_it_refuses_when_a_shared_surface_has_no_derivable_owner(self):
        t = self.a_stage_producing("ARCH", "ADR", "SEC")
        proc = synth(self.project, self.ITEM, "--task", t["id"], "--derive")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("surface", proc.stdout)

    def test_a_dry_run_writes_nothing(self):
        t = self.a_stage_producing("TP", "TEST")
        synth(self.project, self.ITEM, "--task", t["id"], "--derive", "--dry-run")
        self.assertEqual(W.children_of(self.graph(), t["id"]), [])


class TestTheParentSurvives(Synthesis):
    """Replacing a stage with its children would delete the stage gate and every
    downstream edge that pointed at it."""

    def setUp(self):
        Synthesis.setUp(self)
        self.parent = self.a_stage_producing("TP", "TEST")
        self.before = dict(self.parent)
        synth(self.project, self.ITEM, "--task", self.parent["id"], "--derive")
        self.after = W.task(self.graph(), self.parent["id"])

    def test_the_parent_keeps_its_definition_of_done(self):
        self.assertEqual(self.after.get("definition_of_done"),
                         self.before.get("definition_of_done"))

    def test_the_parent_waits_for_every_child(self):
        kids = [c["id"] for c in W.children_of(self.graph(), self.parent["id"])]
        for k in kids:
            self.assertIn(k, self.after["depends_on"])

    def test_downstream_still_depends_on_the_parent(self):
        downstream = [t for t in self.graph()["tasks"]
                      if self.parent["id"] in (t.get("depends_on") or [])
                      and not t.get("parent")]
        self.assertTrue(downstream, "nothing downstream still points at the stage")

    def test_children_inherit_the_stage_entry_conditions(self):
        for c in W.children_of(self.graph(), self.parent["id"]):
            for dep in self.before.get("depends_on") or []:
                self.assertIn(dep, c["depends_on"],
                              "a child could start before its stage could have")

    def test_the_parent_is_not_runnable_until_its_children_are_done(self):
        graph = self.graph()
        for t in graph["tasks"]:
            if t["id"] != self.parent["id"] and not t.get("parent"):
                t["state"] = "accepted"
        W.save_graph(self.project, graph)
        self.assertNotIn(self.parent["id"], [t["id"] for t in W.runnable(self.graph())])
        graph = self.graph()
        for c in W.children_of(graph, self.parent["id"]):
            c["state"] = "accepted"
        W.save_graph(self.project, graph)
        self.assertIn(self.parent["id"], [t["id"] for t in W.runnable(self.graph())])


class TestTheSplitActuallyParallelises(Synthesis):
    """The reason to decompose at all. A split whose children serialise has
    changed the shape of the graph and none of its behaviour."""

    def test_independent_children_are_offered_together(self):
        parent = self.a_stage_producing("TP", "TEST")
        synth(self.project, self.ITEM, "--task", parent["id"], "--derive")
        graph = self.graph()
        for t in graph["tasks"]:
            if not t.get("parent") and t["id"] != parent["id"]:
                t["state"] = "accepted"
        W.save_graph(self.project, graph)
        offered = [t["id"] for t in W.runnable(self.graph())]
        kids = [c["id"] for c in W.children_of(self.graph(), parent["id"])]
        self.assertEqual(sorted(offered), sorted(kids),
                         "the children did not become available at the same time")

    def test_a_shared_surface_still_admits_one_owner(self):
        parent = self.a_stage_producing("ARCH", "ADR", "SEC")
        proc = self.propose({
            "parent": parent["id"],
            "rationale": "The contract is designed first; the record and the threat model follow.",
            "children": [
                {"key": "api", "title": "Design the activation API contract",
                 "role": "solution-architect", "produces": ["ARCH"],
                 "coupled_surface": parent["coupled_surface"]},
                {"key": "adr", "title": "Record the activation decisions",
                 "role": "solution-architect", "produces": ["ADR"], "depends_on": ["api"]},
                {"key": "sec", "title": "Threat model the activation credentials",
                 "role": "security-architect", "produces": ["SEC"], "depends_on": ["api"]},
            ],
            "review": self.REVIEW})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        kids = {c["id"]: c for c in W.children_of(self.graph(), parent["id"])}
        holders = [c for c in kids.values() if c.get("coupled_surface")]
        self.assertEqual(len(holders), 1, "the surface must have exactly one owner")


class TestTheRulesRefuse(Synthesis):
    def parent_and(self, **override):
        parent = self.a_stage_producing("TP", "TEST")
        base = {
            "parent": parent["id"],
            "children": [
                {"key": "plan", "title": "Write the test plan", "role": "qa-lead",
                 "produces": ["TP"]},
                {"key": "tests", "title": "Write the automated tests", "role": "qa-engineer",
                 "produces": ["TEST"]},
            ]}
        base.update(override)
        return parent, base

    def refusal(self, payload):
        proc = self.propose(payload)
        self.assertEqual(proc.returncode, 1, "this should have been refused:\n" + proc.stdout)
        return proc.stdout

    def test_ts01_a_dropped_artifact(self):
        parent, p = self.parent_and()
        p["children"][1]["produces"] = ["TP"]
        self.assertIn("TS-01", self.refusal(p))

    def test_ts01_an_artifact_the_stage_does_not_owe(self):
        parent, p = self.parent_and()
        p["children"][1]["produces"] = ["TEST", "ARCH"]
        self.assertIn("TS-01", self.refusal(p))

    def test_ts02_an_unknown_role(self):
        parent, p = self.parent_and()
        p["children"][1]["role"] = "quality-wizard"
        self.assertIn("TS-02", self.refusal(p))

    def test_ts02_a_role_that_cannot_write_what_it_is_given(self):
        parent, p = self.parent_and()
        p["children"][1]["role"] = "docs-writer"
        self.assertIn("TS-02", self.refusal(p))

    def test_ts03_risk_cannot_be_lowered(self):
        parent, p = self.parent_and()
        p["children"][0]["risk"] = "LOW"
        self.assertIn("TS-03", self.refusal(p))

    def test_ts03_risk_may_be_raised(self):
        parent, p = self.parent_and()
        p["children"][0]["risk"] = "CRITICAL"
        proc = self.propose(p)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_ts04_a_dependency_outside_the_stage(self):
        parent, p = self.parent_and()
        p["children"][1]["depends_on"] = ["T-001"]
        self.assertIn("TS-04", self.refusal(p))

    def test_ts04_a_cycle_between_siblings(self):
        parent, p = self.parent_and()
        p["children"][0]["depends_on"] = ["tests"]
        p["children"][1]["depends_on"] = ["plan"]
        self.assertIn("TS-04", self.refusal(p))

    def test_ts05_an_invented_predicate(self):
        parent, p = self.parent_and()
        p["children"][0]["definition_of_done"] = ["looks_fine(TP)"]
        self.assertIn("TS-05", self.refusal(p))

    def test_ts05_a_real_predicate_with_the_wrong_arity(self):
        parent, p = self.parent_and()
        p["children"][0]["definition_of_done"] = ["artifact_exists(TP, extra)"]
        self.assertIn("TS-05", self.refusal(p))

    def test_ts06_decomposing_twice(self):
        parent, p = self.parent_and()
        self.assertEqual(self.propose(p).returncode, 0)
        self.assertIn("TS-06", self.refusal(p))

    def test_ts06_decomposing_a_child(self):
        parent, p = self.parent_and()
        self.propose(p)
        child = W.children_of(self.graph(), parent["id"])[0]
        deeper = {"parent": child["id"], "children": [
            {"key": "a", "title": "Half of the test plan", "role": "qa-lead"},
            {"key": "b", "title": "The other half of it", "role": "qa-lead"}]}
        self.assertIn("TS-06", self.refusal(deeper))

    def test_ts08_a_surface_left_unowned(self):
        parent = self.a_stage_producing("ARCH", "ADR", "SEC")
        p = {"parent": parent["id"], "children": [
            {"key": "a", "title": "Design the activation API", "role": "solution-architect",
             "produces": ["ARCH", "ADR"]},
            {"key": "b", "title": "Threat model the credentials", "role": "security-architect",
             "produces": ["SEC"]}]}
        self.assertIn("TS-08", self.refusal(p))

    def test_a_refusal_writes_nothing(self):
        parent, p = self.parent_and()
        p["children"][1]["produces"] = ["TP"]
        self.propose(p)
        self.assertEqual(W.children_of(self.graph(), parent["id"]), [])
        self.assertIsNone(W.task(self.graph(), parent["id"]).get("synthesis"))

    def test_a_stage_already_underway_is_not_decomposed(self):
        parent, p = self.parent_and()
        graph = self.graph()
        W.task(graph, parent["id"])["state"] = "working"
        W.save_graph(self.project, graph)
        self.assertIn("TS-07", self.refusal(p))


class TestItIsRecorded(Synthesis):
    def test_the_decomposition_is_in_the_history_with_its_reasoning(self):
        parent = self.a_stage_producing("TP", "TEST")
        proc = self.propose({
            "parent": parent["id"],
            "rationale": "The plan is reviewed before the tests are written against it.",
            "children": [
                {"key": "plan", "title": "Write the test plan", "role": "qa-lead",
                 "produces": ["TP"]},
                {"key": "tests", "title": "Write the automated tests", "role": "qa-engineer",
                 "produces": ["TEST"], "depends_on": ["plan"]},
            ]}, "--proposed-by", "qa-lead")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        events = [h for h in W.history(self.project, self.ITEM) if h["kind"] == "synthesized"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["mode"], "proposed")
        self.assertEqual(events[0]["proposed_by"], "qa-lead")
        self.assertIn("reviewed before", events[0]["rationale"])
        got = W.task(self.graph(), parent["id"])["synthesis"]
        self.assertEqual(got["mode"], "proposed")
        self.assertEqual(len(got["children"]), 2)


if __name__ == "__main__":
    unittest.main()
