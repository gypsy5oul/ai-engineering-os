---
name: root-cause-analysis
description: Produce a post-incident analysis - timeline, root cause, contributing factors, detection gaps and typed corrective actions. Use after any significant incident, and when a defect's underlying cause matters more than the immediate fix.
---

# Root cause analysis

Explain why the system permitted this, and what specifically changes as a result.

## Timeline first

Reconstruct from evidence with sources: deployment records, telemetry, logs, alerts, chat, the incident record. For each entry: timestamp, what happened, how we know.

Mark clearly which entries are **observed** and which are **inferred**. Blurring the two is how a confident wrong cause gets published.

Include what happened before the incident began. The change that caused it usually landed earlier and sat harmless until a condition arrived.

## Distinguish three things

- **Trigger** — what made it start now. ("Traffic doubled at 14:00.")
- **Root cause** — the condition that made it possible at all. ("The connection pool was sized for a single instance and had no queueing behaviour.")
- **Contributing factors** — what made it worse, slower to detect or slower to fix.

Fixing the trigger fixes nothing. Traffic will double again.

## "Human error" is never a root cause

If someone ran the wrong command, the finding is: why did the system allow a single command to cause this, why was it not caught, and why was it not reversible. People will keep making mistakes; systems can be built to absorb them.

## Detection gaps — ask at every stage

| Stage | Question |
| --- | --- |
| Requirements | Was the condition ever considered? |
| Architecture | Was this failure mode designed for? |
| Review | Would a reviewer have seen it? Why did nobody? |
| Test | What test would have caught it, and why did it not exist? |
| CI | Could a pipeline stage have caught it? |
| Monitoring | Why did we learn from a customer instead of an alert? |
| Runbook | Did the responder have what they needed? |

Each gap becomes a corrective action or an explicit decision to accept it.

## Corrective actions

Every action has: an owner, a **type**, an acceptance criterion, and a target. Types map directly onto work:

- defect
- technical debt
- architecture change
- new requirement
- monitoring improvement
- automation work
- process or documentation change

"Be more careful" is not an action. "Add a pool-saturation alert at 80% with runbook RB-14, owner: platform" is.

Distinguish **corrective** (stops this recurring) from **preventive** (stops the class recurring). Most RCAs produce only corrective actions and the same class returns in a different shape.

## Repetition

Check prior RCAs. A cause that has appeared before is not a new finding; it is evidence that a previous corrective action was not effective, and that is escalated to the human owner as a process failure.

## Output

Store in `docs/rcas/` with an artifact header linking the incident, the defects created and the requirements raised. The RCA is not complete until every action exists in a backlog with an owner.
