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
sys.path.insert(0, os.path.join(ROOT, "scripts"))


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

    def pinned_stages(self):
        """Stages the shipped template pins in ai.execution_overrides.

        The template pins ARCH: subagent, which is a real project decision and now
        actually takes effect. A test that picked the first team stage was testing
        the pin rather than the degradation it meant to.
        """
        path = os.path.join(self.project, ".ai-engineering", "project.yaml")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        block = body.split("execution_overrides:")[1].split("\n\n")[0] if \
            "execution_overrides:" in body else ""
        return {line.split(":")[0].strip() for line in block.splitlines() if ":" in line}

    def team_task(self):
        pinned = self.pinned_stages()
        return next(t for t in self.graph()["tasks"]
                    if t.get("execution") == "team" and t.get("stage") not in pinned)


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
        pinned = self.pinned_stages()
        t = next(x for x in g["tasks"] if x.get("stage") not in pinned)
        t["execution"], t["risk"] = "background", "CRITICAL"
        W.save_graph(self.project, g)
        r = self.resolved()[t["id"]]
        self.assertEqual(r["resolved"], "subagent")
        self.assertIn("nobody is watching", r["why"])


class TestResolutionIsOnTheLivePath(unittest.TestCase):
    """A correct resolver nobody calls is the defect this repository keeps
    producing. execution-policy.json named it as its enforcement for two versions
    while the spawn path never consulted it and the answer went to a terminal."""

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-exec-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Execution resolution on the live path"],
                     ["plan", "--item", "SFTP-FEAT-001"]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)

    def start(self, agent_type, agent_id="a1"):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=self.project)
        subprocess.run([sys.executable, os.path.join(ROOT, "hooks", "scripts", "inject_context.py")],
                       input=json.dumps({"hook_event_name": "SubagentStart",
                                         "agent_type": "ai-engineering-os:" + agent_type,
                                         "agent_id": agent_id, "session_id": "S1"}),
                       capture_output=True, text=True, env=env, timeout=60)
        return W.load_graph(self.project, "SFTP-FEAT-001")

    def held(self, graph, agent_id="a1"):
        return next(t for t in graph["tasks"] if t.get("owner_agent") == agent_id)

    def test_claiming_a_task_records_its_resolution(self):
        t = self.held(self.start("engineering-director"))
        self.assertIsInstance(t["execution"], dict,
                              "execution stayed a bare string, so nothing resolved")
        self.assertIn("resolved", t["execution"])
        self.assertTrue(t["execution"].get("resolved"))
        self.assertTrue(t["execution"].get("resolution_reason"))
        self.assertTrue(t["execution"].get("resolved_at"))

    def test_a_degradation_is_recorded_in_history(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        team = [t for t in graph["tasks"] if W.declared_execution(t) == "team"]
        self.assertTrue(team, "the fixture has no team-declared task to degrade")
        target = team[0]
        for t in graph["tasks"]:
            if t["id"] == target["id"]:
                t["depends_on"] = []
            else:
                t["state"] = "accepted"
        W.save_graph(self.project, graph)

        after = self.start(target["role"], agent_id="team-1")
        t = W.task(after, target["id"])
        self.assertEqual(t["execution"]["declared"], "team")
        self.assertNotEqual(t["execution"]["resolved"], "team",
                            "teams are not enabled here, so this must have degraded")
        kinds = [h["kind"] for h in W.history(self.project, "SFTP-FEAT-001")]
        self.assertIn("execution_resolved", kinds,
                      "a degradation the organization accepted was not written down")

    def test_declared_and_effective_are_different_questions(self):
        t = self.held(self.start("engineering-director"))
        W.set_execution(t, resolved="worktree")
        self.assertEqual(W.declared_execution(t), t["execution"]["declared"])
        self.assertEqual(W.effective_execution(t), "worktree")

    def test_an_isolated_resolution_flags_that_the_briefing_will_not_arrive(self):
        """An isolated spawn receives no additionalContext, so the task briefing
        this plugin exists to deliver silently does not reach the agent."""
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        t = graph["tasks"][0]
        import resolve_execution
        W.set_execution(t, declared="worktree")
        t["role"] = "backend-developer"
        resolve_execution.record_resolution(self.project, "SFTP-FEAT-001", t, graph)
        if t["execution"]["resolved"] == "worktree":
            self.assertTrue(t["execution"]["briefing_required"])
        else:
            self.assertFalse(t["execution"]["briefing_required"])

    def test_the_runtime_binding_names_every_identity(self):
        t = self.held(self.start("engineering-director"))
        b = W.runtime_binding("SFTP-FEAT-001", t)
        self.assertEqual(b["work_item"], "SFTP-FEAT-001")
        self.assertEqual(b["graph_task"], t["id"])
        self.assertEqual(b["agent_id"], "a1")
        self.assertEqual(b["session_id"], "S1")
        self.assertIn("declared", b["execution"])


class TestResolutionAppliesToDecomposedTasks(unittest.TestCase):
    """`execution` became an object in v0.23 for any task that came from a
    decomposition. The resolver kept reading the raw field, so `declared` was a
    dict, no rule matched, the dict was returned as the mode, and writing it back
    failed schema validation inside a try/except. Execution resolution silently
    did not apply to decomposed tasks for three versions."""

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-exec-child-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Execution resolution on a decomposed task"],
                     ["plan", "--item", "SFTP-FEAT-001"]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "synthesize_tasks.py"),
                        "--project", self.project, "--item", "SFTP-FEAT-001", "--task", "T-008",
                        "--derive", "--no-infer"], capture_output=True, timeout=180)

    def child(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        kids = W.children_of(graph, "T-008")
        self.assertTrue(kids, "the fixture did not decompose")
        return graph, kids[0]

    def test_the_mode_is_a_string_not_the_execution_object(self):
        import resolve_execution
        graph, child = self.child()
        self.assertIsInstance(child["execution"], dict, "the fixture is not exercising the case")
        mode, why = resolve_execution.resolve(self.project, graph, child)
        self.assertIsInstance(mode, str)
        self.assertIn(mode, ("inline", "subagent", "background", "team", "worktree",
                             "dynamic-workflow"))

    def test_the_resolution_persists_on_a_child(self):
        import resolve_execution
        graph, child = self.child()
        resolve_execution.record_resolution(self.project, "SFTP-FEAT-001", child, graph)
        W.save_graph(self.project, graph)
        after = W.task(W.load_graph(self.project, "SFTP-FEAT-001"), child["id"])
        self.assertTrue(after["execution"].get("resolved"))
        self.assertTrue(after["execution"].get("resolution_reason"))


class TestTeamsAreRefusedWhereTheyWouldOverwrite(unittest.TestCase):
    """Teammates are not worktree-isolated. The documentation is explicit that two
    of them editing one file overwrite each other and that the only remedy is
    partitioning by file, so where the tasks have said which files they own, that
    can be checked rather than trusted."""

    def setUp(self):
        import resolve_execution
        self.R = resolve_execution
        self.graph = {"tasks": [
            {"id": "T-001", "state": "working", "role": "backend-developer",
             "owns_paths": ["src/api/handler.py"], "execution": "subagent"},
            {"id": "T-002", "state": "queued", "role": "solution-architect",
             "execution": "team", "risk": "HIGH"},
        ]}
        self.task = self.graph["tasks"][1]

    def overlap(self, mine, theirs):
        self.task["owns_paths"] = list(mine)
        self.graph["tasks"][0]["owns_paths"] = list(theirs)
        return self.R.overlapping_paths(self.task, [self.graph["tasks"][0]])

    def test_a_shared_file_is_reported(self):
        self.assertIn("src/api/handler.py",
                      self.overlap(["src/api/handler.py"], ["src/api/handler.py"]) or "")

    def test_disjoint_files_are_not(self):
        self.assertIsNone(self.overlap(["src/a.py"], ["src/b.py"]))

    def test_an_undeclared_task_claims_nothing(self):
        """The absence of a declaration is not evidence of separation."""
        self.task.pop("owns_paths", None)
        self.assertIsNone(self.R.overlapping_paths(self.task, [self.graph["tasks"][0]]))

    def test_a_finished_sibling_does_not_count(self):
        self.graph["tasks"][0]["state"] = "accepted"
        self.assertIsNone(self.overlap(["src/api/handler.py"], ["src/api/handler.py"]))


class TestTheTeamBranchActuallyUsesTheOverlapCheck(unittest.TestCase):
    """Testing the helper is not testing the rule. This drives resolve() itself
    with teams genuinely available, which is the only path where the check runs."""

    def setUp(self):
        import re
        import resolve_execution
        self.R = resolve_execution
        self.project = tempfile.mkdtemp(prefix="aieos-team-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        cfg = re.sub(r"agent_teams_available:\s*\w+", "agent_teams_available: true", cfg)
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        self.previous = os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")
        os.environ["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
        self.addCleanup(self.restore)
        ok, why = self.R.teams_available(self.project)
        self.assertTrue(ok, "the fixture cannot exercise the team branch: %s" % why)

    def restore(self):
        if self.previous is None:
            os.environ.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
        else:
            os.environ["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = self.previous

    def graph_with(self, mine, theirs, sibling_state="working"):
        return {"tasks": [
            {"id": "T-001", "state": sibling_state, "role": "backend-developer",
             "owns_paths": list(theirs), "execution": "subagent"},
            {"id": "T-002", "state": "queued", "role": "qa-lead", "stage": "NOPIN",
             "execution": "team", "risk": "HIGH", "owns_paths": list(mine)},
        ]}

    def test_an_overlapping_team_becomes_a_worktree(self):
        graph = self.graph_with(["src/api/handler.py"], ["src/api/handler.py"])
        mode, why = self.R.resolve(self.project, graph, graph["tasks"][1])
        self.assertEqual(mode, "worktree")
        self.assertIn("overwrite", why)

    def test_a_disjoint_team_stays_a_team(self):
        graph = self.graph_with(["src/a.py"], ["src/b.py"], sibling_state="queued")
        mode, _ = self.R.resolve(self.project, graph, graph["tasks"][1])
        self.assertEqual(mode, "team")
