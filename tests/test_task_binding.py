"""TaskCreated: the native task is bound to the organizational one at creation.

Before this hook existed the association was first worked out at `TaskCompleted`,
from a subject line, at the last possible moment. Everything in between ran with
it unrecorded. These tests hold the two halves of the fix: that the binding
happens at the earliest event the platform offers, and that the refusals which
come with it stay narrow enough to live with.

Every refusal is tested four ways, because exit 2 on this event does not warn --
Claude Code deletes the task and strips its id out of every other task's edges --
so a false positive here destroys work rather than delaying it.
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
sys.path.insert(0, os.path.join(ROOT, "hooks", "lib"))
import workitem as W  # noqa: E402
import binding as B  # noqa: E402

HOOKS = os.path.join(ROOT, "hooks", "scripts")


def cl(project, sub, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), sub,
         "--project", project] + list(args),
        capture_output=True, text=True, timeout=120)


class Bound(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-bind-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)
        proc = cl(self.project, "open", "--type", "feature", "--risk", "MEDIUM",
                  "--intent", "Partners time out on large transfers")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.wid = proc.stdout.split()[0]
        self.assertEqual(cl(self.project, "plan", "--item", self.wid).returncode, 0)
        self.graph = W.load_graph(self.project, self.wid)
        self.tasks = self.graph["tasks"]

    # ---------------------------------------------------------------- driving

    def fire(self, subject=None, native="task-abc", description=None, teammate=None,
             project=None):
        payload = {"hook_event_name": "TaskCreated", "task_id": native,
                   "task_subject": subject if subject is not None else "work"}
        if description is not None:
            payload["task_description"] = description
        if teammate:
            payload["teammate_name"] = teammate
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = ROOT
        env["CLAUDE_PROJECT_DIR"] = project or self.project
        proc = subprocess.run([sys.executable, os.path.join(HOOKS, "bind_task.py")],
                              input=json.dumps(payload), capture_output=True, text=True,
                              env=env, cwd=project or self.project, timeout=30)
        return proc

    def reload(self):
        return W.load_graph(self.project, self.wid)

    def first_runnable(self):
        """A task with no unmet dependencies, so the happy path is genuinely happy."""
        g = self.reload()
        for t in g["tasks"]:
            if W.dependencies_met(g, t) and t["state"] not in ("accepted", "abandoned"):
                return t
        self.fail("the planned graph has no runnable task")

    def history(self):
        path = os.path.join(self.project, ".ai-engineering", "work", self.wid, "history.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def kinds(self):
        return [h["kind"] for h in self.history()]


class TestTheBindingHappens(Bound):
    def test_a_marker_binds_the_native_task_at_creation(self):
        t = self.first_runnable()
        proc = self.fire(subject="%s: draft the thing" % t["id"], native="task-777")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        bound = W.task(self.reload(), t["id"])
        self.assertEqual(bound.get("native_task"), "task-777")

    def test_the_binding_is_recorded_in_the_durable_history(self):
        """The graph carries the association; the history carries when it was made
        and on what evidence. A binding nobody can audit is a guess with a field."""
        t = self.first_runnable()
        self.fire(subject="%s go" % t["id"], native="task-778")
        entry = next(h for h in self.history() if h["kind"] == "task_created")
        self.assertEqual(entry["task"], t["id"])
        self.assertEqual(entry["native_task"], "task-778")
        self.assertEqual(entry["resolved_by"], "marker")
        self.assertTrue(entry["bound"])
        self.assertEqual(entry["role"], t["role"])

    def test_the_marker_is_found_in_the_description_too(self):
        t = self.first_runnable()
        proc = self.fire(subject="do the work", description="This covers %s." % t["id"],
                         native="task-779")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(W.task(self.reload(), t["id"]).get("native_task"), "task-779")

    def test_an_already_bound_task_is_recognised_without_a_marker(self):
        """Prose can be edited after the fact; the recorded id cannot."""
        t = self.first_runnable()
        W.bind_native_task(self.project, self.wid, t["id"], "task-780")
        proc = self.fire(subject="no marker at all", native="task-780")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        entry = next(h for h in self.history() if h["kind"] == "task_created")
        self.assertEqual(entry["resolved_by"], "bound")

    def test_the_teammate_name_is_recorded_but_never_treated_as_a_role(self):
        """It is a display name. Reading it as a registry role would attribute work
        to an agent the organization never assigned."""
        t = self.first_runnable()
        self.fire(subject="%s go" % t["id"], native="task-781", teammate="Riley")
        entry = next(h for h in self.history() if h["kind"] == "task_created")
        self.assertEqual(entry["teammate"], "Riley")
        self.assertEqual(entry["role"], t["role"])
        self.assertNotEqual(entry["role"], "Riley")


class TestItStaysQuietWhenItShould(Bound):
    """The false-positive half. Exit 2 deletes the task, so silence is the default."""

    def test_a_task_with_no_marker_is_left_alone(self):
        proc = self.fire(subject="read the changelog", native="task-900")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertNotIn("task_created", self.kinds())

    def test_a_project_with_no_work_item_is_left_alone(self):
        empty = tempfile.mkdtemp(prefix="aieos-empty-")
        self.addCleanup(shutil.rmtree, empty, True)
        proc = self.fire(subject="T-001 do it", native="task-901", project=empty)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_payload_with_no_task_id_is_left_alone(self):
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = ROOT
        env["CLAUDE_PROJECT_DIR"] = self.project
        proc = subprocess.run([sys.executable, os.path.join(HOOKS, "bind_task.py")],
                              input=json.dumps({"hook_event_name": "TaskCreated"}),
                              capture_output=True, text=True, env=env, cwd=self.project,
                              timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_substring_of_a_longer_id_does_not_bind(self):
        """`T-001` is inside `T-0010`. Substring matching would bind the wrong task
        and a later completion would close work it was never about."""
        g = self.reload()
        g["tasks"][0]["id"] = "T-0010"
        for t in g["tasks"]:
            t["depends_on"] = [d for d in (t.get("depends_on") or []) if d != "T-001"]
        W.save_graph(self.project, g)
        self.assertEqual(B.markers({"task_subject": "T-0010 go"}), {"T-0010"})
        self.assertNotIn("T-001", B.markers({"task_subject": "T-0010 go"}))


class TestItRefusesWhatIsActuallyWrong(Bound):
    """The negative half. Each of these is a task the organization can say is wrong,
    not one whose evidence is merely missing."""

    def test_an_invented_task_id_is_refused(self):
        proc = self.fire(subject="T-999 do the thing", native="task-902")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("T-999", proc.stderr)
        self.assertIn("not a task", proc.stderr)
        self.assertIn("unknown_task", [h.get("reason") for h in self.history()])

    def test_naming_two_tasks_is_refused_rather_than_guessed(self):
        a, b = self.tasks[0]["id"], self.tasks[1]["id"]
        proc = self.fire(subject="%s and %s together" % (a, b), native="task-903")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("would be a guess", proc.stderr)

    def test_a_task_whose_dependencies_are_open_is_refused(self):
        g = self.reload()
        blocked = next((t for t in g["tasks"] if t.get("depends_on")), None)
        if blocked is None:
            self.skipTest("the planned graph has no dependent task")
        proc = self.fire(subject="%s go" % blocked["id"], native="task-904")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("not accepted yet", proc.stderr)

    def test_an_accepted_task_cannot_be_started_again(self):
        t = self.first_runnable()
        g = self.reload()
        W.task(g, t["id"])["state"] = "accepted"
        W.save_graph(self.project, g)
        proc = self.fire(subject="%s go" % t["id"], native="task-905")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("already accepted", proc.stderr)

    def test_one_native_task_cannot_be_bound_to_two_graph_tasks(self):
        a, b = self.first_runnable(), None
        g = self.reload()
        b = next(t for t in g["tasks"] if t["id"] != a["id"])
        W.bind_native_task(self.project, self.wid, a["id"], "task-906")
        proc = self.fire(subject="%s go" % b["id"], native="task-906")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("already bound", proc.stderr)

    def test_a_task_assigned_to_a_role_nobody_holds_is_refused(self):
        t = self.first_runnable()
        g = self.reload()
        W.task(g, t["id"])["role"] = "chief-vibes-officer"
        W.save_graph(self.project, g)
        proc = self.fire(subject="%s go" % t["id"], native="task-907")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("agent-registry", proc.stderr)

    def test_every_refusal_says_what_to_do_next(self):
        """A refusal that does not name the way forward gets worked around."""
        for subject, native in [("T-999 go", "task-910"),
                                ("%s and %s" % (self.tasks[0]["id"], self.tasks[1]["id"]),
                                 "task-911")]:
            proc = self.fire(subject=subject, native=native)
            self.assertEqual(proc.returncode, 2)
            self.assertTrue(any(w in proc.stderr for w in
                                ("control_loop.py", "Split it", "own task")),
                            "no route forward in: %s" % proc.stderr)


class TestTheControlItselfCanFail(Bound):
    """The failure-of-the-control half: what happens when the check cannot run.

    The tiering is deliberately narrower than the completion gate's. Refusing a
    completion leaves finished work needing a second look; refusing a creation
    destroys the task, so only CRITICAL blocks on a broken check."""

    def corrupt(self):
        path = os.path.join(self.project, ".ai-engineering", "work", self.wid, "graph.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("tasks: [ this is not\n  valid: yaml: at all\n")

    def test_a_broken_check_does_not_block_medium_risk_work(self):
        self.corrupt()
        proc = self.fire(subject="T-001 go", native="task-920")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def break_after_risk_is_read(self, risk):
        """Corrupt the graph in a way that survives loading and raises later.

        Risk is read off the graph task, so a corruption early enough to stop the
        graph loading also makes the risk unknowable -- which is the case above.
        This one loads fine and raises at the role check, so the hook knows how
        risky the work is at the moment its own check breaks."""
        t = self.first_runnable()
        path = os.path.join(self.project, ".ai-engineering", "work", self.wid, "graph.yaml")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        # A list where a string belongs: unhashable, so `role not in roles` raises.
        text = text.replace("  - id: %s\n    title:" % t["id"],
                            "  - id: %s\n    role: [not, a, role]\n    title:" % t["id"], 1)
        text = text.replace("    role: %s\n" % t["role"], "", 1)
        text = text.replace("    risk: %s\n" % (t.get("risk") or "LOW"),
                            "    risk: %s\n" % risk, 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return t

    def test_a_broken_check_blocks_critical_work(self):
        t = self.break_after_risk_is_read("CRITICAL")
        proc = self.fire(subject="%s go" % t["id"], native="task-921")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("CRITICAL", proc.stderr)
        self.assertIn("could not run", proc.stderr)

    def test_the_same_break_does_not_block_high_risk_work(self):
        """Narrower than the completion gate on purpose: that one blocks at HIGH
        and CRITICAL. Refusing a completion leaves finished work needing a second
        look; refusing a creation deletes the task."""
        t = self.break_after_risk_is_read("HIGH")
        proc = self.fire(subject="%s go" % t["id"], native="task-922")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_break_before_risk_is_known_does_not_block(self):
        """When the graph will not load at all the hook cannot know how risky the
        work is, and guessing upward would stop every session over one bad file."""
        self.corrupt()
        proc = self.fire(subject="T-001 go", native="task-923")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_an_unparseable_payload_never_crashes_the_session(self):
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = ROOT
        env["CLAUDE_PROJECT_DIR"] = self.project
        proc = subprocess.run([sys.executable, os.path.join(HOOKS, "bind_task.py")],
                              input="not json at all", capture_output=True, text=True,
                              env=env, cwd=self.project, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestBothEndsResolveTheSameWay(unittest.TestCase):
    """TaskCreated and TaskCompleted deriving the association separately is how the
    durable graph came to disagree with the gate the first time."""

    GRAPH = {"tasks": [{"id": "T-001", "title": "a", "role": "backend-developer",
                        "state": "queued"},
                       {"id": "T-002", "title": "b", "role": "code-reviewer",
                        "state": "queued", "native_task": "n-2"}]}

    def test_a_recorded_binding_beats_the_prose(self):
        t, how = B.resolve(self.GRAPH, {"task_id": "n-2", "task_subject": "T-001 go"})
        self.assertEqual(t["id"], "T-002")
        self.assertEqual(how, "bound")

    def test_an_unknown_marker_is_reported_not_swallowed(self):
        """The gate used to treat this identically to an unrelated task, so a task
        referring to an invented id looked exactly like ordinary work."""
        t, how = B.resolve(self.GRAPH, {"task_id": "n-9", "task_subject": "T-404 go"})
        self.assertIsNone(t)
        self.assertEqual(how, "missing")

    def test_no_marker_is_unknown_rather_than_missing(self):
        t, how = B.resolve(self.GRAPH, {"task_id": "n-9", "task_subject": "tidy up"})
        self.assertIsNone(t)
        self.assertEqual(how, "unknown")

    def test_two_markers_are_ambiguous(self):
        t, how = B.resolve(self.GRAPH, {"task_id": "n-9", "task_subject": "T-001 and T-002"})
        self.assertIsNone(t)
        self.assertEqual(how, "ambiguous")

    def test_the_completion_gate_uses_the_same_module(self):
        with open(os.path.join(HOOKS, "gate_task_completion.py"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("import binding as B", body)
        self.assertIn("B.resolve(graph, data)", body)
        self.assertNotIn("TASK_MARKER = re.compile", body)


class TestThePlatformClaimsAreRecorded(unittest.TestCase):
    """Every platform claim this hook rests on has to be checkable, or the next
    version silently turns the gate off."""

    def capabilities(self):
        with open(os.path.join(ROOT, "policies", "platform-capabilities.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_blocking_claim_is_recorded_as_load_bearing(self):
        cap = self.capabilities()["capabilities"]["hook.TaskCreated.can_block"]
        self.assertTrue(cap["available"])
        self.assertTrue(cap["load_bearing"])
        self.assertEqual(cap["used_by"], "hooks/scripts/bind_task.py")

    def test_the_absence_of_dependency_edges_is_still_recorded(self):
        """It is the reason the task graph is this plugin's own artifact. If it ever
        becomes false that decision is worth revisiting, and a silent change is not
        an opportunity to revisit anything."""
        cap = self.capabilities()["capabilities"]["hook.TaskCreated.carries_dependencies"]
        self.assertFalse(cap["available"])
        self.assertEqual(cap["evidence"], "absent")

    def test_the_drift_checker_covers_both_claims(self):
        with open(os.path.join(ROOT, "scripts", "check_platform_drift.py"),
                  encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn('"id": "task-created-payload"', body)
        self.assertIn('"id": "task-created-blocks"', body)

    def test_the_hook_is_registered_on_the_event(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
            hooks = json.load(fh)["hooks"]
        self.assertIn("TaskCreated", hooks)
        cmd = hooks["TaskCreated"][0]["hooks"][0]["command"]
        self.assertIn("bind_task.py", cmd)


if __name__ == "__main__":
    unittest.main()
