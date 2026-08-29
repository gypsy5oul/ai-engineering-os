"""Persistent memory for the roles that read the same codebase repeatedly.

The capability is small and the risk is not. A reviewer that remembers is faster;
a reviewer that *believes* what it remembers has replaced the policy with its own
recollection, and nothing about a memory looks different from a fact once it is
written down.

The evidence for that is not hypothetical. Verified live against 2.1.250: told the
bare fact "the retention window is 30 days", the probe agent wrote back an
invented justification -- "likely driven by compliance standards, regulatory
frameworks, or internal data governance policies" -- and promoted the fact into a
rule it would enforce: "Flag any architectural decisions or cleanup operations
that might violate this window." Nobody said either. Left alone, memory
manufactures a `why` and an imperative.

So these tests hold three things: only the approved roles have it, only project
scope is permitted, and every role that holds it carries the instruction that
stops the behaviour above.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from frontmatter import read as read_fm  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


POLICY = load("policies/agent-memory.json")
APPROVED = [r["role"] for r in POLICY["who_holds_it"]["roles"]]


def agent(name):
    return read_fm(os.path.join(ROOT, "agents", "%s.md" % name))


def holders():
    out = {}
    for fname in sorted(os.listdir(os.path.join(ROOT, "agents"))):
        if not fname.endswith(".md"):
            continue
        fm, body = agent(fname[:-3])
        if fm.get("memory") is not None:
            out[fname[:-3]] = (fm, body)
    return out


class TestOnlyTheApprovedRolesHoldIt(unittest.TestCase):
    def test_the_holders_are_exactly_the_policy_list(self):
        self.assertEqual(sorted(holders()), sorted(APPROVED))

    def test_the_five_are_the_ones_the_brief_named(self):
        self.assertEqual(sorted(APPROVED), sorted([
            "architecture-reviewer", "code-reviewer", "performance-reviewer",
            "reliability-reviewer", "agent-evaluator"]))

    def test_every_holder_is_a_role_that_reviews_rather_than_authors(self):
        """An author with recollections of what it decided last time will reproduce
        them, which is how a codebase acquires a convention nobody chose."""
        registry = {a["name"]: a for a in load("policies/agent-registry.json")["agents"]}
        for role in APPROVED:
            with self.subTest(role=role):
                purpose = registry[role]["purpose"].lower()
                self.assertTrue(
                    any(w in purpose for w in ("review", "evaluat")),
                    "%s holds memory and does not review: %s" % (role, purpose))

    def test_each_holder_has_a_stated_reason(self):
        for entry in POLICY["who_holds_it"]["roles"]:
            with self.subTest(role=entry["role"]):
                self.assertGreater(len(entry["why"]), 40)

    def test_adding_a_role_is_a_governance_decision(self):
        self.assertIn("AP-10", POLICY["who_holds_it"]["adding_one"])


class TestOnlyProjectScopeIsPermitted(unittest.TestCase):
    """`user` stores at ~/.claude/agent-memory and applies across every project, so
    a reviewer carries an observation from one client's codebase into another's.
    `local` is explicitly not checked into version control, which makes it a
    private model of the codebase nobody can review."""

    def test_every_holder_declares_project(self):
        for role, (fm, _body) in holders().items():
            with self.subTest(role=role):
                self.assertEqual(fm["memory"], "project")

    def test_the_policy_requires_project_and_says_why_not_the_others(self):
        scope = POLICY["scope"]
        self.assertEqual(scope["required"], "project")
        self.assertIn("across every project", scope["user_is_forbidden"])
        self.assertIn("not checked into version control", scope["local_is_forbidden"])

    def test_the_validator_refuses_the_other_two(self):
        with open(os.path.join(ROOT, "scripts", "validate_plugin.py"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("def check_agent_memory(", body)
        self.assertIn("check_agent_memory()", body)


class TestTheInstructionThatStopsTheObservedBehaviour(unittest.TestCase):
    """Each of these corresponds to something the probe agent actually did."""

    def test_every_holder_says_memory_is_never_authority(self):
        rule = POLICY["the_rule"]["statement"].rstrip(".").lower()
        for role, (_fm, body) in holders().items():
            with self.subTest(role=role):
                self.assertIn(rule, body.lower())

    def test_every_holder_forbids_inventing_a_justification(self):
        """The probe wrote 'likely driven by compliance standards...'. Nobody said
        that."""
        for role, (_fm, body) in holders().items():
            with self.subTest(role=role):
                self.assertIn("justification nobody gave you", body)

    def test_every_holder_forbids_writing_memory_as_a_rule(self):
        """The probe wrote 'Flag any architectural decisions that might violate this
        window' -- a rule it had written for itself."""
        for role, (_fm, body) in holders().items():
            with self.subTest(role=role):
                self.assertIn("imperative", body.lower())

    def test_every_holder_prefers_a_pointer_to_a_copy(self):
        for role, (_fm, body) in holders().items():
            with self.subTest(role=role):
                self.assertIn("pointer to a copy", body)

    def test_every_holder_names_what_never_goes_in(self):
        for role, (_fm, body) in holders().items():
            with self.subTest(role=role):
                for forbidden in ("verdict", "approval", "person"):
                    self.assertIn(forbidden, body.lower())


class TestItIsNotASecondSourceOfTruth(unittest.TestCase):
    def test_the_policy_names_what_authority_remains(self):
        remains = " ".join(POLICY["the_rule"]["authority_remains"]).lower()
        for source in ("policies", "artifacts", "task graph", "decision records"):
            self.assertIn(source, remains)

    def test_a_finding_must_cite_an_artifact_rather_than_a_memory(self):
        """The compensating control for the thing no hook can check."""
        self.assertIn("is not a finding", POLICY["the_rule"]["consequence"])

    def test_verdicts_and_approvals_are_explicitly_not_stored(self):
        blob = " ".join(POLICY["what_it_is_not_for"]).lower()
        self.assertIn("verdict", blob)
        self.assertIn("approval", blob)
        self.assertIn("polic", blob)


class TestItSaysWhatItCannotDo(unittest.TestCase):
    def test_it_admits_no_hook_sees_a_memory_write(self):
        """The platform writes it, not the Write tool, so guard_write never fires
        and the write scope does not apply."""
        limits = " ".join(POLICY["not_enforceable"])
        self.assertIn("No hook sees a memory write", limits)
        self.assertIn("guard_write", limits)

    def test_it_admits_nothing_detects_a_stale_memory(self):
        self.assertIn("stale memory", " ".join(POLICY["not_enforceable"]))

    def test_it_admits_the_writer_and_the_reader_are_the_same_model(self):
        self.assertIn("same model", " ".join(POLICY["not_enforceable"]))


class TestThePlatformClaimsAreRecorded(unittest.TestCase):
    def caps(self):
        return load("policies/platform-capabilities.json")["capabilities"]

    def test_project_scope_is_recorded_as_verified_live(self):
        cap = self.caps()["agent.memory.project_scope"]
        self.assertTrue(cap["available"])
        self.assertEqual(cap["evidence"], "empirical")
        self.assertIn("live", cap["verified"])

    def test_the_elaboration_behaviour_is_recorded_as_load_bearing(self):
        """It is the reason the instruction exists, so it is the claim that must not
        quietly stop being true."""
        cap = self.caps()["agent.memory.elaborates_what_it_is_told"]
        self.assertTrue(cap["load_bearing"])
        self.assertIn("invented justification", cap["note"])


class TestTheOptionalSectionIsTiedToTheFrontmatter(unittest.TestCase):
    """Both directions. A role given a persistent store and no instruction about it
    holds a capability nobody told it how to use; a section describing one the role
    does not have is documentation of nothing."""

    def test_the_registry_declares_the_optional_section(self):
        spec = load("policies/agent-registry.json")["role_contract_optional_sections"]["Memory"]
        self.assertEqual(spec["after"], "Escalation")
        self.assertIn("frontmatter", spec["required_when"])
        self.assertIn("does not", spec["forbidden_when"])

    def test_every_holder_has_the_section_and_no_one_else_does(self):
        with_section = set()
        for fname in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            if not fname.endswith(".md"):
                continue
            _fm, body = agent(fname[:-3])
            if "## Memory" in body:
                with_section.add(fname[:-3])
        self.assertEqual(with_section, set(holders()))

    def test_the_validator_reads_the_section_list_from_the_registry(self):
        """Its own note said it did, and it carried a literal copy. They agreed,
        which is why nothing noticed."""
        with open(os.path.join(ROOT, "scripts", "validate_plugin.py"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn('_registry_json().get("role_contract_sections")', body)


if __name__ == "__main__":
    unittest.main()
