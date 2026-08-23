# Working on this repository

## Setup

```bash
git clone https://gitlab.example.com/ai-engineering/ai-engineering-os.git
cd ai-engineering-os
claude --plugin-dir .
```

`/reload-plugins` picks up changes without restarting. `SKILL.md` edits take
effect immediately; agents, hooks and policies need the reload.

Requirements: Python 3.8+ as `python3`. Nothing else. No `pip install`, ever —
the bundled `minyaml` and `jsonschema_mini` exist so CI and a fresh laptop behave
identically.

## The gate

Run this before proposing a change:

```bash
./scripts/check_all.sh
```

It runs everything CI runs, in the order CI runs it, and fails fast on the first
problem because a broken manifest makes every later result meaningless. The
thirteen steps are plugin structure, schemas and the shipped project template,
stage contracts and model routing, department execution cycles, notification
routing, documentation links, the secret scan, the tests, the end-to-end SDLC
simulation, fault injection, the liveness checker, the deterministic
evaluations, and Claude Code's own structural validation.

The script is the list. Keeping a copy of it here is how the two drift, so run
individual commands from it while iterating and let the script decide whether a
change is ready to propose.

### A wrinkle in `claude plugin validate`

This repository is both a plugin and a marketplace. With
`.claude-plugin/marketplace.json` present, `claude plugin validate .` validates
the **marketplace** manifest and never looks at `plugin.json`. To validate the
plugin itself, run it against a copy with the marketplace file removed —
`scripts/check_all.sh` does this automatically, and CI runs both.

## The end-to-end simulation

```bash
python3 scripts/simulate_sdlc.py --all
python3 scripts/simulate_sdlc.py --scenario feature -v
python3 scripts/simulate_sdlc.py --scenario incident --keep   # leave the project to inspect
```

Ten scenarios — feature, defect, incident, security-block, release-rollback,
agent-change, onboarding, change-request, migration, migration-rollback — each
run against a throwaway project. They create real
artifacts with real headers, emit real events, produce real rollups, and evaluate
each stage's definition of done **at the moment that stage completes**.

That last detail matters. Evaluating at the end of the run tests the final state
rather than the stage: `WF-DEFECT/TRIAGE` requires the defect to be **open** and
`WF-DEFECT/VERIFY` requires it **closed**, and both are correct at their own
moment.

Every other check in this repository asks whether a document is well-formed.
This asks whether the organization can actually be **operated**. A workflow that
reads well but cannot be completed is a contradiction, and this is where it
surfaces — it found four real defects on its first run. See
[the audit record](production-readiness.md).

Add a scenario when you add a workflow. `tests/test_simulation.py` fails if any
workflow has no simulation, or if any department cycle is never completed by one.

## Adding an agent

1. **Justify it.** Read `docs/agent-model.md`. Most requests are skills or
   policies. If it would have the same authority, inputs and outputs as an
   existing role, it is that role.
2. Add the entry to `policies/agent-registry.json`: owner, risk, models, tool
   profile, spawn permissions, evaluation suite, review frequency.
3. `python3 scripts/scaffold_agent.py <name>` renders the file with the canonical
   sections.
4. Fill every section. `Not your responsibility` and `Forbidden actions` are the
   ones that prevent role creep — write them first.
5. Add a write scope in `policies/write-scope.json` if it can write.
6. Create `evaluations/<suite>/` with at least one adversarial case derived from
   its `Forbidden actions`.
7. Run the gate.

## Adding a skill

1. `mkdir skills/<name>` and write `SKILL.md`.
2. The `description` decides when Claude loads it: state what it does **and when
   to use it**, triggers first.
3. Keep the body high-signal. Depth goes in a `reference.md` beside it.
4. Never hard-code a technology unless the skill declares itself
   platform-specific in its own description.
5. Add it to the table in `docs/skills.md` — `tests/test_repository.py` fails if
   you forget.

## Adding a guard rule

1. Add the rule to `policies/hook-policy.json`: id, category, action, pattern,
   message, **remediation**. Validation fails without a remediation.
2. Add **two** tests: one that it blocks the dangerous case, one that it does not
   block the ordinary case that resembles it.
3. `EVAL-DEV-002` must still pass. If your rule broke it, it is too broad.
4. Hook changes are AP-10: governance review and human approval.

Rules are data. The scripts evaluate rules and should rarely change.

## Adding a workflow

A YAML file in `sdlc/workflows/` validated by
`schemas/sdlc-workflow.schema.json`. Stage owners must exist in the registry;
referenced skills must exist; `parallel_with` and failure-path targets must name
real stages. A stage that declares `artifacts` must have an owner that can write —
`tests/test_repository.py` checks that, and it caught a real defect during
development.

## Conventions

- Filenames kebab-case; an agent's `name` equals its filename stem.
- Model aliases only, never dated identifiers.
- Machine-read configuration is JSON; human-authored configuration may be YAML.
- Policy documents carry a `version` and a `description` explaining the intent,
  not just the shape.
- Documentation says what is not implemented as plainly as what is.

## Repository test philosophy

`tests/test_repository.py` tests the organization, not just the code: that
reviewers cannot write, that CRITICAL agents cannot write, that no default model
sits below its risk floor, that every approval-policy id is referenced somewhere,
that every agent and skill appears in its catalogue.

Three of those found real defects during the initial build. They are cheap to
write and they are the reason cross-document drift does not accumulate.

## Commits and branches

Follow `skills/git-workflow`. Branch `feature/*` or `defect/*`, conventional
commit subjects, traceability identifiers in the body, merge request with what,
why, how verified, risk and rollback.

The guards apply to work on this repository too. Editing `agents/` or `hooks/`
escalates to you, deliberately: you are changing the control system.
