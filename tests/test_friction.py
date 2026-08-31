"""Measuring what an execution cost, without inventing any of it.

A friction number is the easiest thing in this repository to fake and the
hardest to notice being faked. Zero and unmeasured render identically, so a
harness that reports `0` where it means `no evidence` produces a dashboard that
says the organization is frictionless precisely when it has measured nothing.

Two properties are held here. Nothing is fabricated: every metric without
evidence is `None` with a stated reason. Nothing is judged: "unnecessary" has a
definition a machine applies, it undercounts, and the undercount is admitted
rather than smoothed over.

The third class is the one that cost a real correction. `execution_diverged` is
the OS noticing that what ran was not what was resolved -- the designed
response, and the only reason divergence is visible at all. Counting it as a
failure awaiting recovery reported the detector working as a 0% recovery rate.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import measure_friction as M  # noqa: E402


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def call(cid, name="Bash", **payload):
    return {"type": "tool_use", "id": cid, "name": name, "input": payload}


def text(body):
    return {"type": "text", "text": body}


def result(cid, content="ok", is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": cid, "content": content,
         "is_error": is_error}]}}


class Transcript(unittest.TestCase):
    def write(self, entries):
        tmp = tempfile.mkdtemp(prefix="aieos-friction-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "agent.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        return path


class TestItCountsWhatHappened(Transcript):
    def test_a_clean_run_has_no_friction(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="python3 -m pytest")),
            result("a"),
            assistant(text("done")),
        ]))
        self.assertEqual(stats["tool_calls"], 1)
        self.assertEqual(stats["failed_tool_calls"], 0)
        self.assertEqual(stats["unnecessary_turns"], 0)

    def test_a_platform_refusal_is_not_an_agent_error(self):
        """The distinction is the whole point: one is the organization's cost and
        one is the model's, and a single `failed` count hides which."""
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="ls /opt/plugin")),
            result("a", "ls in '/opt/plugin' was blocked. For security, Claude Code may "
                        "only list files in the project", is_error=True),
            assistant(call("b", command="python3 broken.py")),
            result("b", "Traceback: SyntaxError", is_error=True),
        ]))
        self.assertEqual(stats["failed_tool_calls"], 2)
        self.assertEqual(stats["permission_refusals"], 1)
        self.assertEqual(stats["agent_errors"], 1)

    def test_a_repeated_call_is_counted_once_as_a_repeat(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="cat x")), result("a"),
            assistant(call("b", command="cat x")), result("b"),
        ]))
        self.assertEqual(stats["tool_calls"], 2)
        self.assertEqual(stats["repeated_calls"], 1)

    def test_a_turn_that_only_repeats_itself_is_unnecessary(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="cat x")), result("a"),
            assistant(call("b", command="cat x")), result("b"),
        ]))
        self.assertEqual(stats["unnecessary_turns"], 1)

    def test_a_turn_that_could_never_have_succeeded_is_unnecessary(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="ls /opt/ai-engineering-plugin")),
            result("a", "was blocked. For security", is_error=True),
        ]))
        self.assertEqual(stats["unnecessary_turns"], 1)

    def test_a_turn_that_did_one_useful_thing_is_not_unnecessary(self):
        """Mixed turns count as work. Anything else would let one refused call in
        a productive turn condemn the whole turn."""
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="ls /opt/ai-engineering-plugin"),
                      call("b", command="python3 -m pytest")),
            result("a", "was blocked. For security", is_error=True),
            result("b", "3 passed"),
        ]))
        self.assertEqual(stats["unnecessary_turns"], 0)

    def test_a_question_with_no_tool_call_is_a_stall(self):
        """In `-p` there is nobody to answer it."""
        stats = M.analyse_transcript(self.write([
            assistant(text("Which retention window should I use?")),
        ]))
        self.assertEqual(stats["clarification_requests"], 1)

    def test_reading_the_rules_is_counted_separately_from_doing_the_work(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", command="grep -rn x /opt/ai-engineering-plugin/policies/")),
            result("a"),
        ]))
        self.assertEqual(stats["documentation_lookups"], 1)
        self.assertEqual(stats["discovery_calls"], 1)

    def test_writing_the_project_s_own_documents_is_the_work_not_friction(self):
        """The first version matched any path under `docs/`, so a product manager
        writing the requirement it was asked for was counted as overhead. That
        reported 59% of a real run as friction when much of it was the
        deliverable."""
        stats = M.analyse_transcript(self.write([
            assistant(call("a", name="Read",
                           file_path="/proj/docs/requirements/GOLD-REQ-001.md")),
            result("a"),
        ]), project="/proj")
        self.assertEqual(stats["documentation_lookups"], 0)

    def test_reading_the_organization_s_rules_from_inside_a_project_still_counts(self):
        stats = M.analyse_transcript(self.write([
            assistant(call("a", name="Read",
                           file_path="/opt/ai-engineering-plugin/policies/x.json")),
            result("a"),
        ]), project="/proj")
        self.assertEqual(stats["documentation_lookups"], 1)

    def test_an_unreadable_transcript_measures_nothing_rather_than_zero(self):
        self.assertIsNone(M.analyse_transcript("/nonexistent/agent.jsonl"))


class TestItRefusesToInventANumber(unittest.TestCase):
    """The property that matters most. A metric with no evidence is `None` and a
    reason, never `0`."""

    def project(self, history=(), tasks=()):
        tmp = tempfile.mkdtemp(prefix="aieos-friction-")
        self.addCleanup(shutil.rmtree, tmp, True)
        wid = "GOLD-FEAT-001"
        base = os.path.join(tmp, ".ai-engineering", "work", wid)
        os.makedirs(base)
        with open(os.path.join(tmp, ".ai-engineering", "work", "CURRENT"), "w",
                  encoding="utf-8") as fh:
            fh.write(wid + "\n")
        with open(os.path.join(base, "history.jsonl"), "w", encoding="utf-8") as fh:
            for h in history:
                fh.write(json.dumps(h) + "\n")
        graph = {"work_item": wid, "generation": 1,
                 "tasks": [dict(t) for t in tasks]}
        with open(os.path.join(base, "graph.yaml"), "w", encoding="utf-8") as fh:
            json.dump(graph, fh)
        return tmp

    def test_a_project_with_no_work_item_measures_nothing(self):
        tmp = tempfile.mkdtemp(prefix="aieos-friction-")
        self.addCleanup(shutil.rmtree, tmp, True)
        data = M.measure(tmp)
        self.assertFalse(data["measured"])
        self.assertIn("no active work item", data["why"])

    def test_no_transcript_means_not_measured_rather_than_zero_friction(self):
        data = M.measure(self.project())
        self.assertFalse(data["measured"])
        self.assertIn("nothing was executed to measure", data["why"])

    def test_human_intervention_rate_is_never_a_number_in_an_unattended_run(self):
        """Zero interventions in a run nobody watched is a property of the
        harness, not of the organization."""
        data = M.measure(self.project())
        self.assertIsNone(data["rates"]["human_intervention_rate"])
        self.assertIn("no human was present",
                      data["not_measured"]["human_intervention_rate"])

    def test_first_pass_acceptance_is_not_measured_with_no_verdict(self):
        data = M.measure(self.project(tasks=[{"id": "T-001", "state": "queued"}]))
        self.assertIsNone(data["rates"]["first_pass_acceptance_rate"])

    def test_first_pass_acceptance_is_measured_once_a_task_has_a_verdict(self):
        data = M.measure(self.project(tasks=[
            {"id": "T-001", "state": "accepted", "attempts": 1},
            {"id": "T-002", "state": "rework", "attempts": 2}]))
        self.assertEqual(data["rates"]["first_pass_acceptance_rate"], 0.5)

    def test_a_task_accepted_on_the_third_attempt_is_not_a_first_pass(self):
        data = M.measure(self.project(tasks=[
            {"id": "T-001", "state": "accepted", "attempts": 3}]))
        self.assertEqual(data["rates"]["first_pass_acceptance_rate"], 0.0)

    def test_every_rate_is_either_a_number_or_explained(self):
        data = M.measure(self.project())
        for name, value in data["rates"].items():
            if value is None:
                with self.subTest(rate=name):
                    self.assertIsNotNone(data["not_measured"].get(name),
                                         "%s is unmeasured and says nothing about why" % name)


class TestADetectorIsNotAFailure(unittest.TestCase):
    """`execution_diverged` is the OS noticing that what ran was not what was
    resolved. Counting it as a failure awaiting recovery reported the detector
    working as a 0% recovery rate."""

    def project(self, history):
        tmp = tempfile.mkdtemp(prefix="aieos-friction-")
        self.addCleanup(shutil.rmtree, tmp, True)
        wid = "GOLD-FEAT-001"
        base = os.path.join(tmp, ".ai-engineering", "work", wid)
        os.makedirs(base)
        with open(os.path.join(tmp, ".ai-engineering", "work", "CURRENT"), "w",
                  encoding="utf-8") as fh:
            fh.write(wid + "\n")
        with open(os.path.join(base, "history.jsonl"), "w", encoding="utf-8") as fh:
            for h in history:
                fh.write(json.dumps(h) + "\n")
        with open(os.path.join(base, "graph.yaml"), "w", encoding="utf-8") as fh:
            json.dump({"work_item": wid, "generation": 1, "tasks": []}, fh)
        return tmp

    def test_a_divergence_alone_leaves_recovery_unmeasured(self):
        data = M.measure(self.project([{"kind": "execution_diverged", "task": "T-001"}]))
        self.assertIsNone(data["rates"]["workflow_recovery_rate"])
        self.assertEqual(data["execution_divergences"], 1)

    def test_the_reason_says_the_detector_worked(self):
        data = M.measure(self.project([{"kind": "execution_diverged", "task": "T-001"}]))
        self.assertIn("designed response", data["not_measured"]["workflow_recovery_rate"])

    def test_an_unattributed_stop_is_a_detection_too(self):
        """The same mistake, made twice. A subagent stopping without a lease is
        the OS noticing it ran outside one; in the mechanism sessions that is the
        expected shape, and four of them reported a run where nothing failed as
        0% recovered."""
        data = M.measure(self.project([
            {"kind": "subagent_stopped_unattributed", "agent": "x"}]))
        self.assertIsNone(data["rates"]["workflow_recovery_rate"])
        self.assertEqual(data["detections_recorded"], 1)

    def test_an_approval_is_governance_and_not_friction(self):
        """The brief's line, held mechanically. A human approving what the
        organization requires a human to approve is the process working; counting
        it as an intervention would make a correct run look expensive."""
        data = M.measure(self.project([
            {"kind": "human_approval_recorded", "policy_ref": "AP-12",
             "approver_id": "a.person", "approver_role": "release-authority"}]))
        self.assertEqual(data["human_approvals_recorded"], 1)
        self.assertIsNone(data["rates"]["human_intervention_rate"])
        self.assertIn("governance rather than friction",
                      data["not_measured"]["human_intervention_rate"])

    def test_an_approval_does_not_count_as_a_drift_detection(self):
        data = M.measure(self.project([
            {"kind": "human_approval_recorded", "policy_ref": "AP-12"}]))
        self.assertEqual(data["detections_recorded"], 0)

    def test_a_real_block_does_enter_the_denominator(self):
        data = M.measure(self.project([{"kind": "task_completion_blocked", "task": "T-001"}]))
        self.assertEqual(data["rates"]["workflow_recovery_rate"], 0.0)

    def test_a_block_that_was_recovered_counts_as_recovered(self):
        data = M.measure(self.project([
            {"kind": "task_completion_blocked", "task": "T-001"},
            {"kind": "lease_released", "task": "T-001"}]))
        self.assertEqual(data["rates"]["workflow_recovery_rate"], 1.0)


class TestItSaysWhatItCannotCount(unittest.TestCase):
    def test_the_undercount_is_admitted(self):
        self.assertIn("undercounts", M.__doc__)

    def test_it_says_nothing_is_judged(self):
        self.assertIn("Nothing is judged", M.__doc__)

    def test_it_says_nothing_is_fabricated(self):
        self.assertIn("Nothing is fabricated", M.__doc__)

    def test_it_reads_transcripts_rather_than_a_session_s_own_account(self):
        self.assertIn("least reliable record", M.__doc__)


if __name__ == "__main__":
    unittest.main()
