# Measuring the organization

An engineering organization that cannot say whether it is improving is a set of
opinions. The point of keeping a durable record is that these numbers are
*derived* from it rather than estimated.

```bash
python3 scripts/telemetry.py --project /path/to/project
```

```
WORK
  3 work item(s): 0 accepted, 3 in progress, 0 escalated, 0 cancelled
  41 task(s), 6 accepted

QUALITY
  rework rate               14%   of the 7 task(s) anyone actually worked
  attempts per task       0.29
  escalation rate          100%   of decisions
  repeated failure         100%   of escalations were the same failure twice

HUMAN INTERVENTION
   1.33 per work item
    approvals                0
    reached a human          1
    open decisions           0
    replans                  3   the plan a human accepted was wrong
```

## The metric that matters

**Human intervention rate: how many times a person had to act, per unit of work,
for it to progress.**

The goal is not zero. A system that never asks a human has either solved
engineering or stopped noticing when it should ask, and the second is far more
likely. What the number is for is the *trend* — whether autonomy is increasing
while the gates that matter stay in place.

What counts:

| Counts | Does not count |
| --- | --- |
| An approval recorded against a work item | An agent verdict — the organization reviewing itself |
| An escalation that reached the human owner | An escalation a lead or head resolved |
| An open decision the organization refused to guess | A guard denial — that is the system working |
| A replan, because the plan a human accepted was wrong | |

## Two denominators worth arguing about

**Rework is measured against work attempted, not work planned.** A graph of forty
tasks with three attempted is not a 7% rework rate.

**Rework comes from the history, not the graph.** A replan rebuilds the graph and
resets attempts to zero, so a change that fought hard and was then replanned would
report as having gone smoothly. That is flattering and exactly backwards, and it
is the reason `history.jsonl` is append-only. This was a real bug in the first
version, and `tests/test_telemetry.py` keeps it fixed.

## What is not measured, and why

A metric that cannot be computed from the durable record is listed here with the
reason, never estimated. An organization that reports a number it cannot derive
teaches its own people not to trust the rest of them.

| | Why not |
| --- | --- |
| **Token cost** | `SubagentStop` carries no usage figures. The `task-notification` block does, and nothing parses it. |
| **Wall clock per task** | Only `started_at` and `last_activity` exist, which measure elapsed time. A task that sat overnight and one that ran for eight hours look identical. |
| **Defect escape rate** | Needs production defects traced to the change that caused them. The link exists in the artifact model; nothing populates it. |
| **Agent utilisation** | Needs a spawn count per role over time. The audit log has the events; nothing aggregates them. |

`check_telemetry_policy_is_live()` enforces both directions: a metric the policy
claims is computed must exist in the code, and a metric it disclaims must **not**
quietly appear in the output — because the reason it was disclaimed still applies.

## A rate of `n/a` is not a rate of zero

`0%` and *"we have not seen one of those yet"* are different claims, and only one
of them should influence a decision.
