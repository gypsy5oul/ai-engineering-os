---
name: adr-management
description: Write, number, supersede and index architecture decision records. Use whenever a decision constrains future work - technology, structure, protocol, data ownership, security control or process. Use also when discovering that a decision was made implicitly and never recorded.
---

# ADR management

An ADR records a decision **and its consequences** at the moment it was made, so that a future reader can tell whether the reasons still hold.

## When a decision needs an ADR

Record it if changing the decision later would require changing code in more than one place, or would require a migration, or would need a discussion. Specifically:

- Technology selection or removal.
- Component boundaries and ownership.
- Protocol, contract or serialisation choice.
- Data model ownership and consistency approach.
- Authentication, authorization or secret-handling approach.
- Consciously accepted technical debt.
- A significant "we deliberately did not do X".

Not everything is an ADR. A naming convention is a standard; a library choice inside an already-approved ecosystem is a dependency review.

## Format

```
---
id: <KEY>-ADR-001
type: adr
title: Use <decision> for <problem>
status: proposed | accepted | superseded | rejected
owner: <role or human>
created: YYYY-MM-DD
links:
  requirements: [<KEY>-REQ-012]
  architecture: [<KEY>-ARCH-003]
---

## Context
The forces at play: requirements, constraints, existing decisions, and what
specifically triggered this decision now.

## Options considered
For each: what it is, and its material advantages and disadvantages *for this
context*. Include the do-nothing option.

## Decision
What was decided, stated so plainly that an implementer needs nothing else.

## Consequences
What becomes easier. What becomes harder. What is now expensive to change.
What we will have to live with. What we will need to revisit, and when.

## Compliance
How a reviewer can tell whether code follows this decision.
```

## Numbering and supersession

- Sequential per project: `<KEY>-ADR-001`, never reused, never renumbered.
- A reversed decision does not get edited. Write a new ADR, set the old one to `superseded`, and set `supersedes` on the new one. The history is the value.
- Index every ADR in `docs/adrs/README.md` with id, title, status and date.

## Rules

- Write the ADR when the decision is made, not at the end of the project. An ADR written afterwards records a rationalisation.
- Consequences must include the negative ones. An ADR with no downsides is not a decision, it is an advertisement.
- An ADR is proposed by the architect and accepted by a human for anything classed AP-02 or AP-03.
- If you find an undocumented decision constraining current work, write the ADR retroactively and mark it clearly as reconstructed.
