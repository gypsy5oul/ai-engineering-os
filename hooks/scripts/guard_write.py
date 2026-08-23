#!/usr/bin/env python3
"""PreToolUse guard for file-writing tools.

Enforces, in order:
  1. Hard-denied paths (private key material, git internals).
  2. Credential-adjacent paths -> escalate to the human.
  3. Governed control-plane paths (.ai-engineering/, agents/, hooks/, ...) -> escalate (AP-10).
  4. Per-role write scope from policies/write-scope.json.
  5. Secret-like content in the payload -> deny.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import hooklib as H  # noqa: E402

EVENT = "PreToolUse"
# Captured as the payload is parsed so the failure handler can still classify the
# action's risk when the evaluation itself has broken.
_SUBJECT = [""]
PATH_KEYS = ("file_path", "notebook_path", "path", "filePath")
CONTENT_KEYS = ("content", "new_string", "new_source", "replacement")


def extract(tool_input):
    path = ""
    for k in PATH_KEYS:
        if tool_input.get(k):
            path = tool_input[k]
            break
    chunks = []
    for k in CONTENT_KEYS:
        v = tool_input.get(k)
        if isinstance(v, str):
            chunks.append(v)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                chunks.append(e["new_string"])
    return path, "\n".join(chunks)


def scan_secrets(text):
    if not text:
        return []
    pol = H.policy_required("secret-patterns.json", "patterns")
    found = []
    for p in pol.get("patterns", []):
        try:
            rx = re.compile(p["pattern"])
        except re.error:
            continue
        m = rx.search(text)
        if not m:
            continue
        value = m.group(len(m.groups())) if m.groups() else m.group(0)
        if any(re.search(a, value or "") for a in p.get("allow_if_matches", [])):
            continue
        found.append((p["id"], p["name"], p.get("severity", "major")))
    return found


def main():
    data = H.read_input()
    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "NotebookEdit"):
        H.allow_silently()

    tool_input = data.get("tool_input") or {}
    path, content = extract(tool_input)
    _SUBJECT[0] = path
    # Plugin agents arrive as "ai-engineering-os:solution-architect". Matched
    # whole, no role in write-scope.json was ever found and every per-role scope
    # was inert. Every other hook already strips it; this one did not.
    agent = (data.get("agent_type") or "").split(":")[-1]
    scope = H.policy_required("write-scope.json", "roles")
    overrides = H.project_overrides()

    # 1. hard deny
    if H.path_matches(path, scope.get("global_hard_deny", [])):
        H.audit({"type": "write_guard", "decision": "deny", "rule": "WS-HARD", "path": path, "agent": agent})
        H.decide(EVENT, "deny",
                 "'%s' is private key material or git internal state. No engineering task requires an agent to write it.\n"
                 "What to do instead: if a key must change, a human rotates it through the secret manager." % path,
                 rule_id="WS-HARD")

    # 2. credential-adjacent, unless it is an example or template file
    exempt = H.path_matches(path, scope.get("global_deny_exceptions", []))
    if not exempt and H.path_matches(
            path, scope.get("global_deny", []) + (overrides.get("extra_protected_paths") or [])):
        H.audit({"type": "write_guard", "decision": "escalate", "rule": "WS-CRED", "path": path, "agent": agent})
        H.decide(EVENT, "escalate",
                 "'%s' holds credential-adjacent configuration. Writing it needs a human decision (AP-08).\n"
                 "What to do instead: reference the secret by name and let the runtime inject the value; never commit one." % path,
                 rule_id="WS-CRED")

    # 3. governed control-plane paths
    gov = scope.get("governed_paths", {})
    if H.path_matches(path, gov.get("paths", [])):
        H.audit({"type": "write_guard", "decision": gov.get("decision", "escalate"),
                 "rule": "WS-GOV", "path": path, "agent": agent})
        H.decide(EVENT, gov.get("decision", "escalate"),
                 "'%s' configures the control system itself. %s\n"
                 "What to do instead: make the change in a merge request with governance review (AP-10)."
                 % (path, gov.get("why", "")), rule_id="WS-GOV")

    # 4. per-role scope
    role = scope.get("roles", {}).get(agent)
    if role:
        if role.get("mode") == "allow" and H.escapes_project(path):
            H.audit({"type": "write_guard", "decision": "deny", "rule": "WS-ESCAPE",
                     "path": path, "agent": agent})
            H.decide(EVENT, "deny",
                     "'%s' resolves outside the project directory. Role '%s' is scoped to paths "
                     "inside the project, and no spelling of a path escapes that.\n"
                     "What to do instead: write inside the project, or ask the human to move the "
                     "file in." % (path, agent), rule_id="WS-ESCAPE")
        if role.get("mode") == "allow" and not H.path_matches(path, role.get("allow", [])):
            H.audit({"type": "write_guard", "decision": "deny", "rule": "WS-SCOPE", "path": path, "agent": agent})
            H.decide(EVENT, "deny",
                     "Role '%s' may write only to: %s. '%s' is outside that scope.\n"
                     "What to do instead: hand this change to the role that owns the path, or ask the human to reassign it."
                     % (agent, ", ".join(role.get("allow", [])), path), rule_id="WS-SCOPE")
        if role.get("mode") == "deny" and H.path_matches(path, role.get("deny", [])):
            H.audit({"type": "write_guard", "decision": "deny", "rule": "WS-SCOPE", "path": path, "agent": agent})
            H.decide(EVENT, "deny",
                     "Role '%s' is not permitted to modify '%s'; that path belongs to another role.\n"
                     "What to do instead: raise the change with the owning role rather than editing it here."
                     % (agent, path), rule_id="WS-SCOPE")

    # 5. secret content
    hits = scan_secrets(content)
    critical = [h for h in hits if h[2] == "critical"]
    if critical:
        names = ", ".join("%s (%s)" % (h[1], h[0]) for h in critical)
        H.audit({"type": "write_guard", "decision": "deny", "rule": "WS-SECRET",
                 "path": path, "agent": agent, "patterns": [h[0] for h in critical]})
        H.decide(EVENT, "deny",
                 "The content being written looks like live secret material: %s.\n"
                 "What to do instead: remove the value, reference it from the secret manager, and if it was ever real, rotate it."
                 % names, rule_id="WS-SECRET")
    if hits:
        H.audit({"type": "write_guard", "decision": "escalate", "rule": "WS-SECRET-SOFT",
                 "path": path, "agent": agent, "patterns": [h[0] for h in hits]})
        H.decide(EVENT, "escalate",
                 "The content contains something shaped like a credential: %s. Confirm it is a placeholder.\n"
                 "What to do instead: use an obvious placeholder such as ${MY_TOKEN} or 'changeme'."
                 % ", ".join("%s (%s)" % (h[1], h[0]) for h in hits), rule_id="WS-SECRET-SOFT")

    H.allow_silently()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        H.fail_safe(EVENT, exc, "guard_write", _SUBJECT[0])
