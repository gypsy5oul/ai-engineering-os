# Security template

## SECURITY_FINDING
```
🔐  Security finding — {severity}
    Area    {area}
    Subject {subject}
    Status  {status}
```

**No exploitation path, no reproduction, no affected endpoint detail.** A chat
space is not an access-controlled vulnerability tracker, and a finding posted
with its exploitation path is a disclosure. Link to the finding record.

## SECURITY_BLOCKED
```
⛔  Release blocked — {finding_id} ({severity})
    Release {release_id}
    Until   remediated, or an exception is granted by {security_owner_role} (AP-04)
```

Urgent. Goes to security and releases.

## SECURITY_EXCEPTION_GRANTED
```
📝  Security exception — {finding_id}
    Granted by      {approver_role} (AP-04)
    Residual risk   {residual_risk}
    Compensating    {compensating_control}
    Expires         {expires}
```

An exception without an expiry is a policy change in disguise, so the expiry is
always shown.

## DEPENDENCY_ADVISORY
```
📦  {dependency} — {route}
    Urgency basis {urgency_basis}
    Current {current} → {target}
```

Urgency comes from exploitability in this deployment or a support end date, never
from a CVSS score alone — so the message shows the basis, not the score.

## Rules

- Severity and area only. Detail lives in the finding record.
- Never post a credential, a token fragment, or a stack trace.
- A security message is never an exception grant. That is AP-04, recorded by a
  named human.
