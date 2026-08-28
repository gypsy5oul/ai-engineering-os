---
id: <KEY>-ADR-000
type: adr
title: <Decision, stated as a decision>
status: proposed         # proposed | accepted | superseded | rejected
owner: solution-architect
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the requirement, incident or constraint that forced this decision>
reviewers: []            # architecture-reviewer verdict goes here
approvals: []            # AP-02 or AP-03, recorded by a named human
dependencies: []
links:
  requirements: []
  architecture: []
---

## Context

The forces: requirements, constraints, existing decisions, and what triggered
this decision now.

## Options considered

### Option 1 — <name>
What it is. Advantages **in this context**. Disadvantages **in this context**.

### Option 2 — <name>

### Option 3 — Do nothing / use what is already approved
Always present. Often correct. It loses only to a named requirement, with its
identifier and its number — not to popularity, flexibility or expected growth.

## Simplicity

The simplest option that satisfies every stated requirement, and the stated
requirement the chosen option needed that the simpler one misses. Delete this
section only if the decision introduces no component, dependency, abstraction or
boundary at all.

| | |
| --- | --- |
| Simplest viable alternative | <named concretely enough to have been built> |
| Requirement it fails | <identifier and number, or "none — this decision is the simpler option"> |
| Evidence | requirement / measurement / constraint, and where it can be read |
| Operational cost accepted | <what must now be run, monitored, patched and carried on-call> |
| Reversible | <what undoing this takes, and at what cost> |

## Decision

<Stated plainly enough that an implementer needs nothing else.>

## Consequences

**Easier:**

**Harder:**

**Now expensive to change:**

**To revisit when:** <the condition that would reopen this>

## Compliance

How a reviewer can tell whether code follows this decision.
