"""Shared helpers for the AI Engineering OS hooks.

Design rules for everything in this package:

1. Fail closed, in tiers. A catastrophic-command screen runs before the policy
   engine and cannot be broken by it. When the full evaluation fails, a
   high-risk-looking action is denied and anything else is escalated to the
   human. Only advisory guards fail open. See hooks/lib/failsafe.py.
2. Never emit "allow". Emitting allow would bypass the user's own permission
   rules. The guards emit only "deny" or "escalate"; staying silent lets
   Claude Code's normal permission flow decide.
3. Every decision is explained. A denial that does not say what to do instead
   just gets worked around.

Requires Python 3.8+ and no third-party packages.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
import time

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
PROJECT_CONFIG_DIR = os.path.join(PROJECT_DIR, ".ai-engineering")


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def read_input():
    """Read the hook payload from stdin. Returns {} if anything is wrong."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def policy(name):
    """Load a policy document. Returns {} when it cannot be read."""
    return load_json(os.path.join(PLUGIN_ROOT, "policies", name))


class PolicyUnavailable(RuntimeError):
    """A policy document a guard depends on is missing, unparseable or empty.

    This must not be confused with "the policy says nothing applies". A corrupt
    rule file that degrades to an empty rule set is a guard that silently stops
    guarding, which is the exact failure the tiered handler exists to catch.
    """


def policy_required(name, key=None, minimum=1):
    """Load a policy document a guard cannot operate without.

    Raises PolicyUnavailable rather than returning an empty document, so the
    caller's failure path runs instead of the guard quietly passing everything.
    """
    path = os.path.join(PLUGIN_ROOT, "policies", name)
    if not os.path.exists(path):
        raise PolicyUnavailable("%s is missing" % name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:
        raise PolicyUnavailable("%s is unparseable: %s" % (name, exc))
    if not isinstance(doc, dict) or not doc:
        raise PolicyUnavailable("%s is empty or not an object" % name)
    if key is not None:
        value = doc.get(key)
        if not value or (hasattr(value, "__len__") and len(value) < minimum):
            raise PolicyUnavailable("%s has no usable '%s'" % (name, key))
    return doc


def project_overrides():
    """Project-local, additive-only security configuration."""
    return load_json(os.path.join(PROJECT_CONFIG_DIR, "security.json"), {})


def project_config():
    """Project configuration, if present. Supports project.json and project.yaml."""
    j = os.path.join(PROJECT_CONFIG_DIR, "project.json")
    if os.path.exists(j):
        return load_json(j, {})
    y = os.path.join(PROJECT_CONFIG_DIR, "project.yaml")
    if os.path.exists(y):
        sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts", "lib"))
        try:
            from minyaml import parse_file  # noqa: E402
            return parse_file(y)
        except Exception:
            return {}
    return {}


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------

def _emit(payload):
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


# The organization's vocabulary is deny/escalate. Claude Code's wire protocol
# accepts only allow/deny/ask/defer, and discards a decision it cannot parse --
# which means the tool call proceeds. "escalate" was emitted verbatim and was
# therefore inert: every escalate-tier rule allowed the command it described.
# Verified against the CLI's own schema and by running a hook that emits each
# value. The policy keeps its word; only the wire value is translated.
WIRE_DECISION = {"deny": "deny", "escalate": "ask"}


def decide(event, decision, reason, rule_id=None, system_message=None):
    """Emit a PreToolUse/PermissionRequest decision and exit.

    decision is "deny" or "escalate". "allow" is deliberately not supported:
    see the module docstring.
    """
    if decision not in WIRE_DECISION:
        raise ValueError("unsupported decision: %s" % decision)
    prefix = "[ai-engineering-os%s]" % (" " + rule_id if rule_id else "")
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": WIRE_DECISION[decision],
            "permissionDecisionReason": "%s %s" % (prefix, reason),
        }
    }
    if system_message:
        payload["systemMessage"] = system_message
    _emit(payload)
    sys.exit(0)


def allow_silently():
    """Emit nothing: Claude Code's normal permission flow applies."""
    sys.exit(0)


def context(event, text):
    _emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})
    sys.exit(0)


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def plugin_data_dir():
    """Where this plugin keeps data that outlives a single hook invocation.

    A hook is a fresh process every time, so anything a guard needs to remember
    between calls -- how many agents a role currently has running, for instance --
    has to live on disk.
    """
    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".claude", "ai-engineering-os")
    return base


def audit_dir():
    return os.path.join(plugin_data_dir(), "audit")


def audit(record):
    """Append one JSONL audit record. Never raises."""
    try:
        d = audit_dir()
        os.makedirs(d, exist_ok=True)
        record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        path = os.path.join(d, time.strftime("%Y-%m") + ".jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def guard_tier(where):
    """Configured failure tier for a guard: 'safety' or 'advisory'."""
    try:
        return policy("hook-policy.json").get("failure_policy", {}) \
            .get("guard_tiers", {}).get(where, "safety")
    except Exception:
        return "safety"


def fail_safe(event, err, where, subject=""):
    """Internal error path. Risk-tiered: see hooks/lib/failsafe.py.

    Never allows a high-risk-looking action just because the guard broke.
    """
    sys.path.insert(0, os.path.join(PLUGIN_ROOT, "hooks", "lib"))
    audit({"type": "hook_error", "hook": where, "error": repr(err), "subject": str(subject)[:400]})
    try:
        from failsafe import failure_decision
        decision, reason = failure_decision(subject, guard_tier(where))
    except Exception:
        decision, reason = "escalate", ("The guard failed and its failure handler also failed. "
                                        "This needs a human decision.")
    notice = ("[ai-engineering-os] guard '%s' could not complete: %r. This is a defect in the "
              "guard. Report it." % (where, err))
    if decision is None:
        _emit({"systemMessage": notice})
        sys.exit(0)
    audit({"type": "hook_error_decision", "hook": where, "decision": decision})
    _emit({
        "hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": WIRE_DECISION[decision],
            "permissionDecisionReason": "[ai-engineering-os GUARD-FAILURE] " + reason,
        },
        "systemMessage": notice,
    })
    sys.exit(0)


# Retained under the old name so that an out-of-tree guard keeps working, but it
# is no longer fail-open: it delegates to the tiered handler.
fail_open = fail_safe


# --------------------------------------------------------------------------
# Path matching
# --------------------------------------------------------------------------

def _glob_to_regex(pattern):
    """Translate a glob with ** semantics into a regex.

    fnmatch treats * as matching separators too, which makes 'docs/*' match
    'docs/a/b'. Directory-aware matching is the whole point here, so the
    translation is done explicitly.
    """
    i, n, out = 0, len(pattern), ["^"]
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c in ".^$+{}[]()|\\":
            out.append("\\" + c)
            i += 1
        else:
            out.append(c)
            i += 1
    out.append("$")
    return re.compile("".join(out))


_GLOB_CACHE = {}


def path_matches(path, patterns):
    """True if path matches any glob. Checks the raw path, the project-relative
    path and the basename so that patterns work regardless of how the tool
    expressed the path."""
    if not path:
        return False
    norm = path.replace("\\", "/")
    # Collapsed before matching. `src/../../../etc/passwd` matched no deny glob
    # and still satisfied `src/**`, so the traversal was invisible to the deny
    # list and legible to the allow list -- exactly backwards.
    flat = os.path.normpath(norm).replace("\\", "/")
    candidates = {flat, os.path.basename(flat)}
    # The raw spelling is only a candidate when it has no traversal in it. Keeping
    # it otherwise is what let `docs/requirements/../src/app.js` satisfy an allow
    # glob for `docs/requirements/**` while actually writing to src/.
    if ".." not in norm.split("/"):
        candidates.add(norm)
    try:
        rel = os.path.relpath(os.path.abspath(path), PROJECT_DIR).replace("\\", "/")
        if not rel.startswith(".."):
            candidates.add(rel)
    except Exception:
        pass
    for pat in patterns or []:
        rx = _GLOB_CACHE.get(pat)
        if rx is None:
            rx = _GLOB_CACHE[pat] = _glob_to_regex(pat)
        for cand in candidates:
            if rx.match(cand) or fnmatch.fnmatch(cand, pat):
                return True
    return False


# --------------------------------------------------------------------------
# Git helpers
# --------------------------------------------------------------------------

def git(*args):
    try:
        out = subprocess.run(["git"] + list(args), cwd=PROJECT_DIR,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def current_branch():
    return git("rev-parse", "--abbrev-ref", "HEAD")


def protected_branches():
    branch_policy = policy("branch-policy.json")
    branches = list(branch_policy.get("protected_branches", []))
    cfg = project_config()
    try:
        extra = cfg.get("repository", {}).get("branching", {}).get("protected_branches", [])
        branches.extend(extra or [])
    except Exception:
        pass
    branches.extend(project_overrides().get("protected_branches", []) or [])
    return branches


def is_protected(branch):
    if not branch:
        return False
    return any(fnmatch.fnmatch(branch, p) for p in protected_branches())


def escapes_project(path):
    """Whether the path resolves outside the project directory.

    An allow-list is a statement about paths inside the project. A candidate that
    leaves it cannot be satisfied by one, however it is spelled.
    """
    if not path:
        return False
    try:
        target = os.path.abspath(os.path.join(PROJECT_DIR, path))
        root = os.path.abspath(PROJECT_DIR)
        return os.path.commonpath([target, root]) != root
    except Exception:
        return True


# --------------------------------------------------------------------------
# Write scope, in one place
# --------------------------------------------------------------------------

def agent_role(data):
    """The role name, however the platform spelled the agent type.

    Plugin agents arrive namespaced (`ai-engineering-os:qa-engineer`). Every hook
    that keys off the role needs the bare name, and the one hook that forgot made
    all 22 write scopes inert for ten versions.
    """
    return (data.get("agent_type") or "").split(":")[-1]


def write_scope_violation(role, path, scope):
    """Why this role may not write this path, or None.

    Shared by guard_write (the Write/Edit tools) and guard_bash (shell writes) so
    the two cannot answer differently. They used to: the tool route was scoped and
    the shell route was not scoped at all, while four documents called the scoping
    mechanical.
    """
    if not role or not path:
        return None
    role_scope = (scope.get("roles") or {}).get(role)
    if role_scope is None:
        return None
    if role_scope.get("mode") == "allow":
        if escapes_project(path):
            return ("it resolves outside the project directory, and the role is scoped to "
                    "paths inside it")
        if not path_matches(path, role_scope.get("allow", [])):
            allowed = role_scope.get("allow") or []
            return ("the role may write only to: %s"
                    % (", ".join(allowed) if allowed else "nothing; it is a reviewer"))
    elif role_scope.get("mode") == "deny":
        if path_matches(path, role_scope.get("deny", [])):
            return "that path belongs to another role"
    return None
