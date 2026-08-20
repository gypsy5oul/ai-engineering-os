# Adopting the OS on a project

## The three pieces

```
company plugin (ai-engineering-os)   installed per engineer, versioned in GitLab
        +
.ai-engineering/project.yaml         the record of human decisions
        +
CLAUDE.md                            what an agent cannot derive from the code
```

A project adopts the OS by installing the plugin and adding the two files. No
agents, skills or hooks are copied into the project. That is the point: an
organization-wide change ships once, and every project gets it on the next plugin
update.

## Running it

In the project repository:

```
/ai-engineering-os:project-onboarding
```

Five stages, from `sdlc/workflows/project-onboarding.yaml`:

1. **Discover** — read manifests, CI, containers, tests, branches. Everything is
   reported as an **observation**.
2. **Ask** — put every decision to a human.
3. **Decide** — write `.ai-engineering/project.yaml`, `CLAUDE.md`, and
   `.ai-engineering/security.json` if the project tightens the defaults.
4. **Structure** — create the knowledge directories and the identifier convention.
5. **Verify** — report what is configured, what is open, and **what the agents
   will refuse to do until each open decision is closed**.

## Observation is not decision

Finding a `pyproject.toml` tells you Python is present. It does not tell you
Python is approved. The distinction is the whole reason onboarding is a workflow
rather than a script: a legacy repository is full of technologies nobody would
choose again, and inferring approval from presence would launder them into policy.

## What is asked

**Identity** — name, uppercase traceability key, description, criticality tier
1–4, accountable owner, compliance regimes.

**Technology, per layer the project has** — frontend, backend, database, cache,
messaging, search, storage, authentication, API style, containerization,
infrastructure-as-code. For each: approved, or merely present?

**Repository** — host, GitLab edition, branch model, protected branches, minimum
approvals, whether the author may approve.

**Environments** — name, purpose, whether production, what data, who approves
deployment.

**Security** — data classification, secret management, project-specific
requirements, what always needs security review.

**Testing** — required levels, coverage target, test data policy.

**Release** — strategy, versioning, who approves production, change window.

**Observability** — metrics, logs, traces, alerting, stated SLOs.

## Unanswered questions

They go in `open_decisions` with an owner and `blocking: true` where engineering
cannot proceed:

```yaml
open_decisions:
  - id: SFTP-OD-001
    question: What is the required RPO and RTO for the audit log store?
    owner: Integration Platform Team lead
    blocking: true
```

A blocking open decision without an owner is a validation error. The purpose is
to make an unmade decision visible rather than letting it be silently made by an
agent picking a plausible default.

## Empty layers are correct

An SFTP appliance has no frontend. A batch pipeline has no UX. Leave the layer
out. The shipped template records the corresponding skipped SDLC stage with its
reason.

## Validate

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_project_config.py"
```

Beyond schema checking it applies rules that make the configuration useful:

- A production environment with `deployment_approval: none` is an error (AP-01).
- Confidential or restricted data with no stated secret management is an error.
- `test_data: production-copy` with regulated data is an error.
- `author_may_approve: true` is an error: it removes the only independent check
  on the merge.
- A blocking open decision without an owner is an error.

## Keeping it current

The configuration is reviewed when the stack changes, when an environment is
added, when data classification changes, and at least at the project's review
cadence. A stale configuration is worse than none, because agents trust it.

## Project settings

`templates/project/settings.json` is a starting point for the project's own
`.claude/settings.json`. It does three things worth doing:

- **Pre-approves the project's ordinary read-only commands.** If everything
  prompts, nothing is noticed, and the guards' escalations stop meaning anything.
- **Denies reading credential files**, as defence in depth. The write guard
  already denies writing them; these rules stop them reaching a transcript.
- **Declares the marketplace and plugin**, so a fresh clone — and a cloud session —
  gets the organization without per-engineer setup.

It does **not** belong at the plugin root. A plugin-root `settings.json` supports
only `agent` and `subagentStatusLine`; anything else there is silently ignored,
which is the worst failure mode a governance control can have.
