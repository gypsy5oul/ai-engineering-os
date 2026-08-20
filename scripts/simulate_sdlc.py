#!/usr/bin/env python3
"""Run a complete SDLC scenario end to end against a throwaway project.

This is an integration test for the organization itself. It creates real
artifacts with real headers, emits real events, produces real rollups, and then
evaluates each stage's machine-checkable definition of done. Anything the model
cannot actually satisfy shows up as a FAIL, which is the point: a workflow that
reads well but cannot be completed is a contradiction, not a process.

  python3 scripts/simulate_sdlc.py --scenario feature
  python3 scripts/simulate_sdlc.py --all
  python3 scripts/simulate_sdlc.py --scenario incident --keep   # leave the project for inspection
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from minyaml import parse_file  # noqa: E402
import check_dod  # noqa: E402

KEY = "SIM"
TODAY = datetime.utcnow().strftime("%Y-%m-%d")


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


MODEL = {a["code"]: a for a in load("policies/artifact-model.json")["artifact_types"]}


# ---------------------------------------------------------------- project

def make_project(path):
    os.makedirs(os.path.join(path, ".ai-engineering"))
    src = os.path.join(ROOT, "templates", "project", "project.yaml")
    with open(src, encoding="utf-8") as fh:
        cfg = fh.read()
    # The shipped template carries a blocking open decision on purpose. A
    # simulation that leaves it open would fail every no_open_blocking_decisions
    # predicate, which tests the template rather than the workflow.
    cfg = cfg.replace("    blocking: true", "    blocking: false")
    with open(os.path.join(path, ".ai-engineering", "project.yaml"), "w", encoding="utf-8") as fh:
        fh.write(cfg)
    for d in ("requirements", "architecture", "adrs", "design", "stories", "test-plans", "qa",
              "security", "release", "incidents", "incidents/evidence", "rcas", "decisions",
              "technical-debt", "runbooks"):
        os.makedirs(os.path.join(path, "docs", d), exist_ok=True)
    os.makedirs(os.path.join(path, "tests"), exist_ok=True)


COUNTER = {}


def next_id(code):
    COUNTER[code] = COUNTER.get(code, 0) + 1
    return "%s-%s-%03d" % (KEY, code, COUNTER[code])


def write_artifact(project, code, **over):
    """Create an artifact satisfying its contract in policies/artifact-model.json."""
    spec = MODEL[code]
    aid = over.pop("id", None) or next_id(code)
    header = {
        "id": aid, "type": spec["type"], "title": over.pop("title", "%s %s" % (spec["type"], aid)),
        "status": over.pop("status", spec["statuses"][0]), "owner": spec["owner_role"],
        "version": 1, "created_at": TODAY, "updated_at": TODAY,
        "source": over.pop("source", "simulation"),
        "reviewers": over.pop("reviewers", []), "approvals": over.pop("approvals", []),
        "dependencies": over.pop("dependencies", []), "links": over.pop("links", {}),
    }
    # Type-specific required fields, filled with something plausible so that
    # required_fields_present can actually be satisfied.
    for field in spec["required_fields"]:
        if field in header:
            continue
        header[field] = over.pop(field, "simulated %s" % field.replace("_", " "))
    header.update(over)

    storage = spec["storage"]
    folder = os.path.join(project, storage) if storage.startswith(("docs/", "tests/")) \
        else os.path.join(project, "docs", "qa")
    os.makedirs(folder, exist_ok=True)
    body = ["---"]
    for k, v in header.items():
        if isinstance(v, (dict, list)):
            body.append("%s: %s" % (k, json.dumps(v)))
        else:
            body.append("%s: %s" % (k, json.dumps(v) if isinstance(v, str) and (":" in v) else v))
    body += ["---", "", "Simulated artifact."]
    with open(os.path.join(folder, aid + ".md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")
    return aid


def verdict(reviewer, v="pass"):
    return {"reviewer": reviewer, "verdict": v, "at": TODAY, "findings": 0}


def approval(ref, role, identity="gitlab:sim-human", decision="approved",
             recorded_in="gitlab-merge-request-approval"):
    return {"id": "%s-sim%03d" % (ref, len(COUNTER)), "policy_ref": ref,
            "approver_id": identity, "approver_role": role, "at": TODAY,
            "recorded_in": recorded_in, "decision": decision}


def rollup(cycle, status="ACCEPTED", rework=1, escalations=None, next_gate="next"):
    return {"cycle": cycle, "status": status, "produced_by": cycle_lead(cycle), "at": TODAY,
            "rework_rounds": rework, "escalations": escalations or [], "next_gate": next_gate}


CYCLES = {}
for name in sorted(os.listdir(os.path.join(ROOT, "sdlc", "cycles"))):
    if name.endswith((".yaml", ".yml")):
        c = parse_file(os.path.join(ROOT, "sdlc", "cycles", name))
        CYCLES[c["id"]] = c


def cycle_lead(cid):
    return CYCLES[cid]["positions"]["lead"]


def emit(project, etype, subject, correlation, **payload):
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "emit_event.py"),
           "--type", etype, "--subject", subject, "--project", project,
           "--project-key", KEY, "--correlation-id", correlation]
    if payload:
        cmd += ["--payload"] + ["%s=%s" % (k, v) for k, v in payload.items()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def check_stage(project, workflow, stage):
    """Evaluate a stage's definition of done against the simulated project."""
    wfs = {}
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            wf = parse_file(os.path.join(base, name))
            wfs[wf["id"]] = wf
    wf = wfs[workflow]
    s = next(x for x in wf["stages"] if x["id"] == stage)
    artifacts = check_dod.load_artifacts(project)
    out = []
    for entry in s["definition_of_done"]:
        fn, args = check_dod.parse_predicate(entry)
        status, detail = check_dod.evaluate(fn, args, artifacts, project)
        out.append((entry, status, detail))
    return out


# ---------------------------------------------------------------- scenarios
#
# A scenario is a list of (workflow, stage, work). The work runs, then that
# stage's definition of done is evaluated immediately. Evaluating at the end of
# the run would test the final state rather than the stage: WF-DEFECT/TRIAGE
# requires the defect to be open and WF-DEFECT/VERIFY requires it closed, and
# both are correct at their own moment.

def scenario_feature(project, log):
    st = {}

    def idea():
        st["feat"] = "%s-FEAT-001" % KEY
        log("engineering-director sequences the work; UX skipped and recorded")
        emit(project, "FEATURE_CREATED", st["feat"], st["feat"], title="Simulated capability",
             requester="project-owner")

    def req():
        log("product-manager + requirements-analyst, gated on testability by qa-lead")
        st["req"] = write_artifact(project, "REQ", status="approved", source="project-owner",
                                   reviewers=[verdict("qa-lead")],
                                   approvals=[approval("AP-03", "project-owner",
                                                       recorded_in="project-decision-log")],
                                   rollup=rollup("CYCLE-PROD", next_gate="FEAS"))
        st["nfr"] = write_artifact(project, "NFR", status="approved", source=st["req"],
                                   target="99.5% over 30 days", reviewers=[verdict("qa-lead")],
                                   rollup=rollup("CYCLE-PROD"))
        emit(project, "REQUIREMENT_APPROVED", st["feat"], st["feat"],
             requirement_count=1, open_decisions=0)

    def feas():
        log("solution-architect assesses against the approved stack")
        st["feas"] = write_artifact(project, "FEAS", status="approved", source=st["req"],
                                    links={"requirements": [st["req"]]},
                                    reviewers=[verdict("architecture-reviewer")],
                                    approvals=[approval("AP-03", "engineering-owner",
                                                        recorded_in="project-decision-log")],
                                    rollup=rollup("CYCLE-ARCH", next_gate="ARCH"))

    def arch():
        log("TEAM: architect + security-architect + sre, reviewed by architecture-reviewer")
        st["arch"] = write_artifact(project, "ARCH", status="approved", source=st["feas"],
                                    links={"requirements": [st["req"], st["nfr"]]},
                                    reviewers=[verdict("architecture-reviewer")],
                                    approvals=[approval("AP-02", "architecture-owner",
                                                        recorded_in="project-decision-log")],
                                    rollup=rollup("CYCLE-ARCH", next_gate="STORY"))
        write_artifact(project, "ADR", status="accepted", source=st["arch"],
                       links={"requirements": [st["req"]], "architecture": [st["arch"]]},
                       reviewers=[verdict("architecture-reviewer")],
                       approvals=[approval("AP-02", "architecture-owner",
                                           recorded_in="project-decision-log")])
        write_artifact(project, "SEC", status="approved", source=st["arch"],
                       links={"architecture": [st["arch"]]},
                       reviewers=[verdict("security-reviewer")])
        emit(project, "ARCHITECTURE_APPROVED", st["feat"], st["feat"], adr_count=1, risks="2")

    def story():
        log("development-lead decomposes; parallel stories own disjoint paths")
        st["story"] = write_artifact(project, "STORY", status="done", source=st["req"],
                                     links={"requirements": [st["req"]],
                                            "architecture": [st["arch"]]},
                                     reviewers=[verdict("qa-lead")],
                                     rollup=rollup("CYCLE-DEV", rework=2, next_gate="REVIEW"))
        write_artifact(project, "EPIC", status="done", source=st["req"],
                       links={"requirements": [st["req"]]})
        emit(project, "STORY_CREATED", st["feat"], st["feat"], story_count=1, epics=1)

    def qadesign():
        log("qa-lead designs the tests BEFORE any implementation exists")
        st["tp"] = write_artifact(project, "TP", status="approved", source=st["req"],
                                  links={"requirements": [st["req"]], "stories": [st["story"]]},
                                  reviewers=[verdict("test-reviewer")],
                                  rollup=rollup("CYCLE-QA", next_gate="DEV"))
        st["test"] = write_artifact(project, "TEST", status="done", source=st["tp"],
                                    links={"test_plans": [st["tp"]], "requirements": [st["req"]],
                                           "stories": [st["story"]]},
                                    reviewers=[verdict("test-reviewer")])
        emit(project, "QA_PLAN_APPROVED", st["feat"], st["feat"], scenario_count=1, uncovered=0)

    def dev():
        log("TEAM: backend/frontend/data · peer review by code-reviewer · 2 rework rounds")
        emit(project, "DEVELOPMENT_STARTED", st["feat"], st["feat"], story_count=1, streams=3)
        emit(project, "DEVELOPMENT_COMPLETED", st["feat"], st["feat"], story_count=1,
             rework_rounds=2)

    def review():
        log("routed reviewers return verdicts; a human other than the author approves (AP-09)")
        write_artifact(project, "REVIEW", status="closed", source=st["story"],
                       links={"stories": [st["story"]], "merge_requests": ["!1"]},
                       reviewers=[verdict("code-reviewer"), verdict("security-reviewer")],
                       approvals=[approval("AP-09", "merge-approver")],
                       rollup=rollup("CYCLE-SEC", next_gate="CI"))
        emit(project, "CODE_REVIEW_COMPLETED", st["feat"], st["feat"], verdict="pass", findings=0)

    def qa():
        log("qa-lead executes; test-reviewer gates coverage and evidence")
        write_artifact(project, "TESTREPORT", status="closed", source=st["tp"],
                       links={"test_plans": [st["tp"]], "stories": [st["story"]]},
                       reviewers=[verdict("test-reviewer")],
                       approvals=[approval("AP-09", "qa-owner",
                                           recorded_in="project-decision-log")],
                       rollup=rollup("CYCLE-QA", next_gate="RELEASE"))
        emit(project, "QA_COMPLETED", st["feat"], st["feat"], verdict="pass", passed=1, failed=0)

    def release():
        log("release-manager assembles; the rollback plan exists BEFORE approval is sought")
        st["rel"] = write_artifact(project, "REL", status="approved", source=st["story"],
                                   links={"stories": [st["story"]], "merge_requests": ["!1"]},
                                   reviewers=[verdict("sre")],
                                   approvals=[approval("AP-01", "release-approver",
                                                       recorded_in="gitlab-release")],
                                   rollback_plan="revert to the previous tag; schema is expand-only")
        emit(project, "RELEASE_APPROVED", st["rel"], st["feat"], release_id=st["rel"],
             approver_role="release-approver")

    def authorize():
        log("a SEPARATE human act, taken at deployment time, not inherited from approval")
        patch_status(project, st["rel"], "authorized")
        emit(project, "DEPLOYMENT_AUTHORIZED", st["rel"], st["feat"], release_id=st["rel"],
             approver_role="release-approver", window="now")

    def deploy():
        log("devops-engineer executes against an AUTHORIZED release; CYCLE-DEVOPS concludes")
        patch_rollup(project, st["rel"], rollup("CYCLE-DEVOPS", next_gate="VERIFY"))

    def verify():
        log("release-manager with sre verifies, never the executor alone")
        patch_status(project, st["rel"], "done")
        emit(project, "DEPLOYMENT_COMPLETED", st["rel"], st["feat"], release_id=st["rel"],
             duration="4m", verification="ok")

    def ops():
        log("sre observes SLOs and alert quality; CYCLE-SRE concludes")
        patch_rollup(project, st["rel"], rollup("CYCLE-SRE", next_gate="next cycle"))

    return [("WF-FEATURE", "IDEA", idea), ("WF-FEATURE", "REQ", req),
            ("WF-FEATURE", "FEAS", feas), ("WF-FEATURE", "ARCH", arch),
            ("WF-FEATURE", "STORY", story), ("WF-FEATURE", "QADESIGN", qadesign),
            ("WF-FEATURE", "DEV", dev), ("WF-FEATURE", "REVIEW", review),
            ("WF-FEATURE", "QA", qa), ("WF-FEATURE", "RELEASE", release),
            ("WF-FEATURE", "AUTHORIZE", authorize), ("WF-FEATURE", "DEPLOY", deploy),
            ("WF-FEATURE", "VERIFY", verify), ("WF-FEATURE", "OPS", ops)]


def scenario_defect(project, log):
    st = {}

    def triage():
        log("qa-lead validates the failure before it becomes a development item")
        st["req"] = write_artifact(project, "REQ", status="approved", source="project-owner",
                                   reviewers=[verdict("qa-lead")])
        st["def"] = write_artifact(project, "DEF", status="open", source="qa execution",
                                   links={"requirements": [st["req"]]},
                                   reviewers=[verdict("code-reviewer")],
                                   rollup=rollup("CYCLE-QA", next_gate="CAUSE"))
        emit(project, "DEFECT_CREATED", st["def"], st["def"], defect_id=st["def"],
             severity="high", summary="sim")

    def test():
        log("the failing regression test is written FIRST and verified to fail")
        st["test"] = write_artifact(project, "TEST", status="done", source=st["def"],
                                    links={"defects": [st["def"]]},
                                    reviewers=[verdict("test-reviewer")])

    def fix():
        log("backend-developer fixes the cause; CYCLE-DEV concludes here")
        patch_rollup(project, st["def"], rollup("CYCLE-DEV", rework=1, next_gate="REVIEW"))

    def review():
        log("routed review; the fix addresses the cause, not the symptom")
        write_artifact(project, "REVIEW", status="closed", source=st["def"],
                       links={"defects": [st["def"]], "merge_requests": ["!2"]},
                       reviewers=[verdict("code-reviewer"), verdict("test-reviewer")],
                       approvals=[approval("AP-09", "merge-approver")])

    def verify():
        log("verified against the ORIGINAL reproduction, by someone other than the fixer")
        patch_status(project, st["def"], "closed")
        patch_rollup(project, st["test"], rollup("CYCLE-QA", next_gate="RELEASE"))
        emit(project, "DEFECT_FIXED", st["def"], st["def"], defect_id=st["def"])

    def release():
        log("expedited route: every gate still carries a verdict")
        write_artifact(project, "REL", status="done", source=st["def"],
                       links={"defects": [st["def"]]}, reviewers=[verdict("sre")],
                       approvals=[approval("AP-01", "release-approver",
                                           recorded_in="gitlab-release")])

    return [("WF-DEFECT", "TRIAGE", triage), ("WF-DEFECT", "TEST", test),
            ("WF-DEFECT", "FIX", fix), ("WF-DEFECT", "REVIEW", review),
            ("WF-DEFECT", "VERIFY", verify), ("WF-DEFECT", "RELEASE", release)]


def scenario_incident(project, log):
    st = {}

    def evidence():
        log("sre states the symptom; commander declares severity and notifies the human")
        st["inc"] = write_artifact(project, "INC", status="open", source="alert",
                                   approvals=[approval("AP-01", "on-call-owner",
                                                       recorded_in="project-decision-log")])
        emit(project, "INCIDENT_CREATED", st["inc"], st["inc"], incident_id=st["inc"],
             severity="1", symptom="sim")
        log("evidence collected and SEALED before any destructive remediation")
        st["evid"] = write_artifact(project, "EVID", status="sealed", source=st["inc"],
                                    links={"incidents": [st["inc"]]}, dependencies=[st["inc"]])

    def mitigate():
        log("TEAM_REQUIRED investigation; every production action authorized by a human")
        patch_status(project, st["inc"], "mitigated")
        emit(project, "INCIDENT_MITIGATED", st["inc"], st["inc"], incident_id=st["inc"],
             mitigation="flag off", approver_role="on-call-owner")

    def rca():
        log("rca-analyst is independent of the commander; root cause must be systemic")
        patch_status(project, st["inc"], "recovered")
        st["rca"] = write_artifact(project, "RCA", status="approved", source=st["inc"],
                                   links={"incidents": [st["inc"]]},
                                   dependencies=[st["inc"], st["evid"]],
                                   reviewers=[verdict("engineering-director")],
                                   approvals=[approval("AP-01", "engineering-owner",
                                                       recorded_in="project-decision-log")],
                                   rollup=rollup("CYCLE-SRE", next_gate="FEEDBACK"))

    def feedback():
        log("typed follow-ups become real backlog items with owners")
        st["def"] = write_artifact(project, "DEF", status="open", source=st["rca"],
                                   links={"rcas": [st["rca"]]})
        patch_links(project, st["rca"], defects=[st["def"]])
        write_artifact(project, "DEBT", status="open", source=st["rca"],
                       links={"rcas": [st["rca"]]})
        patch_status(project, st["inc"], "closed")
        emit(project, "RCA_COMPLETED", st["inc"], st["inc"], incident_id=st["inc"],
             root_cause="systemic", action_count=2)

    return [("WF-INCIDENT", "EVIDENCE", evidence), ("WF-INCIDENT", "MITIGATE", mitigate),
            ("WF-INCIDENT", "RCA", rca), ("WF-INCIDENT", "FEEDBACK", feedback)]


def scenario_security_block(project, log):
    st = {}

    def classify():
        log("dependency-reviewer classifies the route; urgency from exploitability, not CVSS")
        st["depa"] = write_artifact(project, "DEPA", status="draft", source="advisory",
                                    route="security-vulnerability",
                                    urgency_basis="reachable in this deployment",
                                    rollup=rollup("CYCLE-SEC", next_gate="SECURITY"))
        emit(project, "DEPENDENCY_ADVISORY", st["depa"], st["depa"], dependency="lib",
             route="security-vulnerability", urgency_basis="reachable")

    def security():
        log("HIGH finding blocks the release; a human grants the exception (AP-04)")
        patch_status(project, st["depa"], "approved")
        _rewrite(project, st["depa"], lambda h: h.update(
            reviewers=[verdict("security-reviewer")],
            approvals=[approval("AP-04", "security-owner",
                                recorded_in="project-decision-log")]))
        emit(project, "SECURITY_BLOCKED", st["depa"], st["depa"], severity="high",
             finding_id=st["depa"], release_id="REL-1")
        emit(project, "SECURITY_EXCEPTION_GRANTED", st["depa"], st["depa"],
             finding_id=st["depa"], approver_role="security-owner", expires="90d")

    return [("WF-DEPENDENCY", "CLASSIFY", classify), ("WF-DEPENDENCY", "SECURITY", security)]


def scenario_release_rollback(project, log):
    st = {}

    def assemble():
        log("release-manager assembles; a change missing a verdict blocks the release")
        st["rel"] = write_artifact(project, "REL", status="approved", source="sim",
                                   links={"stories": [], "merge_requests": ["!9"]},
                                   reviewers=[verdict("qa-lead"), verdict("security-reviewer"),
                                              verdict("sre"), verdict("test-reviewer")],
                                   approvals=[approval("AP-01", "release-approver",
                                                       recorded_in="gitlab-release")],
                                   rollback_plan="revert tag",
                                   rollback_triggers="error rate above 2%")

    def staging():
        log("TEAM: qa, security and operability validate the same candidate; CYCLE-QA concludes")
        st["tr"] = write_artifact(project, "TESTREPORT", status="closed", source=st["rel"],
                                  links={"test_plans": [], "stories": []},
                                  reviewers=[verdict("test-reviewer")],
                                  approvals=[approval("AP-09", "qa-owner",
                                                      recorded_in="project-decision-log")],
                                  rollup=rollup("CYCLE-QA", next_gate="APPROVE"))

    def approve():
        log("content approved by a named human (AP-01)")

    def authorize():
        log("deployment authorized separately, at deployment time")
        patch_status(project, st["rel"], "authorized")

    def deploy():
        log("devops executes; CYCLE-DEVOPS concludes")
        patch_rollup(project, st["rel"], rollup("CYCLE-DEVOPS", next_gate="VERIFY"))

    def verify():
        log("post-deployment verification; CYCLE-SRE concludes")
        patch_status(project, st["rel"], "done")
        patch_rollup(project, st["rel"], rollup("CYCLE-SRE", next_gate="OPS"))

    def rollback():
        log("a trigger fired; rollback is itself an authorized act")
        patch_status(project, st["rel"], "rolled-back")
        emit(project, "DEPLOYMENT_FAILED", st["rel"], st["rel"], release_id=st["rel"],
             trigger="error rate", rollback_state="complete")

    return [("WF-RELEASE", "ASSEMBLE", assemble), ("WF-RELEASE", "STAGING", staging),
            ("WF-RELEASE", "APPROVE", approve), ("WF-RELEASE", "AUTHORIZE", authorize),
            ("WF-RELEASE", "DEPLOY", deploy), ("WF-RELEASE", "VERIFY", verify),
            ("WF-RELEASE", "ROLLBACK", rollback)]


def scenario_agent_change(project, log):
    st = {}

    def design():
        log("agent-architect decides agent, skill, reviewer, policy or nothing")
        st["adr"] = write_artifact(project, "ADR", status="accepted", source="governance finding",
                                   reviewers=[verdict("architecture-reviewer")],
                                   approvals=[approval("AP-10", "ai-governance-owner",
                                                       recorded_in="gitlab-merge-request-approval")],
                                   rollup=rollup("CYCLE-ARCH", next_gate="IMPLEMENT"))

    def security():
        log("security reviews permission, hook and policy changes")
        write_artifact(project, "SEC", status="approved", source=st["adr"],
                       links={"architecture": []},
                       reviewers=[verdict("security-reviewer")],
                       rollup=rollup("CYCLE-SEC", next_gate="GOVERN"))

    def govern():
        log("ai-governance produces findings; a named human approves (AP-10)")
        write_artifact(project, "REVIEW", status="closed", source=st["adr"],
                       links={"stories": [], "merge_requests": ["!42"]},
                       reviewers=[verdict("ai-governance"), verdict("agent-evaluator")],
                       approvals=[approval("AP-10", "ai-governance-owner")])

    def release():
        log("version bump, changelog, migration note where behaviour changed")

    return [("WF-AGENT-CHANGE", "DESIGN", design), ("WF-AGENT-CHANGE", "SECURITY", security),
            ("WF-AGENT-CHANGE", "GOVERN", govern), ("WF-AGENT-CHANGE", "RELEASE", release)]


# ---------------------------------------------------------------- helpers

def _rewrite(project, aid, mutate):
    for dirpath, dirnames, files in os.walk(project):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in files:
            if name != aid + ".md":
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            parts = text.split("---")
            header = {}
            for line in parts[1].strip().splitlines():
                k, v = line.split(":", 1)
                v = v.strip()
                try:
                    header[k.strip()] = json.loads(v)
                except Exception:
                    header[k.strip()] = v
            mutate(header)
            body = ["---"]
            for k, v in header.items():
                body.append("%s: %s" % (k, json.dumps(v) if isinstance(v, (dict, list, str)) else v))
            body += ["---", "", "Simulated artifact."]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(body) + "\n")
            return True
    return False


def patch_links(project, aid, **edges):
    def m(h):
        links = h.get("links") or {}
        for k, v in edges.items():
            links.setdefault(k, [])
            links[k] = list(set(links[k]) | set(v))
        h["links"] = links
        h["version"] = int(h.get("version", 1)) + 1
    _rewrite(project, aid, m)


def patch_rollup(project, aid, value):
    def m(h):
        h["rollup"] = value
        h["version"] = int(h.get("version", 1)) + 1
    _rewrite(project, aid, m)


def patch_status(project, aid, status):
    def m(h):
        h["status"] = status
        h["version"] = int(h.get("version", 1)) + 1
    _rewrite(project, aid, m)


def scenario_onboarding(project, log):
    st = {}

    def discover():
        log("observation only: finding a manifest does not mean the stack is approved")

    def ask():
        log("every decision to a human; what cannot be answered becomes a DEC")
        st["dec"] = write_artifact(project, "DEC", status="answered", source="onboarding",
                                   question="Which backend framework is approved?",
                                   options="fastapi | spring | none",
                                   impact="blocks ARCH", blocks="ARCH",
                                   decided_option="fastapi", decided_at=TODAY,
                                   approvals=[approval("AP-03", "project-owner",
                                                       recorded_in="project-decision-log")],
                                   rollup=rollup("CYCLE-PROD", next_gate="DECIDE"))

    def decide():
        log("configuration authored from human answers, never from inference")

    def verify():
        log("report: configured, open, and what the agents will refuse to do")

    return [("WF-ONBOARDING", "DISCOVER", discover), ("WF-ONBOARDING", "ASK", ask),
            ("WF-ONBOARDING", "DECIDE", decide), ("WF-ONBOARDING", "VERIFY", verify)]


SCENARIOS = {
    "onboarding": scenario_onboarding,
    "feature": scenario_feature,
    "defect": scenario_defect,
    "incident": scenario_incident,
    "security-block": scenario_security_block,
    "release-rollback": scenario_release_rollback,
    "agent-change": scenario_agent_change,
}


def run(name, keep=False, verbose=False):
    project = tempfile.mkdtemp(prefix="aieos-sim-%s-" % name)
    COUNTER.clear()
    current = {"stage": ""}

    def log(what):
        print("   %-11s %s" % (current["stage"], what))

    print("\n=== %s ===" % name)
    make_project(project)
    steps = SCENARIOS[name](project, log)

    totals = {"PASS": 0, "FAIL": 0, "REQUIRES-EVIDENCE": 0}
    failures = []
    for workflow, stage, work in steps:
        current["stage"] = stage
        work()
        # Evaluated the moment the stage completes, not at the end of the run.
        results = check_stage(project, workflow, stage)
        counts = {"PASS": 0, "FAIL": 0, "REQUIRES-EVIDENCE": 0}
        for entry, status, detail in results:
            counts[status] += 1
            totals[status] += 1
            if status == "FAIL":
                failures.append((stage, entry, detail))
            if verbose:
                print("       %-18s %s" % (status, entry))
        mark = "ok " if not counts["FAIL"] else "FAIL"
        print("   %s %-11s DoD: %d pass · %d fail · %d need evidence"
              % (mark, "", counts["PASS"], counts["FAIL"], counts["REQUIRES-EVIDENCE"]))

    if failures:
        print("\n   failures:")
        for stage, entry, detail in failures:
            print("     %-11s %-38s %s" % (stage, entry, detail[:70]))

    log_dir = os.path.join(project, ".ai-engineering", "events")
    n_events = 0
    if os.path.isdir(log_dir):
        for f in os.listdir(log_dir):
            with open(os.path.join(log_dir, f)) as fh:
                n_events += sum(1 for line in fh if line.strip())
    print("\n   %d stage(s) · %d predicate(s): %d pass · %d fail · %d need evidence · %d events"
          % (len(steps), sum(totals.values()), totals["PASS"], totals["FAIL"],
             totals["REQUIRES-EVIDENCE"], n_events))

    if keep:
        print("   project kept at %s" % project)
    else:
        shutil.rmtree(project, ignore_errors=True)
    return totals["FAIL"], failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    names = sorted(SCENARIOS) if (args.all or not args.scenario) else [args.scenario]
    total_failures, all_failures = 0, []
    for name in names:
        f, details = run(name, args.keep, args.verbose)
        total_failures += f
        all_failures += details

    print("\n%s" % ("=" * 78))
    if total_failures:
        print("%d definition-of-done failure(s) across %d scenario(s)."
              % (total_failures, len(names)))
        print("Each is a workflow that cannot actually be completed as written.")
    else:
        print("All %d scenario(s) completed with every definition of done satisfied." % len(names))
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())
