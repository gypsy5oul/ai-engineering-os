#!/usr/bin/env python3
"""Validate a project's .ai-engineering configuration.

  python3 scripts/validate_project_config.py [path]

Defaults to .ai-engineering/project.yaml then .ai-engineering/project.json in the
current directory. Beyond schema validation it applies the rules that make the
configuration useful rather than merely well-formed.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from jsonschema_mini import validate  # noqa: E402
from minyaml import parse_file  # noqa: E402


def find_config(explicit):
    if explicit:
        return explicit
    for candidate in (".ai-engineering/project.yaml", ".ai-engineering/project.json"):
        if os.path.exists(candidate):
            return candidate
    return None


def semantic_checks(cfg):
    errors, warnings = [], []

    # Two fields carry the traceability prefix and work item ids are built from
    # project.key. The shipped template sets both to the same value, so a
    # disagreement only appears when somebody fills the config in by hand -- and
    # then their work items are called PROJ-FEAT-001.
    key = (cfg.get("project") or {}).get("key")
    id_prefix = (cfg.get("knowledge") or {}).get("id_prefix")
    if key and id_prefix and key != id_prefix:
        errors.append("project.key is %r and knowledge.id_prefix is %r. They are the same fact, "
                      "and ids are built from project.key, so the other is a decoy."
                      % (key, id_prefix))

    envs = cfg.get("environments") or []
    if not any(e.get("production") for e in envs):
        warnings.append("no environment is marked production: production guards will not be "
                        "reinforced by environment naming")
    for env in envs:
        if env.get("production") and env.get("deployment_approval") in (None, "none"):
            errors.append("environment '%s' is production but has deployment_approval 'none'; "
                          "production deployment is AP-01 and requires a human" % env.get("name"))
        if env.get("data") == "production" and not env.get("production"):
            warnings.append("environment '%s' holds production data but is not marked production; "
                            "it inherits production-grade access rules regardless" % env.get("name"))

    sec = cfg.get("security") or {}
    if sec.get("data_classification") in ("confidential", "restricted") and not sec.get("secret_management"):
        errors.append("data_classification is %s but secret_management is not stated"
                      % sec["data_classification"])
    if sec.get("data_classification") in ("confidential", "restricted") and not sec.get("threat_model"):
        warnings.append("data_classification is %s and no threat model is referenced"
                        % sec["data_classification"])

    tech = cfg.get("technology") or {}
    for layer, value in tech.items():
        if isinstance(value, dict) and value.get("status") == "proposed" and not value.get("adr"):
            warnings.append("technology.%s is 'proposed' with no ADR reference" % layer)
    if not tech:
        errors.append("technology is empty: agents would have to guess the stack, which they must not do")

    testing = cfg.get("testing") or {}
    tier = (cfg.get("project") or {}).get("tier")
    levels = testing.get("required_levels") or []
    if tier in (1, 2) and "integration" not in levels:
        warnings.append("tier %s project does not require integration tests" % tier)
    if testing.get("test_data") == "production-copy" and sec.get("data_classification") in ("confidential", "restricted"):
        errors.append("testing.test_data is 'production-copy' with %s data classification; "
                      "that moves regulated data into test environments"
                      % sec.get("data_classification"))

    for od in cfg.get("open_decisions") or []:
        if od.get("blocking") and not od.get("owner"):
            errors.append("blocking open decision %s has no owner" % od.get("id"))

    repo = cfg.get("repository") or {}
    branching = repo.get("branching") or {}
    if not branching.get("protected_branches"):
        warnings.append("repository.branching.protected_branches is not set; the organization "
                        "defaults from policies/branch-policy.json apply")
    mr = repo.get("merge_request") or {}
    if mr.get("author_may_approve"):
        errors.append("repository.merge_request.author_may_approve is true; an author approving "
                      "their own change removes the only independent check on the merge")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    path = find_config(args.path)
    if not path:
        print("ERROR no .ai-engineering/project.yaml or project.json found.")
        print("      Run /ai-engineering-os:project-onboarding to create one.")
        return 1
    if not os.path.exists(path):
        print("ERROR %s does not exist" % path)
        return 1

    try:
        cfg = parse_file(path) if path.endswith((".yaml", ".yml")) else json.load(open(path, encoding="utf-8"))
    except Exception as exc:
        print("ERROR %s: cannot parse (%s)" % (path, exc))
        return 1

    schema = json.load(open(os.path.join(ROOT, "schemas", "project-config.schema.json"), encoding="utf-8"))
    errors = ["schema: " + e for e in validate(cfg, schema)]
    sem_errors, warnings = semantic_checks(cfg)
    errors += sem_errors

    for w in warnings:
        print("WARN  %s" % w)
    for e in errors:
        print("ERROR %s" % e)
    print("\n%s: %d error(s), %d warning(s)" % (path, len(errors), len(warnings)))
    if errors or (args.strict and warnings):
        return 1
    print("Project configuration is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
