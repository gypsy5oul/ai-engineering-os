"""Render an agent definition file from the registry plus a role-contract body.

Used by scripts/scaffold_agent.py and by the initial authoring pass. Keeping
rendering in one place is why every agent file has the same section order,
which is in turn what makes scripts/validate_plugin.py able to check them.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _sections():
    """The canonical section order, from policies/agent-registry.json.

    Read rather than restated. This file used to carry its own copy, which drifted
    two sections out of date and made scaffold_agent.py emit a definition the
    validator refused -- the documented way to create an agent failing the build.
    """
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    with open(os.path.join(root, "policies", "agent-registry.json"), encoding="utf-8") as fh:
        return json.load(fh)["role_contract_sections"]


SECTIONS = _sections()


def load_policies():
    reg = json.load(open(os.path.join(ROOT, "policies", "agent-registry.json")))
    prof = json.load(open(os.path.join(ROOT, "policies", "tool-permissions.json")))
    scope = json.load(open(os.path.join(ROOT, "policies", "write-scope.json")))
    return reg, prof, scope


def _bullets(items):
    return "\n".join("- " + i for i in items) if items else "- None."


def write_scope_line(name, scope, tools):
    """The `| Write scope |` cell, from policies/write-scope.json.

    The only place this string is built. Seven agents' tables had drifted from
    the policy: two did not know they were allowed to write the artifacts they
    own, and three planned infrastructure edits the guard rejects. The body table
    is what the agent itself reads; the policy is what the hook enforces. They
    have to be the same sentence.
    """
    role_scope = (scope.get("roles") or {}).get(name)
    if role_scope is None:
        return ("Not applicable (no write tools)." if "Write" not in tools
                else "Unscoped: governed only by the global deny list.")
    if role_scope["mode"] == "allow":
        return "May write only to: `%s`" % "`, `".join(role_scope["allow"])
    if not role_scope["deny"]:
        return "Unscoped within this repository."
    return "May write anywhere except: `%s`" % "`, `".join(role_scope["deny"])


def render(entry, body, profiles, scope):
    prof = profiles["profiles"][entry["tool_profile"]]
    tools = ", ".join(prof["tools"])
    fm = [
        "---",
        "name: %s" % entry["name"],
        # Always quoted. A description containing ": " is a syntax error to any
        # strict YAML parser, and validate_plugin.py rejects it -- the renderer
        # emitting one meant the scaffold produced a file that failed the build.
        'description: "%s"' % body["description"].replace('"', '\\"'),
        "tools: %s" % tools,
        "model: %s" % entry["default_model"],
    ]
    if body.get("skills"):
        fm.append("skills:")
        for s in body["skills"]:
            fm.append("  - %s" % s)
    if body.get("color"):
        fm.append("color: %s" % body["color"])
    fm.append("---")

    scope_line = write_scope_line(entry["name"], scope, prof["tools"])

    spawn = entry["may_spawn"]
    spawn_line = ("May spawn: `%s`" % "`, `".join(spawn)) if spawn else "May not spawn other agents. Delegation requests go to %s." % (
        body.get("escalates_to") or "the human operator")

    contract = [
        "| Field | Value |",
        "| --- | --- |",
        "| Department | %s |" % entry["department"],
        "| Reports to | %s |" % body["reports_to"],
        "| Owner | %s |" % entry["owner"],
        "| Version | %s |" % entry["version"],
        "| Lifecycle status | %s |" % entry["status"],
        "| Risk class | %s |" % entry["risk"],
        "| Tool profile | %s (`%s`) |" % (entry["tool_profile"], tools),
        "| Write scope | %s |" % scope_line,
        "| Default model | %s (escalates to %s) |" % (entry["default_model"], entry["escalation_model"]),
        "| Evaluation suite | `evaluations/%s/` |" % entry["evaluation_suite"],
        "| Review frequency | %s |" % entry["review_frequency"],
        "| Team spawn permission | %s |" % spawn_line,
    ]

    approvals = entry["requires_human_approval_for"]
    parts = [
        "\n".join(fm),
        "",
        "# %s" % body["title"],
        "",
        "## Role contract",
        "",
        "\n".join(contract),
        "",
        "## Purpose",
        "",
        body["purpose"],
        "",
        "## Responsibilities",
        "",
        _bullets(body["responsibilities"]),
        "",
        "## Not your responsibility",
        "",
        _bullets(body["not_responsible"]),
        "",
        "## Authority",
        "",
        _bullets(body["authority"]),
        "",
        "## Allowed actions",
        "",
        _bullets(body["allowed"]),
        "",
        "## Forbidden actions",
        "",
        _bullets(body["forbidden"] + (
            ["Proceeding without human approval on: " + "; ".join(approvals) + "."] if approvals else [])),
        "",
        "## Required inputs",
        "",
        _bullets(body["inputs"]),
        "",
        "## Expected outputs",
        "",
        _bullets(body["outputs"]),
        "",
        # No Skills or Model policy section: v0.8.0 removed both. Skills duplicated
        # the frontmatter, and Model policy addressed the caller from a file only
        # the callee reads -- a running subagent cannot change its own model.
        "## Escalation",
        "",
        _bullets(body["escalation"]),
        "",
        "## Review requirements",
        "",
        _bullets(body["review"]),
        "",
        "## Handoff",
        "",
        _bullets(body["handoff"]),
        "",
        "## Definition of done",
        "",
        _bullets(body["dod"]),
        "",
    ]
    return "\n".join(parts)
