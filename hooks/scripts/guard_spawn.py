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
import ledger  # noqa: E402

EVENT = "PreToolUse"
TYPE_KEYS = ("subagent_type", "agent_type", "agentType", "type", "name")


def requested_type(tool_input):
    for k in TYPE_KEYS:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            return v.split(":")[-1].strip()
    return ""


def concurrency_limits():
    policy = H.policy("concurrency-policy.json")
    return (policy.get("per_role", {}),
            policy.get("default_max_concurrent", 2),
            (policy.get("session_limit") or {}).get("max_concurrent"),
            (policy.get("ledger") or {}).get("entry_ttl_seconds", 1800))


def concurrency_check(caller, target, data):
    """Is this spawn one too many? Returns (over_limit, reason).

    Spawn authority says whether a role may delegate. This says how much. A role
    permitted to spawn thirteen kinds of agent may otherwise spawn thirteen agents
    for a one-line change, and each one is a full Claude session.

    Over the limit escalates rather than denies: a wide fan-out is sometimes
    right, and the person running the session is the one who can tell. What must
    not happen is that it occurs without anyone choosing it.
    """
    try:
        per_role, default_max, session_max, ttl = concurrency_limits()
        session = data.get("session_id")
        if not session:
            # Without a session id there is no boundary to count within, and one
            # shared ledger would make unrelated work contend for the same slots.
            # So the count is not applied -- but "the control cannot be scoped"
            # is not the same as "the control does not apply", and silently
            # disabling a limit for HIGH and CRITICAL roles reads as the second.
            risk = (H.policy("agent-registry.json") or {})
            entry = next((a for a in risk.get("agents", []) if a["name"] == target), {})
            level = str(entry.get("risk", "MEDIUM")).upper()
            H.audit({"type": "concurrency_unscoped", "caller": caller, "target": target,
                     "risk": level, "why": "no session_id in the payload"})
            if level == "CRITICAL":
                return True, ("This spawn carries no session id, so the concurrency limit cannot "
                              "be counted against anything -- and '%s' is a CRITICAL role.\n"
                              "What to do instead: confirm this fan-out is intended. The limit is "
                              "not being enforced here, so you are the limit." % target)
            # HIGH and below are allowed and audited. Escalating every one of them
            # would put a prompt in front of ordinary work on the strength of a
            # missing field, which is how a guard trains people to click through it.
            return False, ""
        mine = len(ledger.open_spawns(H.plugin_data_dir(), session, ttl, caller))
        cap = (per_role.get(caller) or {}).get("max_concurrent", default_max)
        if mine >= cap:
            return True, ("'%s' already has %d agent(s) running and its limit is %d. Each one is a "
                          "full Claude session.\nWhat to do instead: let some finish, or say why "
                          "this change needs more parallel work than the limit assumes. Limits are "
                          "in policies/concurrency-policy.json." % (caller, mine, cap))
        total = len(ledger.open_spawns(H.plugin_data_dir(), session, ttl))
        if session_max and total >= session_max:
            return True, ("This session already has %d agent(s) running and the limit is %d. "
                          "Spawning '%s' would be one more.\nWhat to do instead: let some finish "
                          "before widening further." % (total, session_max, target))
    except Exception:
        # A broken ledger must never block delegation. This is a guardrail against
        # runaway fan-out, not a safety boundary.
        return False, ""
    return False, ""


def record_spawn(caller, target, data):
    try:
        if not data.get("session_id"):
            return
        _, _, _, ttl = concurrency_limits()
        ledger.record(H.plugin_data_dir(), data.get("session_id"), caller, target, ttl)
    except Exception:
        pass


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
        over, reason = concurrency_check(caller, target, data)
        if over:
            H.audit({"type": "spawn_guard", "decision": "escalate", "caller": caller,
                     "target": target, "rule": "CC-LIMIT", "session": data.get("session_id")})
            H.decide(EVENT, "escalate", reason, rule_id="CC-LIMIT")
        record_spawn(caller, target, data)
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
