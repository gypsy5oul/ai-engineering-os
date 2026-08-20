"""Engineering communications tests.

The subsystem is safe because three things are separate: policy decides whether
and to whom, the agent writes, and a credentialed act sends. Each test here
defends one of those seams.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from route_event import route  # noqa: E402
from minyaml import parse_file  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def event(etype, subject="SFTP-X-001", level=None, **payload):
    cat = {e["type"]: e for e in load("notification/event-catalogue.json")["events"]}
    return {"id": "EVT-20250101-000000-aaaa", "type": etype, "at": "2025-01-01T00:00:00Z",
            "project": "SFTP", "source": {"kind": "workflow-stage"},
            "level": level or cat[etype]["level"], "subject": subject,
            "payload": payload}


class TestRoutingIsDeterministic(unittest.TestCase):
    def test_worker_events_are_never_sent(self):
        cat = load("notification/event-catalogue.json")["events"]
        for e in cat:
            if e["level"] != "worker":
                continue
            with self.subTest(event=e["type"]):
                d = route(event(e["type"]))
                self.assertFalse(d["send"], "%s is worker-level" % e["type"])

    def test_incident_events_are_immediate_and_urgent(self):
        d = route(event("INCIDENT_CREATED", "SFTP-INC-007", severity=1))
        self.assertTrue(d["send"])
        self.assertEqual(d["mode"], "immediate")
        self.assertEqual(d["priority"], "urgent")
        self.assertEqual([c["name"] for c in d["channels"]], ["incidents"])

    def test_a_narrower_rule_wins(self):
        """DEFECT_CREATED is immediate at high severity, aggregated otherwise."""
        high = route(event("DEFECT_CREATED", severity="high"))
        low = route(event("DEFECT_CREATED", severity="low"))
        self.assertEqual(high["mode"], "immediate")
        self.assertEqual(low["mode"], "aggregate")

    def test_unknown_event_types_are_a_policy_error_not_a_send(self):
        d = route({"id": "EVT-20250101-000000-aaaa", "type": "MADE_UP",
                   "at": "2025-01-01T00:00:00Z", "project": "X",
                   "source": {"kind": "human"}, "level": "team", "subject": "S"})
        self.assertFalse(d["send"])
        self.assertEqual(d["severity"], "policy-error")

    def test_the_thread_key_is_the_subject(self):
        d = route(event("FEATURE_CREATED", "SFTP-FEAT-103"))
        self.assertEqual(d["thread_key"], "SFTP-FEAT-103")

    def test_duplicates_inside_the_window_are_suppressed(self):
        with tempfile.TemporaryDirectory() as project:
            log = os.path.join(project, ".ai-engineering", "events")
            os.makedirs(log)
            from datetime import datetime
            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            first = event("DEFECT_CREATED", "SFTP-DEF-1", severity="high")
            first["at"] = now
            with open(os.path.join(log, "2025-01.jsonl"), "w") as fh:
                fh.write(json.dumps(first) + "\n")
            second = dict(first, id="EVT-20250101-000001-bbbb", at=now)
            d = route(second, project)
            self.assertFalse(d["send"])
            self.assertIn("duplicate", d["reason"])


class TestPolicyShape(unittest.TestCase):
    def setUp(self):
        self.pol = load("notification/notification-policy.json")
        self.cat = load("notification/event-catalogue.json")
        self.chans = load("notification/channels.json")["channels"]
        self.agents = {a["name"] for a in load("policies/agent-registry.json")["agents"]}

    def test_every_rule_targets_a_real_channel_and_template(self):
        for r in self.pol["rules"]:
            for c in [r["channel"]] + list(r.get("also_channels") or []):
                self.assertIn(c, self.chans, r["event"])
            if r.get("template"):
                self.assertTrue(os.path.exists(os.path.join(
                    ROOT, "notification", "templates", r["template"] + ".md")), r["event"])

    def test_recipients_are_roles_not_agents(self):
        for r in self.pol["rules"]:
            for role in r.get("recipients", []):
                self.assertNotIn(role, self.agents,
                                 "%s notifies the agent %s" % (r["event"], role))

    def test_every_event_type_has_a_routing_outcome(self):
        ruled = {r["event"] for r in self.pol["rules"]}
        for e in self.cat["events"]:
            self.assertTrue(e["type"] in ruled or e["level"] in self.pol["levels"], e["type"])

    def test_every_channel_only_admits_the_levels_it_declares(self):
        """Routing a lower level into a channel is what turns a space into noise."""
        levels = {e["type"]: e["level"] for e in self.cat["events"]}
        for r in self.pol["rules"]:
            if r["notify"] == "never":
                continue
            for c in [r["channel"]] + list(r.get("also_channels") or []):
                spec = self.chans[c]
                accepts = spec.get("accepts_levels")
                if not accepts:
                    continue
                with self.subTest(event=r["event"], channel=c):
                    self.assertTrue(
                        levels[r["event"]] in accepts
                        or r["event"] in spec.get("also_accepts_events", []),
                        "%s is %s-level, '%s' accepts %s"
                        % (r["event"], levels[r["event"]], c, accepts))

    def test_the_incidents_space_stays_narrow(self):
        spec = self.chans["incidents"]
        self.assertEqual(spec["accepts_levels"], ["incident"])
        self.assertEqual(spec.get("also_accepts_events", []), ["RCA_COMPLETED"])


class TestNoCredentialsInTheRepository(unittest.TestCase):
    def test_channels_name_env_vars_and_hold_no_urls(self):
        chans = load("notification/channels.json")["channels"]
        for name, c in chans.items():
            self.assertTrue(c.get("webhook_env"), name)
            for value in c.values():
                if isinstance(value, str):
                    self.assertNotIn("chat.googleapis.com", value, name)

    def test_no_webhook_url_anywhere_in_the_tree(self):
        import re
        pattern = re.compile(r"https://chat\.googleapis\.com/\S*key=|hooks\.slack\.com/services/\S")
        hits = []
        for dirpath, dirnames, files in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for name in files:
                if not name.endswith((".json", ".yaml", ".md", ".py", ".sh", ".txt")):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if pattern.search(fh.read()):
                        hits.append(os.path.relpath(path, ROOT))
        self.assertEqual(hits, [])


class TestSeparationOfFormattingAndSending(unittest.TestCase):
    def test_the_agent_holds_no_execution_tools(self):
        reg = {a["name"]: a for a in load("policies/agent-registry.json")["agents"]}
        profiles = load("policies/tool-permissions.json")["profiles"]
        tools = profiles[reg["notification-agent"]["tool_profile"]]["tools"]
        self.assertNotIn("Bash", tools)
        self.assertNotIn("Agent", tools)

    def test_the_agent_can_only_write_to_the_outbox(self):
        scope = load("policies/write-scope.json")["roles"]["notification-agent"]
        self.assertEqual(scope["mode"], "allow")
        self.assertTrue(all(p.startswith((".ai-engineering/outbox", "docs/communications"))
                            for p in scope["allow"]), scope["allow"])

    def test_the_dispatcher_defaults_to_a_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            decision = os.path.join(d, "r.json")
            message = os.path.join(d, "m.txt")
            with open(decision, "w") as fh:
                json.dump({"send": True, "priority": "high", "thread_key": "S-1",
                           "channels": [{"name": "qa", "webhook_env": "AIEOS_TEST_UNSET"}],
                           "recipients": []}, fh)
            with open(message, "w") as fh:
                fh.write("test message")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "aieos-notify"),
                                "--decision", decision, "--message", message],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0)
            self.assertIn("DRY RUN", r.stdout)
            self.assertIn("Nothing was published", r.stdout)

    def test_the_dispatcher_refuses_to_send_without_a_webhook(self):
        with tempfile.TemporaryDirectory() as d:
            decision, message = os.path.join(d, "r.json"), os.path.join(d, "m.txt")
            with open(decision, "w") as fh:
                json.dump({"send": True, "priority": "high",
                           "channels": [{"name": "qa", "webhook_env": "AIEOS_TEST_DEFINITELY_UNSET"}],
                           "recipients": []}, fh)
            with open(message, "w") as fh:
                fh.write("test")
            env = dict(os.environ)
            env.pop("AIEOS_TEST_DEFINITELY_UNSET", None)
            r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "aieos-notify"),
                                "--decision", decision, "--message", message, "--send"],
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 1)
            self.assertIn("not set in the environment", r.stdout)

    def test_the_dispatcher_honours_a_do_not_send_decision(self):
        with tempfile.TemporaryDirectory() as d:
            decision, message = os.path.join(d, "r.json"), os.path.join(d, "m.txt")
            with open(decision, "w") as fh:
                json.dump({"send": False, "reason": "worker-level"}, fh)
            with open(message, "w") as fh:
                fh.write("should not be sent")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "aieos-notify"),
                                "--decision", decision, "--message", message, "--send"],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0)
            self.assertIn("policy says do not send", r.stdout)


class TestEventsComeFromTheSdlc(unittest.TestCase):
    def test_catalogue_and_stages_agree_in_both_directions(self):
        cat = load("notification/event-catalogue.json")["events"]
        stage_emits = {}
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            for s in wf["stages"]:
                for t in s.get("emits", []) or []:
                    stage_emits.setdefault(t, []).append("%s/%s" % (wf["id"], s["id"]))
        for e in cat:
            if "/" not in e["emitted_by"]:
                continue
            with self.subTest(event=e["type"]):
                self.assertIn(e["type"], stage_emits)
                self.assertIn(e["emitted_by"], stage_emits[e["type"]])

    def test_emitting_an_unknown_event_type_is_refused(self):
        with tempfile.TemporaryDirectory() as project:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "emit_event.py"),
                                "--type", "NOT_A_REAL_EVENT", "--subject", "X-1",
                                "--project", project],
                               capture_output=True, text=True, timeout=30)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("unknown event type", r.stdout + r.stderr)

    def test_the_event_log_is_append_only_in_practice(self):
        with tempfile.TemporaryDirectory() as project:
            for _ in range(3):
                subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "emit_event.py"),
                                "--type", "DEFECT_FIXED", "--subject", "X-1",
                                "--project", project, "--payload", "defect_id=X-1"],
                               capture_output=True, text=True, timeout=30)
            log_dir = os.path.join(project, ".ai-engineering", "events")
            lines = []
            for name in os.listdir(log_dir):
                with open(os.path.join(log_dir, name)) as fh:
                    lines += [l for l in fh if l.strip()]
            self.assertEqual(len(lines), 3)
            self.assertEqual(len({json.loads(l)["id"] for l in lines}), 3)


if __name__ == "__main__":
    unittest.main()
