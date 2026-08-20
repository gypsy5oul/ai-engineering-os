# Daily summary template

Posted once, at the project's configured time, to `engineering-announcements`.
Built from the event log by `scripts/notify_digest.py` — deterministic counts,
not a model's recollection.

```
Engineering Daily Summary — {project}  ·  {date}

🚀 FEATURES
   {active} active · {completed} completed today · {awaiting} awaiting approval

💻 DEVELOPMENT
   {stories_complete} stories complete · {in_review} in review · {blocked} blocked
   Rework rounds today: {rework_rounds}

🧪 QA
   {tests_executed} executed · {passed} passed · {failed} failed
   {open_defects} open defects ({critical} critical, {high} high)

🔐 SECURITY
   {critical_findings} critical · {high_findings} high · {open_exceptions} open exceptions

🚢 RELEASE
   {release_state}

🚨 INCIDENTS
   {incident_state}

⛔ BLOCKERS
   {blockers}
```

## What belongs in blockers

Only things that are stopping work and have an owner:

```
   DEF-421   authentication regression — qa-owner
   DEC-17    database choice pending — project-owner  (blocking ARCH, 3 days)
```

An open decision's **age** matters more than its existence. A `DEC` open for
three days is a different message from one opened this morning.

## Rules

- **Counts come from the event log**, not from asking a model what it remembers.
- A section with nothing in it says so — "No active incidents" — rather than
  being omitted. An absent section reads as an omission, not as good news.
- Never list individuals. Roles and ids.
- If the digest would be entirely empty, send it anyway. Silence is ambiguous:
  it could mean a quiet day or a broken pipeline.
