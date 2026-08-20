---
id: <KEY>-STORY-000
type: story
title: <One behaviour change>
status: draft            # draft | in-review | approved | done
owner: development-lead
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the requirement this decomposes>
reviewers: []            # qa-lead testability verdict
approvals: []
dependencies: []         # story ids that must land first
links:
  requirements: []
  architecture: []
  adrs: []
  tests: []
---

## Business context

Why, linked to the requirement.

## Technical context

Components, contracts and architecture references involved.

## Owned paths

Files or modules this story may modify. Two parallel stories must not overlap here.

## Acceptance criteria

- <derived from the requirement, not invented here>

## Non-functional requirements

## Dependencies

| Depends on | Why |
| --- | --- |

## Test expectations

| Level | What it must cover |
| --- | --- |

## Definition of done

- Acceptance criteria met and demonstrated by tests
- Required test levels pass
- Lint, type checks and static analysis pass
- Routed reviews complete with no unresolved HIGH finding
- Documentation updated where behaviour changed
- Traceability identifiers in commits and the merge request
