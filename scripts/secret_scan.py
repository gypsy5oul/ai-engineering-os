#!/usr/bin/env python3
"""Scan the repository for secret material using policies/secret-patterns.json.

A safety net, not a replacement for a dedicated scanner in CI. It is here so that
a repository adopting the AI Engineering OS has a secret check on day one even if
its pipeline has none.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks", "lib"))
from hooklib import path_matches  # noqa: E402

MAX_BYTES = 2_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=".")
    ap.add_argument("--include-self-exclusions", action="store_true",
                    help="also scan files this repository excludes from its own scan")
    args = ap.parse_args()

    pol = json.load(open(os.path.join(ROOT, "policies", "secret-patterns.json"), encoding="utf-8"))
    patterns = [(p, re.compile(p["pattern"])) for p in pol["patterns"]]
    allow = {p["id"]: [re.compile(a) for a in p.get("allow_if_matches", [])] for p in pol["patterns"]}
    excludes = list(pol["scan_excludes"])
    if not args.include_self_exclusions:
        excludes += pol.get("self_exclusions", [])

    findings = []
    for dirpath, dirnames, filenames in os.walk(args.target):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__", "reports")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, args.target)
            if path_matches(rel, excludes):
                continue
            if path_matches(rel, pol["path_denylist"]):
                findings.append((rel, "PATH", "critical", "credential-bearing file present in the tree"))
                continue
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            for meta, rx in patterns:
                for m in rx.finditer(text):
                    value = m.group(len(m.groups())) if m.groups() else m.group(0)
                    if any(a.search(value or "") for a in allow[meta["id"]]):
                        continue
                    line = text[:m.start()].count("\n") + 1
                    findings.append((("%s:%d" % (rel, line)), meta["id"], meta["severity"], meta["name"]))
                    break

    for rel, rid, sev, name in findings:
        print("%-8s %-6s %s  %s" % (sev.upper(), rid, rel, name))
    critical = [f for f in findings if f[2] == "critical"]
    print("\n%d finding(s), %d critical" % (len(findings), len(critical)))
    if critical:
        print("A committed secret must be rotated, not merely deleted.")
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
