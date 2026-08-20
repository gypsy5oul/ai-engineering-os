---
name: agent-development
description: Author and maintain the components of the AI Engineering OS itself - agents, skills, hooks, policies and schemas. Use when adding or changing anything in this plugin. Enforces the canonical role-contract structure and the platform's actual capabilities.
---

# Agent development

Build the organization's own components to the standard the organization imposes.

## Decide what the thing is, before building it

| The need | The right shape |
| --- | --- |
| A durable organizational role with authority, inputs and outputs | **Agent** |
| A capability many roles use | **Skill** |
| An independent check on someone else's work | **Reviewer agent** (read-only tools) |
| A rule that must hold regardless of what the model decides | **Hook** |
| A statement of who may do what | **Policy** |
| A shape that must be validated | **Schema** |

Most requests are skills or policies. An agent is justified only when a role boundary genuinely exists: different authority, different inputs, different accountability. Two agents that differ only in wording must be merged.

## Authoring an agent

Frontmatter carries only fields Claude Code supports: `name`, `description`, `tools`, `model`, optional `skills`, `color`. Everything organizational — owner, risk, version, status, evaluation suite, spawn permissions — lives in `policies/agent-registry.json`, which the validator keeps in sync with the files.

The body follows the canonical section order (Role contract, Purpose, Responsibilities, Not your responsibility, Authority, Allowed actions, Forbidden actions, Required inputs, Expected outputs, Skills, Model policy, Escalation, Review requirements, Handoff, Definition of done). `scripts/scaffold_agent.py` generates the skeleton; the validator enforces it.

Tools must match a named profile in `policies/tool-permissions.json` exactly. Reviewers never get `Write` or `Edit`: independence has to be structural.

## Authoring a skill

- The body is what loads into context. Keep it high-signal; move depth into `reference.md` beside it and link to it.
- The `description` is how Claude decides to use it. State what it does **and when to use it**, with the trigger cases first.
- Never hard-code a technology unless the skill is explicitly platform-specific and says so in its description.
- Write rules that change behaviour. A skill that restates general good practice costs context and changes nothing.

## Authoring a hook

- Rules live in `policies/hook-policy.json`, not in code. Code evaluates rules.
- Emit only `deny` or `escalate`. Never `allow`: that would override the user's own permission rules.
- Fail open with a loud message. A guard that crashes a session gets disabled, and then it protects nothing.
- Every denial says what to do instead.
- Every rule needs two tests: one proving it blocks the dangerous case, one proving it does not block the ordinary case that resembles it. False positives are how guards lose their authority.

## Verify against the platform, not against memory

Before using a capability, check the current Claude Code documentation. Where the platform cannot do something, document the limitation in `docs/troubleshooting.md` and the README's limitations section. **Never implement a fiction that looks like it works.**

## Before proposing the change

These commands run from the plugin repository itself, not from a project.
This skill maintains the plugin; the working directory is the checkout.

```
python3 scripts/validate_plugin.py
python3 scripts/validate_schemas.py
python3 scripts/secret_scan.py
python3 -m unittest discover -s tests -v
python3 scripts/run_evaluations.py
```

Then update the registry, the changelog, and a migration note if organizational behaviour changed.
