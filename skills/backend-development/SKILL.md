---
name: backend-development
description: Implement server-side, service and integration code against an approved story, architecture and technology configuration. Use for backend implementation and defect fixes. Technology-neutral - the approved stack comes from the project configuration, never from this skill.
---

# Backend development

Implement the story that exists, in the stack that is approved, and prove it with tests.

## Before writing code

1. Read the story, its acceptance criteria and its definition of done.
2. Read the architecture for the components you are touching, and the API contracts.
3. Read `.ai-engineering/project.yaml` for the approved stack, coding standards and testing requirements.
4. Read the surrounding code. Match its conventions; a change that is idiomatic elsewhere and alien here is a maintenance cost.
5. For anything beyond a trivial change, write the implementation plan first: files to change, order, risks, and how you will verify.

## While writing code

- Implement the acceptance criteria and nothing else. Unrequested improvements are a separate change.
- No interface for one implementation, no configuration for a value that is the same in every environment, no framework inside a feature. Each of those becomes right when the second implementation, the second value or the second consumer actually exists; say that, rather than building it early.
- Reach for the standard library and the already-approved dependencies before adding one. A new dependency needs a statement of what the existing ones fail to do.
- Delete what this change makes dead. Removal is the cheapest simplification available and the one most often skipped.
- Handle the failure paths as deliberately as the happy path: invalid input, absent dependency, slow dependency, partial write, concurrent access.
- Make retryable operations idempotent. Anything reachable by a retry, a redelivery or a duplicate request will eventually be called twice.
- Bound everything: query results, batch sizes, concurrency, memory, retries. Unbounded is a production incident with a delay fuse.
- Set timeouts explicitly on every outbound call. A default of "wait forever" is the most common cause of cascading failure.
- Never log secrets, credentials, tokens or personal data. Log identifiers, not payloads.
- Return errors that a caller can act on, and preserve the cause when wrapping.
- Configuration comes from the environment; secrets come from the secret manager. Neither belongs in the repository.

## Tests

Write tests that would fail if the behaviour regressed. Cover the acceptance criteria, the boundaries and the failure paths. A test that only asserts a mock was called proves nothing about the system.

Run the project's full local gate before opening the merge request: tests, lint, type checks, static analysis.

## Git and merge request

Follow `git-workflow` and `gitlab-workflow`. Branch, commit with traceability identifiers, push the branch, open a merge request describing what changed, why, the risk and how it was verified.

## Escalate rather than improvise

- An acceptance criterion that cannot be met within the design → `development-lead`, then `solution-architect`.
- A need for a technology outside the approved stack → technology decision (AP-03).
- A destructive migration → `data-engineer` and human approval (AP-05).
- A security-relevant discovery → `security-reviewer`, immediately, before the merge request.

## Never

- Weaken or delete a test to make a build pass.
- Disable a lint, type or security check instead of fixing the cause.
- Commit or push to a protected branch.
- Approve your own change.
- Bundle unrelated changes into one merge request.
