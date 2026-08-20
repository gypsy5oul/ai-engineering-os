---
name: observability
description: Design SLIs, SLOs, metrics, logs, traces, alerts and runbooks, and assess whether a change is observable in production. Use when defining monitoring, reviewing operational readiness, or when an incident revealed that nobody could see what was happening.
---

# Observability

The test is simple: when this breaks at 03:00, can the responder tell what is wrong from the telemetry alone?

## SLIs and SLOs

An SLI measures what users experience: request success rate, latency at a percentile, freshness, correctness. Not CPU.

An SLO is a target on an SLI over a window, derived from a **stated requirement**. If no availability or latency requirement exists, say so — inventing "99.9%" creates a constraint nobody chose and a budget nobody agreed to.

The error budget follows from the SLO and is the mechanism for deciding whether to ship or to stabilise.

## The three signals

**Metrics** — aggregate, cheap, good for alerting and trends. Watch cardinality: a label with unbounded values (user id, request id, URL path with parameters) will eventually cost more than the service.

**Logs** — structured, with a consistent set of fields: timestamp, level, service, version, trace id, and the identifiers that let you follow one request. Never log secrets, tokens or personal data; log identifiers instead. Log at boundaries and at decisions, not on every line.

**Traces** — for anything crossing a process boundary. Propagate context through every hop including asynchronous ones, or the trace stops where the interesting part starts.

Correlate them: the same trace id in logs, traces and error reports turns three tools into one investigation.

## Alerts

An alert exists to make a human act. Therefore:

- Alert on **symptoms** users feel, not on causes. "Checkout error rate above 2%" beats "CPU above 80%".
- Every alert names its runbook.
- Every alert states what action to take. An alert with no action is deleted, not tuned.
- Page only for what needs a human now. Everything else is a ticket or a dashboard.
- Tune for the false-positive rate you can sustain. A team that ignores alerts has no monitoring.

## Runbooks

Written for someone woken up: what this alert means, how to confirm it, the first three things to check, the mitigations with their blast radius, how to verify recovery, and when to escalate to whom. Keep them next to the alert definition so they change together.

## Reviewing a change for observability

- Does the new failure mode produce a signal?
- Can you tell the difference between "working", "degraded" and "down" from telemetry?
- Is there an alert, and does it have a runbook?
- Do new fields carry any secret or personal data into logs?
- Does any new metric label have unbounded cardinality?
- Is the deployment itself visible in telemetry, so a correlation with a release is possible?

## Cost

Telemetry is not free. State the retention and the volume implication of what you add. Uncontrolled log growth becomes a budget conversation that ends with sampling being applied by someone who does not know which logs matter.
