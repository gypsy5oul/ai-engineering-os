---
id: <KEY>-REL-000
type: release
title: Release <version>
status: draft            # draft | in-review | approved | done | rolled-back
owner: release-manager
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the change set assembled for this release>
reviewers: []            # sre operability verdict, qa and security verdicts
approvals: []            # AP-01, recorded in the GitLab release
dependencies: []
links:
  stories: []
  defects: []
  merge_requests: []
---

## Contents

| Id | Change | Type |
| --- | --- | --- |

## Breaking changes

<Explicit, or "None". This is the section consumers read.>

## Required operational actions

<Configuration, migration or manual steps operators must take. Or "None".>

## Migration

| Step | Duration | Locking | Verification | Reversible |
| --- | --- | --- | --- | --- |

## Rollback plan

**Trigger conditions:**

**Steps:**

**Not recoverable by rollback:** <usually data written in the new format>

**Rollback available until:**

## Gate verdicts

| Gate | Verdict | By |
| --- | --- | --- |
| Code review | | |
| QA | | |
| Security | | |
| Performance | | |

## Verification plan (production)

| Check | Owner | Window | On failure |
| --- | --- | --- | --- |

## Known issues
