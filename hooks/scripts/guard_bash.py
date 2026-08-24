#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Evaluates the command against policies/hook-policy.json plus the branch policy,
and returns deny / escalate / silence. See docs/hooks.md for the full model.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import hooklib as H  # noqa: E402
from failsafe import screen_catastrophic  # noqa: E402

EVENT = "PreToolUse"
# Captured as the payload is parsed so the failure handler can still classify the
# action's risk when the evaluation itself has broken.
_SUBJECT = [""]
SEVERITY_ORDER = {"deny": 0, "escalate": 1, "warn": 2}


# The token every production rule matches on. It appears in seven rule patterns
# and, before this, `production_markers` in the policy was read by nothing: a
# project adding its own marker to that list changed precisely nothing, while the
# list sat there looking like the place to add one.
MARKER_TOKEN = "prod|prd|production|live"


def marker_alternation(pol, overrides):
    """The production markers, from the policy and the project, as one alternation.

    Longest first, so `production` is matched before `prod` would swallow its
    prefix.
    """
    markers = list(pol.get("production_markers") or [])
    markers += list((overrides or {}).get("production_markers") or [])
    seen = [m for m in dict.fromkeys(markers) if m]
    if not seen:
        return MARKER_TOKEN
    # Escaped, because a marker is the literal name of an environment. Unescaped,
    # `prod-eu(1` is an unbalanced group that fails to compile, and every rule
    # carrying the token was dropped -- five of the seven production rules gone
    # because a project made a typo while trying to tighten its own policy.
    return "|".join(re.escape(m) for m in sorted(seen, key=len, reverse=True))


def compile_rules(pol, overrides, dropped=None):
    """Compile the rule set. `dropped` collects anything that would not compile.

    The policy says projects may tighten freely and that loosening is never
    silent. A rule discarded here is loosening, so it has to be reported the way
    a rejected waiver is -- in the decision, in the audit record and at session
    start -- rather than vanishing.
    """
    rules = []
    dropped = [] if dropped is None else dropped
    alternation = marker_alternation(pol, overrides)
    for r in pol.get("rules", []):
        flags = re.I if "i" in (r.get("flags") or "") else 0
        pattern = r["pattern"].replace(MARKER_TOKEN, alternation)
        try:
            rules.append((re.compile(pattern, flags), r))
        except re.error as exc:
            dropped.append("%s (%s)" % (r.get("id", "?"), exc))
    for i, pat in enumerate(overrides.get("extra_deny_patterns", []) or []):
        try:
            rules.append((re.compile(pat, re.I), {
                "id": "PROJ-%02d" % (i + 1), "category": "project-defined", "action": "deny",
                "message": "Blocked by a project-defined rule in .ai-engineering/security.json.",
                "remediation": "Ask the project owner why this rule exists before working around it."}))
        except re.error as exc:
            dropped.append("extra_deny_patterns[%d] (%s)" % (i, exc))
    return rules


def active_waivers(overrides):
    """Waivers require both a justification and an expiry. Anything else is ignored."""
    import datetime
    live, rejected = set(), []
    for w in overrides.get("allow_rule_ids", []) or []:
        if not isinstance(w, dict):
            rejected.append(str(w))
            continue
        rid, why, exp = w.get("id"), w.get("justification"), w.get("expires")
        if not (rid and why and exp):
            rejected.append(str(rid))
            continue
        try:
            if datetime.date.fromisoformat(str(exp)) < datetime.date.today():
                rejected.append("%s (expired %s)" % (rid, exp))
                continue
        except Exception:
            rejected.append("%s (bad expiry)" % rid)
            continue
        live.add(rid)
    return live, rejected


# Shell forms that write to a named path. Best-effort by construction: a shell is
# a programming language and this is a regex. It exists because the alternative
# was nothing at all -- guard_write covered Write/Edit and the shell route was
# unscoped, while four documents called the scoping mechanical.
SHELL_WRITES = [
    re.compile(r">>?\s*(?P<path>[^\s|;&<>]+)"),
    re.compile(r"\btee\b(?:\s+-a)?\s+(?P<path>[^\s|;&<>-][^\s|;&<>]*)"),
    re.compile(r"\bsed\b[^|;&]*?\s-i[^\s]*\s+(?:(?:-e\s+)?[^\s|;&]+\s+)?(?P<path>[^\s|;&<>]+)"),
    re.compile(r"\b(?:cp|mv|install)\b\s+(?:-[^\s]+\s+)*[^\s|;&]+\s+(?P<path>[^\s|;&<>]+)"),
    re.compile(r"\btruncate\b[^|;&]*\s(?P<path>[^\s|;&<>]+)"),
    re.compile(r"\bdd\b[^|;&]*\bof=(?P<path>[^\s|;&<>]+)"),
]
# Writes that say nothing about the repository. A role scoped to docs/ is not
# doing anything untoward by redirecting into a scratch file.
TRANSIENT = re.compile(r"^(/dev/|/tmp/|\$|/proc/)|(^|/)\.\w+$")


def shell_write_targets(command):
    """Paths this command looks like it writes to."""
    out = []
    for rx in SHELL_WRITES:
        for m in rx.finditer(command):
            path = (m.group("path") or "").strip("\"'")
            if not path or TRANSIENT.match(path) or path.startswith("-"):
                continue
            out.append(path)
    return list(dict.fromkeys(out))


PUSH_TARGET = re.compile(r"\bgit\s+push\b(?P<rest>[^&|;]*)")


def push_targets(command):
    """Best-effort extraction of the branch a push would land on."""
    targets = []
    for m in PUSH_TARGET.finditer(command):
        rest = m.group("rest")
        toks = [t for t in rest.split() if not t.startswith("-")]
        # git push <remote> <refspec>...
        for tok in toks[1:] if len(toks) > 1 else []:
            # `git push origin "main"` and `git push origin +main` both land on
            # main. Matched literally, neither looked like main at all.
            ref = tok.strip("\"'").lstrip("+")
            ref = ref.split(":")[-1].strip("\"'")
            ref = re.sub(r"^refs/heads/", "", ref)
            if ref and ref not in ("HEAD",):
                targets.append(ref)
        if len(toks) <= 1 and re.search(r"\bgit\s+push\b", command):
            targets.append(None)  # pushes the current branch
    return targets


def git_branch_check(command):
    """Returns (decision, rule_id, message, remediation) or None."""
    if not re.search(r"\bgit\s+(push|commit)\b", command):
        return None
    branch = H.current_branch()

    if re.search(r"\bgit\s+push\b", command):
        for target in push_targets(command):
            name = target if target is not None else branch
            if H.is_protected(name):
                return ("escalate", "GIT-00",
                        "This pushes to '%s', which is a protected branch (%s)." % (
                            name, ", ".join(H.protected_branches())),
                        "Push a feature/, defect/ or hotfix/ branch and open a merge request instead. "
                        "A direct push to a protected branch needs a human decision (AP-09).")

    if re.search(r"\bgit\s+commit\b", command) and H.is_protected(branch):
        return ("escalate", "GIT-00b",
                "The working tree is on protected branch '%s'." % branch,
                "Create a branch first: git switch -c feature/<story-id>-<slug>. "
                "See policies/branch-policy.json for the naming model.")
    return None


def main():
    data = H.read_input()
    tool = data.get("tool_name", "")
    if tool != "Bash":
        H.allow_silently()
    command = (data.get("tool_input") or {}).get("command") or ""
    _SUBJECT[0] = command
    if not command.strip():
        H.allow_silently()

    # Tier 0. Runs before anything is loaded from disk, so it holds even when the
    # policy file is missing or malformed. See hooks/lib/failsafe.py.
    why = screen_catastrophic(command)
    if why:
        H.audit({"type": "bash_guard", "decision": "deny", "rules": ["TIER-0"],
                 "category": "catastrophic", "command": command[:800],
                 "session": data.get("session_id"), "agent": data.get("agent_type")})
        H.decide(EVENT, "deny",
                 "Blocked by the catastrophic-command screen: %s.\n"
                 "What to do instead: this class of command is never run from an agent session. "
                 "If it is genuinely required, a human runs it outside the session." % why,
                 rule_id="TIER-0")

    # Required, not optional: a corrupt rule file must trigger the tiered failure
    # path rather than degrade to "no rules apply".
    pol = H.policy_required("hook-policy.json", "rules")
    overrides = H.project_overrides()
    waived, rejected_waivers = active_waivers(overrides)

    hits = []
    dropped_rules = []
    for rx, rule in compile_rules(pol, overrides, dropped_rules):
        if rule.get("id") in waived:
            H.audit({"type": "waived", "rule": rule.get("id"), "command": command[:400]})
            continue
        if rx.search(command):
            hits.append(rule)

    # The same write scope the Write tool is held to. Escalate rather than deny:
    # the tool route knows the exact path and refuses, while this route inferred
    # it from a regex, and a mis-parse should cost a prompt rather than a blocked
    # task. Either way the command does not proceed unremarked.
    role = H.agent_role(data)
    if role:
        scope = H.policy("write-scope.json") or {}
        for target in shell_write_targets(command):
            why = H.write_scope_violation(role, target, scope)
            if why:
                hits.append({"id": "WS-SHELL", "category": "write-scope", "action": "escalate",
                             "message": "This writes '%s' through the shell, and role '%s' may "
                                        "not write it: %s." % (target, role, why),
                             "remediation": "Hand the change to the role that owns the path. "
                                            "The Write tool refuses this outright; the shell is "
                                            "checked on a best-effort reading of the command."})
                break

    branch_hit = git_branch_check(command)
    if branch_hit:
        decision, rid, msg, remedy = branch_hit
        hits.append({"id": rid, "category": "protected-branch", "action": decision,
                     "message": msg, "remediation": remedy})

    if dropped_rules:
        # Reported on the very next decision even when nothing matched, because
        # the rule that would have matched may be one of the dropped ones.
        H.audit({"type": "rules_dropped", "rules": dropped_rules,
                 "session": data.get("session_id")})

    if not hits:
        if dropped_rules:
            H.decide(EVENT, "escalate",
                     "Some safety rules could not be compiled, so this command was not fully "
                     "checked: %s\nWhat to do instead: fix the malformed entry in "
                     ".ai-engineering/security.json -- production_markers are literal environment "
                     "names and extra_deny_patterns must be valid regular expressions."
                     % ", ".join(dropped_rules), rule_id="POLICY-BROKEN")
        H.allow_silently()

    hits.sort(key=lambda r: SEVERITY_ORDER.get(r.get("action", "warn"), 3))
    top = hits[0]
    action = top.get("action", "warn")
    ids = ", ".join(h.get("id", "?") for h in hits)

    H.audit({"type": "bash_guard", "decision": action, "rules": [h.get("id") for h in hits],
             "category": top.get("category"), "command": command[:800],
             "session": data.get("session_id"), "agent": data.get("agent_type")})

    note = ""
    if rejected_waivers:
        note = " Ignored invalid waivers: %s." % ", ".join(rejected_waivers)
    if dropped_rules:
        note += (" Warning: these rules did not compile and were NOT applied: %s."
                 % ", ".join(dropped_rules))

    reason = "%s %s\nWhat to do instead: %s%s" % (
        top.get("message", "Blocked."), "(rules: %s)" % ids if len(hits) > 1 else "",
        top.get("remediation", "Ask the human operator."), note)

    if action in ("deny", "escalate"):
        H.decide(EVENT, action, reason, rule_id=top.get("id"))
    # warn / audit
    H.allow_silently()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        # _SUBJECT is captured while parsing. stdin is already consumed by this
        # point, so re-reading it here would hand the failure handler an empty
        # string and silently defeat the high-risk screen.
        H.fail_safe(EVENT, exc, "guard_bash", _SUBJECT[0])
