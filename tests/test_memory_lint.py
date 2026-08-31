"""Linting committed agent memory, and the entry that proved it was needed.

Memory is the only mechanism in this organization by which a role can accumulate
beliefs nobody approved, and nothing about a memory looks different from a fact
once it is written down. The rule is `policies/agent-memory.json`'s: memory
records *what* was observed, *where*, and *when*; it does not create a policy, a
justification nobody supplied, a requirement, a target, an approval or a verdict.

That rule cannot be enforced at write time — the platform writes memory, not the
`Write` tool, so no hook sees it. What can be enforced is what lands in the
repository, which is the whole reason project scope is the only scope permitted
here: it is committed, and a committed thing can be linted.

The canonical negative case below is not invented. It is the entry a real
`claude -p` probe produced against 2.1.250 when told one bare fact, quoted
verbatim from the evidence recorded in CHANGELOG v0.41.0. It manufactured a
justification and rewrote the fact as a rule it would enforce. Every rule in the
linter exists because of a way memory was observed, or is structurally able, to
stop being a record and start being an authority.

The false-positive class matters as much as the negative one. A lint that flags
"the endpoint never returns 204" teaches people to delete memories rather than
rewrite them, and a deleted memory is a re-derivation cost with no finding.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import lint_memory as L  # noqa: E402


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


POLICY = load("policies/agent-memory.json")
LINT = POLICY["lint"]

# Verbatim, from the live probe recorded in CHANGELOG v0.41.0. Told only "the
# retention window for this project is 30 days", the agent supplied the rest.
PROBE_ENTRY = """\
The retention window for this project is 30 days.

**Why:** likely driven by compliance standards, regulatory frameworks, or
internal data governance policies, though the specific driver was not stated.

**How to apply:** When designing data lifecycle or cleanup strategies, ensure that
no data is deleted before 30 days have elapsed. Flag any architectural decisions
or cleanup operations that might violate this window.
"""

# What the same observation looks like when it stays an observation.
GOOD_ENTRY = """\
GOLD-ARCH-001 (2026-08-28) says the transfer path is synchronous. The retry
policy for it is in `src/retention/policy.py`, not in configuration, which is
where I looked first on the previous two reviews.
"""


def findings(body, known_ids=frozenset()):
    return L.lint_entry("entry.md", body, set(known_ids))


def rules_fired(body, known_ids=frozenset()):
    return {r for r, _msg in findings(body, known_ids)}


def errors_fired(body, known_ids=frozenset()):
    return {r for r in rules_fired(body, known_ids) if r in L.ERRORS}


class TestTheEntryThatMotivatedThis(unittest.TestCase):
    """The negative case. Real output from a real session, not a fixture written
    to make a linter look good."""

    def test_it_is_caught(self):
        self.assertTrue(errors_fired(PROBE_ENTRY),
                        "the entry this lint was built for passes it")

    def test_the_invented_justification_is_caught(self):
        self.assertIn("ML-03", rules_fired(PROBE_ENTRY))

    def test_the_finding_quotes_the_words_nobody_said(self):
        msg = dict(findings(PROBE_ENTRY))["ML-03"]
        self.assertIn("likely", msg)

    def test_the_fact_rewritten_as_a_rule_is_caught(self):
        self.assertIn("ML-04", rules_fired(PROBE_ENTRY))

    def test_both_of_its_imperatives_are_reachable(self):
        """Buried mid-sentence, which is why ML-04 is not anchored to a line
        start: "...strategies, ensure that no data is deleted" and "...have
        elapsed. Flag any architectural decisions"."""
        self.assertIsNotNone(L.imperative("cleanup strategies, ensure that no data is deleted"))
        self.assertIsNotNone(L.imperative("have elapsed. Flag any architectural decisions"))

    def test_it_is_also_unsourced_and_undated(self):
        """Two warnings rather than errors. The entry's problem is not that it
        lacks provenance; it is that it invented authority."""
        fired = rules_fired(PROBE_ENTRY)
        self.assertIn("ML-01", fired)
        self.assertIn("ML-02", fired)
        self.assertNotIn("ML-01", L.ERRORS)
        self.assertNotIn("ML-02", L.ERRORS)

    def test_the_policy_records_where_it_came_from(self):
        blob = json.dumps(POLICY)
        self.assertIn("likely driven by compliance standards", blob)
        self.assertIn("2.1.250", blob)


class TestAWellFormedEntryPasses(unittest.TestCase):
    """The positive case. If nothing passes, the lint is a ban."""

    def test_no_findings_at_all(self):
        self.assertEqual(findings(GOOD_ENTRY), [])

    def test_it_still_passes_when_artifact_ids_are_checked(self):
        self.assertEqual(findings(GOOD_ENTRY, {"GOLD-ARCH-001"}), [])

    def test_it_records_what_where_and_when(self):
        self.assertTrue(L.ARTIFACT_ID.search(GOOD_ENTRY))
        self.assertTrue(L.PATHISH.search(GOOD_ENTRY))
        self.assertTrue(L.DATE.search(GOOD_ENTRY))


class TestLegitimateProseIsNotFlagged(unittest.TestCase):
    """The false-positive class. Each of these is an observation that happens to
    contain a word the rules care about. Flagging them is how a lint gets routed
    around, and the routing-around looks like deleting the memory."""

    CLEAN = [
        ("a modal verb inside an observation",
         "GOLD-ARCH-001 (2026-08-28): the retry policy must be read from "
         "`src/retention/policy.py` rather than configuration."),
        ("`never` describing behaviour rather than commanding it",
         "In `src/retention/policy.py` (2026-08-28) the purge endpoint never "
         "returns 204; it returns 202 and finishes out of band."),
        ("`always` describing behaviour",
         "GOLD-ARCH-001 (2026-08-28): the scheduler always runs in UTC, which is "
         "why the local-time test in `tests/test_policy.py` was misleading."),
        ("a number that is not a target",
         "`src/retention/policy.py` (2026-08-28) has 13 cases in "
         "`tests/test_policy.py`, and 3 of them cover the leap-second path."),
        ("a check that was performed, not one being demanded",
         "I checked `tests/test_policy.py` on 2026-08-28: it does not cover the "
         "timezone path, so a change there has no signal."),
        ("prose mentioning a review without recording its verdict",
         "The review record for GOLD-ARCH-001 lives under `docs/reviews/` "
         "(2026-08-28), which is where to look rather than re-deriving it."),
    ]

    def test_none_of_them_raises_an_error(self):
        for label, body in self.CLEAN:
            with self.subTest(case=label):
                self.assertEqual(errors_fired(body), set(),
                                 "%r is an observation, not an authority" % body[:60])

    def test_none_of_them_raises_anything_at_all(self):
        """They carry a pointer and a date, so the provenance warnings are silent
        too. This is the shape an entry is supposed to have."""
        for label, body in self.CLEAN:
            with self.subTest(case=label):
                self.assertEqual(findings(body), [], label)

    def test_the_narrowing_is_deliberate_and_recorded(self):
        source = open(os.path.join(ROOT, "scripts", "lint_memory.py"),
                      encoding="utf-8").read()
        self.assertIn("never returns 204", source,
                      "the false positive that shaped ML-04 is not written down")


class TestEachRuleFires(unittest.TestCase):
    """One entry per rule. A rule nobody has watched fire is an assumption."""

    SOURCED = "GOLD-ARCH-001 (2026-08-28): "

    def test_ml_01_no_pointer(self):
        self.assertIn("ML-01", rules_fired("The window is 30 days, as of 2026-08-28."))

    def test_ml_02_no_date_or_version(self):
        self.assertIn("ML-02", rules_fired("GOLD-ARCH-001 says the path is synchronous."))

    def test_ml_02_accepts_a_version_instead_of_a_date(self):
        self.assertNotIn("ML-02", rules_fired(
            "GOLD-ARCH-001 at v1.2.0 says the path is synchronous."))

    def test_ml_03_invented_justification(self):
        self.assertIn("ML-03", rules_fired(
            self.SOURCED + "the window is 30 days, probably for regulatory reasons."))

    def test_ml_04_written_as_a_rule(self):
        self.assertIn("ML-04", rules_fired(
            self.SOURCED + "Always check the retention window before a cleanup."))

    def test_ml_05_stores_a_target(self):
        self.assertIn("ML-05", rules_fired(
            self.SOURCED + "the p99 for this endpoint must not exceed 250ms."))

    def test_ml_06_stores_a_verdict(self):
        self.assertIn("ML-06", rules_fired(
            self.SOURCED + "the threat model was approved by the security review."))

    def test_ml_07_names_a_person(self):
        self.assertIn("ML-07", rules_fired(
            self.SOURCED + "the caching decision was made by @someone."))

    def test_ml_08_dangling_artifact_reference(self):
        fired = rules_fired(self.SOURCED + "see also GOLD-REQ-404.",
                            known_ids={"GOLD-ARCH-001"})
        self.assertIn("ML-08", fired)

    def test_ml_08_is_silent_when_the_artifact_exists(self):
        self.assertNotIn("ML-08", rules_fired(
            self.SOURCED + "see also GOLD-REQ-001.",
            known_ids={"GOLD-ARCH-001", "GOLD-REQ-001"}))

    def test_ml_08_is_silent_when_the_project_has_no_artifacts_to_check(self):
        """No index is not the same as an empty index. A project with no `docs/`
        must not have every pointer called dangling."""
        self.assertNotIn("ML-08", rules_fired(self.SOURCED + "see also GOLD-REQ-404."))

    def test_the_error_rules_are_the_ones_that_claim_authority(self):
        self.assertEqual(L.ERRORS, {"ML-03", "ML-04", "ML-05", "ML-06", "ML-07"})


class TestPolicyAndCodeAgree(unittest.TestCase):
    """The rules are read from the policy so the lint and the instruction agents
    follow cannot drift apart. That only holds if they name the same rules."""

    def test_every_policy_rule_is_implemented(self):
        declared = {r["id"] for r in LINT["rules"]}
        implemented = set()
        for body in ("x", PROBE_ENTRY):
            implemented |= rules_fired(body, {"NONE-X-001"})
        implemented |= {"ML-05", "ML-06", "ML-07", "ML-08", "ML-09"}
        self.assertEqual(declared, implemented)

    def test_every_error_rule_is_declared_in_the_policy(self):
        declared = {r["id"] for r in LINT["rules"]}
        self.assertTrue(L.ERRORS <= declared)

    def test_the_severity_text_matches_the_code(self):
        sev = LINT["severity"]
        for rule in sorted(L.ERRORS):
            with self.subTest(rule=rule):
                self.assertIn(rule, sev.split("are errors")[0])

    def test_each_rule_says_what_it_means_and_why(self):
        for r in LINT["rules"]:
            with self.subTest(rule=r["id"]):
                self.assertGreater(len(r["means"]), 20)
                self.assertGreater(len(r["why"]), 30)

    def test_the_rule_that_cannot_be_weakened_is_stated(self):
        self.assertEqual(POLICY["the_rule"]["statement"],
                         "Memory is never organizational authority.")

    def test_it_says_what_it_cannot_decide(self):
        blob = " ".join(LINT["not_enforceable"]) + LINT["what_it_can_decide"]
        self.assertIn("true", blob.lower())


class TestItDoesNotBlockRuntimeWrites(unittest.TestCase):
    """The brief's line: this is a repository/CI quality check. Memory is written
    by the platform, and a lint that tried to intercept that would be both
    impossible and the wrong layer."""

    def test_no_hook_invokes_it(self):
        hooks = json.dumps(load("hooks/hooks.json"))
        self.assertNotIn("lint_memory", hooks)

    def test_no_hook_script_invokes_it(self):
        base = os.path.join(ROOT, "hooks", "scripts")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                with self.subTest(script=name):
                    self.assertNotIn("lint_memory", fh.read())

    def test_it_says_so_itself(self):
        self.assertIn("cannot be enforced when a memory is written", L.__doc__)

    def test_a_project_with_no_memory_is_not_an_error(self):
        tmp = tempfile.mkdtemp(prefix="aieos-memlint-")
        self.addCleanup(shutil.rmtree, tmp, True)
        found, agents = L.lint(tmp)
        self.assertEqual((found, agents), ([], 0))


class TestTheCheckerActuallyFails(unittest.TestCase):
    """End to end through the CLI, because the exit code is what CI reads."""

    def project(self, entries, index=None, artifacts=()):
        tmp = tempfile.mkdtemp(prefix="aieos-memlint-")
        self.addCleanup(shutil.rmtree, tmp, True)
        agent = os.path.join(tmp, ".claude", "agent-memory", "code-reviewer")
        os.makedirs(agent)
        for name, body in entries.items():
            with open(os.path.join(agent, name), "w", encoding="utf-8") as fh:
                fh.write("---\nname: %s\n---\n\n%s" % (name[:-3], body))
        if index is None:
            index = "".join("- [x](%s) — hook\n" % n for n in entries)
        if index:
            with open(os.path.join(agent, "MEMORY.md"), "w", encoding="utf-8") as fh:
                fh.write(index)
        for aid in artifacts:
            docs = os.path.join(tmp, "docs", "architecture")
            os.makedirs(docs, exist_ok=True)
            with open(os.path.join(docs, "%s.md" % aid), "w", encoding="utf-8") as fh:
                fh.write("---\nid: %s\ntype: architecture\n---\n\nbody\n" % aid)
        return tmp

    def run_lint(self, project, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "lint_memory.py"),
             "--project", project] + list(extra),
            capture_output=True, text=True, timeout=120)

    def test_a_clean_store_exits_zero(self):
        proc = self.run_lint(self.project({"good.md": GOOD_ENTRY},
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Nothing here claims authority it does not have", proc.stdout)

    def test_the_probe_entry_exits_nonzero(self):
        proc = self.run_lint(self.project({"retention.md": PROBE_ENTRY}))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ML-03", proc.stdout)
        self.assertIn("ML-04", proc.stdout)

    def test_mutating_a_clean_entry_into_a_rule_fails_it(self):
        """The mutation: one sentence, from recording a fact to commanding one."""
        mutated = GOOD_ENTRY + "\nAlways read the policy before reviewing a change.\n"
        proc = self.run_lint(self.project({"good.md": mutated},
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ML-04", proc.stdout)

    def test_mutating_a_clean_entry_into_a_justification_fails_it(self):
        mutated = GOOD_ENTRY.replace("says the transfer path is synchronous",
                                     "says the transfer path is synchronous, probably "
                                     "because of an upstream latency budget")
        proc = self.run_lint(self.project({"good.md": mutated},
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ML-03", proc.stdout)

    def test_warnings_alone_do_not_fail_the_build(self):
        proc = self.run_lint(self.project(
            {"thin.md": "GOLD-ARCH-001 says the transfer path is synchronous."}))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("ML-02", proc.stdout)

    def test_strict_makes_them_fail(self):
        proc = self.run_lint(self.project(
            {"thin.md": "GOLD-ARCH-001 says the transfer path is synchronous."}),
            "--strict")
        self.assertEqual(proc.returncode, 1)

    def test_an_unindexed_entry_is_reported(self):
        proc = self.run_lint(self.project({"good.md": GOOD_ENTRY}, index="- [x](other.md) — h\n",
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertIn("ML-09", proc.stdout)
        self.assertIn("not listed in MEMORY.md", proc.stdout)

    def test_an_index_pointing_at_nothing_is_reported(self):
        proc = self.run_lint(self.project({"good.md": GOOD_ENTRY},
                                          index="- [x](good.md) — h\n- [y](gone.md) — h\n",
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertIn("does not exist", proc.stdout)

    def test_entries_with_no_index_at_all_are_reported(self):
        proc = self.run_lint(self.project({"good.md": GOOD_ENTRY}, index="",
                                          artifacts=["GOLD-ARCH-001"]))
        self.assertIn("ML-09", proc.stdout)

    def test_json_output_is_machine_readable(self):
        proc = self.run_lint(self.project({"retention.md": PROBE_ENTRY}), "--json")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["agents"], 1)
        self.assertIn("ML-03", {f["rule"] for f in payload["findings"]})

    def test_the_repository_itself_is_clean(self):
        """This repo commits no project-scope memory of its own, and the golden
        project's is linted with everything else. If either changes, this is
        where it surfaces."""
        proc = self.run_lint(ROOT)
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
