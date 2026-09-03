# ai-engineering-os

A versioned, governed AI engineering organization that runs on Claude Code.

This repository is a Claude Code plugin. It does not contain an application, an
agent runtime, or a replacement for anything Claude Code already does. It
contains the **organization**: the roles, the lifecycle they follow, the rules
they operate under, the guards that enforce those rules, and the evaluations
that prove any of it works.

## How the pieces fit

Claude Code is the execution engine. This plugin is the organization that decides
what should be executed, by whom, and whether the result counts.

```
  a human states an intent
            │
            ▼
  WORK ITEM ─────────────────────────────── durable, in the project's git
   intent · objective · risk · owner        (delete every session; this survives)
            │
            ▼
  TASK GRAPH ────────────────────────────── generated per change, not fixed
   dependencies from artifact flow          (independent work runs in parallel)
            │
            ▼
  ┌─────────┴──────────┐
  │  for each task     │
  │                    ▼
  │        EXECUTION RESOLVER ───────────── how: inline · subagent · background · team
  │                    │                    where: shared · worktree · remote
  │                    │                    (two dimensions, from runtime facts)
  │                    ▼
  │            CLAUDE CODE ──────────────── spawns and runs the agent
  │                    │
  │        ┌───────────┴───────────┐
  │        │ SubagentStart         │ ◄── injects this agent's work item and task
  │        │ SubagentStop          │ ◄── records the result against that task
  │        │ TaskCompleted         │ ◄── refuses to close if the DoD fails
  │        └───────────┬───────────┘
  │                    ▼
  │            DEFINITION OF DONE ───────── machine-checkable predicates
  │                    │
  │        ┌───────────┴───────────┐
  │        ▼                       ▼
  │     ACCEPT                  FAILED
  │        │                       │
  │        │        ┌──────────────┼──────────────┐
  │        │        ▼              ▼              ▼
  │        │     RETRY          REWORK        ESCALATE
  │        │        │              │       (bounded: 3 attempts,
  │        └────────┴──────────────┘        2 replans, or the same
  │                 │                        failure twice)
  └─────────────────┘
            │
            ▼
  ACCEPTED  ──────────────────────────────  artifacts in git, GitLab is the record
```

Three separations do the real work:

- **The workflow says what must be true. The task graph says how this change gets
  there. Claude Code says how execution happens.** Change any one without
  touching the others.
- **An agent verdict is not a human approval.** Independence is the write
  scope, not the absence of a write tool: a reviewer may write its own review
  record and nothing else, so it can never author what it reviews.
- **Guards are mechanical; contracts are not.** What must hold regardless of what
  a model decides is enforced by a hook. Everything else is written down and
  followed, and `docs/limitations.md` says which is which.

And one principle runs through all of them:

- **Simplicity by default.** Build the simplest thing that satisfies the stated
  functional, non-functional, reliability, security, scalability and operational
  requirements. Not the smallest — a design that drops a requirement is
  incomplete, not simple. Complexity is bought with a requirement and the
  purchase is recorded, checked by `complexity_justified(ARCH)` and reviewed
  independently under `RR-11`. Nothing is prohibited.
  See [simplicity.md](docs/simplicity.md).

## What it gives you

| | |
| --- | --- |
| **30 agents** | An optimized organization: product, architecture, UX, engineering, data, QA, security, platform, release, SRE, incident, documentation, AI governance, and five independent specialist reviewers. |
| **43 skills** | Reusable capabilities from requirements engineering to root cause analysis, including **engineering simplicity** and seven **AI product engineering** capabilities. Technology-neutral: they name no provider. |
| **12 hook events** | Command, write and spawn guards, context injection, result observation, a **task-creation gate** that binds native tasks to the graph and refuses ones the graph forbids, a completion gate, a teammate-idle gate, worktree lifecycle recording and a session self-test. 45 command rules, **risk-tiered failure** so a broken policy file cannot open the guard, and a self-test at session start. |
| **7 department cycles** | Level 2: human owner → agent head → lead → worker → peer review → rework → accept → rollup. A macro stage cannot advance until its department's internal loop reaches ACCEPTED. |
| **10 SDLC workflows** | Machine-readable stages with entry criteria, artifact contracts, a **checkable definition of done**, separate agent and human gates, risk-driven model routing and execution mode. |
| **33 policies** | Model routing, risk, approvals and **approval authority**, artifact model, execution and isolation, **workflow intensity**, **simplicity**, **AI evaluation**, **agent memory**, **decomposition review**, system of record, branching, review routing, write scoping, spawn hierarchy, lifecycle, MCP. |
| **90 evaluation cases** | 62 deterministic checks that run in CI, plus 28 behavioural cases with rubrics that are never auto-passed. |
| **31 artifact types** | Full contracts: who creates, modifies, reviews and approves each, where it is stored, what it depends on. Plus 31 definition-of-done predicates. |
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
python3 scripts/certify.py               # Golden Project certification, synthetic path
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
3. **Open the work item.** This is the step that turns the diagram above into
   something running. Until a work item exists, the hooks that inject context and
   gate completion have nothing to attach to and stay silent.

   ```bash
   python3 scripts/control_loop.py open  --project . --type feature \
       --intent "Partners time out on large transfers"
   python3 scripts/control_loop.py plan  --project . --item ACME-FEAT-001
   python3 scripts/control_loop.py next  --project . --item ACME-FEAT-001
   ```
4. **Work.** Delegate to the roles, or spawn an agent team using the patterns in
   `/ai-engineering-os:team-patterns`. Each spawned agent is handed its own task
   automatically. Record what came back, and let the loop decide:

   ```bash
   python3 scripts/control_loop.py observe --project . --item ACME-FEAT-001 \
       --task T-003 --outcome accepted
   python3 scripts/control_loop.py decide  --project . --item ACME-FEAT-001 --task T-003
   python3 scripts/control_loop.py status  --project . --item ACME-FEAT-001
   ```

   `docs/work-items.md` is the full account: what the loop decides, what bounds
   it, and what happens when it runs out of moves.

## Repository layout

```
.claude-plugin/plugin.json       Plugin manifest
.claude-plugin/marketplace.json  Private marketplace catalogue
agents/                          30 role definitions
skills/                          43 skills
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

Read in this order and each one builds on the last.

**Understand it**

| | |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | **Start here.** Day one on a real project, end to end |
| [architecture.md](docs/architecture.md) | How the plugin is put together, and what it deliberately is not |
| [work-items.md](docs/work-items.md) | The durable work item, the task graph, the bounded control loop |
| [sdlc.md](docs/sdlc.md) | The nine workflows and what each stage must produce |
| [department-cycles.md](docs/department-cycles.md) | The loop inside a stage: worker → peer → lead → accept, and how much of it a task walks |

**The organization**

| | |
| --- | --- |
| [organization.md](docs/organization.md) | The 30 agents, and what each one owns |
| [agent-model.md](docs/agent-model.md) | Role contracts: authority, tools, risk, lifecycle |
| [skills.md](docs/skills.md) | The 43 skills and who loads them |
| [organization-freeze.md](docs/organization-freeze.md) | Why the agent set does not grow |

**The rules, and what actually enforces them**

| | |
| --- | --- |
| [governance.md](docs/governance.md) | Who decides what, and how that changes |
| [approvals.md](docs/approvals.md) | An agent verdict is never a human approval |
| [simplicity.md](docs/simplicity.md) | Simplicity by default: the two questions, the complexity ledger, and why no hook enforces it |
| [hooks.md](docs/hooks.md) | The guards, the 45 command rules, risk-tiered failure |
| [model-policy.md](docs/model-policy.md) | Risk floors, and why a model cannot be downgraded past one |
| [security.md](docs/security.md) | Threat model and the boundaries that hold |
| [limitations.md](docs/limitations.md) | **What is not enforced.** Read this before trusting anything |

**Running it**

| | |
| --- | --- |
| [execution.md](docs/execution.md) | How the work runs and where it runs — two dimensions, resolved separately |
| [liveness-and-limits.md](docs/liveness-and-limits.md) | What happens when nothing happens; concurrency caps |
| [knowledge-structure.md](docs/knowledge-structure.md) | The 31 artifact types and their traceability |
| [communications.md](docs/communications.md) | Events, routing, digests |
| [gitlab.md](docs/gitlab.md) | GitLab as the system of record |
| [enterprise-deployment.md](docs/enterprise-deployment.md) | Managed settings, and what they do not prevent |
| [project-onboarding.md](docs/project-onboarding.md) | Configuring a project |
| [troubleshooting.md](docs/troubleshooting.md) | When something does not work |
| [examples/](docs/examples/README.md) | The three worked scenarios, and what each one shows |

**Proving it works**

| | |
| --- | --- |
| [evaluation.md](docs/evaluation.md) | Agent, workflow and organization evaluations; fault injection |
| [telemetry.md](docs/telemetry.md) | What is measured, and what is refused as unmeasurable |
| [production-readiness.md](docs/production-readiness.md) | The end-to-end simulation and what it proves |
| [certification.md](docs/certification.md) | The Golden Project, and the line between synthetic validation and real-agent evidence |

**Extending and changing it**

| | |
| --- | --- |
| [development.md](docs/development.md) | Working on the plugin itself |
| [agent-teams.md](docs/agent-teams.md) | When teams help, and their real limits |
| [mcp.md](docs/mcp.md) | The extension model, and why nothing ships yet |
| [lsp.md](docs/lsp.md) | Language intelligence, and why no server ships |
| [release.md](docs/release.md) | Versioning, tagging, migration notes |

## Requirements

- Claude Code (recent version; agent teams additionally require
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- Python 3.8 or later on PATH as `python3`, for the hooks and the tooling

## Status

Version 0.45.2. **Architecture frozen**: the agent set is fixed at 30 and further work is schema hardening and implementation correctness, not conceptual redesign. See [organization freeze](docs/organization-freeze.md). Every agent is in the `pilot` lifecycle state: validated,
evaluated on its deterministic cases, and not yet promoted to `production`.
Promotion requires a human governance decision per `GOVERNANCE.md`.

## Licence

Apache-2.0. See `LICENSE`.
