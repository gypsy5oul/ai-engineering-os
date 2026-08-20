import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks", "scripts")


def run_hook(name, payload, env=None, cwd=None):
    """Run a hook script and return (decision, reason, exit_code, raw)."""
    environ = dict(os.environ)
    environ.setdefault("CLAUDE_PLUGIN_ROOT", ROOT)
    if env:
        environ.update(env)
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS, name + ".py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=environ, cwd=cwd or ROOT, timeout=30)
    raw = proc.stdout.strip()
    if not raw:
        return None, "", proc.returncode, raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "malformed", raw, proc.returncode, raw
    hso = data.get("hookSpecificOutput", {})
    return hso.get("permissionDecision"), hso.get("permissionDecisionReason", ""), proc.returncode, raw


# What Claude Code's PreToolUse schema accepts. A decision outside this set is
# discarded and the tool call proceeds, so a guard that emits one is inert.
PLATFORM_DECISIONS = ("allow", "deny", "ask", "defer")

# The organization's escalate tier maps onto this wire value.
ESCALATE = "ask"


def bash(command, **kw):
    return run_hook("guard_bash", {"tool_name": "Bash", "tool_input": {"command": command}}, **kw)


def write(path, content="", tool="Write", agent=None):
    payload = {"tool_name": tool, "tool_input": {"file_path": path, "content": content}}
    if agent:
        payload["agent_type"] = agent
    return run_hook("guard_write", payload)


def spawn(caller, target):
    payload = {"tool_name": "Agent", "tool_input": {"subagent_type": target}}
    if caller:
        payload["agent_type"] = caller
    return run_hook("guard_spawn", payload)
