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


def compile_rules(pol, overrides):
    rules = []
    for r in pol.get("rules", []):
        flags = re.I if "i" in (r.get("flags") or "") else 0
        try:
            rules.append((re.compile(r["pattern"], flags), r))
        except re.error:
            continue
    for i, pat in enumerate(overrides.get("extra_deny_patterns", []) or []):
        try:
            rules.append((re.compile(pat, re.I), {
                "id": "PROJ-%02d" % (i + 1), "category": "project-defined", "action": "deny",
                "message": "Blocked by a project-defined rule in .ai-engineering/security.json.",
                "remediation": "Ask the project owner why this rule exists before working around it."}))
        except re.error:
            continue
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


PUSH_TARGET = re.compile(r"\bgit\s+push\b(?P<rest>[^&|;]*)")


def push_targets(command):
    """Best-effort extraction of the branch a push would land on."""
    targets = []
    for m in PUSH_TARGET.finditer(command):
        rest = m.group("rest")
        toks = [t for t in rest.split() if not t.startswith("-")]
        # git push <remote> <refspec>...
        for tok in toks[1:] if len(toks) > 1 else []:
            ref = tok.split(":")[-1]
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
    for rx, rule in compile_rules(pol, overrides):
        if rule.get("id") in waived:
            H.audit({"type": "waived", "rule": rule.get("id"), "command": command[:400]})
            continue
        if rx.search(command):
            hits.append(rule)

    branch_hit = git_branch_check(command)
    if branch_hit:
        decision, rid, msg, remedy = branch_hit
        hits.append({"id": rid, "category": "protected-branch", "action": decision,
                     "message": msg, "remediation": remedy})

    if not hits:
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
