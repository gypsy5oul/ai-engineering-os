#!/usr/bin/env python3
"""Resolve the model and effort for a piece of work.

role + task risk + complexity + reversibility -> model, effort

The role default alone never decides. This is the executable form of
policies/model-policy.json, so that the routing table is applied rather than
remembered.

  python3 scripts/resolve_model.py --role backend-developer --risk HIGH --complexity novel
  python3 scripts/resolve_model.py --workflow WF-FEATURE --stage ARCH
  python3 scripts/resolve_model.py --all
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402

RANK = {"haiku": 0, "fable": 1, "sonnet": 1, "inherit": 1, "opus": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def project_overrides(project):
    if not project:
        return {}
    for cand in ("project.yaml", "project.json"):
        p = os.path.join(project, ".ai-engineering", cand)
        if os.path.exists(p):
            if p.endswith((".yaml", ".yml")):
                cfg = parse_file(p)
            else:
                with open(p, encoding="utf-8") as fh:
                    cfg = json.load(fh)
            return ((cfg.get("ai") or {}).get("model_overrides") or {})
    return {}


def resolve(role, risk, complexity, reversibility="reversible", project=None):
    policy = load("policies/model-policy.json")
    registry = {a["name"]: a for a in load("policies/agent-registry.json")["agents"]}
    floors = {c: v["implies"]["model_floor"]
              for c, v in load("policies/risk-classification.json")["classes"].items()}

    entry = registry.get(role)
    trace = []

    default = entry["default_model"] if entry else "sonnet"
    chosen, effort = default, "medium"
    trace.append("role default: %s (%s)" % (default, role if entry else "unknown role"))

    for rule in policy["routing"]:
        when = rule["when"]
        if risk and "risk" in when and risk not in when["risk"]:
            continue
        if complexity and "complexity" in when and complexity not in when["complexity"]:
            continue
        if "reversibility" in when and reversibility not in when["reversibility"]:
            continue
        chosen, effort = rule["model"], rule.get("effort", effort)
        trace.append("routing rule matched (%s): %s / %s"
                     % (", ".join("%s=%s" % (k, "|".join(v)) for k, v in when.items()), chosen, effort))
        break

    if entry and RANK[default] > RANK[chosen]:
        trace.append("role default %s is above the routed %s; the role floor wins" % (default, chosen))
        chosen = default

    floor = floors.get(risk or (entry["risk"] if entry else "MEDIUM"))
    if floor and RANK[chosen] < RANK[floor]:
        trace.append("risk floor for %s is %s; raised" % (risk, floor))
        chosen = floor

    override = project_overrides(project).get(role)
    if override:
        want = override.get("model", chosen)
        if RANK[want] < RANK[chosen]:
            trace.append("project override to %s REFUSED: below the %s floor" % (want, chosen))
        else:
            trace.append("project override: %s" % want)
            chosen = want
        if override.get("effort"):
            effort = override["effort"]

    for line in policy.get("mandatory_escalation", []):
        pass  # documented, applied by the caller with task context

    if entry and entry["risk"] == "CRITICAL":
        chosen, effort = "opus", "high"
        trace.append("CRITICAL role: never de-escalated")

    return {"role": role, "risk": risk, "complexity": complexity, "model": chosen,
            "effort": effort, "trace": trace}


def stage_lookup(workflow_id, stage_id):
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in os.listdir(base):
        if not name.endswith((".yaml", ".yml")):
            continue
        wf = parse_file(os.path.join(base, name))
        if wf["id"] != workflow_id:
            continue
        for s in wf["stages"]:
            if s["id"] == stage_id:
                return s
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role")
    ap.add_argument("--risk", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    ap.add_argument("--complexity", choices=["routine", "complex", "novel"], default="routine")
    ap.add_argument("--reversibility", choices=["reversible", "hard-to-reverse", "irreversible"],
                    default="reversible")
    ap.add_argument("--workflow")
    ap.add_argument("--stage")
    ap.add_argument("--project")
    ap.add_argument("--all", action="store_true", help="resolve every stage of every workflow")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.all:
        base = os.path.join(ROOT, "sdlc", "workflows")
        rows = []
        for name in sorted(os.listdir(base)):
            if not name.endswith((".yaml", ".yml")):
                continue
            wf = parse_file(os.path.join(base, name))
            for s in wf["stages"]:
                r = resolve(s["owner"], s.get("risk"), s.get("complexity", "routine"),
                            project=args.project)
                rows.append((wf["id"], s["id"], s["owner"], s.get("risk"),
                             s.get("complexity", "routine"), s.get("execution"),
                             r["model"], r["effort"]))
        if args.json:
            print(json.dumps([dict(zip(
                ["workflow", "stage", "owner", "risk", "complexity", "execution", "model", "effort"], r))
                for r in rows], indent=2))
        else:
            print("%-16s %-10s %-22s %-8s %-9s %-9s %-7s %s"
                  % ("WORKFLOW", "STAGE", "OWNER", "RISK", "COMPLEX", "EXEC", "MODEL", "EFFORT"))
            for r in rows:
                print("%-16s %-10s %-22s %-8s %-9s %-9s %-7s %s" % r)
        return 0

    if args.workflow and args.stage:
        s = stage_lookup(args.workflow, args.stage)
        if not s:
            print("ERROR no such stage")
            return 2
        result = resolve(s["owner"], s.get("risk"), s.get("complexity", "routine"),
                         project=args.project)
        result["execution"] = s.get("execution")
    elif args.role:
        result = resolve(args.role, args.risk, args.complexity, args.reversibility, args.project)
    else:
        print(__doc__)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("model: %s   effort: %s" % (result["model"], result["effort"]))
        for line in result["trace"]:
            print("  - %s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
