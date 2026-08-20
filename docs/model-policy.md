# Model policy

## The rule

Role alone never determines the model. **Role default + task risk + reasoning
demand** does.

Hard-coding "Opus for architects, Sonnet for developers, Haiku for testers" is
wrong in both directions: it wastes capability on a routine architecture note and
starves a subtle concurrency defect of the reasoning it needs.

## Two places, deliberately

| Where | What it holds | Changes when |
| --- | --- | --- |
| `agents/*.md` frontmatter and `policies/agent-registry.json` | The role's **default** | The role changes |
| `policies/model-policy.json` | How task properties move off that default | Model economics or capability changes |

Separating them means model routing can be revised on its own release cadence
without touching 29 role definitions.

## Aliases only

Only `opus`, `sonnet`, `haiku`, `fable` and `inherit` appear anywhere. No dated
model identifier is hard-coded, so a model release does not invalidate the
organization. `tests/test_repository.py` enforces this.

## Routing

From `policies/model-policy.json`:

| Risk | Complexity | Model | Effort |
| --- | --- | --- | --- |
| CRITICAL | any | opus | high |
| HIGH | complex or novel | opus | high |
| HIGH | routine | sonnet | high |
| MEDIUM | novel | opus | medium |
| MEDIUM | complex | sonnet | medium |
| MEDIUM | routine | sonnet | low |
| LOW | routine and reversible | haiku | low |
| LOW | otherwise | sonnet | low |

## Always escalated

Regardless of role default:

- Security review of authentication, authorization, cryptography or secret handling.
- Any architecture decision recorded as an ADR.
- Analysis of any irreversible operation: destructive migration, data deletion,
  production change.
- Any evaluation gating promotion of a HIGH or CRITICAL agent.

## De-escalation

Permitted only for LOW-risk, well-specified, reversible work: documentation
formatting and link maintenance, mechanical test scaffolding from an approved
test design, changelog assembly from an existing change list.

## Risk floors

`policies/risk-classification.json` sets a model floor per risk class, and
`tests/test_repository.py` fails if any role's default falls below its floor.
That test found a real defect during development: `dependency-reviewer` was
defaulted to `haiku` on the reasoning that dependency review is mechanical.
It is mechanical, but it is also a security gate, and the MEDIUM floor moved it
to `sonnet`.

## Resolution, executed rather than remembered

```bash
python3 scripts/resolve_model.py --role backend-developer --risk HIGH --complexity novel
python3 scripts/resolve_model.py --workflow WF-FEATURE --stage ARCH
python3 scripts/resolve_model.py --all      # every stage of every workflow
```

The resolver prints its reasoning, so a surprising answer is diagnosable:

```
model: opus   effort: high
  - role default: sonnet (backend-developer)
  - routing rule matched (risk=HIGH, complexity=complex|novel): opus / high
```

Every workflow stage declares `risk` and `complexity`, so routing is resolvable
for the whole lifecycle without anyone deciding case by case.
`tests/test_repository.py` asserts it resolves for every stage.

## Override layers

Highest priority first, each settable only by the authority named:

| Layer | Set by | Effect |
| --- | --- | --- |
| Organization allowlist | Administrator, via `availableModels` | A blocked value is substituted by Claude Code. A role that must run on opus in a restricted environment needs that verified, not assumed. |
| Per-invocation | The delegating agent or the operator | The escalation mechanism. Always permitted upward. |
| Project | `.ai-engineering/project.yaml` under `ai.model_overrides` | May raise a role. May lower it only where the risk floor permits. |
| Stage | The workflow stage's risk and complexity | Resolved through the routing table. |
| Role default | `policies/agent-registry.json` | The floor when nothing else applies. |

A project override below the risk floor is **refused**, and the refusal appears
in the trace:

```
  - project override to haiku REFUSED: below the opus floor
```

## Operational notes

- **Effort is set in the agent's frontmatter.** Claude Code validates `effort` on
  plugin agent files against `low`, `medium`, `high`, `xhigh`, `max` or an integer.
  What it does *not* honour on a plugin agent is `permissionMode`, `hooks` and
  `mcpServers` — it warns and ignores those three, so this plugin never sets them.
  `skills`, `model`, `tools` and `effort` all apply.
- **`fable`:** accepted, never selected by the routing table. It is there for a project override on a role where speed matters more than depth, and ranks with `sonnet`, so it cannot be used to slip under a HIGH or CRITICAL floor.
- **Agent teams:** a teammate's model is fixed at spawn. The lead must apply this
  policy when spawning, because it cannot correct the choice afterwards.
- **`CLAUDE_CODE_SUBAGENT_MODEL`** overrides frontmatter for every subagent. Do
  not set it organization-wide; it defeats the whole policy.
- **Organization allowlists:** if `availableModels` blocks a value, Claude Code
  substitutes. A role that must run on `opus` in a restricted environment needs
  that verified rather than assumed.
