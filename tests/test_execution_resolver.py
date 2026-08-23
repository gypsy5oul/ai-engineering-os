"""Execution mode is chosen when the task runs, not when the workflow was written.

A declared mode is a recommendation made before the situation existed. The tests
that matter are the ones where a fact overrules it.
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


class Resolver(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-exec-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        with open(os.path.join(ROOT, "templates", "project", "project.yaml")) as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w") as fh:
            fh.write(cfg)
        for sub, extra in (("open", ["--type", "feature", "--risk", "HIGH",
                                     "--intent", "Resumable partner transfers"]),
                           ("plan", ["--item", "SFTP-FEAT-001"])):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
                            sub, "--project", self.project] + extra,
                           capture_output=True, timeout=120)

    def resolved(self, teams=False):
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
        if teams:
            env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "resolve_execution.py"),
             "--project", self.project, "--item", "SFTP-FEAT-001", "--all", "--json"],
            capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-300:])
        return {r["task"]: r for r in json.loads(proc.stdout)}

    def graph(self):
        return W.load_graph(self.project, "SFTP-FEAT-001")

    def team_task(self):
        return next(t for t in self.graph()["tasks"] if t.get("execution") == "team")


class TestDegradation(Resolver):
    def test_a_team_stage_degrades_when_teams_are_not_available(self):
        """Teams are experimental, off by default and interactive-only. Nothing in
        the lifecycle may depend on them."""
        tid = self.team_task()["id"]
        r = self.resolved(teams=False)[tid]
        self.assertEqual(r["resolved"], "subagent")
        self.assertTrue(r["changed"])
        self.assertIn("EXPERIMENTAL_AGENT_TEAMS", r["why"])

    def allow_teams(self):
        path = os.path.join(self.project, ".ai-engineering", "project.yaml")
        with open(path, encoding="utf-8") as fh:
            cfg = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cfg.replace("agent_teams_available: false", "agent_teams_available: true"))

    def test_it_stands_when_teams_are_available(self):
        self.allow_teams()
        tid = self.team_task()["id"]
        self.assertEqual(self.resolved(teams=True)[tid]["resolved"], "team")

    def test_the_project_can_veto_teams_even_when_the_environment_allows_them(self):
        """Both halves have to agree. The shipped template says unavailable, which
        is why the environment variable alone is not enough."""
        tid = self.team_task()["id"]
        r = self.resolved(teams=True)[tid]
        self.assertEqual(r["resolved"], "subagent")
        self.assertIn("project records", r["why"])


class TestIsolationIsNotFree(Resolver):
    def test_a_reviewer_with_no_write_tools_is_not_isolated(self):
        """A worktree protects files the role could not have touched."""
        g = self.graph()
        t = next(x for x in g["tasks"] if x["role"] == "code-reviewer")
        t["execution"] = "worktree"
        W.save_graph(self.project, g)
        r = self.resolved()[t["id"]]
        self.assertEqual(r["resolved"], "subagent")
        self.assertIn("no write tools", r["why"])

    def test_a_writer_alongside_a_running_sibling_is_isolated(self):
        g = self.graph()
        writer = next(x for x in g["tasks"] if x["role"] == "development-lead")
        other = next(x for x in g["tasks"] if x["id"] != writer["id"])
        other["state"] = "working"
        W.save_graph(self.project, g)
        self.assertEqual(self.resolved()[writer["id"]]["resolved"], "worktree")

    def test_a_writer_alone_is_not_isolated(self):
        g = self.graph()
        writer = next(x for x in g["tasks"] if x["role"] == "development-lead")
        W.save_graph(self.project, g)
        self.assertNotEqual(self.resolved()[writer["id"]]["resolved"], "worktree")

    def test_two_tasks_on_one_surface_are_isolated_rather_than_sequenced(self):
        """The parallelism survives and the integration becomes an explicit step."""
        g = self.graph()
        # Both must be roles that can write: the read-only rule fires first, and
        # correctly so -- there is nothing to isolate for a reviewer.
        writers = [x for x in g["tasks"] if x["role"] in ("development-lead", "sre",
                                                          "devops-engineer")]
        a, b = writers[0], writers[1]
        a["coupled_surface"] = b["coupled_surface"] = "database-schema"
        b["state"] = "working"
        W.save_graph(self.project, g)
        r = self.resolved()[a["id"]]
        self.assertEqual(r["resolved"], "worktree")
        self.assertIn("database-schema", r["why"])


class TestRiskOverrules(Resolver):
    def test_critical_work_is_not_sent_to_the_background(self):
        """The point of the risk tier is that somebody is watching, and a
        background task is precisely the one nobody is."""
        g = self.graph()
        t = g["tasks"][3]
        t["execution"], t["risk"] = "background", "CRITICAL"
        W.save_graph(self.project, g)
        r = self.resolved()[t["id"]]
        self.assertEqual(r["resolved"], "subagent")
        self.assertIn("nobody is watching", r["why"])
