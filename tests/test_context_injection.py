"""The two hooks that make the control loop work at runtime.

SubagentStart injects the work item; SubagentStop records what came back. Both
were verified empirically against Claude Code 2.1.237 before being built:
SubagentStart's additionalContext does reach the subagent, and SubagentStop does
carry last_assistant_message. TaskCreated and TaskCompleted exist in the binary
but fire for neither an Agent spawn nor a todo list, which is why nothing here
depends on them.
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


class Hooked(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-ctx-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w") as fh:
            fh.write(cfg)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                        "open", "--project", self.project, "--type", "feature",
                        "--risk", "HIGH", "--intent", "Partners time out on large transfers"],
                       capture_output=True, timeout=120)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                        "plan", "--project", self.project, "--item", "SFTP-FEAT-001"],
                       capture_output=True, timeout=120)

    def hook(self, script, payload):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=self.project)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "hooks", "scripts", script)],
            input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, "a hook must always exit 0: " + proc.stderr[-300:])
        return json.loads(proc.stdout) if proc.stdout.strip() else None


class TestContextInjection(Hooked):
    def start(self, agent_type):
        return self.hook("inject_context.py",
                         {"hook_event_name": "SubagentStart", "agent_type": agent_type,
                          "agent_id": "a1"})

    def test_an_agent_receives_its_work_item(self):
        out = self.start("product-manager")
        self.assertIsNotNone(out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("SFTP-FEAT-001", ctx)
        self.assertIn("Partners time out", ctx)

    def test_it_receives_its_own_task_and_not_the_whole_graph(self):
        ctx = self.start("product-manager")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Requirement discovery", ctx)
        self.assertNotIn("Release planning", ctx,
                         "the product manager was handed the release manager's task")

    def test_intent_and_objective_both_reach_the_agent(self):
        """An agent that only sees the organization's restatement cannot notice
        that the restatement is wrong."""
        ctx = self.start("product-manager")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("requester's words", ctx)
        self.assertIn("organization understood", ctx)

    def test_a_previous_failure_is_carried_into_the_retry(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                        "observe", "--project", self.project, "--item", "SFTP-FEAT-001",
                        "--task", "T-002", "--outcome", "failed",
                        "--detail", "the target has no measurable indicator"],
                       capture_output=True, timeout=120)
        ctx = self.start("product-manager")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Attempt 2 of 3", ctx)
        self.assertIn("no measurable indicator", ctx)

    def test_a_coupled_surface_is_flagged_to_whoever_touches_it(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        t = graph["tasks"][2]
        t["coupled_surface"] = "api-contract"
        role = t["role"]
        W.save_graph(self.project, graph)
        ctx = self.start(role)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("api-contract", ctx)
        self.assertIn("raise it rather than changing it", ctx)

    def test_it_says_nothing_when_no_work_item_is_active(self):
        """A session doing something other than a tracked change is a normal
        session, not an error."""
        os.remove(os.path.join(self.project, ".ai-engineering", "work", "CURRENT"))
        self.assertIsNone(self.start("product-manager"))

    def test_an_unknown_role_gets_the_item_but_no_task(self):
        ctx = self.start("docs-writer")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("SFTP-FEAT-001", ctx)
        self.assertNotIn("## Your task", ctx)


class TestSubagentObservation(Hooked):
    def stop(self, agent_type, message):
        return self.hook("observe_subagent.py",
                         {"hook_event_name": "SubagentStop", "agent_type": agent_type,
                          "agent_id": "a1", "last_assistant_message": message})

    def test_a_thin_result_is_called_out(self):
        """A subagent that stops without saying anything useful looks identical to
        one that succeeded, unless something outside it is watching."""
        out = self.stop("product-manager", "done")
        self.assertIsNotNone(out)
        self.assertIn("little or no result", out["systemMessage"])

    def test_a_real_result_is_recorded_without_comment(self):
        self.assertIsNone(self.stop(
            "product-manager",
            "Produced SFTP-REQ-001 with four acceptance criteria and SFTP-NFR-001 "
            "quantifying the transfer success target at 99.5% over 30 days."))

    def test_the_result_is_attributed_to_the_task(self):
        self.stop("product-manager",
                  "Produced SFTP-REQ-001 with four acceptance criteria and the "
                  "non-functional target quantified at 99.5% over 30 days.")
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        self.assertIn("SFTP-REQ-001", W.task(graph, "T-002")["result"])
        stops = [h for h in W.history(self.project, "SFTP-FEAT-001")
                 if h["kind"] == "subagent_stopped"]
        self.assertEqual(stops[0]["tasks"], ["T-002"])

    def test_it_never_blocks_a_stop(self):
        for msg in ("", "done", "x" * 5000):
            with self.subTest(msg=msg[:12]):
                out = self.stop("product-manager", msg)
                self.assertTrue(out is None or "decision" not in out,
                                "the observer tried to block a stop it had no business blocking")
