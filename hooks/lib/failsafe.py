"""Risk-tiered failure behaviour for the guards.

A blanket fail-open is wrong: the moment a guard breaks is exactly the moment it
is needed. A blanket fail-closed is also wrong: a guard that cannot evaluate
anything blocks every command and gets disabled by its users, after which it
protects nothing.

The resolution is to make the failure path itself tiered, and to make the
highest tier impossible to break:

  Tier 0  CATASTROPHIC   Pure-regex screen with no file I/O, no policy load and
                         no imports beyond `re`. It runs BEFORE the policy
                         engine and cannot be broken by a malformed policy file,
                         a missing file, or a bug in the evaluator. Always DENY.

  Tier 1  HIGH-RISK      A small hardcoded screen for production, secret and
                         destructive shapes. Consulted only when the full
                         evaluation has already failed. DENY, because the
                         command looks dangerous and the system can no longer
                         prove otherwise.

  Tier 2  EVERYTHING ELSE  Full evaluation failed and the command does not match
                         tier 0 or 1. ESCALATE to the human: fail closed without
                         bricking the session.

  Tier 3  ADVISORY       Guards whose purpose is organizational rather than
                         safety (the spawn hierarchy). ALLOW with a loud notice.

Nothing dangerous proceeds silently. Nothing benign is blocked by a broken
guard. Configured in policies/hook-policy.json under `failure_policy`.
"""
import re

# --------------------------------------------------------------------------
# Tier 0. Deliberately duplicated from policies/hook-policy.json rather than
# loaded from it. This list is the floor: it must hold when the policy file is
# unreadable, unparseable or wrong. Keep it short, keep it obvious, and keep it
# in sync via tests/test_failsafe.py, which asserts every entry here is also
# covered by a policy rule.
# --------------------------------------------------------------------------
CATASTROPHIC = [
    (r"\brm\b(?=(?:[^|;&]*\s)-[a-zA-Z]*[rR])(?=(?:[^|;&]*\s)-[a-zA-Z]*f)[^|;&]*?\s"
     r"[\"']?(/|/\*|~|~/|\$HOME|\$HOME/|"
     r"/(?:usr|bin|sbin|lib|lib64|etc|var|boot|opt|srv|dev|proc|sys|root|home)(?:/[^\s\"']*)?)"
     r"[\"']?\s*(?:[;&|]|$)",
     "recursive force delete of a root or home path"),
    (r"\bmkfs(\.[a-z0-9]+)?\b", "filesystem creation"),
    (r"\bdd\b[^|;&]*\bof=/dev/(sd|nvme|disk|hd)", "raw write to a block device"),
    (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|k|da)?sh\b", "piping a download into a shell"),
    (r"\bgit\s+(filter-branch|filter-repo)\b|\bgit\s+reflog\s+delete\b", "history rewriting"),
    (r"--dangerously-skip-permissions|\bdisableAllHooks\b", "disabling the permission or hook system"),
    (r"(cat|less|more|head|tail|bat|xxd|base64|strings)\s+[^|;&]*((~|\$HOME)/\.ssh/(id_|.*key)|\.aws/credentials|\.netrc)",
     "reading private key material or stored credentials"),
    (r"\b(curl|wget|nc|ncat|socat)\b[^|;&]*(--data|-d|-T|--upload-file)\s*@?[^|;&]*(\.env|credentials|id_rsa|\.pem)",
     "sending credential material to a network destination"),
    (r"\b(?:printenv|env|set)\b\s*\|[^|;&]*\b(?:curl|wget|nc|ncat|socat|mail)\b",
     "piping the environment to a network command"),
    # Tier 0 is a strict subset of the deny tier. Verbs the policy escalates
    # rather than denies (edit, patch, replace, set, apply) do not belong here.
    (r"\bkubectl\b(?=[^|;&]*\b(?:delete|drain|scale|exec)\b)"
     r"(?=[^|;&]*(?:-n|--namespace)[=\s]+[^\s]*(?<![A-Za-z])(?:prod|prd|production|live)(?![A-Za-z]))",
     "destroying or disrupting a production Kubernetes workload"),
    (r"(?:\beval\b|\bbash\b|\bsh\b|\bsource\b)\s*[^|;&]*(?:\$\(|<\()\s*(?:sudo\s+)?(?:curl|wget)\b",
     "executing the output of a network download"),
    (r"\b(?:cat|less|head|tail|grep|awk|sed|od|xxd|base64|strings|cp|dd)\b[^|;&]*"
     r"(?:(?:~|\$HOME|/home/[^/\s]+|/root)/)?\.(?:ssh/(?:id_[^\s]*|[^\s]*key[^\s]*)|aws/credentials|netrc)",
     "reading or copying private key material or stored credentials"),
    (r"(?:>>?|\btee\b|\bsed\b\s+[^|;&]*-i|\bcp\b|\bmv\b)\s*[^|;&]*(?:^|[\s=\"\'/])(?:agents|policies|hooks|schemas)/",
     "writing to the control plane through the shell"),
]

# Tier 1. Consulted only on the failure path. Broader and blunter than the real
# rules on purpose: on this path a false positive costs one escalation, and a
# false negative costs whatever the command does.
HIGH_RISK = [
    (r"(?<![A-Za-z])(?:prod|prd|production|live)(?![A-Za-z])", "names a production target"),
    (r"\b(terraform|terragrunt|pulumi|helm)\b", "infrastructure or release tooling"),
    (r"\b(DROP|TRUNCATE|DELETE)\s+(TABLE|DATABASE|SCHEMA|FROM)\b", "destructive data operation"),
    (r"\bgit\s+push\b", "publishes commits"),
    (r"\brm\b[^|;&]*-[a-zA-Z]*[rR]", "recursive delete"),
    (r"(secret|credential|token|password|\.pem|id_rsa|\.env)", "touches credential-shaped material"),
    (r"\b(chmod|chown|sudo|su)\b", "changes privilege or ownership"),
]

_CATASTROPHIC = [(re.compile(p, re.I), why) for p, why in CATASTROPHIC]
_HIGH_RISK = [(re.compile(p, re.I), why) for p, why in HIGH_RISK]


def screen_catastrophic(text):
    """Tier 0. Returns a reason string, or None. Cannot raise."""
    if not text:
        return None
    try:
        for rx, why in _CATASTROPHIC:
            if rx.search(text):
                return why
    except Exception:
        return None
    return None


def screen_high_risk(text):
    """Tier 1. Returns a reason string, or None. Cannot raise."""
    if not text:
        return None
    try:
        for rx, why in _HIGH_RISK:
            if rx.search(text):
                return why
    except Exception:
        return None
    return None


def failure_decision(subject, tier):
    """Decide what to do when the full evaluation could not complete.

    tier is the guard's configured tier: "safety" or "advisory".
    Returns (decision, reason). decision is "deny", "escalate" or None (allow).
    """
    if tier == "advisory":
        return None, ("The %s guard could not complete. It is an organizational guard, not a "
                      "safety boundary, so the action proceeds. This is a defect: report it."
                      % subject)

    why = screen_high_risk(subject if isinstance(subject, str) else "")
    if why:
        return "deny", ("The guard could not complete its evaluation, and this action %s. "
                        "It is denied because the system can no longer prove it is safe.\n"
                        "What to do instead: report the guard failure, and if the action is "
                        "genuinely required, a human performs it outside the agent session." % why)

    return "escalate", ("The guard could not complete its evaluation. The action does not match "
                        "the high-risk screen, but it has not been checked against the full "
                        "policy either, so it needs a human decision.\n"
                        "What to do instead: confirm the action, and report the guard failure.")
