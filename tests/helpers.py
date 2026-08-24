import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks", "scripts")


_NEUTRAL_REPO = None


def neutral_repo():
    """A throwaway git repo on a feature branch, used as the default cwd.

    Guard rules like GIT-00b look at the branch the working tree is on, so a test
    run inside the plugin's own checkout gave different answers depending on which
    branch the developer happened to be standing on. That is an environment
    dependency, not a test: renaming this repository's branch to `main` turned two
    green tests red without a line of guard code changing.
    """
    global _NEUTRAL_REPO
    if _NEUTRAL_REPO is None:
        import tempfile, atexit, shutil
        path = tempfile.mkdtemp(prefix="aieos-neutral-")
        atexit.register(shutil.rmtree, path, True)
        _init_repo(path, "feature/neutral")
        _NEUTRAL_REPO = path
    return _NEUTRAL_REPO


def _init_repo(path, branch):
    """A repo needs one commit: on an unborn HEAD git cannot name the branch,
    so branch-aware rules see nothing and quietly do not fire."""
    run = lambda *a: subprocess.run(["git"] + list(a), cwd=path, capture_output=True, timeout=30)
    run("init", "-q")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "test")
    with open(os.path.join(path, ".keep"), "w") as fh:
        fh.write("")
    run("add", ".keep")
    run("commit", "-q", "-m", "init")
    run("checkout", "-q", "-B", branch)


def repo_on_branch(branch):
    """A throwaway git repo standing on a named branch."""
    import tempfile, atexit, shutil
    path = tempfile.mkdtemp(prefix="aieos-branch-")
    atexit.register(shutil.rmtree, path, True)
    _init_repo(path, branch)
    return path


def run_hook(name, payload, env=None, cwd=None):
    """Run a hook script and return (decision, reason, exit_code, raw)."""
    environ = dict(os.environ)
    environ.setdefault("CLAUDE_PLUGIN_ROOT", ROOT)
    if env:
        environ.update(env)
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS, name + ".py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=environ, cwd=cwd or neutral_repo(), timeout=30)
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


def bash(command, agent=None, **kw):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent:
        payload["agent_type"] = agent
    return run_hook("guard_bash", payload, **kw)


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
