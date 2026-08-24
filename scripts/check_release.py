#!/usr/bin/env python3
"""Release readiness gate. Runs on a tag.

Confirms the tag, the manifest and the marketplace entry agree, that the
changelog documents the version, and that no placeholder survived into a release.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def load(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        print("\nusage: check_release.py\n\nTakes no arguments. Exits non-zero when "
              "something would block a release.")
        return 0

    manifest = load(".claude-plugin/plugin.json")
    version = manifest.get("version", "")
    tag = os.environ.get("CI_COMMIT_TAG", "")

    # `claude plugin tag` derives the tag from the manifest as
    # {plugin-name}--v{version}. A bare vX.Y.Z tag is accepted for a repository
    # tagged by hand, but the prefixed form is what the CLI produces.
    expected = "%s--v%s" % (manifest["name"], version)
    if tag and tag not in (expected, "v" + version, version):
        errors.append("tag %s matches neither %s (what `claude plugin tag` creates) nor v%s"
                      % (tag, expected, version))

    marketplace = load(".claude-plugin/marketplace.json")
    for entry in marketplace.get("plugins", []):
        if entry.get("name") != manifest["name"]:
            continue
        if entry.get("version") != version:
            errors.append("marketplace entry version %s does not match plugin.json %s"
                          % (entry.get("version"), version))
        src = entry.get("source") or {}
        url = src.get("url", "")
        if "example.com" in url:
            errors.append("marketplace source still points at the placeholder URL %s" % url)
        ref = src.get("ref")
        expected_ref = "%s--v%s" % (manifest["name"], version)
        if tag and ref != tag:
            errors.append("marketplace source ref %s does not match the tag %s" % (ref, tag))
        elif not tag and ref and ref not in (expected_ref, "v" + version):
            errors.append("marketplace source ref %r names neither %s nor v%s; new installs would "
                          "resolve to a tag that does not exist" % (ref, expected_ref, version))

    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        changelog = fh.read()
    if version not in changelog:
        errors.append("CHANGELOG.md has no entry for %s" % version)

    for rel in ("GOVERNANCE.md",):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            if "*unassigned*" in fh.read():
                print("WARN  %s still has unassigned governance roles" % rel)

    placeholder = re.compile(r"\bTODO\b|\bFIXME\b|<PROJECT NAME>")
    for folder in ("agents", "skills", "policies"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if placeholder.search(fh.read()):
                        errors.append("%s contains placeholder text" % os.path.relpath(path, ROOT))

    for e in errors:
        print("ERROR %s" % e)
    print("\n%d release blocker(s)" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
