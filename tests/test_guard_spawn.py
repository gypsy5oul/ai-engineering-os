"""Spawn guard tests: the organizational hierarchy is enforced for agents and
deliberately not enforced for the human-driven main session."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import spawn, run_hook  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = json.load(open(os.path.join(ROOT, "policies", "agent-registry.json"), encoding="utf-8"))
AGENTS = {a["name"]: a for a in REGISTRY["agents"]}


class TestHierarchy(unittest.TestCase):
    def test_permitted_spawn_allowed(self):
        for caller, target in (("development-lead", "backend-developer"),
                               ("qa-lead", "qa-engineer"),
                               ("engineering-director", "solution-architect"),
                               ("incident-commander", "rca-analyst")):
            with self.subTest(caller=caller, target=target):
                self.assertIsNone(spawn(caller, target)[0], "%s -> %s" % (caller, target))

    def test_developer_cannot_spawn_upward(self):
        for target in ("security-architect", "solution-architect", "release-manager",
                       "engineering-director"):
            with self.subTest(target=target):
                decision, reason, _, _ = spawn("backend-developer", target)
                self.assertEqual(decision, "deny", target)
                self.assertIn("development-lead", reason)

    def test_critical_roles_require_a_human(self):
        for caller in ("engineering-director", "development-lead", "agent-developer"):
            with self.subTest(caller=caller):
                decision, reason, _, _ = spawn(caller, "ai-governance")
                self.assertEqual(decision, "ask")
                self.assertIn("CRITICAL", reason)

    def test_self_spawn_denied(self):
        self.assertEqual(spawn("development-lead", "development-lead")[0], "deny")

    def test_main_session_unconstrained(self):
        for target in ("ai-governance", "backend-developer", "security-reviewer"):
            with self.subTest(target=target):
                self.assertIsNone(spawn(None, target)[0], target)

    def test_plugin_namespaced_names_resolve(self):
        payload = {"tool_name": "Agent", "agent_type": "ai-engineering-os:backend-developer",
                   "tool_input": {"subagent_type": "ai-engineering-os:security-architect"}}
        self.assertEqual(run_hook("guard_spawn", payload)[0], "deny")

    def test_registry_has_no_edge_into_critical(self):
        critical = {n for n, a in AGENTS.items() if a["risk"] == "CRITICAL"}
        for name, agent in AGENTS.items():
            for target in agent["may_spawn"]:
                self.assertNotIn(target, critical,
                                 "%s may_spawn CRITICAL role %s" % (name, target))

    def test_every_spawn_target_exists(self):
        for name, agent in AGENTS.items():
            for target in agent["may_spawn"]:
                self.assertIn(target, AGENTS, "%s may_spawn unknown %s" % (name, target))


class TestBehaviour(unittest.TestCase):
    def test_non_agent_tool_ignored(self):
        self.assertEqual(run_hook("guard_spawn", {"tool_name": "Bash", "tool_input": {}})[3], "")

    def test_malformed_input_does_not_crash(self):
        for payload in ({}, {"tool_name": "Agent"}, {"tool_name": "Agent", "tool_input": {}}):
            with self.subTest(payload=payload):
                self.assertEqual(run_hook("guard_spawn", payload)[2], 0)

    def test_denial_names_the_escalation_path(self):
        _, reason, _, _ = spawn("qa-engineer", "security-reviewer")
        self.assertIn("qa-lead", reason)


if __name__ == "__main__":
    unittest.main()


class TestConcurrencyLimit(unittest.TestCase):
    """Spawn authority says whether a role may delegate. This says how much.

    engineering-director may spawn thirteen kinds of agent. Nothing in the
    hierarchy stopped it spawning thirteen agents for a one-line change, and each
    one is a full Claude session.
    """

    def setUp(self):
        import tempfile, shutil
        self.data = tempfile.mkdtemp(prefix="aieos-cc-")
        self.addCleanup(shutil.rmtree, self.data, True)
        with open(os.path.join(ROOT, "policies", "concurrency-policy.json"), encoding="utf-8") as fh:
            self.policy = json.load(fh)

    def spawn(self, caller, target, session="S1"):
        return run_hook("guard_spawn",
                        {"tool_name": "Agent", "agent_type": caller, "session_id": session,
                         "tool_input": {"subagent_type": target}},
                        env={"CLAUDE_PLUGIN_DATA": self.data})

    def stop(self, target, session="S1"):
        return run_hook("check_artifacts",
                        {"hook_event_name": "SubagentStop", "session_id": session,
                         "agent_type": target},
                        env={"CLAUDE_PLUGIN_DATA": self.data})

    def cap(self, role):
        return (self.policy["per_role"].get(role) or {}).get(
            "max_concurrent", self.policy["default_max_concurrent"])

    def test_a_role_may_run_up_to_its_limit(self):
        cap = self.cap("development-lead")
        for i in range(cap):
            with self.subTest(spawn=i + 1):
                self.assertIsNone(self.spawn("development-lead", "backend-developer")[0])

    def test_one_past_the_limit_needs_a_decision(self):
        """Escalate, not deny: a wide fan-out is sometimes right, and the person
        running the session is the one who can tell."""
        cap = self.cap("development-lead")
        for _ in range(cap):
            self.spawn("development-lead", "backend-developer")
        decision, reason, _, _ = self.spawn("development-lead", "backend-developer")
        self.assertEqual(decision, "ask")
        self.assertIn("CC-LIMIT", reason)

    def test_finishing_work_frees_a_slot(self):
        cap = self.cap("development-lead")
        for _ in range(cap):
            self.spawn("development-lead", "backend-developer")
        self.assertEqual(self.spawn("development-lead", "backend-developer")[0], "ask")
        self.stop("backend-developer")
        self.assertIsNone(self.spawn("development-lead", "backend-developer")[0],
                          "a slot was not released when the subagent stopped")

    def test_the_session_total_is_capped_across_roles(self):
        total = self.policy["session_limit"]["max_concurrent"]
        filled = 0
        for role, target in (("development-lead", "backend-developer"),
                             ("qa-lead", "qa-engineer"),
                             ("security-architect", "security-reviewer"),
                             ("product-manager", "ux-designer")):
            while filled < total and self.spawn(role, target)[0] is None:
                filled += 1
        decision, reason, _, _ = self.spawn("product-manager", "requirements-analyst")
        self.assertEqual(decision, "ask")
        self.assertIn("session", reason.lower())

    def test_sessions_do_not_see_each_other(self):
        cap = self.cap("development-lead")
        for _ in range(cap):
            self.spawn("development-lead", "backend-developer", session="S1")
        self.assertIsNone(self.spawn("development-lead", "backend-developer", session="S2")[0],
                          "one session's fan-out constrained an unrelated session")

    def test_a_broken_ledger_never_blocks_delegation(self):
        """This is a guardrail against runaway fan-out, not a safety boundary."""
        state = os.path.join(self.data, "state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "spawns-S1.json"), "w") as fh:
            fh.write("{ not a list")
        self.assertIsNone(self.spawn("development-lead", "backend-developer")[0])

    def test_a_spawn_with_no_session_is_not_counted(self):
        """Regression: without a session id every caller shared one ledger, so
        unrelated work contended for the same slots and eventually blocked."""
        for i in range(self.cap("development-lead") + 3):
            decision, _, _, _ = run_hook(
                "guard_spawn",
                {"tool_name": "Agent", "agent_type": "development-lead",
                 "tool_input": {"subagent_type": "backend-developer"}},
                env={"CLAUDE_PLUGIN_DATA": self.data})
            with self.subTest(spawn=i + 1):
                self.assertIsNone(decision, "an unscoped spawn was counted against a limit")

    def test_the_hierarchy_still_wins_over_the_limit(self):
        """Being under the limit does not make a forbidden spawn allowed."""
        decision, _, _, _ = self.spawn("backend-developer", "engineering-director")
        self.assertEqual(decision, "deny")

