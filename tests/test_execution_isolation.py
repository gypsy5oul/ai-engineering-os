"""Two capabilities that only work if the platform really has them.

Both were added after verifying the installed Claude Code rather than
remembering it, and both are easy to turn back into fiction by editing one file
and not the other. These tests hold the pieces together:

  * Isolation. `policies/execution-policy.json` now says that parallel workers
    who cannot own disjoint paths get separate git worktrees and that the merge
    is a declared step. The skill and the doc must name the same mechanisms the
    policy names, and the policy must keep admitting, in its own words, that no
    hook can force any of it.

  * Language intelligence. Claude Code reads LSP configuration only from a
    plugin's own `.lsp.json`, and `claude plugin validate` does not look at that
    file at all -- a broken one surfaces only at load time in the /plugin Errors
    tab. So this repository validates the `.lsp.json` it ships as a template
    itself, and asserts that its own root carries none, because "technology
    neutral" is a claim that should be checked rather than repeated.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402


def load_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


POLICY = "policies/execution-policy.json"
SKILL = "skills/team-patterns/SKILL.md"
DOC = "docs/execution.md"


class TestIsolationPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = load_json(POLICY)
        self.isolation = self.policy.get("isolation")

    def test_the_policy_declares_isolation_at_all(self):
        self.assertIsNotNone(self.isolation,
                             "%s has no 'isolation' section; the parallel-work rule is back to "
                             "'do not edit the same file'" % POLICY)
        self.assertEqual(self.isolation.get("default"), "shared-checkout",
                         "isolation must default to the shared checkout: making every worker pay "
                         "for a checkout by default is a cost, not a safety property")

    def test_every_mode_exists_and_says_when_to_use_it(self):
        modes = self.isolation.get("modes", {})
        self.assertEqual(set(modes), {"shared-checkout", "worktree", "remote"})
        for name, mode in modes.items():
            with self.subTest(mode=name):
                self.assertTrue(mode.get("meaning"), "%s has no meaning" % name)
                self.assertTrue(mode.get("use_when"), "%s says nothing about when to use it" % name)

    def test_remote_says_it_has_never_run_here(self):
        """It is in the enum because the platform has it, and a resolver that cannot
        name a mode has to call it something else -- which is the mistake the
        execution/isolation split exists to correct. A mode nothing has ever run
        that does not say so is a claim."""
        remote = self.isolation["modes"]["remote"]
        self.assertIn("Never run here", remote.get("status", ""))

    def test_the_two_dimensions_are_declared_as_separate(self):
        """The schema, the policy and the resolver all have to agree that these are
        different questions, or one of them quietly merges them again."""
        dims = self.policy.get("dimensions")
        self.assertTrue(dims, "the policy does not declare its dimensions")
        self.assertNotIn("worktree", dims["execution"],
                         "worktree is a place, not a way of running")
        self.assertNotIn("subagent", dims["isolation"])
        self.assertEqual(set(dims["isolation"]), set(self.isolation["modes"]))

    def test_every_combination_the_split_makes_possible_is_written_down(self):
        """Including team+worktree, which could not be expressed at all before: the
        only way to isolate a team was to stop calling it one."""
        combos = {(c["execution"], c["isolation"])
                  for c in self.policy["dimensions"]["combinations"]}
        for pair in (("team", "worktree"), ("team", "shared-checkout"),
                     ("subagent", "worktree"), ("inline", "shared-checkout"),
                     ("background", "worktree")):
            self.assertIn(pair, combos)
        for c in self.policy["dimensions"]["combinations"]:
            self.assertTrue(c.get("means"), "%s has no explanation" % (c,))

    def test_worktree_names_all_three_ways_the_platform_offers(self):
        how = self.isolation["modes"]["worktree"]["how"]
        blob = json.dumps(how)
        for token in ("isolation", "EnterWorktree", "ExitWorktree", "frontmatter"):
            self.assertIn(token, blob, "worktree.how does not mention %r" % token)

    def test_the_merge_is_a_declared_step_with_an_owner(self):
        integration = self.isolation.get("integration")
        self.assertIsNotNone(integration, "isolation without an integration step is a branch nobody owns")
        self.assertTrue(integration.get("rule"))
        self.assertTrue(integration.get("owner"))
        steps = integration.get("steps") or []
        self.assertGreaterEqual(len(steps), 3, "a merge described in fewer than three steps is a hope")
        blob = " ".join(steps).lower()
        for token in ("worktreebranch", "merge", "test"):
            self.assertIn(token, blob, "the integration steps never mention %r" % token)

    def test_the_policy_admits_what_it_cannot_enforce(self):
        """The repository's premise is that a control that is not real is worse than none."""
        claims = self.isolation.get("not_enforceable") or []
        self.assertTrue(claims, "isolation claims enforcement it does not have")
        blob = " ".join(claims).lower()
        self.assertIn("hook", blob)
        self.assertTrue(re.search(r"no hook can force", blob),
                        "not_enforceable must say plainly that no hook can force a worktree")

    def test_the_same_files_rule_distinguishes_a_team_from_a_subagent(self):
        """Two corrections live in this one rule.

        It first said only "do not use a team when the work touches the same
        files", which is a rule that can only say no. It was then softened to point
        at worktree isolation for everybody -- and that is wrong for a team.
        Teammates are separate instances sharing one checkout, so a worktree holds
        the whole team and isolates none of them from each other.

        So the rule now forks by mode: a fork for subagents, a stop for a team.
        """
        team = load_json(POLICY)["modes"]["team"]
        same_files = [r for r in team["do_not_use_when"] if "same files" in r]
        self.assertEqual(len(same_files), 1)
        rule = same_files[0]
        self.assertIn("worktree", rule,
                      "the rule must still offer subagents the isolation answer")
        self.assertIn("subagent", rule,
                      "a colliding team is not team-shaped; the rule must say what it becomes")

    def test_the_policy_says_a_worktree_cannot_isolate_a_team_from_itself(self):
        """The architectural correction, stated where the rule lives. The resolver
        used to return `worktree` for a colliding team while its own comment said
        teammates are not worktree-isolated, and two tests asserted it."""
        pol = load_json(POLICY)
        team_iso = pol.get("team_isolation") or {}
        self.assertIn("cannot isolate a team from itself", team_iso.get("statement", ""))
        self.assertIn("one checkout", team_iso.get("why", ""))
        self.assertIn("subagent", team_iso.get("so", ""))

    def test_the_baseref_trap_is_recorded(self):
        """Default baseRef is 'fresh', so an isolated worker does not see the branch you are on.

        Nothing in the plugin can change that default. Everything it can do is say so.
        """
        blob = " ".join(self.isolation.get("constraints_from_the_platform") or [])
        self.assertIn("baseRef", blob)
        self.assertIn("fresh", blob)


class TestIsolationIsDocumentedConsistently(unittest.TestCase):
    """The skill is what an agent reads; the doc is what a human reads; the policy
    is what validation reads. A mechanism named in one and missing from another is
    how the three drift apart."""

    MECHANISMS = ("isolation", "EnterWorktree", "ExitWorktree", "worktreeBranch",
                  "baseRef", "bgIsolation")

    def test_every_mechanism_appears_in_the_policy_the_skill_and_the_doc(self):
        policy = json.dumps(load_json(POLICY))
        skill = read(SKILL)
        doc = read(DOC)
        for token in self.MECHANISMS:
            for label, text in (("policy", policy), ("skill", skill), ("doc", doc)):
                with self.subTest(mechanism=token, where=label):
                    self.assertIn(token, text, "%s never mentions %r" % (label, token))

    def test_the_skill_and_the_doc_both_own_the_merge(self):
        for rel in (SKILL, DOC):
            with self.subTest(file=rel):
                text = read(rel).lower()
                self.assertIn("merge", text)
                self.assertIn("worktreebranch", text)

    def test_the_doc_is_honest_about_enforcement(self):
        text = read(DOC).lower()
        self.assertIn("cannot force a worktree", text,
                      "docs/execution.md must not leave a reader believing a hook enforces isolation")

    def test_read_only_workers_are_told_not_to_isolate(self):
        """A reviewer in a worktree reviews a copy and buys nothing but a checkout."""
        self.assertIn("read-only", read(SKILL))
        policy_blob = json.dumps(load_json(POLICY)["isolation"]["modes"]["worktree"])
        self.assertIn("read-only", policy_blob)


# The verified shape of one entry in a plugin's .lsp.json, taken from the manifest
# schema inside the installed CLI. `claude plugin validate` does NOT check this
# file -- only the equivalent `lspServers` block in plugin.json -- so nothing but
# this test stands between the shipped template and a config that fails silently
# at load time.
LSP_REQUIRED = ("command", "extensionToLanguage")
LSP_OPTIONAL = {
    "args": list, "transport": str, "env": dict, "initializationOptions": dict,
    "settings": dict, "workspaceFolder": str, "startupTimeout": int,
    "shutdownTimeout": int, "restartOnCrash": bool, "maxRestarts": int,
    "diagnostics": bool,
}
LSP_TEMPLATE = "templates/project/lsp.json"


class TestShippedLspTemplate(unittest.TestCase):
    def setUp(self):
        self.servers = load_json(LSP_TEMPLATE)

    def test_it_is_an_object_keyed_by_server_name(self):
        self.assertIsInstance(self.servers, dict)
        self.assertTrue(self.servers, "an empty template teaches nothing")

    def test_every_server_satisfies_the_platform_schema(self):
        for name, cfg in self.servers.items():
            with self.subTest(server=name):
                for key in LSP_REQUIRED:
                    self.assertIn(key, cfg, "%s: %s is required" % (name, key))
                command = cfg["command"]
                self.assertIsInstance(command, str)
                self.assertTrue(command)
                if " " in command:
                    self.assertTrue(command.startswith("/"),
                                    "%s: Claude Code rejects a command containing a space unless it "
                                    "is an absolute path; arguments belong in args" % name)
                mapping = cfg["extensionToLanguage"]
                self.assertIsInstance(mapping, dict)
                self.assertTrue(mapping, "%s: extensionToLanguage needs at least one mapping" % name)
                for ext, lang in mapping.items():
                    self.assertTrue(ext.startswith("."),
                                    "%s: extension %r must start with a dot" % (name, ext))
                    self.assertIsInstance(lang, str)
                for key, value in cfg.items():
                    if key in LSP_REQUIRED:
                        continue
                    self.assertIn(key, LSP_OPTIONAL,
                                  "%s: %r is not a field Claude Code reads; it would be silently "
                                  "ignored" % (name, key))
                    expected = LSP_OPTIONAL[key]
                    if expected is int:
                        self.assertTrue(isinstance(value, int) and not isinstance(value, bool),
                                        "%s: %s must be an integer" % (name, key))
                    else:
                        self.assertIsInstance(value, expected, "%s: %s has the wrong type" % (name, key))
                if "transport" in cfg:
                    self.assertIn(cfg["transport"], ("stdio", "socket"))

    def test_the_template_can_never_be_loaded_by_accident(self):
        """It lives under templates/ and is not named .lsp.json, so Claude Code
        never sees it. That is what lets it carry a concrete worked example
        without the company layer adopting a language."""
        self.assertNotEqual(os.path.basename(LSP_TEMPLATE), ".lsp.json")
        self.assertTrue(LSP_TEMPLATE.startswith("templates/"))


class TestThisPluginShipsNoLanguageServer(unittest.TestCase):
    """Technology neutrality, checked rather than asserted.

    An extensionToLanguage map cannot be parameterised, and extension claims are
    global across plugins: a placeholder here would outrank a project's real
    server for that extension.
    """

    def test_the_plugin_root_has_no_lsp_config(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, ".lsp.json")),
                         "this plugin must not claim any file extension")

    def test_the_manifest_declares_no_lsp_servers(self):
        manifest = load_json(".claude-plugin/plugin.json")
        self.assertNotIn("lspServers", manifest)


class TestLanguageIntelligenceDeclaration(unittest.TestCase):
    def setUp(self):
        self.cfg = parse_file(os.path.join(ROOT, "templates/project/project.yaml"))
        self.section = self.cfg.get("language_intelligence")

    def test_the_shipped_template_declares_it(self):
        self.assertIsNotNone(self.section,
                             "templates/project/project.yaml must show a project how to declare "
                             "its language intelligence, including declaring that it has none")
        self.assertIn(self.section.get("provider"), ("companion-plugin", "none"))

    def test_the_schema_knows_the_section(self):
        schema = load_json("schemas/project-config.schema.json")
        self.assertIn("language_intelligence", schema["properties"],
                      "the top-level schema forbids additional properties, so an undeclared "
                      "section would make every project file using it invalid")

    def test_a_companion_plugin_provider_names_the_plugin(self):
        if self.section.get("provider") != "companion-plugin":
            self.skipTest("template declares no companion plugin")
        self.assertTrue(self.section.get("plugin"),
                        "without a plugin id nobody can tell which plugin to install")

    def test_the_declaration_and_the_lsp_template_stay_in_step(self):
        """Two shipped examples of the same decision. If they disagree, the one a
        reader copies is the wrong one."""
        template = load_json(LSP_TEMPLATE)
        for server in self.section.get("servers") or []:
            with self.subTest(server=server["name"]):
                self.assertIn(server["name"], template,
                              "%s is declared in project.yaml but absent from %s"
                              % (server["name"], LSP_TEMPLATE))
                entry = template[server["name"]]
                self.assertEqual(server["command"], entry["command"])
                self.assertEqual(sorted(server["extensions"]),
                                 sorted(entry["extensionToLanguage"]))

    def test_the_doc_exists_and_covers_the_required_fields(self):
        doc = read("docs/lsp.md")
        for token in (".lsp.json", "extensionToLanguage", "command", "lspServers"):
            self.assertIn(token, doc)
        self.assertIn("plugin validate", doc,
                      "docs/lsp.md must warn that the CLI validator does not read .lsp.json")


if __name__ == "__main__":
    unittest.main()
