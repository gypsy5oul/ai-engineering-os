# The organization

30 agents. The number is a design output, not a target: the objective stated in
`docs/agent-model.md` is the smallest set of roles that covers the work without
losing a role boundary. Where two candidate roles differed only in wording they
were merged, and the reasoning is recorded in the notes below.

Each entry links to its definition. The authoritative machine-readable record is
`policies/agent-registry.json`; `scripts/validate_plugin.py` fails if the two
disagree.

## Executive and governance

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`engineering-director`](../agents/engineering-director.md) | Owns end-to-end delivery of a change: sequences SDLC stages, forms teams, arbitrates cross-department conflict, and escalates decisions that need a human. | opus | HIGH | lead | writes `docs/decisions/**`, `docs/sdlc/**…`; may spawn 13 roles |

## AI governance

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`ai-governance`](../agents/ai-governance.md) | Independent authority over the AI Engineering OS itself: agent lifecycle, risk classification, permission and model policy, evaluation standards. | opus | CRITICAL | review-readonly | read-only |

## AI / agent engineering

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`agent-architect`](../agents/agent-architect.md) | Designs the organization itself: agent boundaries, skill decomposition, team patterns, hook policy and the extension model. | opus | HIGH | author | writes `agents/**`, `docs/**…` |
| [`agent-developer`](../agents/agent-developer.md) | Implements and maintains agents, skills, hooks and evaluations in this repository. | sonnet | HIGH | implementer | writes |
| [`agent-evaluator`](../agents/agent-evaluator.md) | Runs and interprets evaluation suites, reports regressions and blocks promotion of agents that fail their gate. | sonnet | HIGH | review-readonly | read-only |

## Product

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`product-manager`](../agents/product-manager.md) | Turns business intent into a prioritised, testable product definition and owns the PRD and its acceptance criteria. | sonnet | MEDIUM | author | writes `docs/requirements/**`, `docs/stories/**…`; may spawn 2 roles |
| [`requirements-analyst`](../agents/requirements-analyst.md) | Elicits, disambiguates and records functional and non-functional requirements with full traceability identifiers. | sonnet | MEDIUM | author | writes `docs/requirements/**` |

## Architecture

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`architecture-reviewer`](../agents/architecture-reviewer.md) | Independently reviews architecture and ADRs for fitness, risk, consistency and non-functional coverage. Cannot author the architecture it reviews. | opus | HIGH | analysis-readonly | read-only |
| [`solution-architect`](../agents/solution-architect.md) | Produces feasibility assessments, HLD/LLD, contracts, data and deployment models, and ADRs for an approved requirement set. | opus | HIGH | author | writes `docs/architecture/**`, `docs/adrs/**…` |

## UX / design

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`ux-designer`](../agents/ux-designer.md) | Produces personas, journeys, wireframe specifications, design-system usage and the frontend contract for user-facing work. | sonnet | LOW | author | writes `docs/design/**` |

## Engineering

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`backend-developer`](../agents/backend-developer.md) | Implements server-side and integration code plus its tests against an approved story, architecture and technology configuration. | sonnet | MEDIUM | implementer | writes, denied `docs/requirements/**`, `docs/architecture/**…` |
| [`code-reviewer`](../agents/code-reviewer.md) | Reviews correctness, maintainability and adherence to project standards on a diff. | sonnet | MEDIUM | review-readonly | read-only |
| [`development-lead`](../agents/development-lead.md) | Decomposes approved architecture into epics, stories and tasks, assigns implementation work and owns the definition of done. | sonnet | MEDIUM | lead | writes `docs/stories/**`, `docs/qa/**…`; may spawn 7 roles |
| [`frontend-developer`](../agents/frontend-developer.md) | Implements client-side code, state, accessibility and its tests against an approved story, UX contract and technology configuration. | sonnet | MEDIUM | implementer | writes, denied `docs/requirements/**`, `docs/architecture/**…` |

## Data engineering

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`data-engineer`](../agents/data-engineer.md) | Owns schema evolution, migrations, data pipelines and data-quality controls within the approved data platform. | sonnet | HIGH | implementer | writes, denied `docs/requirements/**`, `docs/architecture/**…` |

## QA

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`performance-reviewer`](../agents/performance-reviewer.md) | Reviews changes for latency, throughput, resource and scalability regressions and specifies the performance tests required. | sonnet | MEDIUM | review-readonly | read-only |
| [`qa-engineer`](../agents/qa-engineer.md) | Writes and executes test cases and automation, records defects with reproduction evidence. | sonnet | MEDIUM | implementer | writes `tests/**`, `test/**…` |
| [`qa-lead`](../agents/qa-lead.md) | Owns test strategy, scenario coverage and the risk-to-test mapping. Participates from story definition, not after implementation. | sonnet | MEDIUM | author | writes `docs/test-plans/**`, `docs/qa/**`; may spawn 3 roles |
| [`test-reviewer`](../agents/test-reviewer.md) | Reviews the test suite for coverage of acceptance criteria and risk, assertion quality and flakiness. | sonnet | MEDIUM | review-readonly | read-only |

## Security

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`dependency-reviewer`](../agents/dependency-reviewer.md) | Reviews dependency additions and upgrades for licence, maintenance, vulnerability and transitive risk. | sonnet | MEDIUM | review-readonly | read-only |
| [`security-architect`](../agents/security-architect.md) | Owns threat models, security requirements, control design and security exceptions for a change. | opus | HIGH | author | writes `docs/security/**`, `docs/adrs/**`; may spawn 2 roles |
| [`security-reviewer`](../agents/security-reviewer.md) | Independently reviews changes for vulnerability classes, secret exposure, authz gaps and supply-chain risk. Has authority to block. | opus | HIGH | review-readonly | read-only |

## Platform / DevOps

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`devops-engineer`](../agents/devops-engineer.md) | Implements CI/CD, build, packaging, environment and infrastructure-as-code within the approved platform. | sonnet | HIGH | implementer | writes, denied `docs/requirements/**`, `docs/architecture/**…` |

## Release management

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`release-manager`](../agents/release-manager.md) | Plans releases: change and dependency analysis, migration and rollback plans, validation and post-deployment verification. | sonnet | HIGH | author | writes `docs/release/**`, `CHANGELOG.md` |

## SRE and incident management

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`incident-commander`](../agents/incident-commander.md) | Runs an incident: severity, comms, work assignment, mitigation decisions, and the handoff into RCA. | opus | HIGH | lead | writes `docs/incidents/**`; may spawn 8 roles |
| [`rca-analyst`](../agents/rca-analyst.md) | Produces the post-incident record: timeline, root cause, contributing factors, detection gaps and corrective actions, independent of the responders. | opus | MEDIUM | author | writes `docs/rcas/**`, `docs/incidents/**` |
| [`reliability-reviewer`](../agents/reliability-reviewer.md) | Reviews changes for failure modes, blast radius, rollback safety, idempotency and observability coverage. | sonnet | MEDIUM | review-readonly | read-only |
| [`sre`](../agents/sre.md) | Owns observability, SLOs, runbooks, alert quality and operational readiness; performs read-only production investigation. | sonnet | HIGH | implementer | writes `ops/**`, `observability/**…` |

## Documentation / knowledge

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`docs-writer`](../agents/docs-writer.md) | Maintains the project knowledge base, artifact links and release/reference documentation. | haiku | LOW | author | writes `docs/**`, `README.md…` |

## Engineering communications

| Agent | Purpose | Model | Risk | Tools | Key permissions |
| --- | --- | --- | --- | --- | --- |
| [`notification-agent`](../agents/notification-agent.md) | Turns a routing decision and an event into a readable notification or digest. Formats only: it does not decide what is sent, to whom, or whether anything is sent at all. | sonnet | MEDIUM | author | writes `.ai-engineering/outbox/**`, `docs/communications/**` |
## Spawn hierarchy

Who may bring in whom. Enforced by `hooks/scripts/guard_spawn.py`; the edges
live in `policies/agent-registry.json`.

```
development-lead
  └── backend-developer
  └── frontend-developer
  └── data-engineer
  └── qa-engineer
  └── code-reviewer
  └── test-reviewer
  └── docs-writer
engineering-director
  └── product-manager
  └── requirements-analyst
  └── solution-architect
  └── architecture-reviewer
  └── ux-designer
  └── development-lead
  └── qa-lead
  └── security-architect
  └── devops-engineer
  └── release-manager
  └── sre
  └── incident-commander
  └── docs-writer
incident-commander
  └── sre
  └── backend-developer
  └── frontend-developer
  └── data-engineer
  └── devops-engineer
  └── security-reviewer
  └── rca-analyst
  └── reliability-reviewer
product-manager
  └── requirements-analyst
  └── ux-designer
qa-lead
  └── qa-engineer
  └── test-reviewer
  └── performance-reviewer
security-architect
  └── security-reviewer
  └── dependency-reviewer
```

Every other agent has no spawn authority and escalates instead; the escalation
target is in `policies/role-hierarchy.json`. No agent may spawn a CRITICAL role:
that always requires a human.

## Roles that were deliberately not created

| Considered | Decision |
| --- | --- |
| `senior-backend-developer`, `senior-frontend-developer` | Seniority is a property of the task, not a different job contract. The same role handles both, with model and effort escalation from `policies/model-policy.json`. Two agents differing only in the word 'senior' would be exactly the duplication this catalogue exists to avoid. |
| `integration-engineer` | Integration work has the same authority, inputs and outputs as backend work. Folded into `backend-developer`. |
| `qa-head`, `qa-architect` | `qa-lead` holds the strategy authority and `test-reviewer` provides the independent check. A third QA layer added approval steps without adding a decision. |
| `security-head` | Security's blocking authority is exercised by `security-reviewer`; the head role is a human, named in `GOVERNANCE.md`. |
| `business-analyst` | Overlapped `requirements-analyst` entirely. |
| `chief-architect`, `cto` | Not agents. The escalation targets for AP-02 and AP-03 are humans. |
| A production deployment agent | Deliberately absent. Production deployment is AP-01 and is performed by a human or by CI under human approval. Creating an agent for it would create a CRITICAL actor with no compensating control. |
