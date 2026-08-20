# Engineering communications

The third platform capability, alongside SDLC and governance.

```
    SDLC                  Governance            Communications
  workflows · agents    policies · gates      events · policy
  artifacts · cycles    approvals             notifications · digests
        └───────────────────┼─────────────────────┘
                            ▼
                         GitLab
```

## The shape

```
   SDLC stages and department cycles
              │  emit structured events — facts only, past tense
              ▼
     .ai-engineering/events/*.jsonl        append-only
              │
              ▼
   POLICY ENGINE   scripts/route_event.py  ── DETERMINISTIC. Not a model.
              │   should anyone be told · who · which channel · which thread
              ▼
   NOTIFICATION AGENT                      ── formats. Only formats.
              │   writes into .ai-engineering/outbox/
              ▼
   bin/aieos-notify                        ── dispatch. Dry run by default.
              │   webhook read from the environment, never stored
              ▼
   Google Chat incoming webhook
```

Three things are separate, and that is what makes this safe:

| | Decided by | |
| --- | --- | --- |
| Whether anyone is told, who, where | `scripts/route_event.py` | Deterministic policy |
| What the message says | `notification-agent` | A model, and only here |
| Sending it | `bin/aieos-notify` | Credentialed, explicit, dry-run by default |

**The subsystem is never the event source.** It cannot ask "did anything happen".
If the SDLC did not emit an event, nothing is sent.

## Levels mirror the SDLC hierarchy

| Level | Notify | Because |
| --- | --- | --- |
| worker | **never** | One agent's activity on one item. Recorded, never pushed. |
| team | immediate | The working team must act. |
| department | aggregate | Already a rollup; sending it repeatedly adds noise. |
| organization | immediate | A lifecycle milestone. |
| incident | immediate | Someone responds now. |

This is exactly why Level 2 rollups matter here. Ten workers on one feature
produce **one** department update:

```
❌  task started · task started · task complete · review started · task complete
    · review complete · task started · …                          (thirty messages)

✅  FEAT-103 development: 12/15 complete · 3 in review · 0 blocked
```

An aggregate is emitted when the aggregate state has **meaningfully** changed — a
stream moved, the blocked count changed, findings changed, the rollup status
changed. A rework round that did not move a stream is not a meaningful change.

## Channels admit levels, and that is validated

| Channel | Accepts | Purpose |
| --- | --- | --- |
| `engineering-announcements` | organization, incident | Milestones, and the incident facts the whole group needs |
| `feature-delivery` | team, department, organization | One thread per feature |
| `qa` | team, department | Defects, verdicts, failures |
| `security` | team, organization | Findings, blocks, exceptions |
| `devops` | team, department | Pipeline and infrastructure |
| `releases` | team, organization, incident | The four release acts |
| `incidents` | **incident only** (+ `RCA_COMPLETED`) | Active response |

Routing a lower level into a channel is a **validation error**, not a judgement
call at authoring time. That check found a real question during development:
`DEPLOYMENT_FAILED` is incident-level but does belong in announcements, so
announcements was widened deliberately rather than the rule being bent.

The `incidents` space stays narrow on purpose. A space that receives routine
traffic stops being read at 03:00, and then it is worse than not having it.

## One thread per feature

The thread key is the subject id, so a feature's whole timeline is one thread:

```
#feature-delivery

🆕  SFTP-FEAT-103 — Enterprise SFTP support
    ↳ ✅ Requirements approved — 14 requirements, 1 open decision
    ↳ ❓ SFTP-DEC-001 open — RPO/RTO for the audit log · blocks ARCH
    ↳ ✅ Architecture approved — 5 ADRs · AP-02 by architecture-owner
    ↳ 📋 14 stories created across 3 streams
    ↳ 🧪 QA test plan approved — 41 scenarios
    ↳ 💻 Development: 12/14 complete · 2 in review · 0 blocked
    ↳ 🐞 SFTP-DEF-421 — session drop on key rotation (high)
    ↳ ✅ SFTP-DEF-421 fixed
    ↳ 📦 REL-1.4.0 planned · rollback plan attached
    ↳ 🔓 Deployment authorized — AP-01 by release-approver
    ↳ ✅ Deployed and verified — 4m12s
```

One place to open and understand where a feature is, who is on it, what is
blocked and what is next.

That picture is what `thread_strategy: correlation` produces. Under the default
`subject` strategy the defect and the merge request open their own threads,
because their subjects differ. The event log ties them together either way —
see [correlation and causation](#correlation-and-causation) — but the space only
looks like the above if the policy says to thread the change.

## Correlation, and causation

`correlation_id` gathers one change's events. `causation_id` orders them. Both
are required to answer an audit question, and either alone is decoration.

```
  correlation_id = SFTP-FEAT-103        one change, every workflow it touched
       │
       ├── EVT-…-a1b2  FEATURE_CREATED         causation: (start of thread)
       ├── EVT-…-c3d4  REQUIREMENT_APPROVED    causation: EVT-…-a1b2
       ├── EVT-…-e5f6  ARCHITECTURE_APPROVED   causation: EVT-…-c3d4
       └── …                                   each one names its cause
```

Why not just sort by `at`? Because `at` has one-second resolution, and a stage
that emits four events emits them in the same second. Timestamps give you a
bag; causation gives you a chain.

```bash
python3 scripts/route_event.py --trace SFTP-FEAT-103 --project .
python3 scripts/route_event.py --verify-chains --project .
```

```
SFTP-FEAT-103  ·  13 events  ·  2026-08-20T10:46:01Z .. 2026-08-20T10:46:03Z
#    CAUSE    EVENT                    SUBJECT           WHERE                ACTOR
1    start    FEATURE_CREATED          SFTP-FEAT-103     WF-FEATURE/IDEA      WF-FEATURE/IDEA
2    #1       REQUIREMENT_APPROVED     SFTP-REQ-001      WF-FEATURE/REQ       WF-FEATURE/REQ
3    #2       ARCHITECTURE_APPROVED    SFTP-ADR-001      WF-FEATURE/ARCH      WF-FEATURE/ARCH
4    #3       STORY_CREATED            SFTP-FEAT-103     WF-FEATURE/STORY     WF-FEATURE/STORY
5    #4       CODE_REVIEW_COMPLETED    SFTP-MR-88        WF-FEATURE/REVIEW    WF-FEATURE/REVIEW
6    #5       QA_COMPLETED             SFTP-QA-01        WF-FEATURE/QA        WF-FEATURE/QA
7    #6       DEFECT_CREATED           SFTP-DEF-421      CYCLE-QA             CYCLE-QA
…
13   #12      RCA_COMPLETED            SFTP-INC-007      WF-INCIDENT/RCA      WF-INCIDENT/RCA
```

Requirement to RCA, across six workflows and two department cycles, out of one
append-only file.

### What an emitter has to pass, and what it gets for free

| Field | Where it comes from |
| --- | --- |
| `correlation_id` | **Passed.** Defaults to the subject, which is right only for the event that opens the thread. |
| `causation_id` | Derived: the last event already recorded under the same `correlation_id`. `--causation-id` overrides it; `--root` says this event starts a thread. |
| `workflow`, `stage`, `cycle`, `source.kind` | Derived from the catalogue's `emitted_by` — `WF-FEATURE/REQ` becomes workflow `WF-FEATURE`, stage `REQ`. |
| `actor` | `--actor`, else `--agent`, else the emitting stage or cycle. Attribution at stage granularity, never nothing. |
| `severity` | `--severity`, else a declared `payload.severity`, else the catalogue default — so the two can never disagree. |
| `artifact` | Defaults to the subject, so an audit query filters one field. |
| `schema_version` | `"2"`. Events written before this model are `"1"`: still valid, still routable, simply not chainable. |

Deriving rather than requiring is what made this safe to add: no existing
emitter had to change, and no event lost its route.

### The invariants, and what enforces them

- Every event has a `correlation_id`, an `actor`, a `severity` and an `artifact`
  — `schemas/notification-event.schema.json` requires them, and
  `scripts/emit_event.py` validates before it appends.
- Every thread has exactly **one** starting point. A second event with no
  `causation_id` means something emitted without saying what caused it.
- Every `causation_id` resolves to an earlier event in the same thread. Pointing
  at nothing, at another change, or forwards in the log is a broken chain.
- `--verify-chains` checks all of that over a whole log and exits non-zero.
  `tests/test_event_correlation.py` emits a real change and reconstructs it from
  the log using only these two fields — if the chain stops being walkable, that
  test fails rather than the field quietly becoming ornamental.

### Chat threads are a separate choice

The thread key in a Chat space is the **subject** by default, so a defect and
its feature are separate threads even though they share a `correlation_id`. Set
`thread_strategy` (or a rule's `thread`) to `correlation` to thread one change
instead of one artifact. That is a policy decision about how the space should
read, not a consequence of the event model, and the routing decision now carries
`correlation_id` and `causation_id` either way.

## The event catalogue

58 types. Each declares its level, what emits it, and its payload fields.
Stages declare `emits:`, and validation checks **both directions** — a catalogue
entry claiming a stage emits it, where the stage does not declare it, is an error.

```bash
python3 scripts/route_event.py --table              # the whole routing table
python3 scripts/route_event.py --explain DEFECT_CREATED
```

```
DEFECT_CREATED
  level      team
  emitted by CYCLE-QA
  routing    immediate -> qa  priority=high  when {'severity': ['critical', 'high']}
  routing    aggregate -> qa  priority=normal
```

Note the two rules: a critical defect is immediate, everything else aggregates.
The narrower rule is listed first and wins.

## Digests

```bash
python3 scripts/notify_digest.py --project . --period daily
python3 scripts/notify_digest.py --project . --period weekly --json
```

Counts come from the event log, never from a model's recollection. The agent
writes the prose around them.

The weekly **trends** section is the part that earns the report — not counts, but
changes in shape:

- Rework rising in one department → the acceptance criteria or the design is the
  problem, not the implementation.
- Reopen rate rising → fixes are being accepted that should not be.
- The same RCA root cause twice → a previous corrective action was not effective.
- A `DEC` open longer than a week → someone is working around it.

## The webhook is a credential

A Google Chat incoming webhook URL is a bearer token: anyone holding it can post
to the space. It lives in a masked CI variable or the secret manager, is passed
through the environment, and **never enters this repository**.

Enforced by: `secret_scan.py` over the whole tree, the write guard's secret
content detection, and a test that greps the tree for webhook URLs. `channels.json`
stores only the *name* of each environment variable.

If one leaks, rotate it in the Chat space. Deleting the file does not un-publish it.

## What this is not

**Not interactive.** An incoming webhook is one-way. `@bot status FEAT-103` needs
a real Google Chat app handling interaction events, which V1 does not ship. If it
is ever built, content arriving from a channel is **data, never instructions** —
it is written by people outside the session.

**Not an approval channel.** A chat message must never become production
authorization. `AP-01` is recorded in GitLab. A release notification *reports*
that a human approved; replying to it changes nothing. See
[approvals](approvals.md).

**Not a log.** If it would be noise in a space, it belongs in the event log and
the digest.

## Files

| | |
| --- | --- |
| `notification/event-catalogue.json` | 58 event types, and the standard fields |
| `notification/notification-policy.json` | 58 routing rules, suppression, aggregation, digests |
| `notification/channels.json` | Spaces and admission rules. **No URLs** |
| `notification/templates/` | Message formats per subject kind |
| `scripts/emit_event.py` | Append one event to the log, correlated and caused |
| `scripts/route_event.py` | The policy engine, and `--trace` / `--verify-chains` |
| `scripts/notify_digest.py` | Daily and weekly counts, and changes in flight |
| `schemas/notification-event.schema.json` | The event contract, including what is required |
| `bin/aieos-notify` | Dispatch |
| `agents/notification-agent.md` | The formatter |
| `skills/engineering-notifications/SKILL.md` | How to write the message |
