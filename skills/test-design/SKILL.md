---
name: test-design
description: Produce a test strategy, scenarios and coverage mapping from requirements, acceptance criteria and architectural risk. Use during story definition, before implementation, so that test design is not biased by the implementation it should be checking.
---

# Test design

Design tests from the requirements, before the code exists. Tests designed after reading the implementation test what the code does, not what it should do.

## Strategy (decide these first)

- **Levels required** — from `.ai-engineering/project.yaml` `testing.required_levels`. Typically unit, integration, contract, end-to-end, plus performance, security and accessibility where relevant.
- **What each level is responsible for.** Overlap is waste; gaps are risk. Write the boundary down.
- **Environments and data** — where each level runs and what data it uses. Production data in a test environment is a security decision, not a convenience.
- **Entry criteria** — what must be true before testing starts.
- **Exit criteria** — what must be true to say testing is done. These gate the release.
- **Automation strategy** — what is automated, at which level, and what stays manual with a stated reason.

## Deriving scenarios

For each acceptance criterion, derive:

1. The **positive** case that demonstrates it.
2. The **boundary** cases: the edges of every stated range, plus empty and maximum.
3. The **negative** cases: invalid input, wrong state, insufficient permission.
4. The **failure** cases: dependency unavailable, slow, or returning bad data.
5. The **concurrency** cases where simultaneous use is possible.

For each architectural risk in the risk register, derive a scenario that would detect it.

For each defect ever found in this area, keep the regression scenario permanently.

## Coverage mapping

Produce the table. It is the deliverable:

| Requirement / criterion | Risk | Scenario id | Level | Automated |
| --- | --- | --- | --- | --- |

Any criterion with no scenario is a gap. Any HIGH risk with no scenario is a gap. State the gaps you are accepting and why — accepted gaps are fine, invisible gaps are not.

## Non-functional testing

- **Performance**: state the baseline, the load profile, and which of load, stress and soak applies. Without a stated target there is nothing to test against; that is a requirements gap.
- **Security**: derive from the threat model, not from a generic checklist.
- **Accessibility**: from the criteria in the UX specification.
- **Resilience**: dependency failure, restart, rollback and degraded operation.

## Anti-patterns

- Scenarios written from the implementation.
- Coverage measured only as a percentage of lines. Line coverage tells you what ran, not what was checked.
- End-to-end tests used to cover logic that a unit test could pin down precisely and quickly.
- "Test everything" strategies, which produce a suite nobody maintains.
- Acceptance criteria too vague to test, accepted anyway. Send them back.
