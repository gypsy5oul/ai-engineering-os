"""The control loop: durable work items, a dynamic task graph, bounded loops.

What these tests are really checking is that the bounds hold. A loop that can
retry forever is a hang, and a plan that can be replaced without a recorded
reason is thrashing — both look like progress from the inside, which is why they
need a test rather than a convention.
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
import workitem as W  # noqa: E402


def cl(project, sub, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), sub,
         "--project", project] + list(args),
        capture_output=True, text=True, timeout=120)


class Loop(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-cl-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)

    def open_item(self, risk="MEDIUM", wtype="feature", intent="Partners time out on transfers"):
        proc = cl(self.project, "open", "--type", wtype, "--risk", risk, "--intent", intent)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout.split()[0]


class TestDurability(Loop):
    """The session is not the system of record."""

    def test_a_work_item_survives_without_any_session(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        item = W.load_item(self.project, wid)
        graph = W.load_graph(self.project, wid)
        self.assertEqual(item["id"], wid)
        self.assertTrue(graph["tasks"])
        self.assertTrue(os.path.exists(
            os.path.join(self.project, ".ai-engineering", "work", wid, "history.jsonl")))

    def test_intent_and_objective_are_kept_apart(self):
        """So a plan that solved the wrong problem can be seen to have done so."""
        wid = self.open_item(intent="Make the transfers stop failing")
        item = W.load_item(self.project, wid)
        self.assertIn("intent", item)
        self.assertIn("objective", item)

    def test_history_is_append_only(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        before = len(W.history(self.project, wid))
        cl(self.project, "observe", "--item", wid, "--task", "T-001", "--outcome", "accepted")
        after = W.history(self.project, wid)
        self.assertGreater(len(after), before)
        self.assertEqual([h["kind"] for h in after][:2], ["opened", "planned"])


class TestPlanIsDynamic(Loop):
    """Not every change is forced through the same sequence."""

    def test_a_low_risk_change_drops_optional_stages(self):
        wid = self.open_item(risk="LOW")
        out = cl(self.project, "plan", "--item", wid).stdout
        self.assertIn("skipped", out)

    def test_a_high_risk_change_keeps_them(self):
        """optional_when is prose. No planner can read "ships no running service"
        out of a sentence of intent, so on a high-risk change the default inverts."""
        low = cl(self.project, "plan", "--item", self.open_item(risk="LOW")).stdout
        p2 = tempfile.mkdtemp(prefix="aieos-cl-")
        self.addCleanup(shutil.rmtree, p2, True)
        os.makedirs(os.path.join(p2, ".ai-engineering"))
        shutil.copy(os.path.join(self.project, ".ai-engineering", "project.yaml"),
                    os.path.join(p2, ".ai-engineering", "project.yaml"))
        cl(p2, "open", "--type", "feature", "--risk", "CRITICAL", "--intent", "Same change, higher stakes")
        high = cl(p2, "plan", "--item", "SFTP-FEAT-001").stdout
        n_low = int(low.split("planned: ")[1].split(" ")[0])
        n_high = int(high.split("planned: ")[1].split(" ")[0])
        self.assertGreater(n_high, n_low,
                           "a critical change dropped as many stages as a trivial one")

    def test_planning_twice_is_refused_without_a_reason(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        proc = cl(self.project, "plan", "--item", wid)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("replan", proc.stdout)


class TestGraphOrdering(Loop):
    def test_only_dependency_satisfied_tasks_are_offered(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        out = json.loads(cl(self.project, "next", "--item", wid, "--json").stdout)
        self.assertEqual(len(out["runnable"]), 1)
        cl(self.project, "observe", "--item", wid, "--task", "T-001", "--outcome", "accepted")
        after = json.loads(cl(self.project, "next", "--item", wid, "--json").stdout)
        self.assertEqual(after["runnable"][0]["id"], "T-002")

    def test_two_tasks_on_one_coupled_surface_are_never_both_offered(self):
        graph = {"work_item": "X", "generated_at": "", "generation": 1, "tasks": [
            {"id": "T-001", "title": "backend", "role": "r", "state": "queued",
             "coupled_surface": "api-contract"},
            {"id": "T-002", "title": "frontend", "role": "r", "state": "queued",
             "coupled_surface": "api-contract"},
            {"id": "T-003", "title": "docs", "role": "r", "state": "queued"}]}
        ids = [t["id"] for t in W.runnable(graph)]
        self.assertIn("T-001", ids)
        self.assertNotIn("T-002", ids, "two agents were offered the same contract to redefine")
        self.assertIn("T-003", ids)

    def test_work_stranded_behind_an_abandoned_task_is_named(self):
        """A graph where work waits on an abandoned task looks busy and is finished.
        Every individual task is in a legal state, so nothing else notices."""
        graph = {"work_item": "X", "generated_at": "", "generation": 1, "tasks": [
            {"id": "T-001", "title": "a", "role": "r", "state": "abandoned"},
            {"id": "T-002", "title": "b", "role": "r", "state": "queued", "depends_on": ["T-001"]},
            {"id": "T-003", "title": "c", "role": "r", "state": "queued", "depends_on": ["T-002"]}]}
        self.assertEqual(W.unreachable(graph), ["T-002", "T-003"])


class TestBoundsHold(Loop):
    def test_the_same_failure_twice_escalates(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        for _ in range(2):
            cl(self.project, "observe", "--item", wid, "--task", "T-002",
               "--outcome", "failed", "--detail", "the target has no measurable indicator")
        proc = cl(self.project, "decide", "--item", wid, "--task", "T-002")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ESCALATE", proc.stdout)
        self.assertIn("same failure twice", proc.stdout)

    def test_attempts_are_bounded(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        for i in range(3):
            cl(self.project, "observe", "--item", wid, "--task", "T-002",
               "--outcome", "failed", "--detail", "cause %d" % i)
        proc = cl(self.project, "decide", "--item", wid, "--task", "T-002")
        # Assert the behaviour and the counts, not the wording: the reason text
        # comes from policies/control-loop-policy.json now, and a test that pins
        # the prose would make the policy unable to explain itself differently.
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ESCALATE", proc.stdout)
        self.assertIn("(3 of 3)", proc.stdout)

    def test_an_exhausted_task_is_not_handed_out_again(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        for i in range(3):
            cl(self.project, "observe", "--item", wid, "--task", "T-002",
               "--outcome", "failed", "--detail", "cause %d" % i)
        out = json.loads(cl(self.project, "next", "--item", wid, "--json").stdout)
        self.assertNotIn("T-002", [t["id"] for t in out["runnable"]])

    def test_replan_is_bounded_too(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        self.assertEqual(cl(self.project, "replan", "--item", wid, "--reason", "one").returncode, 0)
        self.assertEqual(cl(self.project, "replan", "--item", wid, "--reason", "two").returncode, 0)
        proc = cl(self.project, "replan", "--item", wid, "--reason", "three")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("REFUSED", proc.stdout)

    def test_a_replan_carries_accepted_work_forward(self):
        wid = self.open_item()
        cl(self.project, "plan", "--item", wid)
        cl(self.project, "observe", "--item", wid, "--task", "T-001", "--outcome", "accepted")
        cl(self.project, "replan", "--item", wid, "--reason", "the design assumed telemetry we lack")
        graph = W.load_graph(self.project, wid)
        self.assertEqual(graph["generation"], 2)
        self.assertEqual(W.task(graph, "T-001")["state"], "accepted")
        kinds = [h for h in W.history(self.project, wid) if h["kind"] == "replanned"]
        self.assertTrue(kinds[0]["reason"], "a replan with no recorded reason is thrashing")


class TestStateMachine(unittest.TestCase):
    def test_terminal_states_are_terminal(self):
        self.assertIsNone(W.path_to("accepted", "rework"))
        self.assertIsNone(W.path_to("abandoned", "queued"))

    def test_observation_traverses_rather_than_demanding_each_step(self):
        """Refusing "this task succeeded" because nobody logged "assigned" is
        pedantry, and pedantry is what makes people bypass the tool."""
        self.assertEqual(W.path_to("queued", "accepted"),
                         ["queued", "assigned", "working", "review", "accepted"])

    def test_a_shortcut_to_accepted_is_not_discovered_by_searching(self):
        """A human accepting an escalated task is legitimate. A search finding that
        route two hops cheaper than doing the work is not."""
        route = W.path_to("queued", "accepted")
        self.assertNotIn("escalated", route)
        self.assertEqual(W.path_to("escalated", "accepted"), ["escalated", "accepted"])


class TestThePolicyIsTheAuthority(Loop):
    """The bounds live in the policy, and the code reads them.

    Regression for a defect found in this very subsystem before it was first
    committed: control_loop.py loaded the policy into a variable and then decided
    everything with a hardcoded if/elif chain. That is the same shape as
    `ai.agent_teams_available`, which sat unread for eight versions -- a file that
    reads like the authority and is decoration.
    """

    def policy(self):
        with open(os.path.join(ROOT, "policies", "control-loop-policy.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_attempt_cap_comes_from_the_policy(self):
        import shutil as _sh
        sandbox = tempfile.mkdtemp(prefix="aieos-pol-")
        self.addCleanup(_sh.rmtree, sandbox, True)
        dst = os.path.join(sandbox, "plugin")
        _sh.copytree(ROOT, dst, ignore=_sh.ignore_patterns(".git", "__pycache__"))
        path = os.path.join(dst, "policies", "control-loop-policy.json")
        with open(path, encoding="utf-8") as fh:
            pol = json.load(fh)
        pol["loops"]["implement"]["max_iterations"] = 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(pol, fh, indent=2)

        project = tempfile.mkdtemp(prefix="aieos-pol-p-")
        self.addCleanup(_sh.rmtree, project, True)
        os.makedirs(os.path.join(project, ".ai-engineering"))
        _sh.copy(os.path.join(self.project, ".ai-engineering", "project.yaml"),
                 os.path.join(project, ".ai-engineering", "project.yaml"))

        def run(sub, *a):
            return subprocess.run(
                [sys.executable, os.path.join(dst, "scripts", "control_loop.py"), sub,
                 "--project", project] + list(a), capture_output=True, text=True, timeout=120)

        run("open", "--type", "feature", "--intent", "Something that will fail")
        run("plan", "--item", "SFTP-FEAT-001")
        graph_path = os.path.join(project, ".ai-engineering", "work", "SFTP-FEAT-001", "graph.yaml")
        with open(graph_path, encoding="utf-8") as fh:
            self.assertIn("max_attempts: 1", fh.read(),
                          "the plan ignored the policy's max_iterations")

        run("observe", "--item", "SFTP-FEAT-001", "--task", "T-002",
            "--outcome", "failed", "--detail", "one failure is now enough")
        out = run("decide", "--item", "SFTP-FEAT-001", "--task", "T-002")
        self.assertIn("ESCALATE", out.stdout,
                      "lowering the policy's bound to 1 changed nothing")

    def test_every_declared_rule_can_actually_fire(self):
        """A rule in the policy with no predicate behind it is a rule that reads
        as governance and never applies."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import control_loop
        declared = {r["when"] for r in self.policy()["decide"]["rules"]}
        implemented = set(control_loop.RULE_PREDICATES)
        self.assertEqual(declared - implemented, set(),
                         "declared in the policy, implemented nowhere")
        self.assertEqual(implemented - declared, set(),
                         "implemented but the policy never declares it")

