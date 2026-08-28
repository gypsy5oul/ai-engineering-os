"""AI product engineering as capabilities, not roles.

The brief that asked for these said explicitly not to add AI-specific agents, and
that is the constraint most at risk here: seven new concerns arrive together and
each one reads like it wants an owner. It does not. A backend developer
implementing an LLM feature is still `backend-developer`; it loads
`llm-integration` while doing it.

The other risk is subtler. Two of these sit next to an existing skill with a
similar name — `agent-evaluation` and `observability` — and a skill that
duplicates one already there is worse than a missing one, because both get
loaded and they disagree.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from frontmatter import read as read_fm  # noqa: E402

AI_SKILLS = ["ai-system-design", "llm-integration", "prompt-engineering",
             "rag-engineering", "agent-tool-design", "ai-evaluation", "ai-observability"]

# The brief listed these as possible and nothing needs them yet. Recorded as a
# decision rather than an oversight, and asserted so that adding one silently is
# a test failure rather than a surprise.
DELIBERATELY_ABSENT = ["model-routing", "ai-performance", "ai-data-engineering"]


def skill(name):
    return read_fm(os.path.join(ROOT, "skills", name, "SKILL.md"))


def agent(name):
    return read_fm(os.path.join(ROOT, "agents", "%s.md" % name))


def preloaders():
    out = {}
    for fname in sorted(os.listdir(os.path.join(ROOT, "agents"))):
        if not fname.endswith(".md"):
            continue
        fm, _ = agent(fname[:-3])
        for s in fm.get("skills") or []:
            out.setdefault(s, set()).add(fname[:-3])
    return out


class TestNoAgentWasAdded(unittest.TestCase):
    """The freeze is the constraint. Seven new concerns is exactly the pressure
    that breaks it."""

    def test_the_agent_set_is_still_thirty(self):
        registry = json.load(open(os.path.join(ROOT, "policies", "agent-registry.json"),
                                  encoding="utf-8"))
        self.assertEqual(len(registry["agents"]), 30)

    def test_no_agent_is_named_for_an_ai_concern(self):
        registry = json.load(open(os.path.join(ROOT, "policies", "agent-registry.json"),
                                  encoding="utf-8"))
        for a in registry["agents"]:
            with self.subTest(agent=a["name"]):
                for token in ("prompt", "llm", "rag", "ml-", "model-engineer"):
                    self.assertNotIn(token, a["name"],
                                     "%s reads like an AI role rather than an "
                                     "organizational one" % a["name"])

    def test_every_ai_skill_is_held_by_a_role_that_already_existed(self):
        loaded = preloaders()
        for name in AI_SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(loaded.get(name),
                                "%s reaches no agent, so nothing can use it" % name)


class TestTheyAreReachable(unittest.TestCase):
    """None of the 30 agents holds the Skill tool, so frontmatter is the only route
    into a role's context. A capability nobody preloads is documentation."""

    def test_the_designing_and_reviewing_roles_both_hold_the_design_skill(self):
        loaded = preloaders()
        self.assertIn("solution-architect", loaded["ai-system-design"])
        self.assertIn("architecture-reviewer", loaded["ai-system-design"],
                      "the reviewer has no shared standard to review the design against")

    def test_the_implementing_and_reviewing_roles_both_hold_the_integration_skill(self):
        loaded = preloaders()
        self.assertIn("backend-developer", loaded["llm-integration"])
        self.assertIn("code-reviewer", loaded["llm-integration"])

    def test_tool_design_reaches_security(self):
        """The tool list is where an AI system's authority actually lives, which
        makes it a security surface rather than an interface preference."""
        self.assertIn("security-reviewer", preloaders()["agent-tool-design"])

    def test_evaluation_reaches_the_roles_that_own_quality(self):
        loaded = preloaders()["ai-evaluation"]
        self.assertTrue({"qa-lead", "qa-engineer", "test-reviewer"} <= loaded)

    def test_observability_reaches_the_roles_that_operate_it(self):
        loaded = preloaders()["ai-observability"]
        self.assertTrue({"sre", "devops-engineer", "reliability-reviewer"} <= loaded)


class TestTheyDoNotDuplicateWhatExists(unittest.TestCase):
    def test_ai_evaluation_says_what_it_is_not(self):
        """`agent-evaluation` evaluates this organization's roles; this one evaluates
        the product. Same discipline, different subject, and a reader who conflates
        them builds a suite that measures neither."""
        fm, body = skill("ai-evaluation")
        self.assertIn("agent-evaluation", fm["description"] + body)
        self.assertIn("evaluates the software the organization is building", body)

    def test_ai_observability_defers_to_the_general_skill(self):
        _fm, body = skill("ai-observability")
        self.assertIn("Use with `observability`", body)
        self.assertIn("SLIs, SLOs, alerts and runbooks all still apply", body)

    def test_the_design_skill_defers_to_architecture_design(self):
        _fm, body = skill("ai-system-design")
        self.assertIn("architecture-design", body)
        self.assertIn("not instead of it", body)

    def test_the_integration_skill_defers_to_backend_development(self):
        _fm, body = skill("llm-integration")
        self.assertIn("backend-development", body)

    def test_tool_design_distinguishes_itself_from_api_design(self):
        _fm, body = skill("agent-tool-design")
        self.assertIn("api-design", body)


class TestTheyAreTechnologyNeutral(unittest.TestCase):
    """The whole plugin mandates no technology. A capability that names a provider
    would be the first exception, and it would be a large one."""

    PROVIDERS = ["openai", "gpt-4", "anthropic", "claude-3", "gemini", "llama",
                 "mistral", "cohere", "pinecone", "weaviate", "langchain",
                 "llamaindex", "huggingface"]

    def test_no_ai_skill_names_a_provider_or_a_framework(self):
        for name in AI_SKILLS:
            _fm, body = skill(name)
            lowered = body.lower()
            for provider in self.PROVIDERS:
                with self.subTest(skill=name, provider=provider):
                    self.assertNotIn(provider, lowered,
                                     "%s names %s; the provider is a project decision under "
                                     "AP-03, not a plugin one" % (name, provider))

    def test_each_says_the_provider_is_a_project_decision(self):
        """The same shape kubernetes-basics uses: applies when the project declares
        it, assumed nowhere else."""
        named = 0
        for name in AI_SKILLS:
            _fm, body = skill(name)
            if "AP-03" in body or "project.yaml" in body:
                named += 1
        self.assertGreaterEqual(named, 5,
                                "no AI skill routes the provider choice to a human decision")


class TestTheProjectCanDeclareItBuildsOne(unittest.TestCase):
    """Before this section existed a project had no way to say the software it
    builds is an AI system, so every one of these skills had nothing to trigger on
    and a model provider was a technology decision with nowhere to be recorded."""

    def setUp(self):
        self.schema = json.load(open(os.path.join(ROOT, "schemas",
                                                  "project-config.schema.json"),
                                     encoding="utf-8"))
        self.section = self.schema["properties"]["ai_system"]

    def test_the_section_exists_and_requires_an_explicit_declaration(self):
        self.assertEqual(self.section["required"], ["builds_ai_features"])

    def test_it_is_never_inferred(self):
        self.assertIn("never inferred", self.section["description"])

    def test_it_is_distinguished_from_the_os_ai_section(self):
        """Two different subjects that share a word. `ai` is how this OS runs the
        project's roles; `ai_system` is what the project's software does."""
        self.assertIn("Distinct from `ai`", self.section["description"])
        self.assertIn("agent_teams_available", str(self.schema["properties"]["ai"]))

    def test_autonomy_is_an_enum_ending_in_the_irreversible_case(self):
        levels = self.section["properties"]["autonomy"]["enum"]
        self.assertEqual(levels[0], "suggests-to-a-human")
        self.assertEqual(levels[-1], "irreversible-action")

    def test_a_provider_carries_the_same_approval_fields_as_any_technology(self):
        ref = self.section["properties"]["model_providers"]["items"]["$ref"]
        self.assertEqual(ref, "#/definitions/techComponent")
        component = self.schema["definitions"]["techComponent"]["properties"]
        self.assertIn("adr", component)
        self.assertIn("status", component)

    def test_the_shipped_template_shows_it_and_still_validates(self):
        import subprocess
        path = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("ai_system:", body)
        self.assertIn("never 'latest'", body)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate_project_config.py"), path],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestWhatWasNotBuilt(unittest.TestCase):
    def test_the_three_deferred_capabilities_do_not_exist(self):
        """Recorded as a decision rather than an oversight. Adding one against an
        expected need rather than a stated one is the finding the simplicity policy
        exists to raise."""
        for name in DELIBERATELY_ABSENT:
            with self.subTest(skill=name):
                self.assertFalse(os.path.isdir(os.path.join(ROOT, "skills", name)))

    def test_the_omission_is_written_down(self):
        with open(os.path.join(ROOT, "docs", "skills.md"), encoding="utf-8") as fh:
            body = fh.read()
        for name in DELIBERATELY_ABSENT:
            self.assertIn(name, body, "%s was skipped without saying so" % name)
        self.assertIn("decision rather than an oversight", body)


class TestEachSkillSaysWhenNotToUseIt(unittest.TestCase):
    """A capability that only says when it applies gets applied to everything
    adjacent. The most valuable line in each of these is the one that sends the
    reader somewhere else."""

    def test_the_design_skill_asks_whether_a_model_is_needed_at_all(self):
        _fm, body = skill("ai-system-design")
        self.assertIn("Deterministic first", body)
        self.assertIn("simplicity-policy.json", body)

    def test_the_retrieval_skill_asks_whether_retrieval_is_needed_at_all(self):
        _fm, body = skill("rag-engineering")
        self.assertIn("Do you need it", body)
        self.assertIn("simplicity-policy.json", body)


if __name__ == "__main__":
    unittest.main()
