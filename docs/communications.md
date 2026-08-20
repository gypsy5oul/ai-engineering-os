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

## The event catalogue

41 types. Each declares its level, what emits it, and its payload fields.
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
| `notification/event-catalogue.json` | 41 event types |
| `notification/notification-policy.json` | 41 routing rules, suppression, aggregation, digests |
| `notification/channels.json` | Spaces and admission rules. **No URLs** |
| `notification/templates/` | Message formats per subject kind |
| `scripts/emit_event.py` | Append one event to the log |
| `scripts/route_event.py` | The policy engine |
| `scripts/notify_digest.py` | Daily and weekly counts |
| `bin/aieos-notify` | Dispatch |
| `agents/notification-agent.md` | The formatter |
| `skills/engineering-notifications/SKILL.md` | How to write the message |
