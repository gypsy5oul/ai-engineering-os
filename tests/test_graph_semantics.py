"""The invariants a task graph must satisfy that its schema cannot express.

These checks existed, scattered across workitem.py, control_loop.py, the hooks
and five test files, which means the next field added to the graph would be
missed by whichever of those places nobody thought about. One validator, and a
test per invariant that breaks the graph deliberately and requires the finding.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validate_graph_semantics as V  # noqa: E402
import workitem as W  # noqa: E402
import yamlemit  # noqa: E402


class Semantics(unittest.TestCase):
    ITEM = "SFTP-FEAT-001"

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-sem-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Semantic invariants of the task graph"],
                     ["plan", "--item", self.ITEM]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)

    def break_it(self, mutate):
        """Write a deliberately invalid graph, past save_graph's schema check."""
        graph = W.load_graph(self.project, self.ITEM)
        mutate(graph, lambda tid: W.task(graph, tid))
        path = os.path.join(self.project, ".ai-engineering", "work", self.ITEM, "graph.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(yamlemit.dump_document(W._stringify_dates(graph)))
        return graph

    def findings(self):
        graph = W.load_graph(self.project, self.ITEM)
        item = W.load_item(self.project, self.ITEM)
        return V.invariants(self.project, self.ITEM, graph, item)

    def names(self):
        return {name for _, name, _ in self.findings()}

    def assertCatches(self, invariant, mutate):
        self.break_it(mutate)
        self.assertIn(invariant, self.names())


class TestAHealthyGraphIsQuiet(Semantics):
    def test_a_freshly_planned_graph_has_no_findings(self):
        self.assertEqual(self.findings(), [],
                         "a validator that fires on a correct graph will be switched off")

    def test_the_command_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate_graph_semantics.py"),
             "--project", self.project, "--item", self.ITEM],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)


class TestStructure(Semantics):
    def test_a_missing_parent(self):
        self.assertCatches("parent_exists", lambda g, t: t("T-003").update({"parent": "T-999"}))

    def test_a_task_that_is_its_own_parent(self):
        self.assertCatches("parent_is_not_self",
                           lambda g, t: t("T-003").update({"parent": "T-003"}))

    def test_a_missing_dependency(self):
        self.assertCatches("dependency_exists",
                           lambda g, t: t("T-004").update({"depends_on": ["T-404"]}))

    def test_a_self_dependency(self):
        self.assertCatches("no_self_dependency",
                           lambda g, t: t("T-004").update({"depends_on": ["T-004"]}))

    def test_a_cycle(self):
        def mutate(g, t):
            t("T-011")["depends_on"] = ["T-012"]
            t("T-012")["depends_on"] = ["T-011"]
        self.assertCatches("acyclic", mutate)

    def test_two_levels_of_decomposition(self):
        def mutate(g, t):
            t("T-003")["parent"] = "T-002"
            t("T-002")["parent"] = "T-001"
        self.assertCatches("one_level_of_decomposition", mutate)


class TestRuntimeOwnership(Semantics):
    def test_one_agent_holding_two_tasks(self):
        def mutate(g, t):
            for tid in ("T-001", "T-002"):
                t(tid).update({"owner_agent": "agent-X", "state": "working"})
        self.assertCatches("one_agent_one_task", mutate)

    def test_a_session_with_no_agent(self):
        def mutate(g, t):
            t("T-005").pop("owner_agent", None)
            t("T-005")["owner_session"] = "S9"
        self.assertCatches("no_session_without_an_agent", mutate)

    def test_a_terminal_task_still_holding_a_lease(self):
        def mutate(g, t):
            t("T-001").update({"state": "abandoned", "owner_agent": "agent-Z"})
        self.assertCatches("terminal_tasks_hold_no_lease", mutate)

    def test_one_native_task_bound_to_two_graph_tasks(self):
        def mutate(g, t):
            t("T-007")["native_task"] = "n1"
            t("T-008")["native_task"] = "n1"
        self.assertCatches("one_native_task_one_graph_task", mutate)

    def test_an_expired_lease_that_was_never_reclaimed(self):
        def mutate(g, t):
            t("T-001").update({"owner_agent": "agent-DEAD", "state": "working",
                               "last_activity": "2020-01-01T00:00:00"})
        self.assertCatches("no_authoritative_expired_lease", mutate)


class TestExecutionTruthfulness(Semantics):
    def test_actual_without_evidence(self):
        self.assertCatches("actual_requires_evidence", lambda g, t: t("T-006").update(
            {"execution": {"declared": "subagent", "actual": "team"}}))

    def test_actual_both_known_and_unknown(self):
        self.assertCatches("actual_is_not_both_known_and_unknown", lambda g, t: t("T-006").update(
            {"execution": {"declared": "subagent", "actual": "team",
                           "actual_evidence": "something", "actual_undetermined": "or not"}}))

    def test_a_resolution_with_no_reason(self):
        self.assertCatches("a_resolution_says_why", lambda g, t: t("T-006").update(
            {"execution": {"declared": "subagent", "resolved": "worktree"}}))


class TestAcceptance(Semantics):
    def test_accepted_over_a_failing_contract(self):
        self.assertCatches("accepted_means_the_contract_was_met",
                           lambda g, t: t("T-010").update({"state": "accepted"}))

    def test_an_accepted_parent_with_open_children(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
                        "--project", self.project, "--item", self.ITEM, "--task", "T-008",
                        "--derive", "--no-infer"], capture_output=True, timeout=180)

        def mutate(g, t):
            t("T-008").update({"state": "accepted", "definition_of_done": []})
        self.assertCatches("accepted_parent_has_accepted_children", mutate)

    def test_unanswerable_predicates_on_accepted_high_risk_work(self):
        def mutate(g, t):
            t("T-010").update({"state": "accepted", "risk": "HIGH",
                               "definition_of_done": ["looks_fine(REQ)"]})
        self.assertCatches("unanswerable_is_not_satisfied", mutate)


class TestDerivedDependencies(Semantics):
    def test_a_derived_dependency_pointing_nowhere(self):
        self.assertCatches("derived_dependency_exists", lambda g, t: t("T-004").update(
            {"derived_depends_on": [{"task": "T-404", "signal": "import_edge",
                                     "evidence": "x"}]}))

    def test_evidence_kept_and_the_edge_dropped(self):
        self.assertCatches("derived_dependency_is_applied", lambda g, t: t("T-004").update(
            {"depends_on": [], "derived_depends_on": [
                {"task": "T-003", "signal": "import_edge", "evidence": "x"}]}))


if __name__ == "__main__":
    unittest.main()
