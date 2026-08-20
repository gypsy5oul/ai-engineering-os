---
name: incident-management
description: Run a production incident - severity, coordination, parallel investigation, mitigation under approval, recovery verification and handoff to RCA. Use when production is degraded, unavailable or behaving incorrectly.
---

# Incident management

Restore service without destroying the evidence that explains it.

## First five minutes

1. **State the symptom in one sentence**, in user-visible terms. "Checkout returns 500 for card payments since 14:02" — not "elevated errors".
2. **Declare severity** from the project's definitions. Severity drives who is woken, not how bad you feel.
3. **Open the record** and start timestamping. Everything after this point goes in it.
4. **Notify the human owner.** An agent never runs an incident alone.
5. **Ask what changed.** Deployments, configuration, feature flags, dependency incidents, certificate expiry, scheduled jobs, traffic. Most incidents are caused by a change, and the change is usually recent.

## Severity (default definitions; the project may override)

- **SEV1** — complete loss of a critical function, or data loss or exposure. Immediate human involvement.
- **SEV2** — major degradation or loss for a subset of users, with no workaround.
- **SEV3** — degradation with a workaround, or a non-critical function affected.
- **SEV4** — minor, no user impact.

Re-evaluate as facts arrive. Under-declaring to avoid waking someone is a failure mode.

## Investigation

Run hypotheses in **parallel**, not in sequence. Sequential investigation anchors on the first plausible theory. Assign each thread an owner and require each to state what evidence would disprove it.

Record every hypothesis and its outcome, including the rejected ones — they are the most valuable part of the record for the next incident.

## Mitigation

Mitigation restores service; it is not the fix. Prefer, in order: roll back the recent change, disable the affected feature, shed or throttle load, fail over, scale.

Every mitigation proposal states its blast radius and its own rollback. Every production action requires human approval (AP-01) — an agent proposes, a human executes or authorises.

Do not destroy evidence. No log rotation, pod deletion, state reset or queue purge that removes what the RCA will need, unless it is the mitigation itself and you have said so.

## Recovery

Declare recovery only when user-visible behaviour is verified, not when a graph returns to normal. Say what you verified and how.

Then decide whether the mitigation is safe to leave in place, and what must happen before it is removed.

## Handoff to RCA

Package: the timeline with sources, the hypotheses and their outcomes, the actions taken with approvals, the telemetry, and the open questions. Hand it to `rca-analyst`, who did not run the incident — that separation is deliberate.

## Communication

Say what is known, what is not known, what is being done, and when the next update comes. Never speculate about cause in an external communication before the RCA. "We are investigating" is honest; a wrong cause published early is a second incident.
