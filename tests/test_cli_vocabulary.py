"""The documented CLI vocabulary and the one argparse enforces are the same list.

`skills/work-item/SKILL.md` listed nine work-item types. `control_loop.py`
accepted seven. Three of the listed nine did not exist, one that did was unlisted,
and the existing invocation check could not have caught either: it reads fenced
command blocks under `docs/`, and this was a sentence, in a skill.

Underneath the wording was a real gap. WF-DEPENDENCY, WF-AGENT-CHANGE and
WF-ONBOARDING each had stages, a definition of done and a simulation scenario, and
no `--type` opened a work item for any of them — three of the nine workflows the
control loop could not drive at all. The documentation described the intention;
nothing compared it to the parser.

So these tests hold two things: that the vocabulary agrees everywhere it is
written down, and that the checker which enforces that actually fails when the two
diverge. A validator nobody has watched fail is an assumption.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import control_loop as CL  # noqa: E402
from minyaml import parse_file  # noqa: E402


def load_json(rel):
    import json
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def parser_choices(flag):
    parser = CL.build_parser()
    for action in parser._actions:
        if not isinstance(getattr(action, "choices", None), dict):
            continue
        for sub in action.choices.values():
            for a in sub._actions:
                if a.option_strings and a.option_strings[-1] == flag and a.choices:
                    return set(a.choices)
    raise AssertionError("no %s flag with choices in the parser" % flag)


class TestTheVocabularyAgrees(unittest.TestCase):
    def test_argparse_offers_exactly_the_types_the_map_defines(self):
        """`--type` is generated from TYPE_WORKFLOW, so the CLI cannot offer a word
        the map does not route."""
        self.assertEqual(parser_choices("--type"), set(CL.TYPE_WORKFLOW))

    def test_the_schema_accepts_exactly_what_the_cli_accepts(self):
        enum = set(load_json("schemas/work-item.schema.json")["properties"]["type"]["enum"])
        self.assertEqual(enum, set(CL.TYPE_WORKFLOW))

    def test_every_type_has_an_identifier_segment(self):
        self.assertEqual(set(CL.TYPE_CODE), set(CL.TYPE_WORKFLOW))

    def test_every_identifier_segment_fits_the_schema_pattern(self):
        """A work item whose id its own schema rejects cannot be saved at all."""
        pattern = load_json("schemas/work-item.schema.json")["properties"]["id"]["pattern"]
        for wtype, code in sorted(CL.TYPE_CODE.items()):
            with self.subTest(type=wtype):
                self.assertRegex("ACME-%s-001" % code, pattern)

    def test_identifier_segments_are_distinct(self):
        """Two types sharing a segment makes the identifier ambiguous about what
        kind of work it names."""
        codes = list(CL.TYPE_CODE.values())
        self.assertEqual(len(codes), len(set(codes)))

    def test_the_skill_documents_exactly_the_types_that_exist(self):
        path = os.path.join(ROOT, "skills", "work-item", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for wtype in sorted(CL.TYPE_WORKFLOW):
            with self.subTest(type=wtype):
                self.assertIn(wtype, text, "%s is accepted and undocumented" % wtype)
        self.assertNotIn("--type feature, defect, incident, change,", text)

    def test_the_skill_names_the_workflow_each_type_routes_to(self):
        """Knowing the word is accepted is not the same as knowing what it does."""
        path = os.path.join(ROOT, "skills", "work-item", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for wtype, wid in sorted(CL.TYPE_WORKFLOW.items()):
            with self.subTest(type=wtype):
                self.assertRegex(text, r"`%s`\s*\|\s*%s\b" % (re.escape(wtype), re.escape(wid)))


class TestEveryVocabularyIsUnderCheck(unittest.TestCase):
    """A checker that happens to match one sentence is not a mechanism.

    `--type` was written as "is one of ..." and `--outcome` as "is a, b or c".
    Holding documentation to a single sentence shape is a rule about prose rather
    than about correctness, so the pattern accepts both -- and these tests hold
    the consequence: every flag argparse constrains is a flag the documentation
    states and the validator compares."""

    def matched(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import validate_plugin as V
        import glob
        _, merged = V._parser_choices()
        found = {}
        targets = (sorted(glob.glob(os.path.join(ROOT, "docs", "*.md")))
                   + sorted(glob.glob(os.path.join(ROOT, "*.md")))
                   + sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))))
        for path in targets:
            if os.path.basename(path) == "CHANGELOG.md":
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in V._VOCAB.finditer(text):
                values = V._documented_values(m.group(2))
                if values and m.group(1) in merged:
                    found[m.group(1)] = values
        return found, merged

    def test_every_constrained_flag_is_documented_and_compared(self):
        found, merged = self.matched()
        self.assertEqual(set(found), set(merged),
                         "a flag argparse constrains that no document states cannot drift "
                         "visibly")

    def test_each_documented_vocabulary_matches_argparse_exactly(self):
        found, merged = self.matched()
        for flag, values in sorted(found.items()):
            with self.subTest(flag=flag):
                self.assertEqual(values, merged[flag])

    def test_a_flag_description_is_not_read_as_a_vocabulary(self):
        """`--project` is the directory to work in` is prose, not an enumeration.
        Reading it as a one-item vocabulary would make every flag a finding."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import validate_plugin as V
        self.assertEqual(V._documented_values("the directory to work in"), set())
        self.assertEqual(V._documented_values("MEDIUM"), set())
        self.assertEqual(V._documented_values("a, b"), {"a", "b"})


class TestEveryWorkflowCanBeStarted(unittest.TestCase):
    """A workflow the control loop cannot open is a lifecycle the organization
    describes and cannot run."""

    def workflows(self):
        base = os.path.join(ROOT, "sdlc", "workflows")
        out = set()
        for name in sorted(os.listdir(base)):
            if name.endswith((".yaml", ".yml")):
                out.add(parse_file(os.path.join(base, name))["id"])
        return out

    def test_every_workflow_is_reachable_from_some_type(self):
        unreachable = self.workflows() - set(CL.TYPE_WORKFLOW.values())
        self.assertEqual(unreachable, set(),
                         "no --type opens a work item for these workflows")

    def test_no_type_routes_to_a_workflow_that_does_not_exist(self):
        self.assertEqual(set(CL.TYPE_WORKFLOW.values()) - self.workflows(), set())

    def test_the_three_that_were_unreachable_now_open_and_plan(self):
        """The regression itself: dependency, agent-change and onboarding could not
        be opened at all, and the skill said they could."""
        project = tempfile.mkdtemp(prefix="aieos-vocab-")
        self.addCleanup(shutil.rmtree, project, True)
        os.makedirs(os.path.join(project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)

        for wtype in ("dependency", "agent-change", "onboarding"):
            with self.subTest(type=wtype):
                opened = subprocess.run(
                    [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), "open",
                     "--project", project, "--type", wtype, "--intent", "check %s" % wtype],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                wid = opened.stdout.split()[0]
                planned = subprocess.run(
                    [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), "plan",
                     "--project", project, "--item", wid],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(planned.returncode, 0, planned.stdout + planned.stderr)
                self.assertIn(CL.TYPE_WORKFLOW[wtype], planned.stdout)


class TestTheCheckerActuallyFails(unittest.TestCase):
    """The failure-of-the-control half. Each case breaks one thing in a copy of the
    repository and asserts the validator says so, because a check that has only
    ever been seen to pass is an assumption with a test name."""

    def sandboxed(self, mutate):
        tmp = tempfile.mkdtemp(prefix="aieos-drift-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = os.path.join(tmp, "p")
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache"))
        mutate(dst)
        return subprocess.run(
            [sys.executable, os.path.join(dst, "scripts", "validate_plugin.py")],
            capture_output=True, text=True, cwd=dst, timeout=300)

    def edit(self, dst, rel, old, new):
        path = os.path.join(dst, rel)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(old, body, "fixture no longer matches %s" % rel)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body.replace(old, new, 1))

    def test_a_documented_value_argparse_rejects_is_an_error(self):
        proc = self.sandboxed(lambda d: self.edit(
            d, "skills/work-item/SKILL.md",
            "onboarding or operations", "onboarding, operations or telepathy"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("argparse rejects telepathy", proc.stdout)

    def test_a_value_argparse_accepts_and_the_docs_omit_is_an_error(self):
        """The quieter direction, and the one that hides a capability nobody uses."""
        proc = self.sandboxed(lambda d: self.edit(
            d, "skills/work-item/SKILL.md",
            "dependency, agent-change, onboarding or operations",
            "agent-change, onboarding or operations"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("without dependency", proc.stdout)

    def test_a_workflow_no_type_opens_is_an_error(self):
        proc = self.sandboxed(lambda d: self.edit(
            d, "scripts/control_loop.py",
            '"dependency": "WF-DEPENDENCY", ', ''))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("WF-DEPENDENCY can be planned but no `--type` opens", proc.stdout)

    def test_a_type_routing_to_a_workflow_that_does_not_exist_is_an_error(self):
        proc = self.sandboxed(lambda d: self.edit(
            d, "scripts/control_loop.py",
            '"dependency": "WF-DEPENDENCY"', '"dependency": "WF-IMAGINARY"'))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("WF-IMAGINARY, which is not a workflow", proc.stdout)

    def test_the_schema_drifting_from_the_cli_is_an_error(self):
        proc = self.sandboxed(lambda d: self.edit(
            d, "schemas/work-item.schema.json", '"dependency", ', ''))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("schemas/work-item.schema.json accepts", proc.stdout)

    def test_an_identifier_segment_the_schema_cannot_express_is_an_error(self):
        """A type can be accepted by the CLI and still produce a work item that
        fails its own schema on save."""
        proc = self.sandboxed(lambda d: self.edit(
            d, "schemas/work-item.schema.json", "|DEP|", "|"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no place for DEP", proc.stdout)

    def test_a_vocabulary_written_without_one_of_is_still_checked(self):
        """The phrasing `--outcome` uses. Before the pattern accepted it, three of
        the four vocabularies were unchecked and looked checked."""
        proc = self.sandboxed(lambda d: self.edit(
            d, "skills/work-item/SKILL.md",
            "`--outcome` is accepted, failed, rejected, blocked or escalated.",
            "`--outcome` is accepted, failed, rejected, blocked or abandoned."))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("argparse rejects abandoned", proc.stdout)

    def test_the_unmodified_repository_passes(self):
        """So the cases above are failing on the mutation and not on the fixture."""
        proc = self.sandboxed(lambda d: None)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])


if __name__ == "__main__":
    unittest.main()
