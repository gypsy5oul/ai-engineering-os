# Incident template

The incidents space stays quiet so that it keeps its authority at 03:00. Only
incident-level events land here, and none of them are aggregated.

## INCIDENT_CREATED
```
🚨  {incident_id} — SEV{severity}
    {symptom}
    Started    {started_at}
    Commander  {commander}
    Owner      {on_call_owner}
```

Symptom in user-visible terms. "Checkout returns 500 for card payments since
14:02", not "elevated errors".

## INCIDENT_SEVERITY_CHANGED
```
⬆️  {incident_id} SEV{from} → SEV{to}
    {reason}
```

## INCIDENT_MITIGATED
```
🟡  {incident_id} mitigated — {mitigation}
    Authorized by {approver_role} (AP-01)
    This is a MITIGATION, not a fix. {what_is_still_true}
```

The distinction is the point. A mitigated incident is not a resolved one.

## INCIDENT_RESOLVED
```
✅  {incident_id} resolved — {duration}
    Verified by {verification}
    RCA owner {rca_analyst}
```

Recovery is declared from verified user-visible behaviour, not from a graph.

## RCA_COMPLETED
```
📋  {incident_id} RCA published
    Root cause  {root_cause}
    Actions     {action_count} typed and owned
    Detection gaps {gap_count}
```

## GUARD_SELFTEST_FAILED
```
🚨  SAFETY GUARDS ARE NOT WORKING — {guard}
    {detail}
    Do not rely on the guards in affected sessions.
```

## Rules

- **Never speculate about cause before the RCA.** "We are investigating" is
  honest; a wrong cause published early is a second incident.
- Never name an individual as a cause. "Human error" is not a root cause here
  either.
- Never post evidence, log contents or configuration into chat. Link to the
  incident record.
