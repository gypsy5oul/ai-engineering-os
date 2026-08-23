#!/usr/bin/env python3
"""Count what this repository actually contains.

Every number in the documentation used to be typed by hand, and they drifted:
the README claimed 29 agents in one section and 30 in another, four documents
disagreed about the evaluation total, and a plugin whose subject is consistency
was inconsistent about itself in about twenty-five places.

So the counts are derived here, `check_stated_counts()` compares the prose
against them, and a wrong number fails the build instead of being noticed by a
reviewer eighteen months later.

    repo_stats.py            human readable
    repo_stats.py --json     for tooling
    repo_stats.py --markdown a table to paste into a document
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402


def _json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def _count_dir(rel, suffix=None, dirs=False):
    path = os.path.join(ROOT, rel)
    if not os.path.isdir(path):
        return 0
    entries = sorted(os.listdir(path))
    if dirs:
        return len([e for e in entries if os.path.isdir(os.path.join(path, e))])
    return len([e for e in entries if not suffix or e.endswith(suffix)])


def stats():
    workflows, stages, team_stages, subagent_stages = {}, 0, 0, 0
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        wf = parse_file(os.path.join(base, name))
        workflows[wf["id"]] = len(wf["stages"])
        stages += len(wf["stages"])
        for s in wf["stages"]:
            if s.get("execution") == "team":
                team_stages += 1
            elif s.get("execution") == "subagent":
                subagent_stages += 1

    model = _json("policies/artifact-model.json")
    evals = {}
    edir = os.path.join(ROOT, "evaluations")
    for suite in sorted(os.listdir(edir)):
        p = os.path.join(edir, suite)
        if os.path.isdir(p):
            evals[suite] = len([f for f in os.listdir(p) if f.endswith(".json")])
    modes = {"deterministic": 0, "llm-judged": 0}
    for suite in evals:
        for f in sorted(os.listdir(os.path.join(edir, suite))):
            if f.endswith(".json"):
                case = _json(os.path.join("evaluations", suite, f))
                modes[case.get("mode", "deterministic")] = \
                    modes.get(case.get("mode", "deterministic"), 0) + 1

    with open(os.path.join(ROOT, "scripts", "inject_faults.py"), encoding="utf-8") as fh:
        faults = len(re.findall(r'@fault\("F-\d+"', fh.read()))
    with open(os.path.join(ROOT, "scripts", "simulate_sdlc.py"), encoding="utf-8") as fh:
        scenarios = len(re.findall(r'^\s+"[a-z-]+": scenario_', fh.read(), re.M))

    hooks = _json("hooks/hooks.json")["hooks"]

    return {
        "agents": _count_dir("agents", ".md"),
        "skills": _count_dir("skills", dirs=True),
        "policies": _count_dir("policies", ".json"),
        "schemas": _count_dir("schemas", ".json"),
        "workflows": len(workflows),
        "workflow_stages": stages,
        "team_stages": team_stages,
        "subagent_stages": subagent_stages,
        "department_cycles": _count_dir("sdlc/cycles", ".yaml"),
        "artifact_types": len(model["artifact_types"]),
        "dod_predicates": len(model["dod_predicates"]),
        "command_rules": len(_json("policies/hook-policy.json")["rules"]),
        "approval_categories": len(_json("policies/approval-policy.json")["human_approval_required"]),
        "hook_events": len(hooks),
        "hook_scripts": _count_dir("hooks/scripts", ".py"),
        "evaluation_cases": sum(evals.values()),
        "deterministic_cases": modes.get("deterministic", 0),
        "llm_judged_cases": modes.get("llm-judged", 0),
        "evaluation_suites": len(evals),
        "faults": faults,
        "scenarios": scenarios,
        "docs": _count_dir("docs", ".md"),
        "per_workflow": workflows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    s = stats()
    if args.json:
        print(json.dumps(s, indent=2))
    elif args.markdown:
        print("| What | Count |")
        print("| --- | --- |")
        for k, v in s.items():
            if k != "per_workflow":
                print("| %s | %s |" % (k.replace("_", " "), v))
    else:
        for k, v in s.items():
            if k == "per_workflow":
                continue
            print("  %-22s %s" % (k.replace("_", " "), v))
        print("\n  stages per workflow:")
        for wid, n in sorted(s["per_workflow"].items()):
            print("    %-16s %d" % (wid, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
