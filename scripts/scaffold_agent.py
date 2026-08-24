#!/usr/bin/env python3
"""Scaffold a new agent definition from its registry entry.

Add the agent to policies/agent-registry.json first, then run:

  python3 scripts/scaffold_agent.py <agent-name>

The registry is the source of truth for ownership, risk, model and permissions;
this only renders the file so the canonical section order is never hand-typed.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from agent_render import load_policies, render  # noqa: E402

PLACEHOLDER = "TODO: fill this in. An unfilled role contract fails validation and review."


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        print("\nusage: scaffold_agent.py <agent-name>\n")
        print("The agent must already exist in policies/agent-registry.json: the registry "
              "carries\nowner, risk class, model policy and spawn permissions, and this "
              "renders the file\nfrom it. Adding the registry entry is the decision; "
              "scaffolding is the consequence.")
        return 0

    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    reg, prof, scope = load_policies()
    entry = next((a for a in reg["agents"] if a["name"] == name), None)
    if entry is None:
        print("ERROR %r is not in policies/agent-registry.json. Add it there first: the registry "
              "carries owner, risk, model policy and spawn permissions." % name)
        return 1
    path = os.path.join(ROOT, "agents", name + ".md")
    if os.path.exists(path):
        print("ERROR %s already exists" % path)
        return 1

    body = {
        "title": name.replace("-", " ").title(),
        "description": PLACEHOLDER + " State what the role does and when to delegate to it.",
        "reports_to": PLACEHOLDER,
        "purpose": PLACEHOLDER,
        "responsibilities": [PLACEHOLDER],
        "not_responsible": [PLACEHOLDER],
        "authority": [PLACEHOLDER],
        "allowed": [PLACEHOLDER],
        "forbidden": [PLACEHOLDER],
        "inputs": [PLACEHOLDER],
        "outputs": [PLACEHOLDER],
        "skills": [],
        "model_policy": PLACEHOLDER,
        "escalation": [PLACEHOLDER],
        "review": [PLACEHOLDER],
        "handoff": [PLACEHOLDER],
        "dod": [PLACEHOLDER],
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(entry, body, prof, scope))
    print("Wrote %s" % os.path.relpath(path, ROOT))
    print("Next: fill every TODO, add evaluation cases in evaluations/%s/, then run "
          "scripts/validate_plugin.py." % entry["evaluation_suite"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
