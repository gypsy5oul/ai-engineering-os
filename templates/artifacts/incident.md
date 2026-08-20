---
id: <KEY>-INC-000
type: incident
title: <Symptom, in user-visible terms>
status: open             # open | mitigated | recovered | closed
owner: incident-commander
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the alert or report that started this>
reviewers: []
approvals: []            # every production action, AP-01, with who authorised it
dependencies: []
links:
  rcas: []
  defects: []
  releases: []
---

## Symptom

One sentence, in terms a user would recognise. Not "elevated errors".

## Severity

| Declared | At | By | Rationale |
| --- | --- | --- | --- |

Re-evaluate as facts arrive. Under-declaring to avoid waking someone is a
failure mode, not politeness.

## Timeline

| Time (UTC) | Event | Source | Observed / inferred |
| --- | --- | --- | --- |

**This artifact is evidence. It is appended to, never rewritten after the fact.**

## Hypotheses

| # | Hypothesis | Owner | What would refute it | Outcome |
| --- | --- | --- | --- | --- |

The rejected ones are the most valuable part of this record for the next incident.

## Production actions

Every one requires human approval (AP-01) before it happens.

| # | Action | Blast radius | Rollback | Approved by | At |
| --- | --- | --- | --- | --- | --- |

## Mitigation

What restored service. **Mitigation is not the fix**; state what is still true
that caused this.

## Recovery

Declared at: <time>  
Verified by: <the user-visible check that was actually run, not the dashboard>

## Handoff to RCA

Analyst: <must not be the incident commander>  
Evidence preserved: <what, and where>  
Open questions:
