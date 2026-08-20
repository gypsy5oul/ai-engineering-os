#!/usr/bin/env python3
"""PreToolUse guard for the Agent tool: enforces the organizational spawn hierarchy.

The main session is a human-driven session, not an organizational role, so it
keeps full delegation authority. Only agents defined in this OS are constrained,
using the may_spawn edges in policies/agent-registry.json.

Limits worth knowing: the hook sees the requested agent type and the caller's
agent type, nothing else. It cannot verify intent, and it cannot see teammate
spawns that Claude Code performs outside the Agent tool. It is a guardrail.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import hooklib as H  # noqa: E402

EVENT = "PreToolUse"
TYPE_KEYS = ("subagent_type", "agent_type", "agentType", "type", "name")


def requested_type(tool_input):
    for k in TYPE_KEYS:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            return v.split(":")[-1].strip()
    return ""


def main():
    data = H.read_input()
    if data.get("tool_name") != "Agent":
        H.allow_silently()

    tool_input = data.get("tool_input") or {}
    target = requested_type(tool_input)
    caller = (data.get("agent_type") or "").split(":")[-1]

    reg = H.policy("agent-registry.json")
    agents = {a["name"]: a for a in reg.get("agents", [])}
    hierarchy = H.policy("role-hierarchy.json")
    defaults = hierarchy.get("defaults", {})

    caller_entry = agents.get(caller)
    if caller_entry is None:
        # Main session or a non-organizational agent type: unconstrained by design.
        H.allow_silently()

    if not target:
        H.allow_silently()

    if target == caller and defaults.get("self_spawn") == "deny":
        H.audit({"type": "spawn_guard", "decision": "deny", "caller": caller, "target": target})
        H.decide(EVENT, "deny",
                 "Role '%s' may not spawn itself. Recursive self-delegation hides work rather than dividing it.\n"
                 "What to do instead: split the work into tasks and do them, or escalate to %s."
                 % (caller, hierarchy.get("escalation", {}).get("paths", {}).get(caller, "the human operator")),
                 rule_id="RH-SELF")

    allowed = caller_entry.get("may_spawn", [])
    target_entry = agents.get(target)

    if target_entry and target_entry.get("risk") == "CRITICAL":
        H.audit({"type": "spawn_guard", "decision": "escalate", "caller": caller, "target": target})
        H.decide(EVENT, "escalate",
                 "'%s' is a CRITICAL role. An agent may not bring it in without a human decision.\n"
                 "What to do instead: state why the review is needed and let the human invoke it."
                 % target, rule_id="RH-CRIT")

    if target in allowed:
        H.allow_silently()

    escalate_to = hierarchy.get("escalation", {}).get("paths", {}).get(caller, "the human operator")
    H.audit({"type": "spawn_guard", "decision": "deny", "caller": caller, "target": target,
             "allowed": allowed, "session": data.get("session_id")})
    H.decide(EVENT, "deny",
             "Role '%s' may not spawn '%s'. Permitted: %s.\n"
             "What to do instead: request it from %s, or state the need and let the human decide. "
             "Spawn authority is defined in policies/agent-registry.json (may_spawn)."
             % (caller, target, ", ".join(allowed) if allowed else "none", escalate_to),
             rule_id="RH-DENY")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        H.fail_safe(EVENT, exc, "guard_spawn")
