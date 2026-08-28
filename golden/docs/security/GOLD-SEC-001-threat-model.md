---
id: GOLD-SEC-001
type: threat-model
title: Retention Window Service threat model
status: approved
owner: security-architect
version: 1
created_at: 2026-08-28
updated_at: 2026-08-28
source: GOLD-ARCH-001
reviewers: []
approvals: []
dependencies: []
links:
  architecture: [GOLD-ARCH-001]
---

## Scope

One deployable. Records in on stdin, decisions out on stdout. No network listener,
no datastore, no credentials, no persistence of its own.

## Assets

| Asset | Why it matters |
| --- | --- |
| The retention decision | A wrong `deletable` decision destroys a record the organization is obliged to keep |
| The record set in transit | Contains the identifiers and dates of confidential records |

## Trust boundaries

One: the process boundary. The caller is trusted to supply the record set and the
policy; the service is trusted to decide. There is no second boundary because
there is no second component — see `policies/simplicity-policy.json`.

## Threats and controls

| Threat | Control |
| --- | --- |
| A record is reported deletable inside its window | The window comparison is inclusive of the boundary date and is unit-tested at the boundary |
| A record under legal hold is reported deletable | Hold is checked before age, and short-circuits. Tested with an expired record under hold |
| A malformed record is silently treated as deletable | An unparseable record raises rather than defaulting; there is no permissive fallback |
| The decision cannot be explained afterwards | Every decision carries the rule that produced it |

## Out of scope, and why

Authentication, authorization, transport security and secret handling. The
service holds no secret, opens no socket and has no caller it can distinguish. A
control for any of these would be a control over nothing.

## Residual risk

The caller can supply a policy with a zero-day retention window. That is a
caller-side decision the service cannot second-guess, and it is recorded here
rather than defended against.
