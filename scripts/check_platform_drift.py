#!/usr/bin/env python3
"""Compare this plugin's beliefs about Claude Code against the installed binary.

policies/platform-capabilities.json records what this plugin thinks the CLI does
and how each belief was established. That file is only worth having if something
notices when it stops being true, and the published documentation cannot do that
job: on 2026-08-24 the docs and the shipped binary disagreed on six points, and
on the most important one -- the permission vocabulary -- following the docs
would have reintroduced a bug that silently allowed every escalated command for
ten versions.

So this reads the binary. It is a grep over minified JavaScript and it says so:
a miss is reported as "could not check", never as agreement.

    check_platform_drift.py
    check_platform_drift.py --binary /path/to/claude
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each belief: what to find, and what it must contain. These are the ones whose
# failure is silent -- a guard that emits an unaccepted value is not an error
# anywhere, it is a command that proceeds.
BELIEFS = [
    {
        "id": "wire-decisions",
        "what": "the permission vocabulary the CLI accepts",
        # Anchored on the permissionDecision message: the binary carries other
        # "Valid types are:" strings, and the first version of this matched a
        # list of network protocols and reported the vocabulary as missing.
        "find": rb"Unknown hook permissionDecision type[^`]{0,60}Valid types are: ([a-z, ]+)",
        "must_contain": ["allow", "deny", "ask"],
        "must_not_contain": ["escalate"],
        "load_bearing": True,
        "why": "hooks/lib/hooklib.py maps the organization's `escalate` to the wire value `ask`. "
               "If a future version accepts `escalate` this mapping becomes unnecessary; if it "
               "stops accepting `ask` the mapping becomes wrong, and every escalate-tier rule "
               "silently allows what it describes.",
    },
    {
        "id": "subagent-start-context",
        "what": "SubagentStart can return additionalContext",
        "find": rb'hookEventName:\w+\("SubagentStart"\),(additionalContext)',
        "must_contain": ["additionalContext"],
        "load_bearing": True,
        "why": "The entire briefing path depends on it. The published documentation says this "
               "event has no hookSpecificOutput at all.",
    },
    {
        "id": "task-completed-payload",
        "what": "the fields TaskCompleted sends",
        "find": rb'hook_event_name:\w+\("TaskCompleted"\),([a-zA-Z_:,()."\s]{0,120})',
        "must_contain": ["task_id", "task_subject"],
        "load_bearing": True,
        "why": "hooks/scripts/gate_task_completion.py binds the native task to a graph task from "
               "these. The documentation names task_title and task_result, which do not exist.",
    },
    {
        "id": "task-created-payload",
        "what": "the fields TaskCreated sends",
        "find": rb'hook_event_name:\w+\("TaskCreated"\),([a-zA-Z_:,()."\s]{0,140})',
        "must_contain": ["task_id", "task_subject"],
        "must_not_contain": ["blocked_by", "depends_on"],
        "load_bearing": True,
        "why": "hooks/scripts/bind_task.py binds the native task to a graph task from these at "
               "creation. If dependency edges ever appear here, the graph could stop inferring "
               "what the platform is willing to state.",
    },
    {
        "id": "task-created-blocks",
        "what": "TaskCreated is in the set of events exit 2 can block",
        "find": rb'aen=\[([^\]]{0,120})\]',
        "must_contain": ["TaskCreated", "TaskCompleted"],
        "load_bearing": True,
        "why": "bind_task.py refuses a task whose dependencies are unmet or whose id was invented. "
               "If TaskCreated leaves the blocking set those refusals become stderr nobody acts "
               "on, and the earliest gate in the lifecycle silently stops being a gate.",
    },
    {
        "id": "teammate-idle-payload",
        "what": "the fields TeammateIdle sends",
        "find": rb'hook_event_name:\w+\("TeammateIdle"\),([a-zA-Z_:,()."\s]{0,120})',
        "must_contain": ["teammate_name"],
        "must_not_contain": ["teammate_id"],
        "why": "hooks/scripts/teammate_idle.py matches a teammate to a lease by name, because no "
               "id is sent. If a teammate_id appears, that correlation should stop being a guess.",
    },
]


def find_binary(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    try:
        which = subprocess.run(["which", "claude"], capture_output=True, text=True, timeout=30)
        if which.returncode == 0 and which.stdout.strip():
            return os.path.realpath(which.stdout.strip())
    except Exception:
        pass
    base = os.path.join(os.path.expanduser("~"), ".local", "share", "claude", "versions")
    if os.path.isdir(base):
        found = sorted(os.listdir(base))
        if found:
            return os.path.join(base, found[-1])
    return None


def installed_version(path):
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            m = re.search(r"(\d+\.\d+\.\d+)", out.stdout)
            if m:
                return m.group(1)
    except Exception:
        pass
    m = re.search(r"(\d+\.\d+\.\d+)", os.path.basename(path or ""))
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary")
    ap.add_argument("--strict", action="store_true",
                    help="treat 'could not check' as a failure")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "policies", "platform-capabilities.json"), encoding="utf-8") as fh:
        model = json.load(fh)
    expected = model.get("tested_against")

    path = find_binary(args.binary)
    if not path:
        print("Claude Code is not installed here, so nothing could be checked.")
        print("The capability model claims %s. Re-run this where the CLI is installed." % expected)
        return 1 if args.strict else 0

    version = installed_version(path)
    print("capability model: %s | installed: %s" % (expected, version or "unknown"))
    if version and expected and version != expected:
        print("\nWARN  the model was verified against %s and %s is installed. Every capability "
              "marked load_bearing should be re-checked before it is trusted."
              % (expected, version))

    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except Exception as exc:
        print("could not read %s: %r" % (path, exc))
        return 1 if args.strict else 0

    failures = unchecked = 0
    print()
    for belief in BELIEFS:
        m = re.search(belief["find"], blob)
        if not m:
            # For a load-bearing belief, "I could not find the thing the briefing
            # path depends on" is not a shrug. The whole point of the file is that
            # these fail silently, and a checker that goes quiet when it cannot
            # look is the same silence one level up.
            if belief.get("load_bearing"):
                failures += 1
                print("FAIL  %-26s could not be found in the binary, and this one is "
                      "load-bearing." % belief["id"])
                print("      %s" % belief["why"])
                print("      Either the pattern moved or the capability went away, and this "
                      "cannot tell which. Check by hand before trusting it.")
            else:
                unchecked += 1
                print("?     %-26s could not be found in the binary. Not agreement: the pattern "
                      "is a grep over minified code and may simply have moved." % belief["id"])
            continue
        got = m.group(1).decode("utf-8", "replace")
        bad = []
        for want in belief.get("must_contain", []):
            if want not in got:
                bad.append("expected %r and it is absent" % want)
        for unwanted in belief.get("must_not_contain", []):
            if unwanted in got:
                bad.append("found %r, which this plugin assumes does not exist" % unwanted)
        if bad:
            failures += 1
            print("FAIL  %-26s %s" % (belief["id"], belief["what"]))
            for line in bad:
                print("      %s" % line)
            print("      saw: %s" % got.strip()[:100])
            print("      why it matters: %s" % belief["why"])
        else:
            print("ok    %-26s %s" % (belief["id"], belief["what"]))

    print("\n%d belief(s) checked, %d failing, %d unverifiable"
          % (len(BELIEFS), failures, unchecked))
    if failures:
        print("A failing belief is not a cosmetic drift. These are the capabilities whose "
              "failure is silent: nothing errors, the guard simply stops working.")
        return 1
    if unchecked and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
