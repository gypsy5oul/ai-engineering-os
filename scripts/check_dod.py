#!/usr/bin/env python3
"""Definition-of-done checker.

Two modes, deliberately distinct:

  --grammar   Validate every DoD predicate in the workflows: known name, correct
              arity, known artifact codes. Runs in this repository's CI.

  (default)   Evaluate the DoD for a workflow stage against a real project. Only
              predicates marked checkable 'project' or 'repo' can be evaluated
              here; predicates marked 'gitlab' are reported as REQUIRES-EVIDENCE
              with the place the evidence lives, never as passing.

  python3 scripts/check_dod.py --grammar
  python3 scripts/check_dod.py --workflow WF-FEATURE --stage REQ --project /path/to/project
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402
from frontmatter import read as read_fm  # noqa: E402

CALL = re.compile(r"^([a-z_]+)\(([^)]*)\)$")


def model():
    with open(os.path.join(ROOT, "policies", "artifact-model.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _cycle_rework_limit(cycle_id):
    base = os.path.join(ROOT, "sdlc", "cycles")
    if not os.path.isdir(base):
        return 3
    for name in os.listdir(base):
        if not name.endswith((".yaml", ".yml")):
            continue
        c = parse_file(os.path.join(base, name))
        if c["id"] == cycle_id:
            return c["rework"]["limit"]
    return 3


def _registry_agents():
    path = os.path.join(ROOT, "policies", "agent-registry.json")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {a["name"] for a in json.load(fh)["agents"]}


def workflows():
    base = os.path.join(ROOT, "sdlc", "workflows")
    out = {}
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            wf = parse_file(os.path.join(base, name))
            out[wf["id"]] = wf
    return out


def cycles():
    base = os.path.join(ROOT, "sdlc", "cycles")
    out = {}
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            c = parse_file(os.path.join(base, name))
            out[c["id"]] = c
    return out


def parse_predicate(entry):
    m = CALL.match(entry.strip())
    if not m:
        return None, None
    raw = m.group(2).strip()
    return m.group(1), ([a.strip() for a in raw.split(",")] if raw else [])


# ---------------------------------------------------------------- grammar

def check_grammar():
    m = model()
    preds, codes = m["dod_predicates"], {a["code"] for a in m["artifact_types"]}
    errors = 0
    for cid, cyc in cycles().items():
        for entry in (cyc.get("acceptance") or {}).get("conditions", []):
            fn, args = parse_predicate(entry)
            if fn is None:
                print("ERROR %s [acceptance]: %r is not a predicate call" % (cid, entry)); errors += 1
            elif fn not in preds:
                print("ERROR %s [acceptance]: unknown predicate %s" % (cid, fn)); errors += 1
            elif len(args) != len(preds[fn]["args"]):
                print("ERROR %s [acceptance]: %s takes %d arg(s), got %d"
                      % (cid, fn, len(preds[fn]["args"]), len(args))); errors += 1

    for wid, wf in workflows().items():
        entries = [("workflow", e) for e in wf.get("definition_of_done", [])]
        for s in wf["stages"]:
            entries += [(s["id"], e) for e in s.get("definition_of_done", [])]
        for where, entry in entries:
            fn, args = parse_predicate(entry)
            if fn is None:
                print("ERROR %s [%s]: %r is not a predicate call" % (wid, where, entry)); errors += 1
            elif fn not in preds:
                print("ERROR %s [%s]: unknown predicate %s" % (wid, where, fn)); errors += 1
            elif len(args) != len(preds[fn]["args"]):
                print("ERROR %s [%s]: %s takes %d arg(s), got %d"
                      % (wid, where, fn, len(preds[fn]["args"]), len(args))); errors += 1
            else:
                for i, a in enumerate(args):
                    if preds[fn]["args"][i] == "artifact_code" and a not in codes:
                        print("ERROR %s [%s]: %s references unknown artifact code %s"
                              % (wid, where, fn, a)); errors += 1
    total = sum(len(w.get("definition_of_done", [])) + sum(len(s.get("definition_of_done", []))
                for s in w["stages"]) for w in workflows().values())
    print("\n%d predicate(s) checked, %d error(s)" % (total, errors))
    return 1 if errors else 0


# ---------------------------------------------------------------- evaluation

def scope_to_change(artifacts, change):
    """Narrow a project's artifacts to one unit of work.

    Predicates used to match every artifact in the project. That made a finished
    run vacuously satisfy a new one, and made two concurrent runs starve each
    other: one feature's IN_PROGRESS rollup failed cycle_accepted for every other
    feature in flight. Scoping by change is what makes the predicates mean
    "this work item" rather than "anything anyone has ever done here".
    """
    if not change:
        return artifacts
    return [a for a in artifacts if a.get("change") == change]


def changes_present(artifacts):
    """The distinct units of work visible in a set of artifacts."""
    return sorted({a["change"] for a in artifacts if a.get("change")})


def load_artifacts(project):
    """Read every artifact header under the project's knowledge root."""
    found = []
    for dirpath, dirnames, files in os.walk(project):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "node_modules", "__pycache__", "templates")]
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                fm, _ = read_fm(os.path.join(dirpath, name))
            except Exception:
                continue
            if isinstance(fm, dict) and fm.get("id") and fm.get("type"):
                fm["_path"] = os.path.relpath(os.path.join(dirpath, name), project)
                found.append(fm)
    return found


def by_code(artifacts, code):
    return [a for a in artifacts
            if re.match(r"^[A-Z][A-Z0-9]{1,9}-%s-[0-9]{3,}$" % re.escape(code), str(a.get("id", "")))]


def evaluate(fn, args, artifacts, project):
    """Returns (status, detail). status is PASS, FAIL or REQUIRES-EVIDENCE."""
    if fn == "artifact_exists":
        hits = by_code(artifacts, args[0])
        return ("PASS" if hits else "FAIL"), "%d artifact(s) of type %s" % (len(hits), args[0])

    if fn == "artifact_status":
        hits = by_code(artifacts, args[0])
        if not hits:
            return "FAIL", "no %s artifact exists" % args[0]
        bad = [a["id"] for a in hits if a.get("status") != args[1]]
        return ("PASS" if not bad else "FAIL"), ("all %s are %s" % (args[0], args[1])
                                                 if not bad else "not %s: %s" % (args[1], ", ".join(bad)))

    if fn == "corrective_actions_tracked":
        # An incident's follow-up may legitimately be a defect, a debt item, a new
        # requirement or an architecture decision. Demanding a defect specifically
        # forced an RCA whose actions were all monitoring or process improvements
        # to invent one.
        KINDS = ("DEF", "DEBT", "REQ", "ADR")
        src = by_code(artifacts, args[0])
        if not src:
            return "FAIL", "no %s artifact exists to link from" % args[0]
        pats = [re.compile(r"^[A-Z][A-Z0-9]{1,9}-%s-" % k) for k in KINDS]
        back = set()
        for kind in KINDS:
            for t_art in by_code(artifacts, kind):
                for v in (t_art.get("links") or {}).values():
                    for e in (v if isinstance(v, list) else [v]):
                        back.add(str(e))
        missing = []
        for a in src:
            edges = []
            for v in (a.get("links") or {}).values():
                edges += v if isinstance(v, list) else [v]
            forward = any(pat.match(str(e)) for e in edges for pat in pats)
            if not forward and a["id"] not in back:
                missing.append(a["id"])
        return ("PASS" if not missing else "FAIL"), (
            "every %s tracks a corrective action (%s)" % (args[0], "/".join(KINDS))
            if not missing else
            "%d %s with no corrective action of any kind: %s"
            % (len(missing), args[0], ", ".join(missing)))

    if fn == "every_linked":
        src = by_code(artifacts, args[0])
        if not src:
            return "FAIL", "no %s artifact exists to link from" % args[0]
        targets = by_code(artifacts, args[1])
        pat = re.compile(r"^[A-Z][A-Z0-9]{1,9}-%s-" % re.escape(args[1]))

        def edges_of(a):
            out = []
            for v in (a.get("links") or {}).values():
                out += v if isinstance(v, list) else [v]
            return [str(e) for e in out]

        # The edge counts in either direction. A requirement cannot link to an
        # architecture that does not exist when the requirement is authored, so
        # requiring a forward link would make the predicate unsatisfiable at the
        # only time it matters. docs/knowledge-structure.md states the model is
        # bidirectional by intent.
        back = set()
        for t_art in targets:
            for e in edges_of(t_art):
                back.add(e)
        missing = []
        for a in src:
            forward = any(pat.match(e) for e in edges_of(a))
            if not forward and a["id"] not in back:
                missing.append(a["id"])
        return ("PASS" if not missing else "FAIL"), (
            "every %s is linked to a %s in one direction or the other" % (args[0], args[1])
            if not missing else
            "%d %s with no %s edge either way: %s"
            % (len(missing), args[0], args[1], ", ".join(missing[:5])))

    if fn == "field_quantified":
        hits = by_code(artifacts, args[0])
        if not hits:
            return "FAIL", "no %s artifact exists" % args[0]
        vague = [a["id"] for a in hits
                 if not re.search(r"\d", str(a.get(args[1], ""))) and not a.get("open_question")]
        return ("PASS" if not vague else "FAIL"), ("quantified" if not vague else
                                                   "unquantified: %s" % ", ".join(vague[:5]))

    if fn == "agent_verdict":
        reviewer, want = args
        for a in artifacts:
            for r in a.get("reviewers") or []:
                if r.get("reviewer") == reviewer and r.get("verdict") == want:
                    return "PASS", "%s recorded %s on %s" % (reviewer, want, a["id"])
        return "FAIL", "no recorded %s verdict from %s" % (want, reviewer)

    if fn == "human_approval_recorded":
        if args[0] == "none":
            return "PASS", "no human approval required at this stage"
        for a in artifacts:
            for ap in a.get("approvals") or []:
                if ap.get("policy_ref") == args[0]:
                    return "PASS", "%s recorded on %s in %s" % (args[0], a["id"], ap.get("recorded_in"))
        return "REQUIRES-EVIDENCE", ("%s must be recorded in GitLab. A session cannot see it; "
                                     "check the merge request or release." % args[0])

    if fn == "promoted_through":
        target = args[0]
        cfg = {}
        for cand in ("project.yaml", "project.json"):
            path = os.path.join(project, ".ai-engineering", cand)
            if not os.path.exists(path):
                continue
            if path.endswith((".yaml", ".yml")):
                cfg = parse_file(path)
            else:
                with open(path, encoding="utf-8") as fh:
                    cfg = json.load(fh)
            break
        ladder = [e.get("name") for e in ((cfg.get("deployment") or {}).get("environments") or [])]
        if not ladder:
            return "REQUIRES-EVIDENCE", ("the project declares no deployment ladder under "
                                         "deployment.environments, so there is nothing to promote "
                                         "through")
        if target not in ladder:
            return "FAIL", ("%r is not in this project's ladder (%s)"
                            % (target, " -> ".join(ladder)))
        # Every rung strictly below the target must carry a promotion record. A
        # release that reached production without a staging record did not skip a
        # test; it skipped the evidence that the test happened.
        below = ladder[:ladder.index(target)]
        promoted = {a.get("environment") for a in by_code(artifacts, "PROM")
                    if a.get("status") == "promoted"}
        missing = [e for e in below if e not in promoted]
        if missing:
            return "FAIL", ("no promotion record for %s. The ladder is %s and it cannot be skipped."
                            % (", ".join(missing), " -> ".join(ladder)))
        return "PASS", ("promoted through %s" % " -> ".join(below + [target]) if below
                        else "%s is the first rung" % target)

    if fn == "no_blocking_open_decisions":
        cfg_path = None
        for cand in ("project.yaml", "project.json"):
            p = os.path.join(project, ".ai-engineering", cand)
            if os.path.exists(p):
                cfg_path = p
                break
        if not cfg_path:
            return "FAIL", "no project configuration"
        if cfg_path.endswith((".yaml", ".yml")):
            cfg = parse_file(cfg_path)
        else:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        blocking = [d["id"] for d in (cfg.get("open_decisions") or []) if d.get("blocking")]
        if args[0] == "unowned":
            blocking = [d["id"] for d in (cfg.get("open_decisions") or [])
                        if d.get("blocking") and not d.get("owner")]
        return ("PASS" if not blocking else "FAIL"), ("none blocking" if not blocking
                                                      else "blocking: " + ", ".join(blocking))

    if fn == "config_valid":
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate_project_config.py")],
                           cwd=project, capture_output=True, text=True)
        return ("PASS" if r.returncode == 0 else "FAIL"), r.stdout.strip().splitlines()[-1] if r.stdout else ""

    if fn == "required_fields_present":
        m = model()
        spec = next((a for a in m["artifact_types"] if a["code"] == args[0]), None)
        if spec is None:
            return "FAIL", "no contract for artifact code %s" % args[0]
        hits = by_code(artifacts, args[0])
        if not hits:
            return "FAIL", "no %s artifact exists" % args[0]
        bad = []
        for a in hits:
            missing = []
            for f in spec["required_fields"]:
                if f not in a:
                    missing.append(f)
                    continue
                value = a[f]
                # An empty list or map is a positive statement that there are
                # none. Only a scalar that is absent or blank is a gap.
                if isinstance(value, (list, dict)):
                    continue
                if value in (None, ""):
                    missing.append(f)
            if missing:
                bad.append("%s missing %s" % (a["id"], ", ".join(missing[:4])))
        return ("PASS" if not bad else "FAIL"), ("all %s complete" % args[0] if not bad
                                                 else "; ".join(bad[:3]))

    if fn == "artifact_owned_by":
        hits = by_code(artifacts, args[0])
        if not hits:
            return "FAIL", "no %s artifact exists" % args[0]
        bad = [a["id"] for a in hits if a.get("owner") != args[1]]
        return ("PASS" if not bad else "FAIL"), ("owned by %s" % args[1] if not bad
                                                 else "wrong owner: %s" % ", ".join(bad[:3]))

    if fn == "decision_resolved":
        hits = [a for a in artifacts if str(a.get("id", "")).endswith(args[0])
                or str(a.get("id", "")) == args[0]]
        if not hits:
            return "FAIL", "no decision %s found" % args[0]
        open_ = [a["id"] for a in hits if a.get("status") == "open"]
        return ("PASS" if not open_ else "FAIL"), ("resolved" if not open_
                                                   else "still open: %s" % ", ".join(open_))

    if fn == "no_open_blocking_decisions_for":
        blocking = [a["id"] for a in by_code(artifacts, "DEC")
                    if a.get("status") == "open" and args[0] in (a.get("blocks") or [])]
        return ("PASS" if not blocking else "FAIL"), ("no open decision blocks %s" % args[0]
                                                      if not blocking else
                                                      "blocked by: %s" % ", ".join(blocking))

    if fn == "evidence_sealed":
        hits = by_code(artifacts, "EVID")
        if not hits:
            return "FAIL", "no evidence record: collect it before any destructive remediation"
        unsealed = [a["id"] for a in hits if a.get("status") != "sealed"]
        return ("PASS" if not unsealed else "FAIL"), ("evidence sealed" if not unsealed
                                                      else "unsealed: %s" % ", ".join(unsealed))

    if fn == "release_authorized":
        hits = by_code(artifacts, "REL")
        if not hits:
            return "FAIL", "no release artifact"
        ok = [a["id"] for a in hits if a.get("status") in ("authorized", "done")]
        return ("PASS" if ok else "FAIL"), ("authorized: %s" % ", ".join(ok) if ok else
                                            "release is approved but not authorized; approval of "
                                            "content does not permit deployment")

    if fn == "human_identity_recorded":
        agent_names = _registry_agents()
        for a in artifacts:
            for ap in a.get("approvals") or []:
                if ap.get("policy_ref") != args[0]:
                    continue
                if not ap.get("approver_id") or not ap.get("approver_role"):
                    return "FAIL", "%s on %s has no approver_id/approver_role" % (args[0], a["id"])
                if ap["approver_role"] in agent_names:
                    return "FAIL", "%s on %s names the agent %s as approver" % (
                        args[0], a["id"], ap["approver_role"])
                return "PASS", "%s by %s (%s)" % (args[0], ap["approver_id"], ap["approver_role"])
        return "REQUIRES-EVIDENCE", "%s not found on any artifact; check GitLab" % args[0]

    if fn in ("cycle_accepted", "cycle_rollup_reported", "no_open_rework"):
        cycle_id = args[0]
        rollups = [(a, a["rollup"]) for a in artifacts
                   if isinstance(a.get("rollup"), dict) and a["rollup"].get("cycle") == cycle_id]
        # An unscoped run that spans several units of work cannot answer the
        # question that was asked. Refusing is the only honest result: silently
        # mixing them is what let a stale rollup satisfy a new feature.
        spanning = changes_present([a for a, _ in rollups])
        if len(spanning) > 1:
            return "FAIL", ("%d units of work carry a %s rollup (%s). Re-run with --change to say "
                            "which one is being evaluated." % (len(spanning), cycle_id,
                                                               ", ".join(spanning)))
        if not rollups:
            if fn == "cycle_rollup_reported":
                return "FAIL", ("no rollup for %s. A department that completed without reporting has "
                                "not finished." % cycle_id)
            return "FAIL", "no work item carries a %s rollup" % cycle_id
        if fn == "cycle_rollup_reported":
            bad = [a["id"] for a, r in rollups if not r.get("produced_by")]
            return ("PASS" if not bad else "FAIL"), (
                "%d rollup(s) reported" % len(rollups) if not bad
                else "rollup without a producer: %s" % ", ".join(bad))
        if fn == "cycle_accepted":
            notdone = ["%s=%s" % (a["id"], r["status"]) for a, r in rollups
                       if r.get("status") != "ACCEPTED"]
            return ("PASS" if not notdone else "FAIL"), (
                "%s accepted" % cycle_id if not notdone else "not accepted: " + ", ".join(notdone))
        limit = _cycle_rework_limit(cycle_id)
        over = ["%s=%d" % (a["id"], r.get("rework_rounds", 0)) for a, r in rollups
                if r.get("rework_rounds", 0) > limit]
        def unresolved(entry):
            # A bare string is an open escalation; a record is open until it is
            # resolved. The list was previously read as open in its entirety, so
            # recording an escalation at all blocked the stage forever.
            return not (isinstance(entry, dict) and entry.get("resolved_at"))

        open_esc = [a["id"] for a, r in rollups
                    if any(unresolved(e) for e in (r.get("escalations") or []))]
        problems = over + ["%s has open escalations" % i for i in open_esc]
        return ("PASS" if not problems else "FAIL"), (
            "no open rework, limit %d" % limit if not problems else "; ".join(problems))

    if fn in ("pipeline_passed",):
        return "REQUIRES-EVIDENCE", "pipeline status lives in GitLab, not in the repository"

    if fn == "no_unresolved_findings":
        # A granted security exception IS the resolution of the finding it covers.
        # Without this, CYCLE-SEC contradicted itself: RELEASE_BLOCKED offers an
        # exception_granted edge so a human can accept a standing risk under AP-04,
        # and then the acceptance conditions could never be satisfied, so the
        # exception led nowhere. Accepted risk is a decision, not an open finding.
        accepted = []
        for a in artifacts:
            for ap in a.get("approvals") or []:
                if ap.get("policy_ref") == "AP-04":
                    accepted.append("%s (%s, %s)" % (a["id"], ap.get("approver_id", "?"),
                                                     ap.get("recorded_in", "?")))
        if accepted:
            return "PASS", ("risk accepted under AP-04 on %s. The finding stands; a named human "
                            "owns it." % ", ".join(accepted))
        return "REQUIRES-EVIDENCE", ("needs the project's own findings list, or a security "
                                     "exception recorded under AP-04")

    if fn in ("tests_pass", "reproduction_fails_before_fix",
              "rollback_plan_or_acknowledged", "every_skip_recorded"):
        return "REQUIRES-EVIDENCE", ("needs the project's own test run, findings list or written "
                                     "record; not derivable from artifact headers alone")

    return "REQUIRES-EVIDENCE", "no evaluator implemented for %s" % fn


def run(workflow_id, stage_id, project, change=None):
    wfs = workflows()
    if workflow_id not in wfs:
        print("ERROR unknown workflow %s. Known: %s" % (workflow_id, ", ".join(sorted(wfs))))
        return 2
    wf = wfs[workflow_id]
    if stage_id:
        stages = [s for s in wf["stages"] if s["id"] == stage_id]
        if not stages:
            print("ERROR unknown stage %s in %s" % (stage_id, workflow_id))
            return 2
        entries = [(stage_id, e) for e in stages[0]["definition_of_done"]]
    else:
        entries = [("workflow", e) for e in wf["definition_of_done"]]

    artifacts = scope_to_change(load_artifacts(project), change)
    print("%s %s | %d artifact(s)%s under %s\n" %
          (workflow_id, stage_id or "(workflow)", len(artifacts),
           (" for %s" % change) if change else "", project))
    counts = {"PASS": 0, "FAIL": 0, "REQUIRES-EVIDENCE": 0}
    for where, entry in entries:
        fn, args = parse_predicate(entry)
        status, detail = evaluate(fn, args, artifacts, project)
        counts[status] += 1
        print("%-18s %-46s %s" % (status, entry, detail))
    print("\n%d pass, %d fail, %d require evidence outside the repository"
          % (counts["PASS"], counts["FAIL"], counts["REQUIRES-EVIDENCE"]))
    if counts["REQUIRES-EVIDENCE"]:
        print("Predicates requiring evidence are never counted as passing. Supply the evidence, "
              "then re-run.")
    # Exit codes are the machine-readable answer, and they used to disagree with the
    # line above: a stage with unmet evidence printed "never counted as passing" and
    # exited 0, which any caller reads as done. Three outcomes, three codes.
    if counts["FAIL"]:
        return 1
    if counts["REQUIRES-EVIDENCE"]:
        return 3
    return 0


def run_cycle(cycle_id, project, change=None):
    """Evaluate a department cycle's acceptance conditions.

    Every cycle declares `determined_by: scripts/check_dod.py against
    acceptance.conditions`, and until this existed that named a mechanism with no
    implementation -- acceptance was whatever the lead wrote into the rollup. The
    exit code is what a caller should act on: 0 only when every condition passes.
    """
    cyc = cycles().get(cycle_id)
    if cyc is None:
        print("ERROR unknown cycle %s. Known: %s" % (cycle_id, ", ".join(sorted(cycles()))))
        return 2
    conditions = (cyc.get("acceptance") or {}).get("conditions", [])
    if not conditions:
        print("ERROR %s declares no acceptance conditions" % cycle_id)
        return 2

    artifacts = scope_to_change(load_artifacts(project), change)
    print("%s acceptance | %d artifact(s)%s under %s\n"
          % (cycle_id, len(artifacts), (" for %s" % change) if change else "", project))
    counts = {"PASS": 0, "FAIL": 0, "REQUIRES-EVIDENCE": 0}
    for entry in conditions:
        fn, args = parse_predicate(entry)
        status, detail = evaluate(fn, args, artifacts, project)
        counts[status] += 1
        print("%-18s %-46s %s" % (status, entry, detail))

    print("\n%d pass, %d fail, %d require evidence outside the repository"
          % (counts["PASS"], counts["FAIL"], counts["REQUIRES-EVIDENCE"]))
    if counts["FAIL"]:
        print("NOT ACCEPTED. The head may request acceptance; this result determines it.")
        return 1
    if counts["REQUIRES-EVIDENCE"]:
        print("NOT ACCEPTED. Evidence outside the repository is missing, and missing evidence is "
              "never read as satisfied. Supply it, then re-run.")
        return 1
    print("ACCEPTED. Every acceptance condition is satisfied.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", action="store_true")
    ap.add_argument("--workflow")
    ap.add_argument("--stage")
    ap.add_argument("--cycle", help="evaluate a department cycle's acceptance conditions")
    ap.add_argument("--change", help="the unit of work to evaluate. Defaults to the project's "
                                     "active work item; without either, predicates match every "
                                     "artifact in the project.")
    ap.add_argument("--project", default=".")
    args = ap.parse_args()
    if not args.change:
        # A work item is a change. When one is active, scope to it rather than
        # silently evaluating every artifact in the project -- which is what made
        # a finished change vacuously satisfy a new one.
        try:
            import workitem
            args.change = workitem.current(os.path.abspath(args.project))
        except Exception:
            pass
    if args.cycle:
        return run_cycle(args.cycle, os.path.abspath(args.project), args.change)
    if args.grammar or not args.workflow:
        return check_grammar()
    return run(args.workflow, args.stage, os.path.abspath(args.project), args.change)


if __name__ == "__main__":
    sys.exit(main())
