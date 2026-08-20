---
name: gitlab-workflow
description: Work with GitLab merge requests, issues, pipelines and releases using features available in GitLab CE. Use when opening or updating a merge request, responding to review, fixing a pipeline failure, or planning a release. Distinguishes CE features from paid-tier features.
---

# GitLab workflow

**Core requirement: everything essential works on GitLab CE.** Features that need Premium or Ultimate are optional enhancements and are marked below. A project declares its edition in `.ai-engineering/project.yaml` under `repository.edition`.

## Merge request description

```
## What
One paragraph: the behaviour change.

## Why
The requirement or defect this addresses, with identifiers.

## How verified
Tests added or changed, what was run, what was observed.

## Risk
What could go wrong, and the blast radius. "None" is rarely true; say
"low: change is confined to X and covered by Y" instead.

## Rollback
How this is reverted if it misbehaves.

Refs: PROJ-REQ-012, PROJ-STORY-142
Closes: #123
```

A merge request that does not say how it was verified is not ready for review.

## Reviewers

Assign per `${CLAUDE_PLUGIN_ROOT}/policies/review-routing.json`. Name the routing rules you applied in the description so the reviewer set is auditable.

The author never approves. On CE, that is a convention plus the project's `repository.merge_request.author_may_approve: false` setting and human discipline; on Premium and above it can be enforced by approval rules.

## Responding to review

Address every comment: change the code, or explain why not. Resolving a thread without either is how findings get lost. Push fixes as new commits during review so the reviewer can see what changed; squash on merge if the project does.

## Pipelines

When CI fails, read the failing job's log before changing anything. Reproduce locally where possible. Fix the cause; never disable the stage, and never use `--no-verify` to get past a hook.

Pipeline definition lives in `.gitlab-ci.yml` and is owned by `devops-engineer`; changes to it are routed to security review (RR-09).

## Issues and traceability

Link merge requests to issues with `Closes #n` / `Refs #n`. Use labels for the artifact type and the SDLC stage. Milestones map to releases. Keep artifact identifiers (`PROJ-REQ-012`) in the text, since they survive across systems in a way issue numbers do not.

## Releases

Tag with the project's versioning scheme. Create a GitLab release from the tag with the release notes produced by `release-manager`. Attach the evidence: pipeline result, QA verdict, security verdict.

## CE versus paid tiers

| Capability | CE | Paid tier |
| --- | --- | --- |
| Merge requests, approvals count | yes | multiple approval rules, code owners enforcement (Premium) |
| Protected branches | yes | more granular push/merge rules (Premium) |
| CI/CD pipelines | yes | multi-project pipeline visualisation (Premium) |
| Container registry, package registry | yes | — |
| Issue tracking, milestones | yes | epics, roadmaps (Premium) |
| Dependency and container scanning | run your own scanners in CI | integrated security dashboards (Ultimate) |
| SAST/DAST | run your own in CI | integrated with vulnerability management (Ultimate) |
| Compliance frameworks, audit events | limited | full (Premium/Ultimate) |

Where a paid feature would be used, the CE path must exist and be documented. Never make an Ultimate feature a hard dependency of a core workflow.
