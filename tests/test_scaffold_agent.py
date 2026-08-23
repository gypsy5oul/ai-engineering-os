"""The documented way to create an agent must produce a file that passes the build.

It did not, for thirteen versions. `scripts/lib/agent_render.py` carried its own
copy of the section order, v0.8.0 removed two sections from the contract without
updating it, and so `scaffold_agent.py` -- the flow `docs/development.md` and
`skills/agent-development/SKILL.md` both prescribe -- emitted a definition the
validator rejected. Nobody noticed because no test ran the two together.

That is the whole point of these tests: not that the renderer works, but that the
renderer and the validator agree.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Scaffolded(unittest.TestCase):
    def sandbox(self, name="contract-reviewer"):
        tmp = tempfile.mkdtemp(prefix="aieos-scaffold-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = os.path.join(tmp, "plugin")
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        path = os.path.join(dst, "policies", "agent-registry.json")
        with open(path, encoding="utf-8") as fh:
            reg = json.load(fh)
        proto = next(a for a in reg["agents"] if a["name"] == "code-reviewer")
        entry = dict(proto)
        entry["name"] = name
        entry["purpose"] = "Reviews API and schema contracts for compatibility and ownership."
        reg["agents"].append(entry)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, indent=2)
        return dst

    def scaffold(self, dst, name="contract-reviewer"):
        return subprocess.run(
            [sys.executable, os.path.join(dst, "scripts", "scaffold_agent.py"), name],
            cwd=dst, capture_output=True, text=True, timeout=120)

    def validate(self, dst):
        return subprocess.run([sys.executable, os.path.join(dst, "scripts", "validate_plugin.py")],
                              cwd=dst, capture_output=True, text=True, timeout=300)


class TestTheDocumentedFlowWorks(Scaffolded):
    def test_a_scaffolded_agent_passes_validation(self):
        dst = self.sandbox()
        out = self.scaffold(dst)
        self.assertIn("Wrote", out.stdout, out.stdout + out.stderr)
        result = self.validate(dst)
        complaints = [l for l in result.stdout.splitlines() if "contract-reviewer" in l]
        self.assertEqual(complaints, [],
                         "the documented way to create an agent produced a file the validator "
                         "rejects:\n  " + "\n  ".join(complaints))

    def test_the_frontmatter_survives_a_strict_yaml_parser(self):
        """The placeholder description contains ': ', which is a syntax error
        unquoted. The renderer emitted it unquoted for as long as the check
        existed."""
        dst = self.sandbox()
        self.scaffold(dst)
        with open(os.path.join(dst, "agents", "contract-reviewer.md"), encoding="utf-8") as fh:
            fm = fh.read().split("---")[1]
        for line in fm.splitlines():
            if line.startswith("description:"):
                value = line.split(":", 1)[1].strip()
                self.assertTrue(value.startswith('"') and value.endswith('"'),
                                "description is not quoted: %s" % line)


class TestOneSourceOfTruth(unittest.TestCase):
    """The renderer and the validator read the same list, rather than each
    keeping a copy that drifts."""

    def sections(self):
        with open(os.path.join(ROOT, "policies", "agent-registry.json"), encoding="utf-8") as fh:
            return json.load(fh)["role_contract_sections"]

    def test_the_renderer_reads_the_contract(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import agent_render
        self.assertEqual(agent_render.SECTIONS, self.sections())

    def test_the_validator_reads_the_contract(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import validate_plugin
        self.assertEqual(list(validate_plugin.AGENT_SECTIONS), self.sections())

    def test_every_shipped_agent_matches_it(self):
        import re
        expected = self.sections()
        for name in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            if not name.endswith(".md"):
                continue
            with self.subTest(agent=name):
                with open(os.path.join(ROOT, "agents", name), encoding="utf-8") as fh:
                    headings = re.findall(r"^## (.+)$", fh.read(), re.M)
                self.assertEqual(headings, expected)

    def test_changing_the_contract_moves_both(self):
        """The regression that matters. Removing a section from the policy must
        change what the renderer emits, or the two have drifted again."""
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import agent_render
        self.assertIn("Definition of done", agent_render.SECTIONS)
        self.assertNotIn("Skills", agent_render.SECTIONS,
                         "the renderer still emits a section the contract dropped in v0.8.0")
        self.assertNotIn("Model policy", agent_render.SECTIONS)
