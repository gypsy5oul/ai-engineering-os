---
id: <KEY>-RCA-000
type: rca
title: <Incident, in user-visible terms>
status: draft
owner: rca-analyst
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the incident id>
reviewers: []            # engineering-director verdict
approvals: []            # engineering owner acceptance
dependencies: []
links:
  incidents: []
  defects: []
  requirements: []
---

## Summary

What users experienced, for how long, and how many were affected.

## Timeline

| Time (UTC) | Event | Source | Observed / inferred |
| --- | --- | --- | --- |

## Trigger

What made it start now.

## Root cause

The systemic condition that made it possible. **"Human error" is not a root
cause** — the finding is why a single action could cause this, why nothing
caught it, and why it was not reversible.

## Contributing factors

## Detection gaps

| Stage | Could it have been caught? | Why it was not |
| --- | --- | --- |
| Requirements | | |
| Architecture | | |
| Review | | |
| Test | | |
| CI | | |
| Monitoring | | |
| Runbook | | |

## What made mitigation slow or risky

## Corrective actions

| # | Action | Type | Owner | Acceptance criterion | Target |
| --- | --- | --- | --- | --- | --- |

Types: defect, technical-debt, architecture-change, new-requirement,
monitoring-improvement, automation, process.

## Preventive actions

Actions that address the class, not just this instance.

## Implications

**Architecture:**  
**Monitoring:**  
**Testing:**  
**Process:**

## Has this happened before?

Prior RCAs with the same cause. A repeat means a previous corrective action was
not effective, and that is escalated as a process failure.
