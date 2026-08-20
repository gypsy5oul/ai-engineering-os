# Engineering communications

The third platform capability, alongside SDLC and governance.

```
        SDLC                Governance          Communications
    workflows · agents    policies · gates    events · policy
    artifacts · cycles    approvals           notifications · digests
          └───────────────────┼───────────────────┘
                              ▼
                           GitLab
```

## The shape

```
   SDLC stages and department cycles
              │  emit structured events (facts only)
              ▼
        event log  (append-only)
              │
              ▼
   POLICY ENGINE  scripts/route_event.py   ── deterministic. No model.
              │   should anyone be notified · who · which channel · which thread
              ▼
   NOTIFICATION AGENT                      ── formats. Only formats.
              │
              ▼
   bin/aieos-notify                        ── dispatch. Secret from the environment.
              │
              ▼
   Google Chat incoming webhook
```

**The notification subsystem is never the event source.** It cannot ask "did
anything happen". If the SDLC did not emit an event, nothing is sent.

**Every event names its change, and its cause.** `correlation_id` gathers one
change's events; `causation_id` names the event that caused this one, so the
chain can be walked backwards from any point. `scripts/route_event.py --trace
<correlation-id>` prints one change end to end and `--verify-chains` proves the
log is intact. See [docs/communications.md](../docs/communications.md).

**Policy routes, the model writes.** Routing and recipients are deterministic.
The agent receives a routing decision and turns it into a readable message. It
cannot decide who is told, or whether anything is sent at all.

## Files

| | |
| --- | --- |
| `event-catalogue.json` | 58 event types, each with a level and what emits it, plus the standard fields every event carries |
| `notification-policy.json` | 58 routing rules, suppression, aggregation, digests |
| `channels.json` | Chat spaces. **No webhook URLs** — environment variable names only |
| `templates/` | Message formats, per subject kind |

## Levels mirror the SDLC hierarchy

| Level | Notify | Because |
| --- | --- | --- |
| worker | **never** | One agent's activity on one item. Recorded, never pushed. |
| team | immediate | The working team must act. |
| department | aggregate | It is already a rollup; sending it repeatedly adds noise. |
| organization | immediate | A lifecycle milestone. |
| incident | immediate | Someone responds now. |

This is why Level 2 rollups matter here: ten workers on one feature produce **one**
department update, not thirty worker events.

## The secret

A Google Chat incoming webhook URL is a bearer credential. It lives in a masked
CI variable or the project's secret manager, and is passed to `bin/aieos-notify`
through the environment. It never enters this repository — `secret_scan.py` runs
over the whole tree in CI, and the write guard denies credential-shaped content.

If one leaks, rotate it in the Chat space. Deleting the file does not un-publish it.

## What this is not

- **Not interactive.** An incoming webhook is one-way. `@bot status FEAT-103`
  needs a real Google Chat app handling interaction events, which V1 does not
  ship.
- **Not an approval channel.** A chat message must never become production
  authorization. Approvals live in GitLab; see `policies/approval-authority.json`.
- **Not a log.** If it would be noise in a space, it belongs in the event log and
  the digest.
