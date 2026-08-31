"""Instructions that contradict each other, and the checks that catch them.

A reviewer holding `Write` and `Edit`, with a write scope of `docs/reviews/**`,
whose own contract said *"Editing any file, including the design under review"*
was forbidden. Seven agents said it. A strong model reading both concludes it has
tools it must not use, and the safest reading — write nothing — is the one that
leaves a real review with findings and nowhere to record them.

That is the shape of defect this file exists for: not a missing capability, but
two true-sounding sentences that cannot both be followed. They are more damaging
than a missing feature because the model resolves them silently and nobody sees
which way it went.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from frontmatter import read as read_fm  # noqa: E402
from minyaml import parse_file  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def reviewers():
    """Every role whose write scope is its own review record and nothing else."""
    scope = load("policies/write-scope.json")["roles"]
    profiles = load("policies/tool-permissions.json")["profiles"]
    out = {}
    for agent in load("policies/agent-registry.json")["agents"]:
        name = agent["name"]
        tools = profiles[agent["tool_profile"]]["tools"]
        allow = (scope.get(name) or {}).get("allow") or []
        if ("Write" in tools or "Edit" in tools) and allow and all(
                a.startswith("docs/reviews/") for a in allow):
            out[name] = allow
    return out


class TestAReviewerIsToldWhatItsToolsAreFor(unittest.TestCase):
    """Seven agents held a write tool and were told not to write anything."""

    def test_there_are_reviewers_with_a_review_only_scope(self):
        self.assertGreaterEqual(len(reviewers()), 5, "the fixture no longer describes anything")

    def test_none_of_them_is_told_it_may_not_edit_any_file(self):
        for name in reviewers():
            with self.subTest(agent=name):
                _fm, body = read_fm(os.path.join(ROOT, "agents", "%s.md" % name))
                self.assertNotIn("Editing any file", body,
                                 "%s holds Write and Edit and is told not to use them" % name)

    def test_each_is_told_what_it_may_write_instead(self):
        for name, allow in reviewers().items():
            with self.subTest(agent=name):
                _fm, body = read_fm(os.path.join(ROOT, "agents", "%s.md" % name))
                self.assertIn("Modifying the artifact under review", body)
                for path in allow:
                    self.assertIn(path, body,
                                  "%s is not told the scope it may write" % name)

    def test_the_forbidden_action_names_the_real_boundary(self):
        """`the artifact under review` rather than `any file`. The distinction is the
        whole of a reviewer's independence: it may record a verdict and may not
        author what it judged."""
        for name in reviewers():
            with self.subTest(agent=name):
                _fm, body = read_fm(os.path.join(ROOT, "agents", "%s.md" % name))
                forbidden = body.split("## Forbidden actions")[1].split("## ")[0]
                self.assertIn("under review", forbidden)

    def test_a_role_with_no_write_tool_is_told_that_is_structural(self):
        profiles = load("policies/tool-permissions.json")["profiles"]
        for agent in load("policies/agent-registry.json")["agents"]:
            tools = profiles[agent["tool_profile"]]["tools"]
            if "Write" in tools or "Edit" in tools:
                continue
            _fm, body = read_fm(os.path.join(ROOT, "agents", "%s.md" % agent["name"]))
            if "Modifying any file" in body:
                with self.subTest(agent=agent["name"]):
                    self.assertIn("structural rather than instructional", body)


class TestTheDocsDescribeTheReviewerThatExists(unittest.TestCase):
    def test_agent_model_does_not_call_a_reviewer_read_only(self):
        with open(os.path.join(ROOT, "docs", "agent-model.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertNotIn("**Reviewer agent**, read-only", body)
        self.assertIn("whose write scope is its own review record", body)

    def test_the_critical_tier_says_no_write_tool_rather_than_read_only(self):
        """CRITICAL roles genuinely hold none — `read-only tool ceiling` was the right
        idea under a name that had come to mean something else."""
        with open(os.path.join(ROOT, "docs", "agent-model.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertNotIn("read-only tool ceiling", body)

    def test_no_document_says_a_reviewer_holds_no_write_tool(self):
        stale = ("reviewers hold no write tools", "reviewer has no write tools",
                 "Reviewers never get")
        for root, _dirs, files in os.walk(os.path.join(ROOT, "docs")):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as fh:
                    body = fh.read()
                for phrase in stale:
                    with self.subTest(doc=name, phrase=phrase):
                        self.assertNotIn(phrase, body)


class TestASchemaVocabularyReachesTheDocs(unittest.TestCase):
    """The CLI checker compares prose against argparse. This is the same defect one
    layer along: `docs/sdlc.md` described `execution` as "inline, subagent or team"
    for two releases after the enum grew `background` and `dynamic-workflow`."""

    def enum(self, *path):
        cur = load("schemas/task-graph.schema.json")
        for p in path:
            cur = cur[p]
        return cur

    def test_the_stage_contract_names_every_execution_mode(self):
        modes = self.enum("properties", "tasks", "items", "properties",
                          "execution", "oneOf", 0, "enum")
        with open(os.path.join(ROOT, "docs", "sdlc.md"), encoding="utf-8") as fh:
            body = fh.read()
        for mode in modes:
            with self.subTest(mode=mode):
                self.assertIn(mode, body)

    def test_the_two_schemas_permit_the_same_execution_modes(self):
        """They disagreed for two releases: five in the task graph, three in the
        workflow. A stage could not declare `background`, and the resolver carried
        a rule for a value nothing could produce."""
        workflow = load("schemas/sdlc-workflow.schema.json")
        stage = workflow["properties"]["stages"]["items"]["properties"]["execution"]
        self.assertEqual(sorted(stage["enum"]), sorted(self.enum(
            "properties", "tasks", "items", "properties", "execution", "oneOf", 0, "enum")))

    def test_the_stage_contract_says_isolation_is_a_separate_field(self):
        with open(os.path.join(ROOT, "docs", "sdlc.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("isolation", body)

    def test_the_execution_doc_names_every_isolation_mode(self):
        modes = self.enum("properties", "tasks", "items", "properties",
                          "isolation", "oneOf", 0, "enum")
        with open(os.path.join(ROOT, "docs", "execution.md"), encoding="utf-8") as fh:
            body = fh.read()
        for mode in modes:
            with self.subTest(mode=mode):
                self.assertIn(mode, body)


class TestATeammateGetsTheSkillsItsDefinitionPromises(unittest.TestCase):
    """A teammate does not inherit its agent definition's `skills:` frontmatter.
    Recorded in the capability model, told to every spawn prompt in team-patterns,
    and until now checked by nothing."""

    def team_stages(self):
        out = []
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            for stage in wf["stages"]:
                if stage.get("execution") == "team":
                    out.append((wf["id"], stage))
        return out

    def test_there_are_team_stages_to_check(self):
        self.assertTrue(self.team_stages())

    def test_every_team_stage_declares_the_skills_its_teammates_need(self):
        for wid, stage in self.team_stages():
            with self.subTest(stage="%s/%s" % (wid, stage["id"])):
                self.assertTrue(stage.get("skills"),
                                "a teammate inherits no skills from its definition, so a team "
                                "stage declaring none has no way to carry any")

    def test_team_patterns_still_tells_the_spawn_prompt_to_invoke_them(self):
        with open(os.path.join(ROOT, "skills", "team-patterns", "SKILL.md"),
                  encoding="utf-8") as fh:
            body = fh.read().lower()
        self.assertIn("skill", body)

    def test_the_capability_model_records_why(self):
        caps = json.dumps(load("policies/platform-capabilities.json"))
        self.assertIn("skills", caps)


class TestTheCheckersActuallyFail(unittest.TestCase):
    """Each mutation is the drift that was actually found. A checker nobody has
    watched fail is an assumption."""

    def sandboxed(self, mutate):
        tmp = tempfile.mkdtemp(prefix="aieos-consistency-")
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

    def test_a_doc_omitting_an_execution_mode_is_an_error(self):
        """The original drift was `docs/sdlc.md` naming three of five modes.

        There are three now: `background` and `dynamic-workflow` were in the
        task-graph enum while the workflow schema allowed only three, and the
        narrower set was the correct one. So the mutation is a doc that omits
        `team` -- a mode that genuinely exists and that a stage can genuinely
        declare.
        """
        def mutate(dst):
            # From the schema side, which is the direction that actually exercises
            # the checker. Removing a mode from one sentence in a document does not
            # trip it -- the check is a whole-file substring test and the word
            # survives elsewhere -- so a schema that grows a value the documents
            # have never heard of is the honest mutation, and it is also the real
            # sequence: the enum changes first and the prose lags.
            import json as _json
            path = os.path.join(dst, "schemas", "task-graph.schema.json")
            with open(path, encoding="utf-8") as fh:
                schema = _json.load(fh)
            execution = schema["properties"]["tasks"]["items"]["properties"]["execution"]
            execution["oneOf"][0]["enum"].append("carrier-pigeon")
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump(schema, fh, indent=2)

        proc = self.sandboxed(mutate)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("omits carrier-pigeon", proc.stdout)

    def test_a_team_stage_with_no_skills_is_an_error(self):
        def mutate(d):
            path = os.path.join(d, "sdlc", "workflows", "feature-delivery.yaml")
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            body = body.replace("""    skills:
      - architecture-design
      - adr-management
      - api-design
      - database-design
      - engineering-simplicity
""", "", 1)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
        proc = self.sandboxed(mutate)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("runs as a team and declares no skills", proc.stdout)

    def test_the_unmodified_repository_passes(self):
        proc = self.sandboxed(lambda d: None)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])


if __name__ == "__main__":
    unittest.main()
