---
name: requirements-engineering
description: Elicit, structure and quantify requirements into a PRD and testable acceptance criteria with traceability identifiers. Use when starting a capability, when requirements are vague or contradictory, or when a downstream role reports that a requirement is untestable. Asks questions rather than inventing business intent.
---

# Requirements engineering

A requirement that cannot fail a test is not a requirement.

## Structure to produce

1. **Business objective** — what changes for the business, and the measure that proves it.
2. **Scope** and **out of scope** — both written down. Out of scope is where most disputes are prevented.
3. **Functional requirements** — identified, one behaviour each.
4. **Non-functional requirements** — quantified. See the table below.
5. **Acceptance criteria** — per requirement, in Given/When/Then or an equivalent testable form.
6. **Constraints** — regulatory, contractual, technical, timeline, budget.
7. **Dependencies** — on teams, systems, data, decisions.
8. **Assumptions** — things believed but unconfirmed, each with who can confirm it.
9. **Risks** — with likelihood, impact and a proposed response.
10. **Open questions** — addressed to a named human, each blocking or non-blocking.
11. **User journeys** — for anything a person interacts with.

## Non-functional dimensions to quantify

| Dimension | The question that must have a number |
| --- | --- |
| Availability | What uptime, measured over what window? |
| Latency | What percentile, at what value, under what load? |
| Throughput | How many operations per unit time, at peak? |
| Capacity | How much data, how many users, growing at what rate? |
| Durability / RPO | How much data may be lost in a disaster? |
| Recovery / RTO | How long may recovery take? |
| Retention | How long is data kept, and what happens then? |
| Security | Which controls are obligations rather than preferences? |
| Compliance | Which regime, which clauses? |
| Accessibility | Which standard, at which level? |
| Observability | What must be measurable in production? |

For each, either write the number the human gave you, or write an open question. **Never write a plausible default.** "99.9%" invented by an agent becomes an architecture constraint nobody chose.

## Identifiers

Use `<PROJECT-KEY>-REQ-nnn` for functional, `<PROJECT-KEY>-NFR-nnn` for non-functional. The key comes from `.ai-engineering/project.yaml` under `project.key`. Every downstream artifact references these; see the `traceability` skill.

## Elicitation questions that surface the most

- What happens today, and what specifically is wrong with it?
- Who is affected, and how would they notice this was delivered?
- What must **not** change?
- What is the worst realistic failure, and who feels it?
- What volume and growth should this handle?
- What is explicitly out of scope for this round?
- What has been tried before, and why did it not stick?

## Anti-patterns

- Unverifiable adjectives: fast, secure, robust, scalable, user-friendly. Replace each with a number or a named standard.
- Solution language in a requirement ("use a message queue"). That is a design decision; record it as a constraint if a human mandated it, otherwise remove it.
- Silently resolving a contradiction between two stated requirements. Name both, ask which wins.
- Bundling several behaviours into one requirement so it cannot be tested or partially delivered.

## Review

The PRD is reviewed by the requester for intent, by `solution-architect` for feasibility and by `qa-lead` for testability. Requirements enter architecture only after that review.
