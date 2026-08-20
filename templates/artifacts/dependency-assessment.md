---
id: <KEY>-DEPA-000
type: dependency-assessment
title: <dependency> <from-version> to <to-version>
status: draft
owner: dependency-reviewer
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <advisory id, end-of-life notice, or the reason for the upgrade>
reviewers: []            # security-reviewer verdict
approvals: []            # AP-04 where an exception is accepted, AP-03 for new capability
dependencies: []
links:
  merge_requests: []
---

## Route

One of: `routine-upgrade` | `security-vulnerability` | `end-of-life` |
`licence-compliance` | `new-capability`.

**Chosen route:** <route>  
**Why:** <what made this route the right one>

`new-capability` leaves WF-DEPENDENCY entirely: it is a technology decision.

## Urgency

Justified by exploitability in **this** deployment, or by a support end date.
A CVSS score alone is not a justification.

| Factor | Finding |
| --- | --- |
| Reachable in this deployment | |
| Exploitable without authentication | |
| Support ends | |
| Upgrade window | |

## Assessment

| Dimension | Finding |
| --- | --- |
| Vulnerability status | |
| Licence compatibility | |
| Maintenance signal | |
| Transitive effect | |

## Impact

| Kind | Detail |
| --- | --- |
| Breaking API changes | |
| **Behaviour changes** | <the ones that break nothing at compile time> |
| Affected call sites | |

## Decision

Proceed / proceed with an exception / replace / remove.
