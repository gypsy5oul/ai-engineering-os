#!/usr/bin/env python3
"""Check that relative markdown links and code references in this repository
resolve. Documentation that points at files which do not exist is worse than no
documentation, because it is trusted."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#")

errors = []


def check(path):
    rel = os.path.relpath(path, ROOT)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    for target in LINK.findall(text):
        if target.startswith(SKIP_PREFIX):
            continue
        target = target.split("#")[0].strip()
        if not target:
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if not os.path.exists(resolved):
            errors.append("%s: broken link -> %s" % (rel, target))


def main():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "reports")]
        for name in filenames:
            if name.endswith(".md"):
                check(os.path.join(dirpath, name))
    for e in errors:
        print("ERROR %s" % e)
    print("\n%d broken link(s)" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
