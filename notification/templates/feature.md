# Feature thread template

One thread per feature, keyed on the subject id. Every lifecycle update replies
into the same thread, so the whole timeline is in one place.

## Thread opener — FEATURE_CREATED

```
🆕  {subject} — {title}

Entered the SDLC.
Stage      Requirements
Owner      {owner_role}
Next       Requirements analysis
```

## Replies

```
✅  Requirements approved — {requirement_count} requirements, {nfr_count} NFRs
    {open_decisions} open decision(s) blocking architecture
```
```
✅  Architecture approved — {adr_count} ADRs · AP-02 by {approver_role}
```
```
📋  {story_count} stories created across {stream_count} streams
```
```
🧪  QA test plan approved — {scenario_count} scenarios, {uncovered} area(s) not covered
```
```
💻  Development update
    Backend   {backend}
    Frontend  {frontend}
    Data      {data}
    {complete}/{total} complete · {in_review} in review · {blocked} blocked
```
```
🔴  Blocked — {story_id}: {reason}
    Escalated to {to}
```
```
❓  {decision_id} open — {question}
    Blocks: {blocks} · Owner: {owner_role}
```

## Rules

- **The thread key is the subject id.** A feature's whole timeline is one thread.
- **Development updates are rollups**, never individual worker activity. Ten
  workers on one feature produce one message.
- **Never name an individual for worker-level work.** Roles and streams only.
- **State the next step.** An update that says what happened but not what is
  waiting is a log line, not a notification.
- Emoji carry state, not decoration: 🆕 new · ✅ passed · 🟡 in progress ·
  🔴 blocked · ❓ decision needed · 🚨 incident.
