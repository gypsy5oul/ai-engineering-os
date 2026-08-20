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
