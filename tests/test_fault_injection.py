"""The fault suite must refuse, and must be shown capable of refusing.

Two layers here, and the second is the one that matters.

The first runs every injected fault and requires the system to stop (or, for a
degradation, to carry on). The second removes a control and requires the
corresponding fault to start failing. A fault-injection suite that still passes
against a broken system is worse than none, because it certifies the damage --
and this is not hypothetical: the first version of F-12 passed for a reason that
had nothing to do with notifications, and only the "which predicate objected"
check caught it.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_faults(cwd=ROOT, fault=None, timeout=300):
    cmd = [sys.executable, os.path.join(cwd, "scripts", "inject_faults.py")]
    if fault:
        cmd += ["--fault", fault]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


class TestFaultsAreHandled(unittest.TestCase):
    def test_every_injected_fault_produces_the_right_outcome(self):
        proc = run_faults()
        self.assertEqual(proc.returncode, 0,
                         "unhandled fault(s):\n%s" % proc.stdout[-3000:])
        self.assertIn("0 unhandled", proc.stdout)

    def test_the_suite_covers_every_class_of_failure(self):
        """Loop-backs, gates, the cycle, degradation, and the controls' own failure."""
        listing = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "inject_faults.py"), "--list"],
            capture_output=True, text=True, timeout=60).stdout
        for needed in ("Architecture is rejected", "QA fails", "rework limit",
                       "escalation is still open", "withdrawn", "Agent teams are unavailable",
                       "notification channel", "GitLab is unreachable", "hook policy",
                       "required model", "nobody moves it", "concurrency limit",
                       "untested rollback", "dimension unanswered"):
            with self.subTest(case=needed):
                self.assertIn(needed, listing)


class TestFaultsDetectRemovedControls(unittest.TestCase):
    """Mutation testing: break a control, require the fault to notice.

    Each entry names a control and a one-line edit that disables it. If the fault
    still passes afterwards, the fault is decorative.
    """

    MUTATIONS = [
        ("F-07", "the rework limit stops being enforced", "scripts/check_dod.py",
         'if r.get("rework_rounds", 0) > limit]', "if False]"),
        ("F-10", "withdrawing an item counts as accepting it", "sdlc/cycles/dev.yaml",
         "    withdrawn: WITHDRAWN\n", "    withdrawn: ACCEPTED\n"),
        ("F-15", "an unavailable model downgrades instead of blocking",
         "scripts/resolve_model.py", 'if risk_now in ("HIGH", "CRITICAL"):', "if False:"),
        ("F-16", "staleness stops being reported", "scripts/check_liveness.py",
         'findings.sort(key=lambda f: -f["hours"])\n    return findings',
         'findings.sort(key=lambda f: -f["hours"])\n    return []'),
        ("F-17", "the concurrency check always says under limit",
         "hooks/scripts/guard_spawn.py", "        if mine >= cap:", "        if False:"),
        ("F-18", "the migration plan stops requiring rollback evidence",
         "policies/artifact-model.json", '"rollback_tested",', '"rollback_procedure_dup",'),
        ("F-19", "blocking decisions stop blocking", "scripts/check_dod.py",
         'if a.get("status") == "open" and args[0] in (a.get("blocks") or [])]', "if False]"),
    ]

    def test_removing_a_control_makes_its_fault_fail(self):
        for fault, what, target, old, new in self.MUTATIONS:
            with self.subTest(control=what):
                tmp = tempfile.mkdtemp(prefix="aieos-mutate-")
                self.addCleanup(shutil.rmtree, tmp, True)
                dst = os.path.join(tmp, "p")
                shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
                path = os.path.join(dst, target)
                with open(path, encoding="utf-8") as fh:
                    body = fh.read()
                self.assertIn(old, body, "mutation for %s no longer applies to %s" % (fault, target))
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body.replace(old, new, 1))
                proc = run_faults(cwd=dst, fault=fault)
                self.assertNotEqual(
                    proc.returncode, 0,
                    "%s still passed after %s. The fault does not test the control.\n%s"
                    % (fault, what, proc.stdout[-1500:]))
