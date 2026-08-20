#!/usr/bin/env python3
"""Fault injection: prove the system refuses to advance when it should.

`simulate_sdlc.py` walks seven happy paths and shows the process can complete.
That is the easier half. A control only earns trust when it is shown to *stop*
something, and every loop in this design exists for a failure that has never been
exercised: architecture rejected, QA failing, security blocking, a rework limit
reached, an approval that never came.

Two rules shape every case here.

**A refusal for the wrong reason is still a bug.** Each fault names the predicate
or transition that must be the one to object. A stage that fails because an
unrelated artifact is missing has not demonstrated the control under test, and
would keep passing after the control was removed.

**Degradation is not failure.** Some faults must *not* stop the lifecycle: a chat
webhook being down, or agent teams being unavailable, must leave delivery running.
Those cases assert the opposite - that nothing blocked.

Run: python3 scripts/inject_faults.py [--fault F-04] [--verbose]
"""
import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

import simulate_sdlc as S           # noqa: E402
import check_dod                    # noqa: E402
from minyaml import parse_file      # noqa: E402

FAULTS = []


def fault(fid, title, expect):
    def wrap(fn):
        FAULTS.append((fid, title, expect, fn))
        return fn
    return wrap


# ------------------------------------------------------------------ helpers

def dod(project, workflow, stage):
    """Stage definition of done as {predicate: (status, detail)}."""
    return {e: (st, d) for e, st, d in S.check_stage(project, workflow, stage)}


def must_fail(results, predicate):
    """The named predicate is the one that objects."""
    if predicate not in results:
        return False, "predicate %r is not in this stage's definition of done" % predicate
    status, detail = results[predicate]
    if status == "PASS":
        return False, "%s passed; the fault was not detected" % predicate
    return True, "%s -> %s (%s)" % (predicate, status, detail[:70])


def must_hold(results, predicate):
    """The named predicate still passes: the fault did not spread."""
    status, _ = results.get(predicate, ("MISSING", ""))
    return status == "PASS", "%s -> %s" % (predicate, status)


def cycle(cid):
    return S.CYCLES[cid]


def workflow(wid):
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            wf = parse_file(os.path.join(base, name))
            if wf["id"] == wid:
                return wf
    raise KeyError(wid)


# ------------------------------------------------- A. the loop-backs must hold

@fault("F-01", "Architecture is rejected",
       "ARCH does not pass, and the workflow has a path back to architecture")
def f01(project):
    S.write_artifact(project, "REQ", status="approved")
    S.write_artifact(project, "ARCH", status="draft",
                     reviewers=[S.verdict("architecture-reviewer", "changes-requested")],
                     rollup=S.rollup("CYCLE-ARCH", status="IN_PROGRESS"))
    ok, why = must_fail(dod(project, "WF-FEATURE", "ARCH"),
                        "agent_verdict(architecture-reviewer, pass)")
    if not ok:
        return False, why
    paths = workflow("WF-FEATURE").get("failure_paths") or []
    back = [p for p in paths if "ARCH" in str(p)]
    if not back:
        return False, "ARCH correctly refused, but no failure path returns to it"
    return True, why + "; failure path back to ARCH exists"


@fault("F-02", "QA fails after development completed",
       "QA does not pass, and the workflow returns to development")
def f02(project):
    S.write_artifact(project, "TESTREPORT", status="draft",
                     reviewers=[S.verdict("test-reviewer", "fail")],
                     rollup=S.rollup("CYCLE-QA", status="IN_PROGRESS"))
    res = dod(project, "WF-FEATURE", "QA")
    ok, why = must_fail(res, "agent_verdict(test-reviewer, pass)")
    if not ok:
        return False, why
    ok2, why2 = must_fail(res, "cycle_accepted(CYCLE-QA)")
    if not ok2:
        return False, "the reviewer verdict objected but the cycle did not: " + why2
    paths = workflow("WF-FEATURE").get("failure_paths") or []
    if not [p for p in paths if "DEV" in str(p)]:
        return False, "QA refused, but nothing routes the work back to development"
    return True, why + "; " + why2


@fault("F-03", "Production verification fails after deploy",
       "VERIFY does not pass, and a rollback stage exists to run")
def f03(project):
    S.write_artifact(project, "REL", status="authorized",
                     approvals=[S.approval("AP-14", "release-approver")])
    res = dod(project, "WF-RELEASE", "VERIFY")
    failing = [k for k, (st, _) in res.items() if st != "PASS"]
    if not failing:
        return False, "VERIFY passed with no verification evidence at all"
    stages = [s["id"] for s in workflow("WF-RELEASE")["stages"]]
    if "ROLLBACK" not in stages:
        return False, "VERIFY refused, but there is no rollback stage to go to"
    return True, "%d predicate(s) unmet; ROLLBACK stage exists" % len(failing)


# ------------------------------------------------------- B. the gates must hold

@fault("F-04", "The requester never accepted scope",
       "REQ does not pass: AP-12 is the decision every later stage derives from")
def f04(project):
    S.write_artifact(project, "REQ", status="approved", reviewers=[S.verdict("qa-lead")])
    S.write_artifact(project, "NFR", status="approved", target="99.9%",
                     reviewers=[S.verdict("qa-lead")])
    res = dod(project, "WF-FEATURE", "REQ")
    ok, why = must_fail(res, "human_approval_recorded(AP-12)")
    if not ok:
        return False, why
    held, detail = must_hold(res, "artifact_exists(REQ)")
    if not held:
        return False, "the missing approval broke an unrelated predicate: " + detail
    return True, why


@fault("F-05", "A high security finding stands with no exception",
       "CYCLE-SEC is not accepted: exception_granted is the only way past it")
def f05(project):
    S.write_artifact(project, "SEC", status="approved")
    conds = cycle("CYCLE-SEC")["acceptance"]["conditions"]
    arts = check_dod.load_artifacts(project)
    results = {}
    for entry in conds:
        fn, args = check_dod.parse_predicate(entry)
        results[entry] = check_dod.evaluate(fn, args, arts, project)
    ok, why = must_fail(results, "no_unresolved_findings(high)")
    if not ok:
        return False, why
    return True, why


@fault("F-06", "Release content was never approved",
       "RELEASE does not pass without AP-01")
def f06(project):
    S.write_artifact(project, "REL", status="in-review")
    ok, why = must_fail(dod(project, "WF-FEATURE", "RELEASE"), "human_approval_recorded(AP-01)")
    return (ok, why)


# ------------------------------------------------- C. the department cycle loop

@fault("F-07", "A work item exceeded the rework limit",
       "no_open_rework fails: the limit is enforced, not merely stated")
def f07(project):
    limit = (cycle("CYCLE-DEV").get("rework") or {}).get("limit", 3)
    S.write_artifact(project, "STORY", status="done",
                     rollup=S.rollup("CYCLE-DEV", rework=limit + 1))
    ok, why = must_fail(dod(project, "WF-FEATURE", "DEV"), "no_open_rework(CYCLE-DEV)")
    return (ok, why)


@fault("F-08", "The rework limit is reached",
       "CHANGES_REQUESTED has a legal move to ESCALATED in every cycle")
def f08(project):
    stuck = []
    for cid, c in S.CYCLES.items():
        if (c.get("rework") or {}).get("limit") is None:
            continue
        edges = (c["transitions"].get("CHANGES_REQUESTED") or {})
        if not any(t == "ESCALATED" for t in edges.values()):
            stuck.append(cid)
    if stuck:
        return False, "no escape at the limit in: %s" % ", ".join(stuck)
    return True, "every cycle with a limit can escalate at it"


@fault("F-09", "An escalation is still open",
       "no_open_rework fails while it is unresolved, and passes once answered")
def f09(project):
    S.write_artifact(project, "STORY", status="done", id="SIM-STORY-901",
                     rollup=S.rollup("CYCLE-DEV", rework=1,
                                     escalations=[{"to": "engineering-director",
                                                   "reason": "architecture_issue"}]))
    ok, why = must_fail(dod(project, "WF-FEATURE", "DEV"), "no_open_rework(CYCLE-DEV)")
    if not ok:
        return False, why
    S.patch_rollup(project, "SIM-STORY-901",
                   S.rollup("CYCLE-DEV", rework=1,
                            escalations=[{"to": "engineering-director",
                                          "reason": "architecture_issue",
                                          "resolved_at": S.TODAY,
                                          "resolution": "ADR amended"}]))
    held, detail = must_hold(dod(project, "WF-FEATURE", "DEV"), "no_open_rework(CYCLE-DEV)")
    if not held:
        return False, "a resolved escalation still blocks closure: " + detail
    return True, why + "; resolving it unblocks"


@fault("F-10", "A work item is withdrawn rather than finished",
       "WITHDRAWN is terminal and is not ACCEPTED")
def f10(project):
    wrong = []
    for cid, c in S.CYCLES.items():
        for src, edges in c["transitions"].items():
            for event, target in edges.items():
                if target == "ACCEPTED" and not (src == "ACCEPTANCE_REQUESTED"
                                                 and event == "dod_pass"):
                    wrong.append("%s: %s --%s--> ACCEPTED" % (cid, src, event))
    if wrong:
        return False, "acceptance reachable without a definition-of-done check: %s" % "; ".join(wrong)
    return True, "ACCEPTED is reachable only via ACCEPTANCE_REQUESTED --dod_pass-->"


# ----------------------------------------- D. degradation must NOT stop delivery

@fault("F-11", "Agent teams are unavailable",
       "every team stage declares how it degrades; nothing depends on teams")
def f11(project):
    missing = []
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        wf = parse_file(os.path.join(base, name))
        for s in wf["stages"]:
            if s.get("execution") == "team" and not s.get("degraded_mode"):
                missing.append("%s/%s" % (wf["id"], s["id"]))
    if missing:
        return False, "team stages with no degraded mode: %s" % ", ".join(missing)
    return True, "all team stages declare a degraded mode"


@fault("F-12", "The notification channel is unreachable",
       "the lifecycle continues: no definition of done depends on a notification")
def f12(project):
    S.write_artifact(project, "REQ", status="approved",
                     reviewers=[S.verdict("qa-lead")],
                     approvals=[S.approval("AP-12", "requester")],
                     rollup=S.rollup("CYCLE-PROD"))
    S.write_artifact(project, "NFR", status="approved", target="99.9%",
                     reviewers=[S.verdict("qa-lead")],
                     rollup=S.rollup("CYCLE-PROD"))
    # Break the channel configuration the way an outage would.
    cfg = os.path.join(project, ".ai-engineering", "notification-channels.json")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    res = dod(project, "WF-FEATURE", "REQ")
    blocked = [k for k, (st, _) in res.items() if st == "FAIL"]
    if blocked:
        return False, "a broken notification channel blocked the stage: %s" % ", ".join(blocked)
    return True, "REQ unaffected by the channel being down"


@fault("F-13", "GitLab is unreachable",
       "evidence that cannot be seen is reported pending, never as satisfied")
def f13(project):
    res = dod(project, "WF-FEATURE", "CI")
    wrong = [k for k, (st, _) in res.items() if st == "PASS"]
    if wrong:
        return False, "claimed to verify GitLab state with no GitLab: %s" % ", ".join(wrong)
    pending = [k for k, (st, _) in res.items() if st == "REQUIRES-EVIDENCE"]
    if not pending:
        return False, "no predicate reported the missing evidence"
    return True, "%d predicate(s) pending rather than passing" % len(pending)


# ---------------------------------------------- E. the controls' own failures

@fault("F-14", "The hook policy file is corrupt",
       "a high-risk command is denied anyway; the guard does not open")
def f14(project):
    import json
    import subprocess
    sandbox = tempfile.mkdtemp(prefix="aieos-fault-")
    try:
        for part in ("hooks", "policies"):
            shutil.copytree(os.path.join(ROOT, part), os.path.join(sandbox, part))
        with open(os.path.join(sandbox, "policies", "hook-policy.json"), "w") as fh:
            fh.write("{ not json")
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=sandbox)
        out = subprocess.run(
            [sys.executable, os.path.join(sandbox, "hooks", "scripts", "guard_bash.py")],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}}),
            capture_output=True, text=True, env=env, timeout=30).stdout.strip()
        if not out:
            return False, "the guard fell silent, which allows the command"
        decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        if decision != "deny":
            return False, "corrupt policy produced %r for terraform destroy" % decision
        return True, "terraform destroy -> deny with no policy file to read"
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


@fault("F-15", "The required model is not in the organization's allowlist",
       "CRITICAL work blocks rather than running on a weaker model")
def f15(project):
    import json
    import subprocess
    cfg = os.path.join(project, ".ai-engineering", "project.yaml")
    body = open(cfg, encoding="utf-8").read()
    if "  available_models: []" in body:
        body = body.replace("  available_models: []",
                            "  available_models:\n    - sonnet\n    - haiku", 1)
    else:
        return False, "the template no longer declares ai.available_models; fault not injected"
    open(cfg, "w", encoding="utf-8").write(body)
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "resolve_model.py"),
         "--role", "security-architect", "--risk", "CRITICAL", "--project", project, "--json"],
        capture_output=True, text=True, timeout=60)
    result = json.loads(proc.stdout)
    if not result.get("blocked"):
        return False, "resolved to %r instead of blocking" % result.get("model")
    if proc.returncode == 0:
        return False, "reported a block but exited 0, so a caller would proceed"
    return True, "blocked, exit %d" % proc.returncode



# ------------------------------------------------- F. nothing happens at all

@fault("F-16", "Work sits in one state and nobody moves it",
       "the stall is detected and named; a state machine cannot see this itself")
def f16(project):
    import subprocess
    docs = os.path.join(project, "docs", "stories")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "stuck.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nid: SIM-STORY-800\ntype: story\ntitle: Nobody picked this up\n"
                 "status: in-review\nowner: development-lead\nversion: 1\n"
                 "created_at: '2026-08-01'\nupdated_at: '2026-08-17T09:00:00'\n"
                 "source: simulation\nlinks: {}\n---\n")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "check_liveness.py"),
         "--project", project, "--now", "2026-08-20T12:00:00", "--json"],
        capture_output=True, text=True, timeout=120)
    import json as _json
    found = _json.loads(proc.stdout)["findings"]
    mine = [f for f in found if f["id"] == "SIM-STORY-800"]
    if not mine:
        return False, "a review untouched for three days was not reported"
    if proc.returncode == 0:
        return False, "reported the stall but exited 0, so nothing automated would act"
    return True, "%s stale %.0fh -> tell %s" % (mine[0]["id"], mine[0]["hours"], mine[0]["notify"])


@fault("F-17", "A role fans out past its concurrency limit",
       "the spawn escalates rather than proceeding; each agent is a full session")
def f17(project):
    import json as _json
    import subprocess
    import tempfile
    data = tempfile.mkdtemp(prefix="aieos-cc-")
    try:
        policy = _json.load(open(os.path.join(ROOT, "policies", "concurrency-policy.json")))
        cap = (policy["per_role"].get("development-lead") or {}).get("max_concurrent", 2)
        env = dict(os.environ, CLAUDE_PLUGIN_DATA=data)
        payload = _json.dumps({"tool_name": "Agent", "agent_type": "development-lead",
                               "session_id": "F17",
                               "tool_input": {"subagent_type": "backend-developer"}})
        guard = os.path.join(ROOT, "hooks", "scripts", "guard_spawn.py")
        for i in range(cap):
            out = subprocess.run([sys.executable, guard], input=payload, capture_output=True,
                                 text=True, env=env, timeout=30).stdout.strip()
            if out:
                return False, "blocked at spawn %d, below the limit of %d" % (i + 1, cap)
        out = subprocess.run([sys.executable, guard], input=payload, capture_output=True,
                             text=True, env=env, timeout=30).stdout.strip()
        if not out:
            return False, "spawn %d was allowed; the limit of %d did nothing" % (cap + 1, cap)
        decision = _json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        if decision != "ask":
            return False, "over the limit produced %r; it should ask, not %s"  % (
                decision, "deny outright" if decision == "deny" else decision)
        return True, "%d allowed, %dth asks" % (cap, cap + 1)
    finally:
        shutil.rmtree(data, ignore_errors=True)



@fault("F-18", "A migration reaches authorization with an untested rollback",
       "AUTHORIZE does not pass: a rollback that has never been run is not a plan")
def f18(project):
    S.write_artifact(project, "MIG", status="in-review",
                     schema_change="Split payload into typed columns",
                     data_impact="4.1M rows",
                     backward_compatibility="dual-read for one release",
                     forward_path="batched backfill",
                     dry_run_evidence="4,118,204 rows transformed",
                     backup_verified="2026-08-20",
                     restore_tested="restored in 18 minutes",
                     rollback_procedure="drop the new columns",
                     rollback_tested="",
                     irreversible_after="the payload column is dropped",
                     expected_duration="~35 minutes", lock_behaviour="no table lock")
    res = dod(project, "WF-MIGRATION", "AUTHORIZE")
    ok, why = must_fail(res, "required_fields_present(MIG)")
    if not ok:
        return False, ("the plan reached authorization with rollback_tested empty: %s" % why)
    ok2, why2 = must_fail(res, "human_approval_recorded(AP-05)")
    if not ok2:
        return False, "no rollback evidence but the approval predicate passed: " + why2
    return True, why


@fault("F-19", "A change request is decided with a dimension unanswered",
       "DECIDE does not pass while a blocking decision is open against the CR")
def f19(project):
    # The decision declares what it blocks; the blocked artifact does not declare
    # the decision. Getting this backwards is how a fault case can pass while
    # testing nothing.
    dec = S.write_artifact(project, "DEC", status="open", blocking=True,
                           blocks=["CR"], title="Who owns the compliance answer")
    S.write_artifact(project, "CR", status="assessing",
                     what_changes="Retention 30 to 90 days", why_now="A customer commitment",
                     current_commitment="SIM-REQ-001", impact={"storage": "3x"},
                     affected_artifacts=[], reversibility="reversible", rejected_options=[],
                     links={"decisions": [dec]},
                     rollup=S.rollup("CYCLE-ARCH", status="IN_PROGRESS"))
    res = dod(project, "WF-CHANGE", "ASSESS")
    ok, why = must_fail(res, "no_open_blocking_decisions_for(CR)")
    if not ok:
        return False, why
    return True, why



@fault("F-20", "A release is sought with readiness still not ready",
       "RELEASE does not pass: the approver reads the readiness record, not a promise")
def f20(project):
    S.write_artifact(project, "PRR", status="not-ready",
                     architecture="approved", security="one HIGH finding open",
                     testing="TESTREPORT accepted", performance="not applicable",
                     observability="alerts defined", runbook="SIM-RUN-001",
                     backup_restore="unchanged", rollback="previous tag redeploys",
                     capacity="within limits",
                     unmet=["A HIGH security finding is open"], accepted_by="")
    S.write_artifact(project, "REL", status="approved",
                     approvals=[S.approval("AP-01", "release-approver")],
                     rollback_plan="revert to the previous tag")
    res = dod(project, "WF-FEATURE", "RELEASE")
    ok, why = must_fail(res, "artifact_status(PRR, ready)")
    if not ok:
        return False, why
    held, detail = must_hold(res, "artifact_exists(REL)")
    if not held:
        return False, "the unready readiness record broke an unrelated predicate: " + detail
    return True, why


@fault("F-21", "Readiness is declared with no runbook",
       "READINESS does not pass: nobody can be woken at 3am to read an intention")
def f21(project):
    S.write_artifact(project, "PRR", status="ready",
                     architecture="approved", security="clean", testing="accepted",
                     performance="not applicable", observability="alerts defined",
                     runbook="to be written", backup_restore="unchanged",
                     rollback="previous tag", capacity="within limits",
                     unmet=[], accepted_by="gitlab:sim-human",
                     reviewers=[S.verdict("reliability-reviewer")])
    res = dod(project, "WF-FEATURE", "READINESS")
    ok, why = must_fail(res, "artifact_exists(RUN)")
    if not ok:
        return False, why
    ok2, why2 = must_fail(res, "every_linked(PRR, RUN)")
    if not ok2:
        return False, "the runbook is missing but the link predicate passed: " + why2
    return True, why



@fault("F-22", "An objective is promised with nothing that can measure it",
       "OBSERVABILITY does not pass: this is why the SLO and the design are separate artifacts")
def f22(project):
    nfr = S.write_artifact(project, "NFR", status="approved", target="99.9% availability")
    S.write_artifact(project, "SLO", status="active", source=nfr,
                     links={"non_functional": [nfr]},
                     sli="successful requests / total requests", objective="99.9%",
                     window="30 days", measured_from="a metric that does not exist yet",
                     error_budget="0.1%", breach_consequence="feature work pauses",
                     reviewers=[S.verdict("reliability-reviewer")])
    res = dod(project, "WF-FEATURE", "OBSERVABILITY")
    ok, why = must_fail(res, "every_linked(SLO, OBS)")
    if not ok:
        return False, why
    ok2, why2 = must_fail(res, "artifact_exists(OBS)")
    if not ok2:
        return False, "no observability design but artifact_exists passed: " + why2
    return True, why


@fault("F-23", "A quantified target ships with no objective at all",
       "OBSERVABILITY does not pass: a number in an NFR is not a commitment anyone can breach")
def f23(project):
    S.write_artifact(project, "NFR", status="approved", target="p95 under 800ms")
    S.write_artifact(project, "OBS", status="active",
                     signals=["request_duration_seconds"], dashboards=["Latency"],
                     alerts=[], health_checks=["/healthz"], logging="structured",
                     tracing="otel", instrumentation_owner="backend-developer", gaps=[],
                     reviewers=[S.verdict("reliability-reviewer")])
    res = dod(project, "WF-FEATURE", "OBSERVABILITY")
    ok, why = must_fail(res, "every_linked(NFR, SLO)")
    if not ok:
        return False, why
    return True, why



@fault("F-24", "A release reaches production having skipped a rung",
       "DEPLOY does not pass: skipping the record is skipping the evidence")
def f24(project):
    S.write_artifact(project, "REL", status="authorized",
                     approvals=[S.approval("AP-14", "release-approver")])
    # dev only. Staging never happened, or happened and nobody recorded it, and
    # from the outside those are the same thing.
    S.write_artifact(project, "PROM", status="promoted", environment="dev",
                     promoted_from="(none)", release_version="1.4.0",
                     evidence="unit and integration suites pass",
                     what_this_does_not_prove="Synthetic data only",
                     promoted_by="gitlab:sim-human")
    ok, why = must_fail(dod(project, "WF-RELEASE", "DEPLOY"), "promoted_through(production)")
    if not ok:
        return False, why
    if "staging" not in why:
        return False, "refused, but did not name the missing rung: %s" % why
    return True, why


# ------------------------------------------------------------------- runner

def run(selected=None, verbose=False):
    chosen = [f for f in FAULTS if not selected or f[0] in selected]
    failures = []
    for fid, title, expect, fn in chosen:
        project = tempfile.mkdtemp(prefix="aieos-fault-")
        try:
            S.make_project(project)
            S.COUNTERS.clear() if hasattr(S, "COUNTERS") else None
            try:
                ok, detail = fn(project)
            except Exception as exc:                       # noqa: BLE001
                ok, detail = False, "the fault case itself raised %r" % exc
        finally:
            shutil.rmtree(project, ignore_errors=True)
        mark = "ok  " if ok else "FAIL"
        print("%s %-6s %s" % (mark, fid, title))
        print("       expected: %s" % expect)
        if verbose or not ok:
            print("       actual:   %s" % detail)
        if not ok:
            failures.append(fid)
    print("\n%d fault(s) injected, %d unhandled" % (len(chosen), len(failures)))
    if failures:
        print("UNHANDLED: %s" % ", ".join(failures))
        print("An unhandled fault means the system advanced when it should have stopped, "
              "or stopped when it should have carried on.")
        return 1
    print("Every injected fault produced the refusal or the tolerance it should.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fault", action="append", help="run only these fault ids")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        for fid, title, expect, _ in FAULTS:
            print("%-6s %-46s %s" % (fid, title, expect))
        return 0
    return run(args.fault, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
