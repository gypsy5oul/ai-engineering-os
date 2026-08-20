---
id: <KEY>-EVID-000
type: evidence
title: Evidence for <incident id>
status: collected        # collected | sealed
owner: sre
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the incident id>
reviewers: []
approvals: []
dependencies: [<KEY>-INC-000]
links:
  incidents: [<KEY>-INC-000]
collected_at: <ISO timestamp>
collector: <who>
hash: <digest of the collected bundle, so tampering is detectable>
---

> **Collected BEFORE any destructive remediation.** A pod restart, a log
> rotation or a queue purge performed first destroys the answer. For a suspected
> security compromise this is mandatory and blocking.
>
> **Sealed and never edited.** An evidence record that can be rewritten is not
> evidence.

## Logs

| Source | Range | Location | Digest |
| --- | --- | --- | --- |

## Timestamps

First observation, alerting, deployment boundaries, configuration changes — in
UTC, with the clock source named.

## Deployment versions

| Component | Version | Deployed at | Commit |
| --- | --- | --- | --- |

## Configuration snapshots

What was actually in effect, not what the repository says should have been.

## Metrics

| Metric | Range | Location |
| --- | --- | --- |

## Traces

## Investigation commands

Every command run during investigation, with its output location. This is part
of the evidence: it records what was looked at and what was not.

| # | Command | Run by | At | Output |
| --- | --- | --- | --- | --- |

## Seal

| Sealed at | By | Digest | Storage |
| --- | --- | --- | --- |
