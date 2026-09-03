# Skill catalogue

43 skills. A skill is a capability many roles share; it is not an organizational
role and does not have authority of its own. The rule for choosing between them
is in `docs/agent-model.md`.

Skills load only when used, so depth costs nothing until it is needed. Where a
skill would grow long, the detail belongs in a `reference.md` beside its
`SKILL.md` rather than in the body.

Risk here is the consequence of the skill being followed badly: a HIGH-risk skill
guides work that can damage production, data or the security boundary.

| Skill | Purpose | Preloaded by | Risk |
| --- | --- | --- | --- |
| [`adr-management`](../skills/adr-management/SKILL.md) | Write, number, supersede and index architecture decision records. | `solution-architect`, `architecture-reviewer`, `agent-architect` | LOW |
| [`agent-development`](../skills/agent-development/SKILL.md) | Author and maintain the components of the AI Engineering OS itself - agents, skills, hooks, policies and schemas. | `agent-architect`, `agent-developer` | HIGH |
| [`agent-evaluation`](../skills/agent-evaluation/SKILL.md) | Design, run and interpret evaluation suites for agents, skills and hooks, including adversarial cases. | `ai-governance`, `agent-developer`, `agent-evaluator` | MEDIUM |
| [`ai-governance`](../skills/ai-governance/SKILL.md) | Review a change to the AI Engineering OS against the governance rules - ownership, least privilege, evaluation coverage, risk classification, lifecycle state and approval paths. | `ai-governance`, `agent-architect`, `agent-evaluator` | HIGH |
| [`agent-tool-design`](../skills/agent-tool-design/SKILL.md) | Design the tools an AI agent is given - the interface, the description, the error messages and the authority - understanding that the description is a prompt and the caller cannot be trusted to call correctly. | `security-reviewer`, `solution-architect` | HIGH |
| [`ai-evaluation`](../skills/ai-evaluation/SKILL.md) | Measure whether the AI system this project is building actually works - datasets, baselines, candidates, metrics and regression. | `qa-engineer`, `qa-lead`, `test-reviewer` | MEDIUM |
| [`ai-observability`](../skills/ai-observability/SKILL.md) | See what an AI system did in production - tracing model and tool calls, cost and token metrics, quality signals, drift, and what may be logged given the data classification. | `devops-engineer`, `reliability-reviewer`, `sre` | MEDIUM |
| [`ai-system-design`](../skills/ai-system-design/SKILL.md) | Design a system whose behaviour comes from a model rather than from code you wrote. | `architecture-reviewer`, `solution-architect` | HIGH |
| [`llm-integration`](../skills/llm-integration/SKILL.md) | Implement the code that calls a model - structured output, retries, timeouts, token budgets, streaming, idempotency and cost control. | `backend-developer`, `code-reviewer` | MEDIUM |
| [`prompt-engineering`](../skills/prompt-engineering/SKILL.md) | Write, version, review and change the prompts that define an AI system's behaviour, treating a prompt as a reviewed artifact rather than a string in a file. | `backend-developer`, `solution-architect` | MEDIUM |
| [`rag-engineering`](../skills/rag-engineering/SKILL.md) | Design and evaluate retrieval-augmented generation - what gets indexed, how it is chunked, how it is retrieved, and how retrieval quality is measured separately from answer quality. | `backend-developer`, `data-engineer` | HIGH |
| [`api-design`](../skills/api-design/SKILL.md) | Design and review interface contracts - REST, GraphQL, gRPC, events or file-based protocols - including versioning, compatibility, errors and pagination. | `solution-architect` | MEDIUM |
| [`architecture-design`](../skills/architecture-design/SKILL.md) | Produce feasibility assessments, high- and low-level design, deployment, availability and capacity models for an approved requirement set. | `solution-architect`, `security-architect`, `agent-architect` | MEDIUM |
| [`architecture-review`](../skills/architecture-review/SKILL.md) | Independently review an architecture, design or ADR for requirement coverage, non-functional fitness, consistency, failure handling and proportionality. | `architecture-reviewer` | MEDIUM |
| [`backend-development`](../skills/backend-development/SKILL.md) | Implement server-side, service and integration code against an approved story, architecture and technology configuration. | `backend-developer` | MEDIUM |
| [`ci-cd`](../skills/ci-cd/SKILL.md) | Design and maintain pipelines, build reproducibility, artifact traceability and deployment mechanics. | `devops-engineer` | HIGH |
| [`change-review`](../skills/change-review/SKILL.md) | Review a diff for correctness, maintainability and standards adherence, and route it to the specialist reviewers the change actually needs. | `development-lead`, `backend-developer`, `frontend-developer`, `data-engineer`, `security-reviewer`, `agent-developer`, `code-reviewer`, `performance-reviewer`, `reliability-reviewer`, `dependency-reviewer`, `test-reviewer` | MEDIUM |
| [`database-design`](../skills/database-design/SKILL.md) | Design schemas, indexes, migrations and data lifecycle within the project's approved data platform. | `solution-architect`, `data-engineer`, `performance-reviewer` | HIGH |
| [`frontend-development`](../skills/frontend-development/SKILL.md) | Implement client-side code, state, accessibility and tests against an approved story and UX contract. | `frontend-developer` | MEDIUM |
| [`engineering-notifications`](../skills/engineering-notifications/SKILL.md) | Turn an SDLC event into a notification a person will read, and build the daily and weekly engineering digests. | `notification-agent` | MEDIUM |
| [`delegated-execution`](../skills/delegated-execution/SKILL.md) | Decide which model does a piece of work and delegate the rest, rather than doing everything at the top tier. Human-invoked; it governs the session driving the repository, not an organizational role. | human-invoked | LOW |
| [`engineering-simplicity`](../skills/engineering-simplicity/SKILL.md) | Choose the simplest solution that satisfies every stated requirement, and justify complexity when it is genuinely needed. | `solution-architect`, `architecture-reviewer`, `requirements-analyst`, `product-manager`, `development-lead`, `backend-developer`, `frontend-developer`, `data-engineer`, `devops-engineer`, `sre`, `qa-lead`, `release-manager`, `performance-reviewer`, `code-reviewer`, `dependency-reviewer` | MEDIUM |
| [`git-workflow`](../skills/git-workflow/SKILL.md) | Branch, commit and manage history according to the organization's branching policy and the project's overrides. | `backend-developer`, `frontend-developer`, `data-engineer`, `qa-engineer`, `devops-engineer`, `agent-developer` | MEDIUM |
| [`gitlab-workflow`](../skills/gitlab-workflow/SKILL.md) | Work with GitLab merge requests, issues, pipelines and releases using features available in GitLab CE. | `backend-developer`, `frontend-developer`, `data-engineer` | MEDIUM |
| [`incident-management`](../skills/incident-management/SKILL.md) | Run a production incident - severity, coordination, parallel investigation, mitigation under approval, recovery verification and handoff to RCA. | `sre`, `incident-commander`, `rca-analyst`, `reliability-reviewer` | HIGH |
| [`kubernetes-basics`](../skills/kubernetes-basics/SKILL.md) | Work safely with Kubernetes for projects whose deployment platform is Kubernetes - workload configuration, health, resources, rollout and safe read-only investigation. | `devops-engineer`, `sre` | HIGH |
| [`observability`](../skills/observability/SKILL.md) | Design SLIs, SLOs, metrics, logs, traces, alerts and runbooks, and assess whether a change is observable in production. | `devops-engineer`, `sre`, `incident-commander`, `reliability-reviewer` | MEDIUM |
| [`performance-engineering`](../skills/performance-engineering/SKILL.md) | Establish baselines, design load, stress and soak tests, analyse capacity and find performance regressions. | `performance-reviewer` | MEDIUM |
| [`project-onboarding`](../skills/project-onboarding/SKILL.md) | Bring a project under the AI Engineering OS by producing a human-approved .ai-engineering/project.yaml. | invoked on demand | MEDIUM |
| [`release-management`](../skills/release-management/SKILL.md) | Plan a release - change analysis, dependency ordering, migration and rollback plans, validation, approval evidence, release notes and post-deployment verification. | `release-manager` | HIGH |
| [`requirements-engineering`](../skills/requirements-engineering/SKILL.md) | Elicit, structure and quantify requirements into a PRD and testable acceptance criteria with traceability identifiers. | `product-manager`, `requirements-analyst`, `ux-designer` | MEDIUM |
| [`root-cause-analysis`](../skills/root-cause-analysis/SKILL.md) | Produce a post-incident analysis - timeline, root cause, contributing factors, detection gaps and typed corrective actions. | `incident-commander`, `rca-analyst` | MEDIUM |
| [`sdlc-navigator`](../skills/sdlc-navigator/SKILL.md) | Place a piece of work in the software lifecycle and decide what happens next. | `engineering-director` | LOW |
| [`security-assessment`](../skills/security-assessment/SKILL.md) | Review a change for vulnerability classes, secret exposure, authorization gaps and supply-chain risk, with severity and an exploitation path per finding. | `security-architect`, `security-reviewer`, `dependency-reviewer` | HIGH |
| [`story-decomposition`](../skills/story-decomposition/SKILL.md) | Break approved architecture and requirements into epics, stories and tasks that can be implemented independently and verified objectively. | `development-lead`, `ux-designer` | LOW |
| [`task-synthesis`](../skills/task-synthesis/SKILL.md) | Decompose one stage of a work item into the several concrete tasks it actually is, as a proposal the organization validates and grafts into the task graph. | `development-lead`, `solution-architect`, `qa-lead` | LOW |
| [`team-patterns`](../skills/team-patterns/SKILL.md) | Choose between a single agent, subagents and an agent team, and spawn the right team with the right context. | `engineering-director` | LOW |
| [`technology-selection`](../skills/technology-selection/SKILL.md) | Run a structured technology decision when the approved stack does not cover a need. | `solution-architect` | MEDIUM |
| [`test-automation`](../skills/test-automation/SKILL.md) | Implement reliable automated tests from an approved test design, and diagnose flaky or low-value tests. | `qa-lead`, `qa-engineer`, `test-reviewer` | MEDIUM |
| [`test-design`](../skills/test-design/SKILL.md) | Produce a test strategy, scenarios and coverage mapping from requirements, acceptance criteria and architectural risk. | `qa-lead`, `qa-engineer`, `test-reviewer` | MEDIUM |
| [`threat-modeling`](../skills/threat-modeling/SKILL.md) | Build or update a threat model for a system or change - assets, trust boundaries, entry points, threats and controls. | `security-architect`, `security-reviewer` | HIGH |
| [`work-item`](../skills/work-item/SKILL.md) | Open, plan and drive a unit of work through the control loop: what to do next, how to record what happened, and what the loop does with it. | `engineering-director`, `development-lead` | LOW |
| [`traceability`](../skills/traceability/SKILL.md) | Assign artifact identifiers and maintain the links between requirements, stories, architecture, ADRs, tests, defects, merge requests, releases, incidents and RCAs. | `engineering-director`, `product-manager`, `requirements-analyst`, `development-lead`, `backend-developer`, `frontend-developer`, `data-engineer`, `docs-writer`, `qa-lead`, `release-manager`, `rca-analyst`, `code-reviewer` | LOW |

## AI product engineering

Seven of the skills above are for building software whose behaviour comes from a
model. They are **capabilities, not roles** — the agent set is still frozen at 30,
and the brief that asked for them said so explicitly. A backend developer
implementing an LLM feature is still `backend-developer`; it just loads
`llm-integration` while doing it.

| Role | + capability | Produces |
| --- | --- | --- |
| `solution-architect` | `ai-system-design` | A design that says what happens when the model is wrong |
| `backend-developer` | `llm-integration` | Client code that validates what came back |
| `solution-architect`, `backend-developer` | `prompt-engineering` | A prompt that is versioned, reviewed and evaluated |
| `backend-developer`, `data-engineer` | `rag-engineering` | Retrieval measured separately from generation |
| `solution-architect`, `security-reviewer` | `agent-tool-design` | Tools whose descriptions are prompts and whose authority is bounded |
| `qa-lead`, `qa-engineer`, `test-reviewer` | `ai-evaluation` | A dataset, a baseline and a candidate |
| `sre`, `devops-engineer`, `reliability-reviewer` | `ai-observability` | Traces that name the prompt, model and index versions |

They are **technology-neutral in the same sense as the rest of the plugin**: none
of them names a provider, an SDK or a model. The provider is a project decision
recorded under AP-03 in `.ai-engineering/project.yaml`, in the new `ai_system`
section — which is separate from `ai`, and the distinction matters: `ai` is how
this OS runs the project's roles, `ai_system` is what the project's own software
uses a model for. Before that section existed a project had no way to say it was
building an AI system at all.

Two of them sit next to a skill with a similar name, and the difference is the
subject rather than the technique:

- **`ai-evaluation` is not `agent-evaluation`.** The first evaluates the product
  the organization is building; the second evaluates this organization's own
  roles. Mixing them produces a suite that measures neither.
- **`ai-observability` is not `observability`.** SLIs, SLOs, alerts and runbooks
  all still apply; what is additionally true is that latency and error rate can
  both be green while the answers are confidently wrong.

Three capabilities the brief listed as possible were **not** built:
`model-routing`, `ai-performance` and `ai-data-engineering`. Nothing in the
current requirement set needs them, and adding a capability against an expected
need rather than a stated one is the finding
`${CLAUDE_PLUGIN_ROOT}/policies/simplicity-policy.json` exists to raise. They are
recorded here so the omission is a decision rather than an oversight.

## Invoking a skill

Every skill is invocable as `/ai-engineering-os:<name>`, and Claude also loads
one automatically when its description matches the task. Agents that name a
skill in their frontmatter get it preloaded when they run as a subagent.

**Caveat for agent teams:** Claude Code does not apply the `skills` frontmatter
field when an agent definition runs as a teammate. A teammate must invoke the
skills it needs explicitly, which is why every spawn prompt in
`skills/team-patterns/SKILL.md` says so.

## Technology skills

The original design listed per-technology skills (`python`, `react`, `postgresql`
and so on). None are shipped, deliberately: baking a technology into the company
layer contradicts technology neutrality, and a project's own conventions live in
its `CLAUDE.md` and `.ai-engineering/project.yaml` where a human approved them.

`kubernetes-basics` is the single exception and says so in its own description:
it applies only when the project declares Kubernetes as its deployment platform.

A project that wants a technology-specific skill adds it to its own
`.claude/skills/`, or the organization adds it in a separate plugin that depends
on this one.
