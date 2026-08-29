#!/usr/bin/env python3
"""Lint committed project-scope agent memory.

Memory is never organizational authority. It records what was observed, where,
and when; it does not create a policy, a justification nobody supplied, a
requirement, a target, an approval or a verdict.

That rule cannot be enforced when a memory is written -- the platform writes it,
not the `Write` tool, so no hook sees it. What can be done is read what landed in
the repository, which is the entire reason project scope is the only scope this
organization permits: it is committed, and a committed thing can be linted and
reviewed.

The rules come from policies/agent-memory.json so the lint and the instruction
agents follow cannot drift apart.

    lint_memory.py --project /path/to/project
    lint_memory.py --project . --json
    lint_memory.py --project . --strict     # warnings become errors

What it decides is shape. Whether an observation is *true* is read by a person
during the role's review, and a perfectly well-formed entry can be entirely wrong.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEMORY_DIR = os.path.join(".claude", "agent-memory")
INDEX = "MEMORY.md"

# Errors: the memory becoming something it is not permitted to be.
# Warnings: the memory being under-sourced, which is repairable -- a lint that
# blocks a build over provenance teaches people to delete memories rather than
# fix them.
ERRORS = {"ML-03", "ML-04", "ML-05", "ML-06", "ML-07"}

ARTIFACT_ID = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-[A-Z]+-[0-9]{3,}\b")
DATE = re.compile(r"\b(20[0-9]{2}-[01][0-9]-[0-3][0-9])\b")
VERSION = re.compile(r"\b(v[0-9]+\.[0-9]+(\.[0-9]+)?|version\s+[0-9]+|@[0-9a-f]{7,40})\b", re.I)
PATHISH = re.compile(r"[\w./-]+\.(py|js|ts|go|java|rb|rs|md|ya?ml|json|toml|sql)\b")

# ML-03. The observed failure: told a bare fact, the agent supplied a reason.
SPECULATION = re.compile(
    r"\b(likely|probably|presumably|appears to be|seems to be|suggests that|"
    r"driven by|due to (?:compliance|regulatory|internal)|most likely|"
    r"this (?:is|was) (?:probably|likely))\b", re.I)

# ML-04. The other half: the fact promoted to a rule the role would enforce.
#
# Two patterns, because an instruction shows itself in two ways and a single
# regex for both was wrong in a way worth recording.
#
# Not anchored to the start of a *line*. The entry that motivated this rule
# buried both of its imperatives mid-sentence -- "...strategies, ensure that no
# data is deleted" and "...have elapsed. Flag any architectural decisions" -- and
# a line-anchored pattern found neither. An instruction does not become advice by
# being in the middle of a paragraph.
#
# But a bare `never \w+` anywhere in the body is worse. "The endpoint
# never returns 204" is an observation, and flagging it teaches people to delete
# memories rather than rewrite them. The distinguishing feature of an imperative
# is mood, and in English mood shows up as position -- a command opens its
# sentence. So `always`/`never`/`ensure`/`flag` fire sentence-initially (or as a
# bullet), while the unambiguous phrases fire anywhere.
#
# A colon opens a sentence too. "GOLD-ARCH-001: Always check the window" is the
# ordinary shape of a sourced memory entry, and it is exactly as much an
# instruction as the same words after a full stop.
IMPERATIVE_OPENER = re.compile(
    r"(?:^|[.!?:;]\s+|\n)\s*(?:[-*+]\s*)?"
    r"((?:always|never|ensure|verify|check|flag|apply|remember|avoid|prefer)\s+\w+"
    r"|do not\s+\w+|don't\s+\w+)", re.I)

# Anywhere in the body: no reading of these is an observation.
IMPERATIVE_PHRASE = re.compile(
    r"\b(ensure that|flag any|make sure|remember to|apply this|"
    r"you (?:must|should)|(?:must|should) (?:be )?(?:always|never)|"
    r"when (?:designing|reviewing|implementing)\b[^.]{0,60}?,\s*"
    r"(?:ensure|check|verify|flag))", re.I)


def imperative(body):
    """The instruction in `body`, or None.

    Phrase first: it is the more specific finding, and quoting `ensure that` in
    the error message is more use to whoever has to rewrite the entry than
    quoting the sentence opener that happens to precede it.
    """
    m = IMPERATIVE_PHRASE.search(body)
    if m:
        return m.group(1)
    m = IMPERATIVE_OPENER.search(body)
    return m.group(1) if m else None


# ML-05 / ML-06. Things that live in artifacts and change without telling memory.
TARGET = re.compile(
    r"\b(p9[59]|SLO|SLA|RPO|RTO|uptime|availability target|"
    r"(?:must|should)\s+(?:not\s+)?exceed|threshold of|target of|"
    r"\b[0-9]+(?:\.[0-9]+)?\s?%\s*(?:availability|success|coverage|uptime))\b", re.I)
VERDICT = re.compile(
    r"\b(approved by|sign-?ed off|AP-[0-9]{2}|verdict|pass-with-conditions|"
    r"changes-requested|was approved|we approved|review passed)\b", re.I)

# ML-07. Not who writes bad code, not who is slow to review.
PERSON = re.compile(r"(@[A-Za-z][\w.-]{2,}|\b[\w.+-]+@[\w-]+\.[\w.]+\b|"
                    r"\b(?:gitlab|github):[A-Za-z][\w-]+)")


def policy():
    with open(os.path.join(ROOT, "policies", "agent-memory.json"), encoding="utf-8") as fh:
        return json.load(fh)


def rules():
    return {r["id"]: r for r in (policy().get("lint") or {}).get("rules", [])}


def project_artifact_ids(project):
    """Every artifact id the project actually has, for ML-08.

    Read from artifact headers rather than from a listing, because an id that
    appears only in prose is not an artifact -- and a memory pointing at one is
    exactly the dangling pointer this rule is about.
    """
    found = set()
    docs = os.path.join(project, "docs")
    for base, _dirs, files in os.walk(docs) if os.path.isdir(docs) else []:
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                with open(os.path.join(base, name), encoding="utf-8") as fh:
                    head = fh.read(4000)
            except OSError:
                continue
            m = re.search(r"^id:\s*([A-Z][A-Z0-9-]+)\s*$", head, re.M)
            if m:
                found.add(m.group(1).strip())
    return found


def strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:], text[:end + 4]
    return text, ""


def lint_entry(path, body, known_ids):
    """Findings for one memory entry. Each is (rule_id, message)."""
    out = []
    named = set(ARTIFACT_ID.findall(body))

    if not (named or PATHISH.search(body)):
        out.append(("ML-01", "names no artifact, file or run it was observed in, so the "
                             "observation has no owner and cannot be found to have gone stale"))
    if not (DATE.search(body) or VERSION.search(body)):
        out.append(("ML-02", "carries no date and no artifact version, so nothing can "
                             "recognise it as stale"))

    m = SPECULATION.search(body)
    if m:
        out.append(("ML-03", "supplies a justification nobody gave: %r. If you were not told "
                             "why, record what and stop" % m.group(0)))

    found = imperative(body)
    if found:
        out.append(("ML-04", "is written as a rule (%r). A role that writes rules for itself "
                             "has replaced the policy with its own recollection"
                             % found.strip()))

    m = TARGET.search(body)
    if m:
        out.append(("ML-05", "stores a requirement or target (%r). A remembered target is a "
                             "number with no owner; targets live in approved artifacts"
                             % m.group(0)))

    m = VERDICT.search(body)
    if m:
        out.append(("ML-06", "stores a verdict or approval (%r). Remembering that something "
                             "passed is how a reviewer stops reviewing" % m.group(0)))

    m = PERSON.search(body)
    if m:
        out.append(("ML-07", "names a person (%r)" % m.group(0)))

    if known_ids:
        dangling = sorted(i for i in named if i not in known_ids)
        if dangling:
            out.append(("ML-08", "points at %s, which the project does not have. A pointer that "
                                 "leads nowhere reads as provenance and is not"
                                 % ", ".join(dangling)))
    return out


def lint_agent_dir(project, agent_dir, known_ids):
    findings = []
    entries = sorted(f for f in os.listdir(agent_dir)
                     if f.endswith(".md") and f != INDEX)
    index_path = os.path.join(agent_dir, INDEX)
    indexed = set()
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            index_text = fh.read()
        indexed = set(re.findall(r"\(([^)]+\.md)\)", index_text))
    elif entries:
        findings.append({"agent": os.path.basename(agent_dir), "entry": INDEX,
                         "rule": "ML-09",
                         "message": "%d entries and no MEMORY.md. The index is what a reviewer "
                                    "reads; an entry outside it is a memory nobody reviewed"
                                    % len(entries)})

    for name in entries:
        path = os.path.join(agent_dir, name)
        with open(path, encoding="utf-8") as fh:
            body, _fm = strip_frontmatter(fh.read())
        for rule_id, message in lint_entry(path, body, known_ids):
            findings.append({"agent": os.path.basename(agent_dir), "entry": name,
                             "rule": rule_id, "message": message})
        if indexed and name not in indexed:
            findings.append({"agent": os.path.basename(agent_dir), "entry": name,
                             "rule": "ML-09",
                             "message": "is not listed in MEMORY.md"})

    for listed in sorted(indexed):
        if not os.path.exists(os.path.join(agent_dir, listed)):
            findings.append({"agent": os.path.basename(agent_dir), "entry": INDEX,
                             "rule": "ML-09",
                             "message": "lists %s, which does not exist" % listed})
    return findings


def lint(project):
    base = os.path.join(project, MEMORY_DIR)
    if not os.path.isdir(base):
        return [], 0
    known = project_artifact_ids(project)
    findings, agents = [], 0
    for name in sorted(os.listdir(base)):
        agent_dir = os.path.join(base, name)
        if not os.path.isdir(agent_dir):
            continue
        agents += 1
        findings += lint_agent_dir(project, agent_dir, known)
    return findings, agents


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="treat provenance warnings as errors too")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    findings, agents = lint(project)
    spec = rules()

    if args.json:
        print(json.dumps({"project": project, "agents": agents, "findings": findings}, indent=2))
    else:
        if not agents:
            print("no committed agent memory under %s" % os.path.join(args.project, MEMORY_DIR))
            return 0
        for f in findings:
            kind = "ERROR" if f["rule"] in ERRORS or args.strict else "WARN "
            print("%s %s/%s [%s] %s" % (kind, f["agent"], f["entry"], f["rule"], f["message"]))
        errs = len([f for f in findings if f["rule"] in ERRORS])
        warns = len(findings) - errs
        print("\n%d memory store(s), %d error(s), %d warning(s)" % (agents, errs, warns))
        if not findings:
            print("Memory records what was observed, where, and when. Nothing here claims "
                  "authority it does not have.")
        for f in findings:
            r = spec.get(f["rule"])
            if r and f["rule"] in ERRORS:
                print("\n  %s %s\n    %s" % (f["rule"], r["means"], r["why"]))
                break

    blocking = [f for f in findings if f["rule"] in ERRORS or args.strict]
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
