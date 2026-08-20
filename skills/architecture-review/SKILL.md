---
name: architecture-review
description: Independently review an architecture, design or ADR for requirement coverage, non-functional fitness, consistency, failure handling and proportionality. Use before implementation begins on any structural change. Never used by the agent that authored the design.
---

# Architecture review

Review is a coverage exercise, not an opinion exercise. Work through the checklist and produce evidence.

## 1. Requirement coverage (do this first)

Build the table before forming any opinion:

| Requirement ID | Addressed by | Verdict |
| --- | --- | --- |

Any requirement with no component that satisfies it is a **critical** finding. Any component with no requirement behind it is a **major** finding: it is unrequested complexity.

## 2. Non-functional fitness

For each quantified NFR, name the mechanism that meets it and check the arithmetic. "Redis handles the load" is not a mechanism; "single-node Redis at 50k ops/s against a stated peak of 8k ops/s" is.

Where an NFR is unquantified, the finding belongs to requirements, not design — but it still blocks.

## 3. Consistency

- Does it contradict an existing ADR? If it supersedes one, is the supersession recorded?
- Does it use a technology outside `.ai-engineering/project.yaml`?
- Does it duplicate a capability the system already has?
- Are the terms used the same as elsewhere in the system, or has a synonym been introduced?

## 4. Failure behaviour

For each dependency and boundary: slow, unavailable, wrong data, duplicated message, partial write. If the design does not answer, that is the finding.

Also: blast radius, isolation, backpressure, retry safety, idempotency, and what the system does when it is degraded rather than down.

## 5. Data

Ownership, consistency model, migration and compatibility strategy, retention, deletion, and what happens to in-flight data during deployment.

## 6. Proportionality

Ask what the design would look like at half the complexity, and whether a stated requirement would actually fail. If nothing would fail, the extra complexity is a finding.

## 7. Decisions

Every significant choice has an ADR with real alternatives. An ADR whose alternatives are obviously straw arguments is a finding: the decision was made elsewhere and justified afterwards.

## Output

Findings, each with: severity (critical / major / minor), the location, the requirement or principle it relates to, and what would resolve it. Then the requirement-coverage table. Then one verdict: **approve**, **approve with conditions** (list them), or **reject** (list what must change).

## Rules

- Do not redesign. Report what is wrong and let the architect decide how to fix it.
- Do not approve on impression. If you did not build the coverage table, you did not review.
- Findings must be resolvable. "Consider scalability" is not a finding.
- Disagreement that survives one round goes to the human architecture owner with both positions stated.
