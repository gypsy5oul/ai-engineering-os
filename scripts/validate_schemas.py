#!/usr/bin/env python3
"""Validate every policy document against its schema, and every schema against
the capabilities of the bundled validator."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from jsonschema_mini import validate, unsupported_keywords  # noqa: E402
from minyaml import parse_file  # noqa: E402

PAIRS = [
    ("policies/agent-registry.json", "schemas/agent-registry.schema.json"),
]

errors, warnings = [], []


def check_json_parses():
    for folder in ("policies", "schemas", "evaluations", ".claude-plugin", "hooks"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                if not name.endswith(".json"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    json.load(open(path, encoding="utf-8"))
                except Exception as exc:
                    errors.append("%s: invalid JSON (%s)" % (os.path.relpath(path, ROOT), exc))


def check_yaml_parses():
    for dirpath, _, files in os.walk(os.path.join(ROOT, "sdlc")):
        for name in files:
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(dirpath, name)
            try:
                parse_file(path)
            except Exception as exc:
                errors.append("%s: invalid YAML (%s)" % (os.path.relpath(path, ROOT), exc))
    for name in ("templates/project/project.yaml",):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            try:
                parse_file(path)
            except Exception as exc:
                errors.append("%s: invalid YAML (%s)" % (name, exc))


def check_pairs():
    for doc_rel, schema_rel in PAIRS:
        doc = json.load(open(os.path.join(ROOT, doc_rel), encoding="utf-8"))
        schema = json.load(open(os.path.join(ROOT, schema_rel), encoding="utf-8"))
        for e in validate(doc, schema):
            errors.append("%s: %s" % (doc_rel, e))


def check_schema_support():
    base = os.path.join(ROOT, "schemas")
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        schema = json.load(open(os.path.join(base, name), encoding="utf-8"))
        unsupported = unsupported_keywords(schema)
        if unsupported:
            warnings.append("schemas/%s uses keywords the bundled validator ignores: %s"
                            % (name, sorted(unsupported)))


def check_template_against_schema():
    tpl = os.path.join(ROOT, "templates", "project", "project.yaml")
    if not os.path.exists(tpl):
        return
    schema = json.load(open(os.path.join(ROOT, "schemas", "project-config.schema.json"), encoding="utf-8"))
    try:
        data = parse_file(tpl)
    except Exception as exc:
        errors.append("templates/project/project.yaml: %s" % exc)
        return
    for e in validate(data, schema):
        errors.append("templates/project/project.yaml: %s (the shipped template must itself be valid)" % e)


def main():
    check_json_parses()
    check_yaml_parses()
    check_pairs()
    check_schema_support()
    check_template_against_schema()
    for w in warnings:
        print("WARN  %s" % w)
    for e in errors:
        print("ERROR %s" % e)
    print("\n%d error(s), %d warning(s)" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
