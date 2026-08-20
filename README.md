# ai-engineering-os

A versioned, governed AI engineering organization that runs on Claude Code.

This repository is a Claude Code plugin. It does not contain an application, an
agent runtime, or a replacement for anything Claude Code already does. It
contains the **organization**: the roles, the lifecycle they follow, the rules
they operate under, the guards that enforce those rules, and the evaluations
that prove any of it works.

```
GitLab  →  ai-engineering-os plugin  →  Claude Code
                                          ├── agents (29 organizational roles)
                                          ├── skills (31 capabilities)
                                          ├── hooks  (safety and governance guards)
                                          └── policies, workflows, evaluations
                                        →  your project repository  →  GitLab
```

## What it gives you

| | |
| --- | --- |
| **30 agents** | An optimized organization: product, architecture, UX, engineering, data, QA, security, platform, release, SRE, incident, documentation, AI governance, and five independent specialist reviewers. |
| **32 skills** | Reusable capabilities from requirements engineering to root cause analysis. Technology-neutral. |
| **4 hook guards** | Command, write, spawn and session guards. 39 command rules, **risk-tiered failure** so a broken policy file cannot open the guard, and a self-test at session start. |
| **7 department cycles** | Level 2: human owner → agent head → lead → worker → peer review → rework → accept → rollup. A macro stage cannot advance until its department's internal loop reaches ACCEPTED. |
| **7 SDLC workflows** | Machine-readable stages with entry criteria, artifact contracts, a **checkable definition of done**, separate agent and human gates, risk-driven model routing and execution mode. |
| **21 policies** | Model routing, risk, approvals and **approval authority**, artifact model, execution mode, system of record, branching, review routing, write scoping, spawn hierarchy, lifecycle, MCP. |
| **58 evaluation cases** | 35 deterministic checks that run in CI, plus 23 behavioural cases with rubrics that are never auto-passed. |
| **21 artifact types** | Full contracts: who creates, modifies, reviews and approves each, where it is stored, what it depends on. Plus 21 definition-of-done predicates. |
| **Zero runtime dependencies** | Everything runs on Python 3.8+ with no `pip install`. |

## Technology neutrality

Nothing here mandates Python, Java, Go, React, PostgreSQL, Kafka, Kubernetes or
any cloud. Technology is a **project** decision, recorded by a human in
`.ai-engineering/project.yaml`. The one platform-specific skill,
`kubernetes-basics`, states in its own description that it applies only when the
project declares Kubernetes.

## Install

### For an engineer

Each engineer uses their own Claude account. This repository never contains
credentials of any kind.

```bash
# Add the private marketplace (replace with your GitLab URL)
claude plugin marketplace add https://gitlab.example.com/ai-engineering/ai-engineering-os.git

# Install
claude plugin install ai-engineering-os@ai-engineering
```

For a private repository, configure a git credential helper first; see
`docs/gitlab.md`.

### For development on the plugin itself

```bash
git clone https://gitlab.example.com/ai-engineering/ai-engineering-os.git
cd ai-engineering-os
claude --plugin-dir .
```

Then `/reload-plugins` after edits.

### Verify

```bash
claude plugin validate .          # Claude Code's own structural check
python3 scripts/validate_plugin.py    # this repository's consistency checks
python3 -m unittest discover -s tests # hook and library tests
python3 scripts/run_evaluations.py    # deterministic evaluation cases
python3 scripts/check_dod.py --grammar   # definition-of-done predicates
python3 scripts/check_cycle.py           # department execution state machines
python3 scripts/simulate_sdlc.py --all   # every loop, end to end, against a real project
python3 scripts/resolve_model.py --all   # model routing for every stage
./scripts/check_all.sh                   # all of the above
```

## Use it on a project

1. **Onboard the project.** In the project repository, run
   `/ai-engineering-os:project-onboarding`. It discovers what it can, asks a
   human everything it cannot, and writes `.ai-engineering/project.yaml`.
   Nothing important is inferred.
2. **Place the work.** `/ai-engineering-os:sdlc-navigator` tells you which
   workflow and stage the request belongs to, what is missing, and which
   approvals apply.
3. **Work.** Delegate to the roles, or spawn an agent team using the patterns in
   `/ai-engineering-os:team-patterns`.

## Repository layout

```
.claude-plugin/plugin.json       Plugin manifest
.claude-plugin/marketplace.json  Private marketplace catalogue
agents/                          29 role definitions
skills/                          32 skills
hooks/hooks.json                 Hook registration
hooks/scripts/                   Guard implementations
hooks/lib/                       Shared hook library
policies/                        Machine-readable governance
schemas/                         JSON Schemas for every structured artifact
sdlc/workflows/                  Level 1: stage-to-stage lifecycle
sdlc/cycles/                     Level 2: department execution cycles
notification/                    Events, routing policy, channels, templates
bin/                             Executables on PATH while the plugin is enabled
evaluations/                     Evaluation suites, one per department
templates/                       Project configuration and artifact templates
scripts/                         Validators, evaluation runner, scaffolding
tests/                           Hook, library and repository tests
docs/                            Documentation, including worked examples
```

`sdlc/` rather than `workflows/`: `workflows/` at a plugin root is reserved by
Claude Code for executable Workflow scripts, and the lifecycle definitions here
are declarative YAML. See `docs/architecture.md` for the full list of deviations
from the original design and why each one exists.

## Documentation

| | |
| --- | --- |
| [docs/getting-started.md](docs/getting-started.md) | **Start here.** Day one: building a new app, end to end |
| [docs/architecture.md](docs/architecture.md) | How the plugin is put together and why |
| [docs/organization.md](docs/organization.md) | The agent catalogue |
| [docs/agent-model.md](docs/agent-model.md) | Role contracts, risk, ownership, lifecycle |
| [docs/skills.md](docs/skills.md) | The skill catalogue |
| [docs/hooks.md](docs/hooks.md) | Guard model, rules and how to change them |
| [docs/agent-teams.md](docs/agent-teams.md) | When teams help, and their real limits |
| [docs/approvals.md](docs/approvals.md) | Agent verdicts versus human approvals |
| [docs/execution.md](docs/execution.md) | Inline, subagent or team, and why |
| [docs/communications.md](docs/communications.md) | Event-driven notifications and digests |
| [docs/organization-freeze.md](docs/organization-freeze.md) | Why the agent set is frozen at 29 |
| [docs/sdlc.md](docs/sdlc.md) | The lifecycle and its workflows (Level 1) |
| [docs/department-cycles.md](docs/department-cycles.md) | The delegation loop inside each stage (Level 2) |
| [docs/governance.md](docs/governance.md) | Who may change what |
| [docs/security.md](docs/security.md) | Security model |
| [docs/model-policy.md](docs/model-policy.md) | Model routing and escalation |
| [docs/project-onboarding.md](docs/project-onboarding.md) | Adopting the OS on a project |
| [docs/knowledge-structure.md](docs/knowledge-structure.md) | Artifacts and traceability |
| [docs/evaluation.md](docs/evaluation.md) | The evaluation framework |
| [docs/liveness-and-limits.md](docs/liveness-and-limits.md) | What happens when nothing happens, and how much a role may run at once |
| [docs/enterprise-deployment.md](docs/enterprise-deployment.md) | Making the plugin non-bypassable via managed settings |
| [docs/gitlab.md](docs/gitlab.md) | GitLab usage, CE compatibility, CI |
| [docs/mcp.md](docs/mcp.md) | The MCP extension model (nothing implemented in V1) |
| [docs/development.md](docs/development.md) | Working on this repository |
| [docs/release.md](docs/release.md) | Versioning and release |
| [docs/production-readiness.md](docs/production-readiness.md) | The end-to-end audit, and what it found |
| [docs/limitations.md](docs/limitations.md) | What V1 cannot do |
| [docs/troubleshooting.md](docs/troubleshooting.md) | When something misbehaves |
| [docs/examples/](docs/examples/) | Three worked end-to-end scenarios |

## Requirements

- Claude Code (recent version; agent teams additionally require
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and an interactive session)
- Python 3.8 or later on PATH as `python3`, for the hooks and the tooling

## Status

Version 0.17.0. **Architecture frozen**: the agent set is fixed at 30 and further work is schema hardening and implementation correctness, not conceptual redesign. See [organization freeze](docs/organization-freeze.md). Every agent is in the `pilot` lifecycle state: validated,
evaluated on its deterministic cases, and not yet promoted to `production`.
Promotion requires a human governance decision per `GOVERNANCE.md`.

## Licence

Apache-2.0. See `LICENSE`.
