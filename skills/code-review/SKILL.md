---
name: code-review
description: Review a diff for correctness, maintainability and standards adherence, and route it to the specialist reviewers the change actually needs. Use on every code change, and when deciding which reviews a change requires.
---

# Code review

Two jobs: route the change to the reviewers it needs, and review the dimension you own.

## Routing

Read `${CLAUDE_PLUGIN_ROOT}/policies/review-routing.json`. Match the change against the signals and take the union of the routed reviewers. The common cases:

| Change | Reviewers |
| --- | --- |
| Documentation only | `docs-writer`, advisory |
| Ordinary source change | `code-reviewer`, `test-reviewer` |
| Contract or schema change | + `architecture-reviewer` |
| Auth, crypto, input handling, secrets | + `security-reviewer` |
| Dependency manifest change | + `dependency-reviewer`, `security-reviewer` |
| Database migration | + `data-engineer`, `architecture-reviewer` |
| Hot path, query pattern, concurrency, caching | + `performance-reviewer` |
| Retry, timeout, failover, health, idempotency | + `reliability-reviewer` |
| CI, container, infrastructure, deployment | + `devops-engineer`, `security-reviewer` |
| This plugin's own components | + `agent-evaluator`, `ai-governance`, `security-reviewer` |

Requiring every reviewer on every change is how review becomes a formality. Route deliberately.

## Reviewing correctness

Start by stating, in your own words, what the change is for. If you cannot, you are not ready to review it.

Then look for the defects tests do not catch:

- **Boundaries**: empty, one, maximum, off-by-one, overflow, unicode, timezone, leap and negative cases.
- **Absent values**: null, missing key, absent optional, default that is wrong for this context.
- **Error paths**: swallowed exceptions, errors that lose the cause, cleanup that does not run, failure that leaves partial state.
- **Concurrency**: shared mutable state, check-then-act races, non-atomic updates, lock ordering, assumptions of single-threaded execution.
- **Resources**: connections, files, handles and goroutines/tasks that are not released on the failure path.
- **Assumptions about input**: trusting order, uniqueness, size or format that nothing guarantees.
- **Behaviour changes that are not in the story**: silent scope creep is a finding.

## Reviewing maintainability

- Does the code say what it does? Names carrying the wrong meaning are worse than long names.
- Is the abstraction earning its keep, or is it indirection for its own sake?
- Is duplication being introduced that will drift?
- Would the next reader need context that is not written down?

## Reviewing tests

Would each test fail if the behaviour regressed? Are the failure paths tested? Is the new behaviour tested at the right level? Detailed coverage review belongs to `test-reviewer`; the basic question belongs to everyone.

## Findings

Each finding: severity, location, the concrete failure it causes, and what would resolve it. "Consider refactoring" is not a finding. Separate **blocking** from **suggestion** explicitly, and do not hold a change hostage to a preference.

## Rules

- Read every changed file. A skim is not a review.
- Never review your own change.
- Approve or reject explicitly. Silence is not a verdict.
- A security-relevant finding goes to `security-reviewer` immediately rather than waiting for the review to finish.
