---
name: sdlc-navigator
description: Place a piece of work in the software lifecycle and decide what happens next. Use at the start of any request, when it is unclear which stage the work is in, when deciding which stages to skip, or when the user asks "what now". Reads the machine-readable workflow definitions and reports the stage, the owner, the gates and the artifacts required.
argument-hint: [what the user is asking for]
---

# SDLC navigator

Answer three questions before anything else happens: **which workflow, which stage, what is missing.**

## 1. Pick the workflow

Read the workflow definitions in `${CLAUDE_PLUGIN_ROOT}/sdlc/workflows/`:

| Situation | Workflow |
| --- | --- |
| New capability or material behaviour change | `feature-delivery.yaml` (WF-FEATURE) |
| Existing specified behaviour is wrong | `defect-fix.yaml` (WF-DEFECT) |
| Production is degraded now | `incident-response.yaml` (WF-INCIDENT) |
| Dependency added, removed or upgraded | `dependency-change.yaml` (WF-DEPENDENCY) |
| Merged work needs to reach production | `release.yaml` (WF-RELEASE) |
| Project has no `.ai-engineering/project.yaml` | `project-onboarding.yaml` (WF-ONBOARDING) |
| This plugin's own agents, skills, hooks or policies change | `agent-change.yaml` (WF-AGENT-CHANGE) |

If the request matches none of them, say so and treat it as ordinary work outside the lifecycle. Do not force a workflow onto a two-line question.

Two workflows are missing from the table on purpose: `change-request.yaml` (WF-CHANGE), which is reached when an approved requirement changes rather than when new work arrives, and `data-migration.yaml` (WF-MIGRATION), which is usually a stage inside another change rather than a change of its own. Route to either only when the request is genuinely about the change or the migration itself.

Naming the workflow is not the same as opening the work. The `--type` that opens a work item for each workflow is listed once, in `/ai-engineering-os:work-item`; send the reader there rather than repeating the vocabulary, because a second copy of it is the next thing to drift.

## 2. Check the entry conditions

Every workflow declares `entry_conditions`. If one fails, that is the work, not the thing the user asked for. The most common failure is a missing project configuration: without it, agents would have to guess the stack, the branch model and the security requirements, so the correct next step is `/ai-engineering-os:project-onboarding`.

## 3. Locate the stage

Walk the `stages` list and find the first stage whose `exit_criteria` are not met by artifacts that actually exist. Do not trust a claim that a stage is done; look for its `outputs`.

## 4. Report

State, in this order:

1. **Workflow and stage** — id and name.
2. **Owner** — the agent that owns the stage.
3. **Missing inputs** — what the stage needs that does not exist yet.
4. **Gate** — `approval_gate.type`. If `human`, name the approval and its policy reference from `${CLAUDE_PLUGIN_ROOT}/policies/approval-policy.json`.
5. **Skipped stages** — which stages this change does not need, each with a reason. Skipping is normal; skipping silently is not.
6. **Next action** — one sentence. If the change is not yet tracked, that action
   is to open a work item: point at the `work-item` skill, which is the control
   loop's own instructions. Do not invent a command; the entry points are the
   skills in this plugin and `${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py`.

## Rules

- A stage is complete when its exit criteria are met, not when someone says it is.
- Skipping a stage is a decision that gets recorded, in `.ai-engineering/project.yaml` under `sdlc.skipped_stages` for permanent skips, or in the change's own record for one-off skips.
- Never invent a stage. The workflows are the definition.
- Backward moves are normal. `failure_paths` says where a failure sends the work.
- Documentation-only and configuration-only changes usually need IDEA, DEV, REVIEW and CI only. Say that rather than running the full lifecycle.
