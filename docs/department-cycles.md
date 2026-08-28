# Department execution cycles

The workflows in `sdlc/workflows/` govern **stage-to-stage** progression. This
governs **task-to-task** delegation, review and rework *inside* a stage.

Both are needed. A macro workflow alone says "DEV, then REVIEW, then QA" and has
nothing to say about how a story becomes accepted work inside DEV.

```
LEVEL 1  ORGANIZATIONAL SDLC          sdlc/workflows/
  Product → Architecture → Development → QA → Security → Release → Operations
     │
     │  each stage runs one of:
     ▼
LEVEL 2  DEPARTMENT EXECUTION          sdlc/cycles/
  head → lead → worker → self-check → peer review → lead review
       → rework → acceptance → rollup
```

**The join:** a stage declares `department_cycle: CYCLE-DEV`, and its definition
of done carries `cycle_accepted(CYCLE-DEV)`, `cycle_rollup_reported(CYCLE-DEV)`
and `no_open_rework(CYCLE-DEV)`. **The macro stage cannot complete until the
internal loop has closed.**

## The generic cycle

```
              HUMAN OWNER  ── governance only
                      │      approves what policy says needs a human,
                      │      receives escalations. Not routine rollups.
                      ▼
                    HEAD  (an AGENT)
                      │  plans, delegates, receives the ROLLUP,
                      │  decides whether the department is done
                      ▼
                    LEAD
                      │  decomposes, assigns, owns aggregate quality
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     WORKER        WORKER        WORKER
        │
        ▼
    IMPLEMENT
        │
        ▼
   SELF VALIDATION        ── the worker runs its own gate first
        │                    submitting work that fails its own tests
      ┌─┴──┐                 wastes a review cycle
    FAIL  PASS
      │     │
      └─────┼──────► IN_PROGRESS
            ▼
      PEER REVIEW          ── detail. Different agent. Cannot edit.
            │
     ┌──────┼───────┬──────────────┐
   minor  major  arch issue    req issue
     │      │         │            │
     ▼      ▼         ▼            ▼
 CHANGES  LEAD    ESCALATED    ESCALATED
 REQUESTED REVIEW      │            │
     │      │          └────────────┴──► out of the department
     │      ▼
     │  LEAD REVIEW        ── adherence and integration, NOT line-level
     │      │
     │   ┌──┼────────────┐
     │  pass changes   cannot
     │   │  required   resolve
     │   │    │           │
     │   │    ▼           ▼
     │   │  CHANGES   ESCALATED
     │   │  REQUESTED
     │   │    │
     └───┼────┘
         ▼
  READY FOR INTEGRATION
         │  every item in the set, not just this one
         ▼
     ACCEPTED  ──────► ROLLUP to the head ──────► macro stage may advance
```

Inspect any cycle:

```bash
python3 scripts/check_cycle.py --graph CYCLE-DEV
python3 scripts/check_cycle.py --trace CYCLE-DEV   # walks a happy path and a rework path
```

## The human governs, an agent manages

Making the head a human puts a person in the middle of every departmental rollup,
which is not an autonomous engineering organization. So the stack is:

```
   HUMAN OWNER          governance only: the approval categories that name this
        │               role, plus anything the head escalates
        ▼
   HEAD (agent)         plans, delegates, receives the rollup, decides done
        ▼
   LEAD (agent)         decomposes, assigns, produces the rollup
        ▼
   WORKER (agent)       executes and self-validates
        ▼
   PEER (agent)         reviews detail, independent, cannot write the artifact
```

`engineering-director` heads six of the seven departments. That is not a
convenience: its role contract already covers sequencing and cross-department
arbitration, and it already holds the spawn authority for every cycle lead.
`check_cycle.py` fails a head that cannot spawn its own lead — a manager that
cannot delegate is not a manager.

**One department keeps a human head, and the reason is argued rather than
assumed.** `CYCLE-SEC` reports to `security-owner` directly, because placing the
delivery-accountable agent above security would put schedule pressure in
security's reporting line — the one thing security's independence exists to
prevent. Validation permits at most one such exception and requires it to state
why.

What each human owner actually decides:

| Cycle | Human owner | Authority |
| --- | --- | --- |
| `CYCLE-PROD` | project-owner | Requirement scope; AP-03 where a technology decision is implied |
| `CYCLE-ARCH` | architecture-owner | AP-02, AP-03, AP-06 |
| `CYCLE-QA` | qa-owner | Accepting residual risk where exit criteria are waived |
| `CYCLE-DEV` | engineering-owner | AP-09; scope beyond the approved stories |
| `CYCLE-SEC` | security-owner | AP-04, AP-08; release blocks on HIGH/CRITICAL |
| `CYCLE-DEVOPS` | engineering-owner | AP-07, AP-01 |
| `CYCLE-SRE` | on-call-owner | AP-01 every production action; AP-11 data access |

A governance role that decides nothing specific decides everything by default,
so `authority` is required and validated.

## Positions, not new agents

The agent set is [frozen at 29](organization-freeze.md). The cycle is defined in
terms of **positions**, filled by existing agents and by the named humans in
`.ai-engineering/project.yaml` under `approval:`.

| Position | Filled by | Sees |
| --- | --- | --- |
| **human owner** | A named human from `approval:` | Escalations and approval requests. **Not routine rollups.** |
| **head** | A lead-profile **agent** | One rollup per work item set. Never an individual review round. |
| **lead** | The department's lead agent | Decomposition, assignment, aggregate quality, integration |
| **worker** | The department's implementer agents | One work item |
| **peer reviewer** | An independent, read-only reviewer | Detail on one item |
| **specialist reviewers** | Routed by `policies/review-routing.json` | One dimension across the output |

The staffing:

| Cycle | Human owner | Head (agent) | Lead | Workers | Peer reviewer |
| --- | --- | --- | --- | --- | --- |
| `CYCLE-DEV` | engineering-owner | `engineering-director` | `development-lead` | backend, frontend, data | `code-reviewer` |
| `CYCLE-QA` | qa-owner | `engineering-director` | `qa-lead` | `qa-engineer` | `test-reviewer` |
| `CYCLE-SEC` | security-owner | **`security-owner` (human)** | `security-architect` | `security-reviewer`, `dependency-reviewer` | mutual |
| `CYCLE-ARCH` | architecture-owner | `engineering-director` | `solution-architect` | `solution-architect` | `architecture-reviewer` |
| `CYCLE-PROD` | project-owner | `engineering-director` | `product-manager` | `requirements-analyst` | `qa-lead` (testability) |
| `CYCLE-DEVOPS` | engineering-owner | `engineering-director` | `devops-engineer` | `devops-engineer` | `reliability-reviewer` |
| `CYCLE-SRE` | on-call-owner | `engineering-director` | `sre` | `sre` | `reliability-reviewer` |

Three cycles — `CYCLE-ARCH`, `CYCLE-DEVOPS` and `CYCLE-SRE` — have the lead and
the worker as the same agent. Small departments genuinely do. In those, the peer reviewer **must** be a different agent, or the
cycle has no independent check at all. `check_cycle.py` fails otherwise.

`CYCLE-SEC` uses `mutual`: the two security workers review each other's items,
because there is no third security reader. Mutual review requires at least two
workers, and the reviewer of an item is never that item's own worker.

## Intensity: how much of the cycle a task walks

The cycle above is correct and it is not free. Worker, self-check, peer review,
lead review, rollup, acceptance is the right shape for a novel change to a
coupled surface. It is what a two-predicate intake step with no reviewer, no gate
and no artifact used to get as well, because the cycle had one path and every
task walked all of it.

**Intensity selects a path through the cycle that already exists.** It does not
define four cycles — four machines would be four things to keep in step.

| Level | Path | Skips |
| --- | --- | --- |
| `MICRO` | worker → self-check → done | `PEER_REVIEW`, `LEAD_REVIEW` |
| `STANDARD` | worker → self-check → peer review → done | `LEAD_REVIEW` |
| `COMPLEX` | worker → self-check → peer → lead → rollup → done | — |
| `CRITICAL` | everything COMPLEX has, plus the human approval its stage names | — |

`SELF_VALIDATION`, `ACCEPTANCE_REQUESTED` and `ACCEPTED` are never skippable.
The first costs one agent and is the cheapest thing in the cycle; the other two
are where the definition of done is evaluated, and **no level changes what the
work has to satisfy**. What intensity removes is a second and a third reader.

### It resolves from facts, and only upward

Eight signals, in `policies/workflow-intensity.json`. Each can only **raise** the
level. A model choosing how much review its own work gets is the failure this
would otherwise introduce; signals that can only raise make the level an
observation rather than an argument.

| Signal | Effect |
| --- | --- |
| CRITICAL risk | forces `CRITICAL`, and nothing may lower it |
| HIGH risk | at least `COMPLEX` |
| novel complexity | at least `COMPLEX` |
| deploys, authorizes, migrates, releases | forces `CRITICAL` — ceremony after the fact is not review |
| incident, release or migration work item | at least `COMPLEX` |
| holds a coupled surface | at least `COMPLEX` — the review that matters sees the consumers |
| names a reviewer, or the DoD contains `agent_verdict` | at least `STANDARD` |
| the DoD contains `human_approval_recorded` | at least `COMPLEX` |

`MICRO` is reached by passing a test, not by being declared — otherwise it would
be unreachable, since nothing lowers. The test is a conjunction of negatives: LOW
risk, routine, no reviewer, no human gate, no coupled surface, produces nothing
another stage consumes, and few enough predicates. It can only apply to a task
every raising signal stayed silent on.

### What it does not do

**It does not weaken independent review.** That is the obvious objection and it
has a specific answer: intensity controls the depth applied to **one task**, and
the department cycle's own acceptance conditions still require an independent
verdict on the **department's output**. A `MICRO` task rolls up into a cycle that
gets peer-reviewed as a whole.

One floor needs no enforcement at all. A task whose definition of done contains
`agent_verdict` cannot be `MICRO`, because a path where nobody produces a verdict
cannot satisfy a predicate that demands one. The policy and the checker cannot
disagree, because the checker decides.

### On a real feature

Resolved against the shipped `WF-FEATURE`, fifteen tasks:

```
MICRO 1   STANDARD 4   COMPLEX 7   CRITICAL 3
```

Four tasks skip a lead review that bought nothing; one skips both readers. The
seven COMPLEX and three CRITICAL tasks are untouched, which is the point — the
level exists so the others can be cheaper without an argument about whether
they should be.

## Why the peer reviewer sits between worker and lead

Without it, every finding reaches the lead and the lead becomes the bottleneck —
and then the head starts seeing line-level issues.

- **Peer reviewer** owns detailed correctness. Minor findings go straight back to
  the worker and never reach the lead.
- **Lead** owns architecture adherence, integration between streams, and whether
  the work meets the *story* rather than the ticket.
- **Head** owns delivery and reads a rollup.

The peer reviewer holds **no write access to the artifact it reviews**. That is
the check `check_cycle.py` actually enforces — not "holds no write tools", which
was too coarse and wrongly flagged `qa-lead` reviewing requirements for
testability. `qa-lead` can write test plans; it cannot write `docs/requirements/`,
so it cannot become a second author of what it reviews.

## Escalation

```
   worker
      ↓  cannot resolve
   peer reviewer
      ↓  cannot resolve, or the finding affects other streams
   lead
      ↓  cannot resolve
   head  (agent)
      ↓  governance decision, or genuinely beyond the department
   human owner
```

**A worker never escalates straight to the head**, and **the head reaches the
human only for governance or for what the department cannot resolve.** An escalation that skipped the lead means the
lead was not told about a problem in its own department; one that reaches the
human for routine work means the head is not doing its job.

Sideways, out of the department entirely:

| Issue | Goes to |
| --- | --- |
| Architecture issue | `solution-architect`, which may escalate to the architecture owner (AP-02) |
| Requirement issue | `product-manager`, and it may become a `DEC` |
| Security issue | `security-reviewer` immediately, ahead of the department's own queue |
| Environment issue | `devops-engineer` |
| Operational issue | `sre` |

## Rework is bounded

Limit **3** rounds per work item. On the fourth, escalate.

A third rework round means the problem is not the implementation. Either the
acceptance criteria are wrong, the design does not admit a clean answer, or the
reviewer and the worker disagree about something nobody has written down. Looping
a fourth time hides that instead of surfacing it.

`no_open_rework(CYCLE-*)` in the macro stage's definition of done fails when any
item has exceeded the limit or has an open escalation.

The limit is a transition, not a note. `CHANGES_REQUESTED --limit_reached-->
ESCALATED` is the move an over-limit item makes, and `check_cycle.py` fails any
cycle that declares a limit without one. Before that edge existed, the limit was
prose: an item that honestly reported a fourth round had no legal move except to
keep cycling, so the machine punished accurate reporting and rewarded editing the
counter.

## QA validates a defect before it becomes a development item

The one sub-cycle that is not the generic loop, because a tester observing a
failure is not the same as a product defect existing.

```
   TESTER observes a failure
            ▼
   DEFECT_TRIAGE   owner: qa-lead
            │
            │  Is this a real failure, or expected behaviour
            │    under a condition nobody wrote down?
            │  Is the expected behaviour what the requirement says?
            │  Is the environment the one the strategy specifies?
            │  Is the test data correct and current?
            │  Does it reproduce, from the record alone,
            │    by someone other than the observer?
            ▼
   ┌────────┬────────────┬──────────────┬───────────────┬──────────────┐
   ▼        ▼            ▼              ▼               ▼
 not-a-   test-      environment-   requirement-    product-
 defect   defect       defect        ambiguity       defect
   │        │            │              │               │
 closed   stays in    devops-       product-manager   risk + impact
 with a   QA as a     engineer      → may become      assessed
 reason   test bug                  a DEC            → DEF → WF-DEFECT
```

Most first-round failures are the environment, the data or a wrong expectation.
Raising all of them as development defects trains developers to disbelieve QA.

## Departments with an extra state

| Cycle | State | Why |
| --- | --- | --- |
| `CYCLE-QA` | `DEFECT_TRIAGE` | Validate before a failure becomes someone else's defect |
| `CYCLE-SEC` | `RELEASE_BLOCKED` | A HIGH or CRITICAL finding blocks the release regardless of where the cycle has reached; it leaves only by remediation or a human-granted exception |
| `CYCLE-SRE` | `INCIDENT_MODE` | During an incident the positions hold but the tempo does not; every production action still requires human authorization |

## The rollup

Produced by the lead on `ACCEPTED`, and on any `ESCALATED` that leaves the
department. It lives in the `rollup:` block of the work-item set's artifact.

```
Story set: SFTP-STORY-042, SFTP-STORY-043
Status:    ACCEPTED

Backend    PASS      Frontend   PASS      Data      PASS
Reviews    PASS      Findings   0 critical, 0 high, 2 medium
Rework     2 rounds  Escalations  none
Next gate  WF-FEATURE/REVIEW
```

A head reading every review comment is doing the lead's job and cannot see the
department. A head reading a rollup can tell whether the department is healthy —
and `rework_rounds` is the number worth watching.

Full format in [`templates/artifacts/rollup.md`](../templates/artifacts/rollup.md).

## Two dimensions of loop

**Intra-department** — worker → peer → lead → worker → accept. Bounded at 3
rounds. Everything above.

**Cross-department** — the macro `failure_paths` in `sdlc/workflows/`. QA raises
a validated defect → Development fixes → QA verifies. Security returns a HIGH
finding → Development fixes → Security re-reviews. DevOps finds the design cannot
be deployed → Architecture revises → Development implements → DevOps retries.

They are different mechanisms and are kept separate. An intra-department loop
that keeps failing becomes an escalation, and an escalation that leaves the
department becomes a cross-department loop with its own artifacts and gates.

## What this enforces, mechanically

```bash
python3 scripts/check_cycle.py
```

- Every state is reachable, and every state can reach a terminal state.
- No dead ends. Work that enters a state can always leave it.
- Both reviews can request changes — a review that can only pass is not a review.
- `CHANGES_REQUESTED` returns to `IN_PROGRESS`, and reaching the rework limit
  leaves it for `ESCALATED`.
- `ACCEPTED` is reachable **only** from `ACCEPTANCE_REQUESTED` via `dod_pass`.
- Withdrawing an escalation reaches `WITHDRAWN`, never `ACCEPTED`. Dropping a work
  item is not the same as meeting its acceptance conditions, and the edge used to
  conflate them — which let a cancelled item satisfy a stage's definition of done
  with no predicate evaluated.
- The peer reviewer is never the worker, and cannot write the artifact it reviews.
- Where the lead is also the worker, the peer reviewer differs.
- Escalation runs worker → peer → lead → head → human owner, in that order.
- The head is an agent that can spawn its own lead, and is never a worker.
- The human owner is never an agent, states specific authority, and fills no
  operational position.
- The rollup is produced by the lead.
- Exactly one cycle claims each macro stage, in both directions.

Acceptance is not the head's to declare. The head *requests* it; `check_dod.py
--cycle` *determines* it, by evaluating the cycle's own `acceptance.conditions`:

```bash
python3 scripts/check_dod.py --cycle CYCLE-DEV --project /path/to/project
```

Anything short of every condition passing prints `NOT ACCEPTED` and exits non-zero.

Against a real project, `check_dod.py` evaluates the join:

```
FAIL   cycle_accepted(CYCLE-DEV)         not accepted: SFTP-STORY-043=ESCALATED
PASS   cycle_rollup_reported(CYCLE-DEV)  2 rollup(s) reported
FAIL   no_open_rework(CYCLE-DEV)         SFTP-STORY-043=4; open escalations
```

The macro `DEV` stage is not done, because the department's internal loop has not
closed.
