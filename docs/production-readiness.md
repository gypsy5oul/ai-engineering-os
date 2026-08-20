# Production-readiness audit — v0.7.0

The architecture was frozen at v0.6.0. This records what happened when the
organization was run end to end for the first time, rather than only validated
as documents.

## Method

`scripts/simulate_sdlc.py` executes seven scenarios against throwaway projects:
feature, defect, incident, security-block, release-rollback, agent-change,
onboarding. Each creates real artifacts with real headers, emits real events,
produces real rollups, and evaluates every stage's machine-checkable definition
of done **at the moment that stage completes**.

Nothing is mocked. If a predicate cannot be satisfied by an artifact the model
permits, it fails.

## What it found

**Four real defects.** Every one had passed static validation, because static
validation checks that documents are well-formed, not that a process can be
completed.

### 1. `required_fields_present` treated an empty list as a missing field

`dependencies: []` is a positive statement that there are none. It is not the
same as the key being absent, and a root requirement legitimately has none. The
predicate failed every root artifact in the organization.

**Fixed:** empty lists and maps satisfy presence; only a scalar that is absent or
blank is a gap.

### 2. `every_linked` only looked forward

`every_linked(REQ, ARCH)` required each requirement to link to an architecture.
**No author can satisfy that**: at the time the requirement is written, the
architecture does not exist. `docs/knowledge-structure.md` already stated the
model is bidirectional by intent, and the predicate contradicted it.

**Fixed:** the edge counts in either direction.

### 3. `cycle_accepted` was required where the department had barely started

The Level 2 wiring added `cycle_accepted`, `cycle_rollup_reported` and
`no_open_rework` to **every** stage declaring a department cycle. In
`WF-INCIDENT`, SRE's engagement spans `EVIDENCE` → `INVESTIGATE` → `RCA`, so
requiring the SRE cycle to be ACCEPTED at `EVIDENCE` asked a department to have
finished before it began.

**Fixed:** stages declare `cycle_role: enters | continues | completes`. Only a
completing stage carries the three predicates, and validation requires **exactly
one** completing stage per workflow per cycle. `WF-INCIDENT/RCA` and
`WF-DEFECT/FIX` gained the cycle declarations they were missing.

### 4. A granted security exception bypassed the definition of done

Found by the new acceptance-gate check rather than the simulation.
`CYCLE-SEC` had `RELEASE_BLOCKED --exception_granted--> ACCEPTED`. A human
accepting residual risk is a real decision, but it is not a reason to skip the
cycle's own conditions.

**Fixed:** `exception_granted` now routes to `ACCEPTANCE_REQUESTED`, where the
definition of done is evaluated like any other path.

## Two design changes made alongside

**The head requests acceptance; it does not declare it.** A new
`ACCEPTANCE_REQUESTED` state sits between `READY_FOR_INTEGRATION` and `ACCEPTED`.
The head initiates; `scripts/check_dod.py` determines. Otherwise every predicate
is advisory and the Level 2 contract reduces to an agent asserting it finished.
`check_cycle.py` now fails any transition reaching `ACCEPTED` other than through
that gate.

**`engineering-director` heading six departments is a consequence, not a design.**
Most departments have one to three workers, so the effective chain is
*organization executive → department lead → workers* — three levels, not four.
`policies/department-cycle.json` records when a dedicated department head becomes
justified: more than one lead, rollup volume the executive cannot absorb, or an
escalation path the executive should not sit on, as security already has.

## Result

```
7 scenarios · 43 stages · 173 predicates
  → 156 pass · 0 fail · 17 require evidence outside the repository
```

The 17 are `pipeline_passed`, `tests_pass` and `human_approval_recorded` —
things that live in GitLab and in the project's own test run. They report
`REQUIRES-EVIDENCE` and are **never** counted as passing.

## What this does not prove

- **Behaviour.** The simulation proves the process can be completed. It does not
  prove an agent will follow it. That is what the evaluation suites test, and 23
  of 58 cases still need a model run.
- **Real projects.** Every scenario runs against a synthetic project built from
  the shipped template.
- **Guard coverage under adversarial use.** The guards have their own tests; the
  simulation does not attack them.

## Standing coverage rule

`tests/test_simulation.py` fails if a workflow has no scenario, or if a
department cycle is never completed by one. Adding a workflow without a scenario
is a build failure, not an oversight discovered later.
