# The agent model

## Agent, skill, reviewer or policy?

Most requests for "a new agent" are not agents.

| The need | The right shape |
| --- | --- |
| A durable role with its own authority, inputs, outputs and accountability | **Agent** |
| A capability several roles use | **Skill** |
| An independent check on another role's output | **Reviewer agent**, read-only |
| A rule that must hold regardless of what the model decides | **Hook** |
| A statement of who may do what | **Policy** |

An agent is justified only when a genuine role boundary exists. If two candidate
agents would have the same authority, the same inputs and the same outputs, they
are one agent with two tasks.

## The role contract

Every agent file carries the same thirteen sections, in the same order. The list
lives once, in `policies/agent-registry.json` under `role_contract_sections`, and
is read by both the renderer that writes a definition and the validator that
checks one. It used to exist in four places, and the renderer's copy drifted two
sections out of date — so `scaffold_agent.py`, the documented way to create an
agent, produced files the build rejected.

| Section | What it establishes |
| --- | --- |
| Role contract | Department, reporting line, owner, version, status, risk, tools, write scope, model, evaluation suite, spawn permission |
| Purpose | Why the role exists, in one paragraph |
| Responsibilities | What it must do |
| Not your responsibility | What it must hand off — the section that prevents role creep |
| Authority | What it may decide and what it may block |
| Allowed actions | The operational envelope |
| Forbidden actions | Hard limits, including every human-approval item that applies |
| Required inputs | What must exist before it can work |
| Expected outputs | What it produces, concretely |
| Escalation | Where each kind of blockage goes |
| Review requirements | Who checks its output |
| Handoff | Who receives what |
| Definition of done | The completion test |

Two sections were removed in v0.8.0 and are worth knowing about, because their
absence is deliberate. **Skills** duplicated the frontmatter, which is what
actually preloads them. **Model policy** told the caller how to escalate, in a
file only the callee reads — and a running subagent cannot change its own model.
Every section that remains changes what the agent does.

"You are a backend developer" is not a role definition. It states a persona and
nothing else: no authority, no limits, no inputs, no completion criterion.

## Seniority

There is no `senior-backend-developer`. Seniority is a property of the **task**,
expressed through model and effort escalation in `policies/model-policy.json`:

| Task | Model | Effort |
| --- | --- | --- |
| Mechanical change from a complete specification | sonnet | low |
| Ordinary story implementation | sonnet | medium |
| Complex or novel implementation, HIGH-risk area | opus | high |

The role contract, the authority and the review requirements are identical in all
three cases, which is exactly why a separate agent would add no information.

## Risk classes

Defined in `policies/risk-classification.json`. Risk drives model floor, tool
ceiling, review depth, evaluation depth and whether a human is required.

| Class | Meaning | Consequences |
| --- | --- | --- |
| LOW | Advisory or cosmetic; a wrong result is obvious and cheap | Single automated review, smoke evaluation |
| MEDIUM | Changes behaviour inside a reviewed merge request, reversible | Peer plus routed specialist review, standard evaluation |
| HIGH | Shapes system-wide properties, security, data or production | Independent same-discipline review, full suite with adversarial cases |
| CRITICAL | Can compromise the ability to detect or prevent harm | Two independent reviewers, named human owner, read-only tool ceiling |

CRITICAL agents may not hold write tools. `tests/test_repository.py` enforces it.

## Least privilege

Tool profiles in `policies/tool-permissions.json`:

| Profile | Tools | Used for |
| --- | --- | --- |
| `analysis-readonly` | Read, Grep, Glob, WebFetch, WebSearch | Reviewers who need external references |
| `review-readonly` | Read, Grep, Glob, Bash | Reviewers who need to run diffs and analysers |
| `operator-readonly` | Read, Grep, Glob, Bash, WebFetch | Read-only investigation of running systems and telemetry |
| `author` | Read, Grep, Glob, Edit, Write | Roles that produce documents, never execute |
| `researching-author` | author plus WebFetch, WebSearch | Authoring whose correctness depends on facts outside the repository |
| `implementer` | Read, Grep, Glob, Edit, Write, Bash | Roles that change code and run tests |
| `orchestrator` | Read, Grep, Glob, Bash, Agent | Pure coordination |
| `delegating-author` | author plus Agent | A department lead that authors and delegates, without executing commands |
| `delegating-researcher` | author plus Agent, WebFetch, WebSearch | A department lead that authors, delegates, and must verify facts outside the repository |
| `lead` | orchestrator plus Edit, Write | Coordination that also authors planning artifacts |

Ten profiles, two of which no role currently holds: `orchestrator` and
`operator-readonly`. Every coordinating role turned out to author something as
well, so they hold `lead`, `delegating-author` or `delegating-researcher`
instead; and the roles that investigate production also write or run diffs, so
they hold `implementer` or `review-readonly`. A profile nobody holds grants
nothing. Both stay because `lead` is defined as `orchestrator` plus Edit and
Write, and because the shape they name is what a new role would be measured
against.

Tool lists cannot express *where* a role may write, so `policies/write-scope.json`
adds that, enforced by `hooks/scripts/guard_write.py`:

- **allow mode** for authoring roles: a QA engineer writes tests and nothing else.
- **deny mode** for implementers: a developer writes code but not architecture,
  not the project configuration, and not this plugin.

Two design consequences worth stating:

- **`release-manager` has no `Bash`.** Release authority must not imply execution
  authority. It plans, assembles evidence and asks a human; it cannot deploy.
- **Reviewers have no `Write`.** Independence that depends on the model choosing
  not to edit is not independence.

## Ownership and lifecycle

Every agent has an owner, a version, a risk class, a review frequency and an
evaluation suite, in `policies/agent-registry.json`. Nothing is ownerless.

Lifecycle, from `policies/agent-lifecycle.json`:

```
draft → development → evaluation → security-assessment → pilot → approved → production → deprecated
```

`security-assessment` is mandatory for HIGH and CRITICAL. The transitions into
`pilot`, `approved` and `production` all require a human decision. **A markdown
file existing does not make an agent production-ready** — everything in this
repository is currently at `pilot`.

## Spawn authority

`may_spawn` in the registry, enforced by `hooks/scripts/guard_spawn.py`:

- The main session is human-driven and unconstrained; only agents are limited.
- A role with no `may_spawn` entries cannot delegate and must escalate.
- No agent may spawn a CRITICAL role. That always requires a human.
- Self-spawning is denied: recursive self-delegation hides work rather than
  dividing it.

The guard sees the caller's agent type and the requested type, nothing more. It
cannot verify intent, and it does not see teammate spawning that happens outside
the `Agent` tool. It is a guardrail, not an authorization system, and
`docs/limitations.md` says so plainly.
