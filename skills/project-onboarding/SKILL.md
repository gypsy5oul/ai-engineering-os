---
name: project-onboarding
description: Bring a project under the AI Engineering OS by producing a human-approved .ai-engineering/project.yaml. Use when a project has no configuration, when the configuration is stale, or when an agent reports that it cannot proceed without knowing the approved stack, environments, branch model, security or testing requirements. Asks the human every decision it cannot observe.
argument-hint: [project name or repository path]
allowed-tools: Read, Grep, Glob, Bash(git *), Bash(ls *), Bash(cat *)
---

# Project onboarding

Produce a configuration that a human has approved. **Observation is not decision.** You may report that the repository contains a `pyproject.toml`; you may not conclude that Python is the approved backend language.

## Step 1 — Discover (observation only)

Look for and report, as observations:

- Build and dependency manifests, and what they imply about languages and frameworks.
- CI configuration and what stages already exist.
- Container, deployment and infrastructure files.
- Test directories, frameworks and any coverage configuration.
- Branch names present in the repository, and which look protected.
- Existing documentation structure.

Present this as "observed", clearly separated from "decided".

## Step 2 — Ask

Ask the human the questions below. Use `AskUserQuestion` for the ones with a small option set; ask the rest directly. Group them so the human answers in a few passes, not thirty.

**Identity**: project name, short uppercase key for traceability identifiers (for example `SFTP`), one-paragraph description, criticality tier 1–4, accountable owner, applicable compliance regimes.

**Technology** (one per layer the project has): frontend, backend, database, cache, messaging, search, storage, authentication, API style, containerization, infrastructure-as-code. For each: is this **approved**, or merely present? Only approved technologies go in the configuration.

**Repository**: host and edition (GitLab CE features only, or Premium/Ultimate available), branch model, protected branches, minimum merge-request approvals, whether the author may approve.

**Environments**: name, purpose, whether it is production, what data it holds, who approves deployment to it.

**Security**: data classification, secret management location, project-specific security requirements, what always requires security review.

**Testing**: required test levels, coverage target if any, test data policy.

**Release**: strategy, versioning scheme, who approves production, change window if any.

**Observability**: metrics, logs, traces, alerting, any stated SLOs.

## Step 3 — Record

Write `.ai-engineering/project.yaml` from `${CLAUDE_PLUGIN_ROOT}/templates/project/project.yaml`. Validate it:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_project_config.py" .ai-engineering/project.yaml
```

Anything the human could not answer goes in `open_decisions` with `blocking: true` if engineering cannot proceed without it. **Never fill a field by inference to make validation pass.**

Also copy `${CLAUDE_PLUGIN_ROOT}/templates/project/CLAUDE.md` into the project root and fill it in, and create the knowledge structure from `${CLAUDE_PLUGIN_ROOT}/templates/project/knowledge-structure/`.

If the project needs stricter guards than the defaults, write `.ai-engineering/security.json` from the template. Project overrides are additive: they can tighten, and any loosening requires a justification and an expiry.

## Step 4 — Report

Report exactly three lists:

1. **Configured** — what is now decided and recorded.
2. **Open** — decisions still outstanding, with owner and whether they block.
3. **Refusals** — what the agents will decline to do until each open decision is closed. For example: "No backend implementation until the backend framework is approved."

## Rules

- The configuration is a record of human decisions. If no human answered, nothing was decided.
- Never write a technology into `technology:` because you found it in the repository. Ask whether it is approved.
- Never invent an availability target, an RPO/RTO or a compliance regime.
- A project may legitimately have empty layers. An SFTP appliance has no frontend; leave it out rather than inventing one.
