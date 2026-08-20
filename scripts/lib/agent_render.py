"""Render an agent definition file from the registry plus a role-contract body.

Used by scripts/scaffold_agent.py and by the initial authoring pass. Keeping
rendering in one place is why every agent file has the same section order,
which is in turn what makes scripts/validate_plugin.py able to check them.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECTIONS = [
    "Role contract",
    "Purpose",
    "Responsibilities",
    "Not your responsibility",
    "Authority",
    "Allowed actions",
    "Forbidden actions",
    "Required inputs",
    "Expected outputs",
    "Skills",
    "Model policy",
    "Escalation",
    "Review requirements",
    "Handoff",
    "Definition of done",
]


def load_policies():
    reg = json.load(open(os.path.join(ROOT, "policies", "agent-registry.json")))
    prof = json.load(open(os.path.join(ROOT, "policies", "tool-permissions.json")))
    scope = json.load(open(os.path.join(ROOT, "policies", "write-scope.json")))
    return reg, prof, scope


def _bullets(items):
    return "\n".join("- " + i for i in items) if items else "- None."


def render(entry, body, profiles, scope):
    prof = profiles["profiles"][entry["tool_profile"]]
    tools = ", ".join(prof["tools"])
    fm = [
        "---",
        "name: %s" % entry["name"],
        "description: %s" % body["description"],
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

    role_scope = scope["roles"].get(entry["name"])
    if role_scope is None:
        scope_line = "Not applicable (no write tools)." if "Write" not in prof["tools"] else "Unscoped: governed only by the global deny list."
    elif role_scope["mode"] == "allow":
        scope_line = "May write only to: `%s`" % "`, `".join(role_scope["allow"])
    else:
        scope_line = "May write anywhere except: `%s`" % "`, `".join(role_scope["deny"]) if role_scope["deny"] else "Unscoped within this repository."

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
        "## Skills",
        "",
        _bullets(["`%s`" % s for s in body.get("skills", [])] or ["None preloaded."]) +
        "\n\nSkills listed in frontmatter are preloaded when this definition runs as a subagent. Claude Code does **not** apply the `skills` field when the same definition runs as an agent-team teammate, so when you are a teammate, invoke the skills you need explicitly.",
        "",
        "## Model policy",
        "",
        body["model_policy"],
        "",
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
