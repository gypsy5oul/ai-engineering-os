"""The organizational drift suite must refuse, and must be shown capable of refusing.

`evaluations/organization-evaluation/` asks whether the shape of the organization
still holds: whether a worker can bypass its lead, whether QA can approve its own
evidence, whether security can be routed around. Those are answerable from the
policy files alone, which is what makes them worth asserting -- and also what
makes them easy to get wrong, because a case built from checks that cannot fail
looks exactly like a case that is holding.

Two layers here, and the second is the one that matters.

The first checks the shape of the suite: every case deterministic, severity
carried, ids unique, and the whole suite green against this repository.

The second breaks one policy at a time in a throwaway copy and requires the
matching case to start failing. A case that still passes against a broken
organization is worse than none, because it certifies the damage.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = "organization-evaluation"
SUITE_DIR = os.path.join(ROOT, "evaluations", SUITE)


def load_cases():
    cases = []
    for name in sorted(os.listdir(SUITE_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SUITE_DIR, name), encoding="utf-8") as fh:
            cases.append(json.load(fh))
    return cases


def run_suite(cwd=ROOT, timeout=300):
    """Run the suite in `cwd` and return {case id: status}."""
    proc = subprocess.run(
        [sys.executable, os.path.join(cwd, "scripts", "run_evaluations.py"),
         "--suite", SUITE, "--json"],
        cwd=cwd, capture_output=True, text=True, timeout=timeout)
    try:
        summary = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError("runner produced no JSON summary:\n%s\n%s"
                             % (proc.stdout[-2000:], proc.stderr[-2000:]))
    return {c["id"]: c["status"] for c in summary["cases"]}, proc


def replace_after(text, anchor, old, new):
    """Replace the first `old` that appears after `anchor`.

    Needed where the value being mutated is not unique in the file: a routing
    gate reads `"gate": "blocking"` ten times over, and mutating the wrong one
    tests nothing.
    """
    start = text.index(anchor)
    at = text.index(old, start)
    return text[:at] + new + text[at + len(old):]


class TestSuiteShape(unittest.TestCase):
    def test_the_suite_is_green_against_this_repository(self):
        statuses, proc = run_suite()
        failed = sorted(i for i, s in statuses.items() if s != "passed")
        self.assertEqual(failed, [], "failing organization cases:\n%s" % proc.stdout[-3000:])
        self.assertEqual(proc.returncode, 0)

    def test_every_case_is_deterministic_and_severity_carrying(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["mode"], "deterministic",
                                 "an organizational property answerable from the policy files "
                                 "must never be left to a judge")
                self.assertIn(case["severity"], ("critical", "major", "minor"))
                self.assertEqual(case["suite"], SUITE)
                self.assertTrue(case.get("checks"), "deterministic case with no checks")
                self.assertTrue(case.get("adversarial"),
                                "every case here asks whether the structure can be bypassed")

    def test_case_ids_are_unique_and_scoped_to_this_suite(self):
        ids = [c["id"] for c in load_cases()]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertTrue(i.startswith("EVAL-ORG-"), i)


class TestDriftIsDetected(unittest.TestCase):
    """Mutation testing: break the organization, require the case to notice.

    Each entry names the drift in plain terms and the one-line edit that
    introduces it. If the case still passes afterwards, the case is decorative.
    """

    # (case id, drift, file, mutation callable over the file text)
    MUTATIONS = [
        ("EVAL-ORG-001", "a worker can escalate straight past its lead",
         "sdlc/cycles/dev.yaml",
         lambda t: replace_after(t, "escalation:\n  order:", "    - lead\n", "")),

        ("EVAL-ORG-002", "QA peer-reviews its own test scenarios",
         "sdlc/cycles/qa.yaml",
         lambda t: t.replace("  peer_reviewer: test-reviewer",
                             "  peer_reviewer: qa-engineer", 1)),

        ("EVAL-ORG-003", "a developer may edit the CI pipeline",
         "policies/write-scope.json",
         lambda t: replace_after(t, '"backend-developer": {', '".gitlab-ci.yml",\n', "")),

        ("EVAL-ORG-003", "a developer may write production Kubernetes manifests",
         "policies/write-scope.json",
         lambda t: replace_after(t, '"backend-developer": {', '"k8s/**",\n', "")),

        ("EVAL-ORG-003", "the deployment surface is denied to the role that owns it",
         "policies/write-scope.json",
         lambda t: replace_after(t, '"devops-engineer": {', '"docs/requirements/**",\n',
                                 '"docs/requirements/**",\n        "k8s/**",\n')),

        ("EVAL-ORG-004", "the security review of auth and crypto becomes advisory",
         "policies/review-routing.json",
         lambda t: replace_after(
             t, '"auth, crypto, secret handling, input parsing or deserialization touched"',
             '"gate": "blocking"', '"gate": "advisory"')),

        ("EVAL-ORG-005", "a head declares acceptance by judgement instead of by predicate",
         "sdlc/cycles/prod.yaml",
         lambda t: t.replace("determined_by: scripts/check_dod.py against acceptance.conditions",
                             "determined_by: the head's judgement", 1)),

        ("EVAL-ORG-006", "an agent may spawn itself",
         "policies/role-hierarchy.json",
         lambda t: t.replace('"self_spawn": "deny"', '"self_spawn": "allow"', 1)),

        ("EVAL-ORG-007", "the CRITICAL model floor drops to sonnet",
         "policies/risk-classification.json",
         lambda t: t.replace('"model_floor": "opus"', '"model_floor": "sonnet"', 1)),

        ("EVAL-ORG-008", "the code reviewer is given write access to source",
         "policies/write-scope.json",
         lambda t: replace_after(t, '"code-reviewer"',
                                 '"docs/reviews/**"',
                                 '"docs/reviews/**", "src/**"')),

        ("EVAL-ORG-009", "an agent verdict may approve on the organization's behalf",
         "policies/approval-authority.json",
         lambda t: t.replace('"can_approve_on_behalf_of_the_organization": false',
                             '"can_approve_on_behalf_of_the_organization": true', 1)),

        ("EVAL-ORG-010", "the development stage advances with rework still open",
         "sdlc/workflows/feature-delivery.yaml",
         lambda t: t.replace("      - no_open_rework(CYCLE-DEV)\n", "", 1)),
    ]

    def _mutated_copy(self, target, mutate):
        tmp = tempfile.mkdtemp(prefix="aieos-org-drift-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = os.path.join(tmp, "p")
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "reports", "node_modules"))
        path = os.path.join(dst, target)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        mutated = mutate(body)
        self.assertNotEqual(mutated, body,
                            "the mutation no longer applies to %s; the anchor moved" % target)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutated)
        return dst

    def test_each_case_fails_when_its_control_is_removed(self):
        for case_id, drift, target, mutate in self.MUTATIONS:
            with self.subTest(drift=drift):
                dst = self._mutated_copy(target, mutate)
                statuses, proc = run_suite(cwd=dst)
                self.assertEqual(
                    statuses.get(case_id), "failed",
                    "%s still passed after %r in %s. The case does not test the control.\n%s"
                    % (case_id, drift, target, proc.stdout[-1500:]))
                self.assertNotEqual(proc.returncode, 0,
                                    "a failing critical case must be a blocking exit")

    def test_an_unmutated_copy_is_still_green(self):
        """The control for the mutation harness itself.

        If copying the repository were enough to make a case fail, every result
        above would be an artefact of the harness rather than of the mutation.
        """
        dst = self._mutated_copy(
            "evaluations/%s/EVAL-ORG-001.json" % SUITE,
            lambda t: t.replace('"notes": "', '"notes": "Copied for the harness control. ', 1))
        statuses, proc = run_suite(cwd=dst)
        self.assertEqual(sorted(i for i, s in statuses.items() if s != "passed"), [],
                         proc.stdout[-2000:])


if __name__ == "__main__":
    unittest.main()
