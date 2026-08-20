# Department rollup

Produced by the **lead**, read by the **head**. It goes in the `rollup:` block of
the work-item set's artifact (the story, epic or change), not in a separate file.

The head reads this and never the individual review rounds. A head reading every
review comment is doing the lead's job and cannot see the department; a head
reading a rollup can tell whether the department is healthy.

```yaml
rollup:
  cycle: CYCLE-DEV
  status: ACCEPTED            # ACCEPTED | ESCALATED | IN_PROGRESS
  produced_by: development-lead
  at: 2025-11-12
  streams:
    - stream: backend
      assignee: backend-developer
      state: READY_FOR_INTEGRATION
      verdict: pass
    - stream: frontend
      assignee: frontend-developer
      state: READY_FOR_INTEGRATION
      verdict: pass
    - stream: data
      assignee: data-engineer
      state: READY_FOR_INTEGRATION
      verdict: pass
  reviews:
    peer: pass
    test-reviewer: pass
    security-reviewer: not-applicable
  open_findings:
    critical: 0
    high: 0
    medium: 2
  rework_rounds: 2
  escalations: []
  artifacts: [SFTP-STORY-042, SFTP-STORY-043]
  next_gate: WF-FEATURE/REVIEW
```

Rendered, that is what the head actually sees:

```
Story set: SFTP-STORY-042, SFTP-STORY-043
Status:    ACCEPTED

Backend    PASS      Frontend   PASS      Data      PASS
Reviews    PASS      Findings   0 critical, 0 high, 2 medium
Rework     2 rounds  Escalations  none
Next gate  WF-FEATURE/REVIEW
```

## What belongs here, and what does not

| In the rollup | Not in the rollup |
| --- | --- |
| Per-stream state and verdict | Individual review comments |
| Aggregate finding counts by severity | Each finding's text |
| Total rework rounds | Which round found what |
| What escalated, and to whom | The escalation conversation |
| Artifact ids produced | Artifact contents |

`rework_rounds` is the number worth watching. Two is ordinary. A pattern of four
across a department means the acceptance criteria, the design or an unwritten
disagreement is the real problem, and no amount of further looping will surface
it.

## When it is produced

On `ACCEPTED`, and on any `ESCALATED` that leaves the department. A department
that completed without reporting has not finished:
`cycle_rollup_reported(CYCLE-*)` is part of the macro stage's definition of done.
