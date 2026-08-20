#!/usr/bin/env python3
"""SessionStart hook: tells the session what organization it is operating in and
whether the project is configured.

Kept short on purpose. Every character here is paid for on every session, so it
carries only what changes behaviour: the entry point, and whether the project
configuration that the agents depend on actually exists.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import hooklib as H  # noqa: E402


# Payloads that MUST be denied. If a safety guard fails to deny one of these at
# session start, the guard is broken and the session is told so prominently. A
# safety system that is silently broken is worse than no safety system, because
# the team stops thinking about the risk it was covering.
SELF_TEST = [
    ("guard_bash", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
    ("guard_bash", {"tool_name": "Bash",
                    "tool_input": {"command": "kubectl delete deploy api -n production"}}),
    ("guard_write", {"tool_name": "Write",
                     "tool_input": {"file_path": "/home/u/.ssh/id_rsa", "content": "x"}}),
]


def self_test():
    """Returns a list of failures. Never raises, never takes more than a moment."""
    failures = []
    for guard, payload in SELF_TEST:
        script = os.path.join(H.PLUGIN_ROOT, "hooks", "scripts", guard + ".py")
        try:
            proc = subprocess.run([sys.executable, script], input=json.dumps(payload),
                                  capture_output=True, text=True, timeout=10)
            out = (proc.stdout or "").strip()
            decision = None
            if out:
                decision = json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision")
            if decision != "deny":
                failures.append("%s did not deny a known-dangerous payload (got %r)"
                                % (guard, decision or "no decision"))
        except Exception as exc:
            failures.append("%s could not run: %r" % (guard, exc))
    return failures


def teams_line(cfg):
    """Reconciles what the project expects about agent teams with what is actually set.

    Enabling teams is a session-level decision with a session-level consequence:
    every named subagent spawn in the main conversation becomes a teammate, and a
    stage written as spawn-then-wait stalls because an idle notification carries no
    output. The project records an expectation; only the environment decides. When
    the two disagree, the session needs to know which way.
    """
    ai = cfg.get("ai") if isinstance(cfg, dict) else None
    expected = (ai or {}).get("agent_teams_available") if isinstance(ai, dict) else None
    if isinstance(expected, str):
        expected = expected.strip().lower() in ("true", "yes", "1")
    enabled = os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "") == "1"

    if enabled and expected is False:
        return ("Agent teams are ENABLED in this environment but the project records them as "
                "unavailable. Every named subagent spawn now launches as a teammate, including "
                "in stages declared execution: subagent, and such a stage stalls rather than "
                "failing. Either unset CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS or update "
                ".ai-engineering/project.yaml.")
    if not enabled and expected is True:
        return ("The project expects agent teams but CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not "
                "set. Team stages must fall back to their declared degraded_mode, and a "
                "TEAM_REQUIRED stage needs the fallback acknowledged before it proceeds.")
    if enabled:
        return ("Agent teams are enabled. Named subagent spawns from this conversation launch as "
                "teammates, so do not write a stage as spawn-then-wait-for-output.")
    return None


def main():
    cfg_dir = H.PROJECT_CONFIG_DIR
    has_yaml = os.path.exists(os.path.join(cfg_dir, "project.yaml"))
    has_json = os.path.exists(os.path.join(cfg_dir, "project.json"))
    lines = ["AI Engineering OS is active. Organizational roles, SDLC stages, review routing and "
             "safety guards come from the ai-engineering-os plugin.",
             "Start with /ai-engineering-os:sdlc-navigator to place the work in the lifecycle."]

    if has_yaml or has_json:
        cfg = H.project_config()
        proj = (cfg.get("project") or {}).get("name") if isinstance(cfg.get("project"), dict) else None
        tech = cfg.get("technology") or {}
        summary = []
        for area in ("frontend", "backend", "database", "deployment"):
            v = tech.get(area) if isinstance(tech, dict) else None
            if isinstance(v, dict):
                v = v.get("framework") or v.get("language") or v.get("primary") or v.get("platform")
            if v:
                summary.append("%s=%s" % (area, v))
        lines.append("Project configuration found at .ai-engineering/%s."
                     % ("project.yaml" if has_yaml else "project.json"))
        if proj:
            lines.append("Project: %s." % proj)
        if summary:
            lines.append("Approved stack: %s. Do not introduce technology outside it without a "
                         "technology decision (AP-03)." % ", ".join(summary))
    else:
        lines.append("No .ai-engineering/ project configuration found. Agents must not guess the "
                     "technology stack, branch model, environments or security requirements. "
                     "Run /ai-engineering-os:project-onboarding before engineering work starts.")

    # Independent of whether the project is configured: the environment alone decides
    # whether teams are on, and being on changes how every spawn behaves.
    note = teams_line(cfg if (has_yaml or has_json) else {})
    if note:
        lines.append(note)

    failures = self_test()
    if failures:
        lines.insert(0, "SAFETY GUARDS ARE NOT WORKING. Do not rely on them in this session:\n  - "
                        + "\n  - ".join(failures)
                        + "\nReport this before doing anything that touches production, "
                          "credentials or protected branches.")
        H.audit({"type": "self_test_failure", "failures": failures})

    text = "\n".join(lines)
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
           "additionalContext": text}
    sys.stdout.write(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
