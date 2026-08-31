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
import briefing  # noqa: E402


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

    def unblock(self, task_id):
        """Mark everything the task waits on as accepted.

        These tests used to reach an agent's task straight after plan, which only
        worked while claim() handed out tasks with unmet dependencies. It no
        longer does, so the graph has to actually be advanced.
        """
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        pending, done = [task_id], set()
        while pending:
            current = pending.pop()
            for dep in W.task(graph, current).get("depends_on") or []:
                if dep not in done:
                    done.add(dep)
                    pending.append(dep)
        for t in graph["tasks"]:
            if t["id"] in done:
                t["state"] = "accepted"
        W.save_graph(self.project, graph)

    def unblock_role(self, role):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        for t in graph["tasks"]:
            if t["role"] == role:
                return self.unblock(t["id"])
        return None

    def hook(self, script, payload):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=self.project)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "hooks", "scripts", script)],
            input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, "a hook must always exit 0: " + proc.stderr[-300:])
        return json.loads(proc.stdout) if proc.stdout.strip() else None


class TestContextInjection(Hooked):
    def start(self, agent_type, unblock=None):
        if unblock:
            self.unblock(unblock)
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
        ctx = self.start("product-manager", unblock="T-002")["hookSpecificOutput"]["additionalContext"]
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
        ctx = self.start("product-manager", unblock="T-002")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Attempt 2 of 3", ctx)
        self.assertIn("no measurable indicator", ctx)

    def test_a_coupled_surface_is_flagged_to_whoever_touches_it(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        t = graph["tasks"][2]
        t["coupled_surface"] = "api-contract"
        role = t["role"]
        W.save_graph(self.project, graph)
        ctx = self.start(role, unblock=t["id"])["hookSpecificOutput"]["additionalContext"]
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


class TestTheDefinitionOfDoneArrivesMeaningful(unittest.TestCase):
    """A briefing used to hand over predicate identifiers and nothing else.

    Watched live against 2.1.251, an agent given `every_skip_recorded();
    config_valid()` spent six commands trying to read the plugin's own source to
    find out what they meant, and every one was refused -- the meanings live in
    the plugin and the plugin is outside an agent's read scope. It guessed
    correctly. Guessing correctly is not being told, and the next agent guesses
    something else.
    """

    def render(self, dod):
        return briefing.render(
            {"id": "X-001", "type": "feature", "risk": "MEDIUM", "stage": "intake",
             "intent": "i", "objective": "o"},
            {"id": "T-001", "title": "t", "role": "engineering-director",
             "definition_of_done": dod})

    def test_a_predicate_arrives_with_its_meaning(self):
        out = self.render(["every_skip_recorded()"])
        self.assertIn("every_skip_recorded()", out)
        self.assertIn("Every stage this change skips carries a written reason", out)

    def test_the_two_predicates_from_the_live_run_are_both_glossed(self):
        out = self.render(["every_skip_recorded()", "config_valid()"])
        self.assertIn("Every stage this change skips carries a written reason", out)
        self.assertIn("validates against schemas/project-config.schema.json", out)

    def test_a_predicate_with_arguments_is_glossed_on_its_name(self):
        out = self.render(["complexity_justified(ARTIFACT_CODE)"])
        self.assertIn("complexity_justified(ARTIFACT_CODE)", out)
        self.assertIn("complexity ledger", out)

    def test_an_unknown_predicate_still_appears(self):
        """Degrading to the old behaviour for one predicate beats dropping it."""
        out = self.render(["not_a_real_predicate()"])
        self.assertIn("not_a_real_predicate()", out)

    def test_the_gloss_is_read_from_the_artifact_model_not_restated(self):
        source = open(os.path.join(ROOT, "scripts", "lib", "briefing.py"),
                      encoding="utf-8").read()
        self.assertIn("artifact-model.json", source)
        self.assertNotIn("Every stage this change skips carries", source,
                         "the gloss is copied into the briefing; the copy will go stale")

    def test_every_predicate_the_model_defines_can_be_glossed(self):
        gloss = briefing._glossary()
        self.assertGreaterEqual(len(gloss), 25)
        for name, (meaning, _evidence) in gloss.items():
            with self.subTest(predicate=name):
                self.assertTrue(meaning.endswith("."), name)

    def test_only_the_first_sentence_travels(self):
        """`means` carries the definition and then the history of why the
        predicate is shaped that way. The agent doing the work needs the first."""
        meaning, _evidence = briefing._glossary()["every_skip_recorded"]
        self.assertEqual(meaning,
                         "Every stage this change skips carries a written reason.")

    def test_every_predicate_says_where_its_evidence_lives(self):
        """The half that was missing. Told what `cycle_rollup_reported` means, a
        real product-manager was called in three times and produced no rollup,
        because nothing said a rollup is a frontmatter mapping rather than a
        document. A predicate an agent cannot locate is one no agent can satisfy."""
        gloss = briefing._glossary()
        for name, (_meaning, evidence) in gloss.items():
            with self.subTest(predicate=name):
                self.assertTrue(evidence, "%s says what it means and not where to put it"
                                % name)

    def test_the_rollup_predicate_names_the_field_and_not_a_document(self):
        _meaning, evidence = briefing._glossary()["cycle_rollup_reported"]
        self.assertIn("rollup:", evidence)
        self.assertIn("produced_by", evidence)

    def test_the_briefing_renders_the_evidence(self):
        out = self.render(["cycle_rollup_reported(CYCLE-PROD)"])
        self.assertIn("Satisfied by:", out)
        self.assertIn("produced_by", out)

    def test_a_human_only_predicate_says_no_agent_may_satisfy_it(self):
        _meaning, evidence = briefing._glossary()["human_approval_recorded"]
        self.assertIn("No agent may create one", evidence)


class TestARetryIsNotAFreshStart(unittest.TestCase):
    """A REQ task refused and re-run produced GOLD-REQ-002 beside the
    GOLD-REQ-001 it had written the first time -- a second artifact with a
    different owner and fewer fields, which then failed the predicates the first
    one had passed and dragged the department rollup down with it.

    The agent had no way to know one existed. It was given a task and a
    definition of done, and both read identically on attempt one and attempt
    three."""

    def project(self, artifacts):
        tmp = tempfile.mkdtemp(prefix="aieos-retry-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for aid, owner in artifacts:
            d = os.path.join(tmp, "docs", "requirements")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "%s.md" % aid), "w", encoding="utf-8") as fh:
                fh.write("---\nid: %s\ntype: requirement\nchange: G-1\nowner: %s\n---\n\nbody\n"
                         % (aid, owner))
        return tmp

    def render(self, project):
        return briefing.render(
            {"id": "G-1", "type": "feature", "risk": "MEDIUM", "stage": "req",
             "intent": "i", "objective": "o"},
            {"id": "T-002", "title": "REQ", "role": "product-manager",
             "produces": ["REQ"], "definition_of_done": ["artifact_exists(REQ)"]},
            None, project)

    def test_an_existing_artifact_is_named(self):
        out = self.render(self.project([("GOLD-REQ-001", "requirements-analyst")]))
        self.assertIn("GOLD-REQ-001", out)
        self.assertIn("amend it", out)

    def test_its_owner_is_named_too(self):
        """The duplicate had a different owner, which is what failed
        artifact_owned_by."""
        out = self.render(self.project([("GOLD-REQ-001", "requirements-analyst")]))
        self.assertIn("requirements-analyst", out)

    def test_the_briefing_says_a_rewrite_does_not_supersede(self):
        out = self.render(self.project([("GOLD-REQ-001", "requirements-analyst")]))
        self.assertIn("does not supersede the old one", out)

    def test_it_does_not_forbid_a_genuinely_new_artifact(self):
        """A REQ stage producing three distinct requirements is decomposition, not
        duplication -- observed in the same run that produced the duplicate. The
        briefing must not turn one finding into a rule against the other."""
        out = self.render(self.project([("GOLD-REQ-001", "requirements-analyst")]))
        self.assertIn("separate artifact", out)

    def test_nothing_is_claimed_when_no_artifact_exists_yet(self):
        out = self.render(self.project([]))
        self.assertNotIn("Already produced", out)

    def test_an_artifact_of_another_type_is_not_offered(self):
        tmp = self.project([])
        d = os.path.join(tmp, "docs", "decisions")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "GOLD-DEC-001.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nid: GOLD-DEC-001\ntype: decision\nchange: G-1\n---\n\nx\n")
        self.assertNotIn("GOLD-DEC-001", self.render(tmp))

    def test_another_change_s_artifact_is_not_offered(self):
        tmp = self.project([])
        d = os.path.join(tmp, "docs", "requirements")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "OTHER-REQ-001.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nid: OTHER-REQ-001\ntype: requirement\nchange: G-9\n---\n\nx\n")
        self.assertNotIn("OTHER-REQ-001", self.render(tmp))

    def test_the_hook_passes_the_project_so_this_reaches_a_real_session(self):
        source = open(os.path.join(ROOT, "hooks", "scripts", "inject_context.py"),
                      encoding="utf-8").read()
        self.assertEqual(source.count("briefing.render(item, None, graph, project)"), 1)
        self.assertEqual(source.count("briefing.render(item, claimed, graph, project)"), 1)


class TestSubagentObservation(Hooked):
    def start(self, agent_type, agent_id="a1"):
        self.unblock_role(agent_type)
        return self.hook("inject_context.py",
                         {"hook_event_name": "SubagentStart", "agent_type": agent_type,
                          "agent_id": agent_id, "session_id": "S1"})

    def stop(self, agent_type, message, agent_id="a1", claim=True):
        # A stop resolves the lease the start took. Without one there is nothing
        # to attribute the result to, which is the point: role is not an identity.
        if claim:
            self.start(agent_type, agent_id)
        return self.hook("observe_subagent.py",
                         {"hook_event_name": "SubagentStop", "agent_type": agent_type,
                          "agent_id": agent_id, "session_id": "S1",
                          "last_assistant_message": message})

    def test_a_result_with_no_lease_is_attributed_to_nothing(self):
        """Better to record that a result belongs nowhere than to guess a task
        for it. Guessing is what wrote one agent's output onto three tasks."""
        self.assertIsNone(self.stop("product-manager", "Produced something substantial "
                                    "with enough detail to not look thin at all.",
                                    agent_id="never-started", claim=False))
        unattributed = [h for h in W.history(self.project, "SFTP-FEAT-001")
                        if h["kind"] == "subagent_stopped_unattributed"]
        self.assertTrue(unattributed)

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
        claimed = [t for t in graph["tasks"] if t.get("result")]
        self.assertEqual(len(claimed), 1,
                         "one agent's result landed on %d tasks" % len(claimed))
        self.assertIn("SFTP-REQ-001", claimed[0]["result"])
        stops = [h for h in W.history(self.project, "SFTP-FEAT-001")
                 if h["kind"] == "subagent_stopped"]
        self.assertEqual(stops[0]["task"], claimed[0]["id"])

    def test_it_never_blocks_a_stop(self):
        for msg in ("", "done", "x" * 5000):
            with self.subTest(msg=msg[:12]):
                out = self.stop("product-manager", msg)
                self.assertTrue(out is None or "decision" not in out,
                                "the observer tried to block a stop it had no business blocking")


class TestTheCompletionGateBindsOnAnIdNotAString(Hooked):
    """`T-001 in "T-0010 done"` is true, and the schema permits both ids, so
    substring matching could close the wrong task. The gate is also the only place
    the platform will actually refuse, so its own failure must not read as a pass."""

    def gate(self, subject, task_id="n1"):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=self.project)
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "hooks", "scripts", "gate_task_completion.py")],
            input=json.dumps({"hook_event_name": "TaskCompleted", "task_id": task_id,
                              "task_subject": subject}),
            capture_output=True, text=True, env=env, timeout=60)

    def test_a_longer_id_is_not_matched_by_a_shorter_one(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        target = next(t for t in graph["tasks"] if t.get("definition_of_done"))
        self.assertEqual(self.gate("%s0 done" % target["id"]).returncode, 0,
                         "T-0010 was matched as T-001")

    def test_the_native_task_id_is_bound_to_the_graph_task(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        target = next(t for t in graph["tasks"] if t.get("definition_of_done"))
        self.gate("%s done" % target["id"], task_id="native-77")
        after = W.task(W.load_graph(self.project, "SFTP-FEAT-001"), target["id"])
        self.assertEqual(after.get("native_task"), "native-77",
                         "the two ids were matched once and never written down")

    def test_an_unrelated_native_task_is_none_of_its_business(self):
        self.assertEqual(self.gate("refactor the parser").returncode, 0)

    def broken_plugin(self):
        """A copy of the plugin whose predicate evaluator raises."""
        root = os.path.join(self.project, "_plugin")
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".ai-engineering", "_plugin"))
        with open(os.path.join(root, "scripts", "check_dod.py"), "a", encoding="utf-8") as fh:
            fh.write("\nraise RuntimeError('the checker is broken')\n")
        return root

    def gate_with(self, root, subject):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=root, CLAUDE_PROJECT_DIR=self.project)
        return subprocess.run(
            [sys.executable, os.path.join(root, "hooks", "scripts", "gate_task_completion.py")],
            input=json.dumps({"hook_event_name": "TaskCompleted", "task_id": "n9",
                              "task_subject": subject}),
            capture_output=True, text=True, env=env, timeout=60)

    def test_a_broken_gate_does_not_pass_high_risk_work(self):
        root = self.broken_plugin()
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        high = next(t for t in graph["tasks"]
                    if t.get("definition_of_done") and t.get("risk") in ("HIGH", "CRITICAL"))
        proc = self.gate_with(root, "%s done" % high["id"])
        self.assertEqual(proc.returncode, 2, "a broken checker read as a satisfied one")
        self.assertIn("could not run", proc.stderr)

    def test_a_broken_gate_does_not_block_low_risk_work(self):
        """A gate that breaks a session is worse than one that misses a case --
        below HIGH, where the cost of being wrong is lower than the cost of a
        stuck session."""
        root = self.broken_plugin()
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        low = next(t for t in graph["tasks"]
                   if t.get("definition_of_done") and t.get("risk") == "LOW")
        self.assertEqual(self.gate_with(root, "%s done" % low["id"]).returncode, 0)


class TestAClaimedTaskIsNeverLeftUnbriefed(Hooked):
    """SubagentStart is not in the CLI's blocking set, so a spawn cannot be
    refused. What can be fixed is the lie: a failure after the claim used to
    leave the task leased to an agent that had received nothing, and SubagentStop
    then attributed whatever that agent did to it."""

    def broken_renderer(self):
        root = os.path.join(self.project, "_plugin")
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".ai-engineering", "_plugin"))
        with open(os.path.join(root, "scripts", "lib", "briefing.py"), "a",
                  encoding="utf-8") as fh:
            fh.write("\n\ndef render(*a, **k):\n"
                     "    raise RuntimeError('the renderer is broken')\n")
        return root

    def start_with(self, root, agent_type="ai-engineering-os:engineering-director"):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=root, CLAUDE_PROJECT_DIR=self.project)
        proc = subprocess.run(
            [sys.executable, os.path.join(root, "hooks", "scripts", "inject_context.py")],
            input=json.dumps({"hook_event_name": "SubagentStart", "agent_type": agent_type,
                              "agent_id": "a1", "session_id": "S1"}),
            capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, "a hook must always exit 0")
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def leased(self):
        return [t["id"] for t in W.load_graph(self.project, "SFTP-FEAT-001")["tasks"]
                if t.get("owner_agent")]

    def test_the_lease_is_released_when_the_briefing_fails(self):
        self.start_with(self.broken_renderer())
        self.assertEqual(self.leased(), [],
                         "a task is leased to an agent that received nothing")

    def test_the_agent_is_told_it_has_no_context(self):
        out = self.start_with(self.broken_renderer())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("no organizational context", ctx)

    def test_high_risk_work_is_told_to_stop(self):
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        W.task(graph, "T-001")["risk"] = "CRITICAL"
        W.save_graph(self.project, graph)
        ctx = self.start_with(self.broken_renderer())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("stop", ctx.lower())

    def test_the_change_risk_is_not_talked_down_by_the_task_risk(self):
        """A LOW task inside a HIGH change is still work nobody should do blind."""
        graph = W.load_graph(self.project, "SFTP-FEAT-001")
        W.task(graph, "T-001")["risk"] = "LOW"
        W.save_graph(self.project, graph)
        ctx = self.start_with(self.broken_renderer())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("HIGH-risk", ctx)

    def test_the_failure_is_recorded(self):
        self.start_with(self.broken_renderer())
        failures = [h for h in W.history(self.project, "SFTP-FEAT-001")
                    if h["kind"] == "briefing_failed"]
        self.assertTrue(failures)
        self.assertEqual(failures[0]["task"], "T-001")

    def test_a_working_briefing_keeps_its_lease(self):
        out = self.start_with(ROOT)
        self.assertIn("Your task", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.leased(), ["T-001"])
