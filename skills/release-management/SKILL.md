---
name: release-management
description: Plan a release - change analysis, dependency ordering, migration and rollback plans, validation, approval evidence, release notes and post-deployment verification. Use when assembling a release or preparing production approval.
---

# Release management

A release is a deliberate event with a plan for being undone.

## 1. Assemble and analyse

List every change in scope with its merge request, its story, and its gate verdicts. For each, note: behaviour change, contract change, migration, configuration change, operational action required.

Then find the interactions. Two individually safe changes that touch the same contract, or a migration that must land before a code change, are the failures that assembly catches and individual review does not.

Any change missing a QA or security verdict blocks the release. Do not proceed and reconcile later.

## 2. Order

Sequence by dependency: schema expansion before code that uses it; code that stops writing the old field before the field is dropped; consumers updated before a producer's breaking change. Write the order down, including which steps can be concurrent.

## 3. Migration plan

From `data-engineer`: what runs, in what order, expected duration, locking behaviour, how progress is observed, how completion is verified, and how it is reversed. Irreversible steps are named as such and need explicit human acknowledgement (AP-05).

## 4. Rollback plan

Produce this **before** seeking approval:

- The trigger conditions: what observation causes a rollback, with numbers.
- Who decides and how fast.
- The exact steps.
- What is **not** recoverable by rolling back — usually data written in the new format.
- How long the rollback stays available.

A release whose rollback plan is "redeploy the previous version" without checking whether the data written since is compatible is not planned.

## 5. Validation and verification

**Staging validation** before approval: the plan `qa-lead` produced, executed with evidence.

**Production verification** after deployment: what is checked, by whom, within what window, and what happens if it fails. Verification that nobody performs is worse than no verification, because it creates false confidence.

## 6. Approval

Present a human with: contents, risk, gate verdicts, migration plan, rollback plan, validation evidence, and verification plan. Then ask (AP-01). Approval is recorded, not assumed from silence.

## 7. Release notes

State: new behaviour, changed behaviour, fixed defects, **breaking changes**, required operational actions, and known issues. Written for the people who operate and consume the system, not for the people who built it.

## 8. After

Record: what was deployed, when, by whom, the verification result, and any deviation from the plan. Deviations are inputs to the next release's plan.

## Versioning

Semantic versioning by default: breaking, feature, fix. The project may use calendar or sequential versioning; it is declared in `.ai-engineering/project.yaml`. Whatever the scheme, a version must identify exactly one artifact.
