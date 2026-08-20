"""Write guard tests: hard denials, credential escalation, control-plane
escalation, per-role write scope and secret content detection."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import write, run_hook  # noqa: E402


class TestHardDenials(unittest.TestCase):
    def test_key_material_denied(self):
        for path in ("/home/u/.ssh/id_rsa", "certs/server.pem", "/root/.aws/credentials",
                     "keys/client.p12"):
            with self.subTest(path=path):
                self.assertEqual(write(path)[0], "deny", path)

    def test_git_internals_denied(self):
        self.assertEqual(write(".git/config")[0], "deny")
        self.assertEqual(write(".git/hooks/pre-commit")[0], "deny")


class TestCredentialAdjacent(unittest.TestCase):
    def test_env_escalates_rather_than_denies(self):
        """Editing a local .env is legitimate; the human confirms it."""
        for path in (".env", ".env.local", "config/secrets/db.yaml"):
            with self.subTest(path=path):
                self.assertEqual(write(path)[0], "ask", path)

    def test_env_example_files_are_exempt_but_still_content_scanned(self):
        """Escalating a committed template trains people to click through the prompt."""
        self.assertIsNone(write(".env.example", "API_URL=http://localhost")[0])
        self.assertIsNone(write(".env.template", "TOKEN=")[0])
        self.assertEqual(write(".env.example", 'AWS = "AKIAIOSFODNN7EXAMPLE"')[0], "deny")

    def test_ordinary_source_and_config_paths_are_untouched(self):
        ordinary = [
            "src/main.go", "src/api/handler.ts", "internal/auth/token.py",
            "web/src/App.tsx", "tests/test_auth.py", "e2e/login.spec.ts",
            "migrations/003_add_col.sql", "Dockerfile", "docker-compose.yaml",
            ".gitlab-ci.yml", "Makefile", "package.json", "go.mod",
            "README.md", "config/app.yaml", "deploy/values.yaml",
            "terraform/main.tf", "scripts/build.sh", "src/keys.go",
            "src/secrets_manager.go",
        ]
        offenders = [p for p in ordinary if write(p, "content")[0] is not None]
        self.assertEqual(offenders, [], "false positives: %s" % offenders)

    def test_ordinary_config_allowed(self):
        for path in ("config/app.yaml", "src/settings.py", "docker-compose.yaml"):
            with self.subTest(path=path):
                self.assertIsNone(write(path, "port: 8080")[0], path)


class TestControlPlane(unittest.TestCase):
    def test_plugin_components_escalate(self):
        for path in ("agents/backend-developer.md", "hooks/hooks.json",
                     "policies/write-scope.json", ".ai-engineering/project.yaml"):
            with self.subTest(path=path):
                decision, reason, _, _ = write(path, "x", agent="backend-developer")
                self.assertEqual(decision, "ask", path)
                self.assertIn("AP-10", reason)


class TestWriteScope(unittest.TestCase):
    def test_qa_cannot_write_source(self):
        decision, reason, _, _ = write("src/payments/service.py", "pass", agent="qa-engineer")
        self.assertEqual(decision, "deny")
        self.assertIn("qa-engineer", reason)

    def test_qa_can_write_tests(self):
        self.assertIsNone(write("tests/test_payments.py", "def test(): pass", agent="qa-engineer")[0])
        self.assertIsNone(write("src/payments/service_test.go", "package x", agent="qa-engineer")[0])

    def test_docs_writer_confined_to_docs(self):
        self.assertIsNone(write("docs/architecture/hld.md", "# HLD", agent="docs-writer")[0])
        self.assertEqual(write("src/main.go", "package main", agent="docs-writer")[0], "deny")

    def test_developer_cannot_write_architecture(self):
        self.assertEqual(write("docs/architecture/hld.md", "x", agent="backend-developer")[0], "deny")
        self.assertIsNone(write("src/api/handler.go", "package api", agent="backend-developer")[0])

    def test_release_manager_confined_to_release_docs(self):
        self.assertIsNone(write("docs/release/1.2.0.md", "notes", agent="release-manager")[0])
        self.assertIsNone(write("CHANGELOG.md", "notes", agent="release-manager")[0])
        self.assertEqual(write("src/api/handler.go", "x", agent="release-manager")[0], "deny")

    def test_unknown_agent_is_unconstrained_by_scope(self):
        """The main session is not an organizational role and keeps its own permissions."""
        self.assertIsNone(write("src/api/handler.go", "package api")[0])


class TestSecretContent(unittest.TestCase):
    def test_live_credentials_denied(self):
        samples = [
            'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"',
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
            'token = "glpat-abcdefghij1234567890"',
            'url = "postgres://svc:s3cr3tvalue@db.internal:5432/app"',
        ]
        for content in samples:
            with self.subTest(content=content[:40]):
                self.assertEqual(write("config/app.py", content)[0], "deny")

    def test_placeholders_allowed(self):
        for content in ('api_key = "${API_KEY}"', 'password = "changeme"',
                        'secret = "your-secret-here"', 'token = "<REDACTED>"',
                        'url = "postgres://user:password@localhost:5432/app"'):
            with self.subTest(content=content):
                self.assertIsNone(write("config/app.py", content)[0], content)

    def test_jwt_escalates(self):
        content = 'sample = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijkl"'
        self.assertEqual(write("docs/api.md", content)[0], "ask")

    def test_edit_payload_is_scanned(self):
        payload = {"tool_name": "Edit", "tool_input": {
            "file_path": "src/app.py", "old_string": "x", "new_string": 'k = "AKIAIOSFODNN7EXAMPLE"'}}
        self.assertEqual(run_hook("guard_write", payload)[0], "deny")


class TestBehaviour(unittest.TestCase):
    def test_non_write_tool_ignored(self):
        decision, _, code, raw = run_hook("guard_write", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertIsNone(decision)
        self.assertEqual(raw, "")
        self.assertEqual(code, 0)

    def test_malformed_input_does_not_crash(self):
        for payload in ({}, {"tool_name": "Write"}, {"tool_name": "Write", "tool_input": {}}):
            with self.subTest(payload=payload):
                self.assertEqual(run_hook("guard_write", payload)[2], 0)

    def test_never_allows(self):
        for path in ("src/a.py", "/home/u/.ssh/id_rsa"):
            self.assertNotEqual(write(path)[0], "allow")


if __name__ == "__main__":
    unittest.main()
