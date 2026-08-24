# Architecture

## What this is

A Claude Code plugin containing an engineering organization: roles, lifecycle,
rules, guards and evaluations. It contains no application, no server, no
scheduler and no orchestration runtime, because Claude Code already provides
those primitives and duplicating them would mean maintaining a second, worse
copy.

```
GitLab (source of truth, review, CI, releases)
   │
   ▼
ai-engineering-os plugin ──► Claude Code session
   │                            ├── agents/     organizational roles
   │                            ├── skills/     shared capabilities
   │                            ├── hooks/      deny / escalate / audit guards
   │                            └── policies/   machine-readable governance
   ▼
project repository (.ai-engineering/project.yaml, CLAUDE.md, code)
   │
   ▼
GitLab
```

## The two layers

**Company layer** — this repository. Reusable across every project. Contains
nothing project-specific and mandates no technology.

**Project layer** — each application repository. Contains `CLAUDE.md`,
`.ai-engineering/project.yaml`, the approved stack, the architecture, the code.
The plugin reads the project layer; it never assumes it.

The seam between them is the reason the OS is reusable. Anything that would have
to change per project belongs in the project layer, and the plugin's job is to
detect when it is missing rather than to guess a value.

## Component model

| Component | Mechanism | Loaded |
| --- | --- | --- |
| Agent | `agents/*.md` with frontmatter and a role contract | On delegation or @-mention |
| Skill | `skills/<name>/SKILL.md` | On invocation or when its description matches |
| Guard | `hooks/hooks.json` → `hooks/scripts/*.py` | On every matching tool call |
| Policy | `policies/*.json` | Read by guards, scripts and agents |
| Workflow (Level 1) | `sdlc/workflows/*.yaml` | Stage-to-stage. Read by `sdlc-navigator` and by validation |
| Department cycle (Level 2) | `sdlc/cycles/*.yaml` | Task-to-task delegation, review and rework inside a stage |
| Evaluation | `evaluations/<suite>/*.json` | Run by `scripts/run_evaluations.py` |
| Schema | `schemas/*.json` | Used by the validators |
| Artifact contract | `policies/artifact-model.json` | Read by `scripts/check_dod.py` and by the agents |
| Approval authority | `policies/approval-authority.json` | The agent-verdict / human-approval split |
| Execution policy | `policies/execution-policy.json` | Inline / subagent / team routing |
| System of record | `policies/system-of-record.json` | What is authoritative, and what is only a mechanism |

Only agents, skills and hooks are Claude Code primitives. Policies, workflows,
evaluations and schemas are **data**: they are read by the primitives, by the
validators and by the agents themselves. That distinction matters, and the next
section is about where the original design assumed otherwise.

## Deviations from the original design, and why

These are the places where the design given to us and the platform disagreed.
In every case the platform won, and the deviation is recorded rather than hidden.

| Original | Actual | Why |
| --- | --- | --- |
| `workflows/` at the plugin root for SDLC definitions | `sdlc/workflows/` | **Verified against the current docs.** `workflows/` at a plugin root is where Claude Code loads *dynamic workflow* JavaScript scripts, namespaced as `/<plugin>:<meta.name>`. Declarative YAML there would not load. The two are different things and the names would collide. |
| `settings.json` at the plugin root carrying settings | Not shipped; a template for the project's own `.claude/settings.json` instead | A plugin-root `settings.json` supports only `agent` and `subagentStatusLine`. Anything else is silently ignored — the worst possible failure mode for a governance control. |
| `.mcp.json` in the plugin | Absent by design | V1 ships no MCP servers. An empty or speculative `.mcp.json` would be fake functionality. The extension model is in `docs/mcp.md` and `policies/mcp-extension.json`. |
| Agent frontmatter carrying owner, risk, version, status | `policies/agent-registry.json` | Claude Code defines the frontmatter fields it supports. Adding organizational fields there risks them being dropped or flagged. A registry is also queryable and diffable, which frontmatter spread across 30 files is not. |
| Agent Team definitions as files | Prompt patterns in `skills/team-patterns/` | There is no team definition format. `~/.claude/teams/*/config.json` is runtime state that Claude Code writes and overwrites; pre-authoring it would be a fiction. |
| `senior-*` developer agents | Seniority as a task property | See `docs/organization.md`. Two agents differing only in the word "senior" is the duplication the design explicitly warns against. |

## How a request flows

1. **SessionStart** injects the organization's presence and whether the project
   is configured. If it is not, the first legitimate action is onboarding.
2. **`sdlc-navigator`** picks the workflow, locates the stage, and names the
   missing inputs and the applicable gates.
3. The **stage owner** does the work, using its skills, inside its authority.
4. **Guards** evaluate every command, write and spawn as it happens.
5. **Review routing** selects reviewers by change signal, not by ceremony.
6. **Approval gates** stop only for the operations in
   `policies/approval-policy.json`.
7. **Artifacts** carry identifiers so the next stage can find what it needs.

## What is authoritative

`policies/system-of-record.json` states it, and `EVAL-AIG-005` enforces it:

- **GitLab** — code, merge requests, human approvals, pipelines, releases.
- **Repository artifacts** — requirements, architecture, tests, incidents, RCAs,
  and the project configuration.
- **Authoritative for nothing** — the agent-team task list, the session
  transcript, the local audit log.

Agent teams are experimental, their task status is known to lag, and `/resume`
does not restore in-process teammates. Any workflow that would break if agent
teams were disabled tomorrow is wrongly designed. See [execution](execution.md).

The resumability test: delete the session and the task list. Can another engineer
say, from GitLab and the repository alone, what stage the change is in and who
owes what? If not, the artifact contract is incomplete.

## Enforcement model

Three layers, deliberately different in strength:

| Layer | Strength | Example |
| --- | --- | --- |
| **Guards** (hooks) | Mechanical, and tiered on failure. Tier 0 cannot be broken by a bad policy file. | A push to `main` escalates whatever the agent intended; `rm -rf /` is denied even with the policy engine dead. |
| **Structure** (tool profiles, write scopes) | Mechanical for the tool layer; best-effort for the shell. | A reviewer has no `Write` tool and an empty write scope, so authoring what it reviews is refused on both routes -- but only the tool route is airtight. |
| **Contract** (role definitions, skills) | Behavioural. Strong, but not a guarantee. | "Never invent an availability target." |

Anything that must hold regardless of model behaviour is in the first two layers.
The role contracts carry judgement, not safety.

## Dynamic workflows: not shipped, but used here

Claude Code has a second, unrelated thing called a workflow: a **JavaScript
script** that orchestrates many subagents, which a plugin may ship in
`workflows/` and which runs as `/<plugin>:<name>`. It holds the plan in code
rather than in Claude's turn-by-turn judgement, and it can apply repeatable
quality patterns such as adversarial cross-checking.

This plugin does not ship one in the lifecycle, deliberately:

- The SDLC definitions in `sdlc/workflows/` are **declarative state**, read by
  agents and by the validators. They are not orchestration and would not benefit
  from being code.
- A dynamic workflow is a good fit for a **fan-out over many items** — audit
  every route handler, migrate 500 files. Routed code review inside a workflow
  stage already works as subagents at a scale that does not need the runtime.
- Shipping both would put `workflows/` and `sdlc/workflows/` in one repository,
  meaning two different things.

The honest summary: the capability is real and it is used here, for review
fan-out over this repository, which is exactly the shape it suits. What it is
not is part of the shipped lifecycle, and `policies/platform-capabilities.json`
records it that way.

## Extension points

- **New agent** — registry entry, `scripts/scaffold_agent.py`, evaluation suite.
- **New guard rule** — a rule in `policies/hook-policy.json` plus two tests: one
  that it blocks, one that it does not block the ordinary case that resembles it.
- **New workflow** — a YAML file validated by `schemas/sdlc-workflow.schema.json`.
- **MCP servers** — categories, invariants and the approval path are in
  `docs/mcp.md`. Nothing is implemented in V1.
- **A future SDLC control plane** — see `docs/limitations.md` for what would
  justify building one, and what it would have to provide that the plugin cannot.

## Why there is no control plane in V1

A control plane would be justified by durable state that Claude Code cannot hold:
approvals that persist beyond a session, cross-session task assignment, and an
authoritative audit log. Today GitLab already holds the first and the third, and
the second is a coordination problem rather than a storage problem. Building a
control plane before those limits actually bite would produce a system that
competes with GitLab and loses. The limits are recorded in
`docs/limitations.md` so that the decision can be revisited with evidence.
