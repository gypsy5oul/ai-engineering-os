# The lifecycle

## The canonical cycle

```
IDEA → REQUIREMENTS → PRODUCT ANALYSIS → FEASIBILITY → ARCHITECTURE → UX
     → STORY DECOMPOSITION → QA TEST DESIGN → DEVELOPMENT → CODE REVIEW → CI
     → SECURITY → QA → PERFORMANCE → E2E → RELEASE → DEPLOYMENT → PRODUCTION
     → SRE / OBSERVABILITY → FEEDBACK / INCIDENTS → RCA → next cycle
```

Two things about this diagram matter more than its shape.

**Stages are skipped constantly, and never silently.** A documentation change
needs IDEA, DEV, REVIEW and CI. A backend-only change skips UX. Skipping is
recorded — permanently in `.ai-engineering/project.yaml` under
`sdlc.skipped_stages`, or per-change in the change's own record.

**QA is not at the end.** QA test design happens *before* development, from the
requirements and the architecture risks. Tests designed after reading the
implementation test what the code does rather than what it should do.

## Two levels of loop

This document is **Level 1**: stage-to-stage progression across the organization.
Inside each stage runs a **Level 2** department execution cycle — head → lead →
worker → self-check → peer review → lead review → rework → acceptance → rollup.

A stage declares `department_cycle: CYCLE-DEV`, and its definition of done
carries `cycle_accepted(CYCLE-DEV)`. **The macro stage cannot advance until the
department's internal loop closes.** See
[department cycles](department-cycles.md).

## The stage contract

Every stage in every workflow declares the same thing, validated against
`schemas/sdlc-workflow.schema.json`:

| Field | Meaning |
| --- | --- |
| `entry_criteria` | What must already be true before the stage may start. Checked, not assumed. |
| `inputs` | What it consumes |
| `actions` | What it does, including why a team is worth its cost where one is used |
| `outputs` | What it produces |
| `produces` | Artifact **codes** from `policies/artifact-model.json` it must create or update |
| `exit_criteria` | Human-readable completion conditions |
| `definition_of_done` | **Machine-checkable predicates**, evaluated by `scripts/check_dod.py` |
| `agent_gate` | An AI verdict. Blocking, but never an approval |
| `human_gate` | A named human's decision, with where it is durably recorded |
| `human_gate.required_when` | The condition under which the gate has something to decide. A gate that fires when the answer is already settled teaches people to approve without reading |
| `risk`, `complexity` | Feed `scripts/resolve_model.py` |
| `execution` | `inline`, `subagent` or `team`; see [execution](execution.md) |
| `department_cycle` | The Level 2 cycle this stage runs internally, if any |

The definition of done is the part that makes this executable rather than
descriptive:

```yaml
definition_of_done:
  - artifact_exists(REQ)
  - artifact_status(REQ, approved)
  - field_quantified(NFR, target)
  - agent_verdict(qa-lead, pass)
  - human_approval_recorded(none)
```

Run against a real project:

```bash
python3 scripts/check_dod.py --workflow WF-FEATURE --stage REQ --project /path/to/project
```

```
PASS   artifact_exists(REQ)              2 artifact(s) of type REQ
FAIL   artifact_status(REQ, approved)    not approved: SFTP-REQ-002
FAIL   field_quantified(NFR, target)     no NFR artifact exists
PASS   agent_verdict(qa-lead, pass)      qa-lead recorded pass on SFTP-REQ-001
```

A department cycle's acceptance conditions are evaluated the same way:

```bash
python3 scripts/check_dod.py --cycle CYCLE-DEV --project /path/to/project
```

The exit code is the answer a caller should act on, and there are three:

| Code | Meaning |
| --- | --- |
| `0` | Every predicate passed |
| `1` | At least one predicate failed |
| `3` | Nothing failed, but evidence outside the repository is missing |

`3` exists because "not yet provable" is not "done". A stage whose only outstanding
predicate is a GitLab pipeline result has not met its definition of done; it has
met the part this repository can see.


Predicates that need evidence outside the repository — a pipeline result, a
GitLab approval — report `REQUIRES-EVIDENCE` and name where the evidence lives.
They are never counted as passing.

## The workflows

Machine-readable in `sdlc/workflows/`, validated against
`schemas/sdlc-workflow.schema.json`. Each stage declares owner, participants,
skills, inputs, outputs, artifacts, exit criteria and approval gate; each
workflow declares entry and exit conditions and its failure paths.

| Workflow | Entry | Teams | Key gates | Exit |
| --- | --- | --- | --- | --- |
| `WF-FEATURE` feature delivery | A human states a business intent | feature-engineering-team | Scope acceptance (AP-12), Architecture (AP-02), QA design (independent), Merge (AP-09), Residual risk when criteria are unmet (AP-13), Release content (AP-01), Deployment authorization (AP-14) | Running in production, verified, traceable |
| `WF-DEFECT` defect fix | A defect record with a reproduction | single-agent | Review (human), Release (AP-01) | Original reproduction gone, regression test exists |
| `WF-INCIDENT` incident and RCA | An alert or credible report | incident-response-team | Every mitigation (AP-01), RCA (human) | Service verified recovered, RCA with owned actions |
| `WF-DEPENDENCY` dependency change | A dependency change, advisory, end-of-life notice or licence change | single-agent | Classification, Security/licence (AP-04 where an exception is needed), Review (human), Release (AP-01) | Merged with the route, urgency and assessment recorded |
| `WF-RELEASE` release | Changes merged with gates satisfied | release-validation-team | Staging validation, Production approval (AP-01) | Deployed and verified, or rolled back and recorded |
| `WF-ONBOARDING` project onboarding | A project with no configuration | single-agent | Human decision capture, Configuration approval | Valid, human-approved `project.yaml` |
| `WF-AGENT-CHANGE` OS change | A gap or governance finding in this plugin | single-agent | Evaluation, Security, Governance (AP-10) | Merged, versioned, released with a migration note |
| `WF-CHANGE` change request | A commitment the organization already made is to change | single-agent | Impact assessment (independent), Decision (AP-15) | Every affected artifact updated or recorded as unaffected |
| `WF-MIGRATION` data migration | Existing data must be transformed, moved or backfilled | single-agent | Design (independent), Rehearsal (independent), Authorization (AP-05) | Executed and verified, with the rollback path open or explicitly closed |

## Stages that are dimensions, not stages

The canonical cycle names SECURITY, PERFORMANCE and E2E. In `WF-FEATURE` they are
not separate stages, deliberately:

| Named in the cycle | Where it lives | Why |
| --- | --- | --- |
| SECURITY | `security-architect` in ARCH; `security-reviewer` routed in REVIEW by RR-04, RR-05 and RR-09 | Security applied as a gate at the end finds design problems too late to fix cheaply. It belongs in architecture and in review. |
| PERFORMANCE | `performance-reviewer` routed in REVIEW by RR-07; performance scenarios in QADESIGN and QA | Performance testing every change is how performance testing gets ignored. It is risk-routed. |
| E2E | A test level within QADESIGN and QA, chosen by `testing.required_levels` | E2E is a level, not a phase. Making it a stage encourages using it for logic a unit test would pin down precisely. |

Making these stages would add three approval steps and no decisions. Where a
project genuinely needs a separate security or performance phase — a regulated
release, a capacity-critical launch — it adds one to
`sdlc.required_stages` in its own configuration.

## Two workflows about the things code cannot undo

**`WF-CHANGE`** exists because "increase retention from 30 days to 90" is one
sentence that touches requirements, architecture, capacity, cost, security,
compliance, testing and release. The work is the impact assessment; the
implementation that follows is ordinary delivery. What separates it from
`WF-FEATURE` is that the system already does the thing — so the change request
must point at the **current commitment** it alters, and the assessment must answer
every declared dimension. `"none, because..."` is an answer; silence is not, and a
dimension with no owner opens a `DEC` rather than being recorded as unaffected.

Rejecting a change request is a normal outcome, and it is not cancellation: a
rejected `CR` reached `DECIDE` and got an answer, while a cancelled one was
abandoned before anyone decided.

**`WF-MIGRATION`** exists because code can be rolled back and data written in a new
format usually cannot. That asymmetry is why more of this workflow happens before
production than after:

```
IMPACT → DESIGN → SAFETY → REHEARSE → AUTHORIZE → EXECUTE → VERIFY → CLOSE
                                                       ↓
                                                   ROLLBACK
```

Three of those stages exist to make a claim testable rather than aspirational:

- **`SAFETY`** restores a backup somewhere and checks its contents. A backup nobody
  has restored is a hope, and the restore's *duration* is the real recovery time.
- **`REHEARSE`** runs the migration against restored production-shaped data and
  then runs the rollback. A rollback that has never been executed is not a rollback
  plan. Row counts are compared against the `IMPACT` prediction, and a mismatch is
  treated as a defect in the query rather than in the prediction.
- **`CLOSE`** records that the rollback path is now shut, and from when. A
  compatibility window that is never explicitly closed is one that quietly stays
  open in everyone's head while the code that supports it rots.

The `MIG` artifact keeps `rollback_procedure` and `rollback_tested` as separate
fields for the same reason, and `irreversible_after` names the point past which
rollback stops being possible. A migration whose answer to that is "immediately"
needs a different design, not a braver deployment.

## Failure paths

Backward movement is normal and is declared, not improvised:

- Requirements cannot be quantified → back to REQ. It blocks architecture rather
  than proceeding on invented numbers.
- Architecture review rejects → back to ARCH.
- QA exit criteria unmet → back to DEV.
- Security returns HIGH or CRITICAL → back to DEV. An exception is a human
  decision (AP-04), never a developer's.
- Post-deployment verification fails → into `WF-INCIDENT`, with the rollback plan
  produced during RELEASE as the first option.

## Dependency work is five routes, not one

`WF-DEPENDENCY` opens with a `CLASSIFY` stage because urgency and approvals
differ completely by route:

| Route | Urgency comes from | Extra approval |
| --- | --- | --- |
| `routine-upgrade` | Nothing; normal release | — |
| `security-vulnerability` | Exploitability **in this deployment**, not the CVSS score alone | AP-04 where no safe version exists and a compensating control is accepted |
| `end-of-life` | A support end date, planned as work rather than deferred until it becomes an incident | — |
| `licence-compliance` | Legal obligation | Legal and governance input before engineering effort |
| `new-capability` | Leaves the workflow entirely | AP-03, via `technology-selection` |

Treating an end-of-life runtime as a routine upgrade is how it becomes an
incident eighteen months later.

## Requirements flow

```
Human / customer → product-manager → requirements-analyst → PRD → product review
```

The PRD captures business objective, functional and non-functional requirements,
acceptance criteria, constraints, dependencies, assumptions, out-of-scope, open
questions, risks and user journeys.

**Requirements agents ask; they do not invent.** An unstated availability target
is an open question addressed to a named human. `EVAL-REQ-001` exists precisely
to test this under pressure.

## Technology discovery

After requirements are approved, architecture identifies what the change needs
across frontend, backend, database, cache, broker, authentication, API style,
containerization, deployment, observability, CI/CD, storage, networking and
security controls.

Anything already in `.ai-engineering/project.yaml` is settled. Anything not there
produces a **technology-decision proposal** through the `technology-selection`
skill — options including "use what we already have", total cost of ownership,
exit path, and a recommendation — and a human decides (AP-03).

## Architecture

Produces what the change needs: feasibility assessment, HLD, LLD for touched
components, API contracts, data model, deployment model, security and
observability architecture, capacity and HA/DR models where the requirements
demand them, ADRs, and an updated risk register.

Review is independent. An architect does not approve its own architecture, and
`architecture-reviewer` has no write tools, so the separation is structural.

## UX

Personas, journeys, screen and state specifications, accessibility criteria and
the frontend contract — before implementation. Skipped entirely for backend-only
work; the shipped example project (an SFTP platform) records exactly that skip.

## Story decomposition

```
requirements + architecture + UX → development-lead → epics → stories → tasks
```

Each story carries business context, technical context, acceptance criteria,
dependencies, non-functional requirements, test expectations, definition of done,
and the **paths it owns**. Parallel stories must own disjoint paths, because
parallel agents editing one file overwrite each other.

## QA-first

```
story → qa-lead → test strategy → scenarios → automation strategy
      → test-reviewer → baseline → development proceeds
```

The final suite maps back to requirements, acceptance criteria, architecture and
risk. Uncovered areas are listed with reasons; an accepted gap is fine, an
invisible one is not.

## Development, review, CI

Developers may inspect, plan, implement, test, lint, branch, commit, push feature
branches, open merge requests, respond to review and fix CI.

Developers may not approve their own merge request or architecture, override
security or QA, bypass a gate, deploy to production, or push to a protected
branch. The last is enforced by a guard; the rest by structure and review.

Review is routed by change signal per `policies/review-routing.json` — described
in full in `skills/change-review/SKILL.md`. Requiring every reviewer on every change
is how review becomes ceremony.

## Release, deployment, production

`release-manager` assembles the change set, confirms every gate has a verdict,
produces the migration and **rollback** plans with trigger conditions, plans
staging validation and production verification, writes release notes, and asks a
named human to approve (AP-01). It cannot deploy: it has no execution tools.

## Operations, incidents, RCA

```
ALERT → INCIDENT → TRIAGE → SEVERITY → INVESTIGATION → MITIGATION
      → RECOVERY → VALIDATION → RCA → CORRECTIVE ACTION → SDLC
```

Investigation runs hypotheses in parallel; sequential investigation anchors on the
first plausible theory. Every production action requires human approval. Recovery
is declared from verified user-visible behaviour, not from a graph.

`rca-analyst` is independent of `incident-commander` by design. RCA produces a
sourced timeline, a systemic root cause — "human error" is rejected — detection
gaps by stage, and corrective actions **typed** as defect, technical debt,
architecture change, new requirement, monitoring improvement, automation or
process. Each has an owner and an acceptance criterion, and each becomes a real
backlog item. That is the arrow back into the next cycle.
