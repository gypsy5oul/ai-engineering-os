# Weekly summary template

Posted Friday afternoon to `engineering-announcements`. The management view.

```
Weekly Engineering Report — {project}  ·  week ending {date}

FEATURES        {completed} completed · {started} started · {in_flight} in flight

DEFECTS         {resolved} resolved · {reopened} reopened · {escaped} escaped to production
                Reopen rate {reopen_rate}

DEPLOYMENT      {releases} releases · {rollbacks} rollbacks
                Lead time {lead_time} · Change failure rate {cfr}

RELIABILITY     {availability} availability · {incidents} incidents ({sev1} SEV1)
                MTTR {mttr}

SECURITY        {critical} critical · {findings} findings · {exceptions_granted} exceptions granted
                {exceptions_expiring} exceptions expiring within 30 days

AI ENGINEERING  {evaluations} agent evaluations · {promoted} promoted · {downgraded} downgraded
                {skills_updated} skills updated · {guard_changes} guard rule changes

TOP BLOCKERS
   {blockers}

TRENDS WORTH WATCHING
   {trends}
```

## Trends worth watching

This is the section that earns the report. Not counts — changes in shape:

- Rework rounds rising in one department. The acceptance criteria or the design
  is the problem, not the implementation.
- Reopen rate rising. Fixes are being accepted that should not be.
- The same RCA root cause appearing twice. A previous corrective action was not
  effective, and that is a process failure, not a new incident.
- An exception approaching expiry with no remediation.
- A `DEC` open longer than a week. Somebody is working around it instead of
  closing it.

## Rules

- Trends are computed from the event log across weeks, not asserted.
- Say when a number is not comparable — a short week, a changed measurement.
- No individual attribution, ever. This report is read by people who have power
  over careers.
