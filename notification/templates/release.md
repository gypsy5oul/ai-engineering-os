# Release template

The release chain is four distinct acts, and each gets its own message — because
collapsing them is exactly the failure `policies/release-authority.json` exists
to prevent.

## RELEASE_PLANNED
```
📦  {release_id} planned
    Contents   {change_count} changes
    Migrations {migration_count} ({irreversible} irreversible)
    Rollback   {rollback_state}
```

## RELEASE_APPROVED
```
✅  {release_id} content approved — AP-01 by {approver_role}
    This approves the CONTENT. Deployment is authorized separately.
```

## DEPLOYMENT_AUTHORIZED
```
🔓  {release_id} deployment authorized — AP-01 by {approver_role}
    Window {window}
```

## DEPLOYMENT_STARTED / COMPLETED
```
🚀  {release_id} deploying to {environment}
```
```
✅  {release_id} deployed and verified — {duration}
    Verification {verification}
    Rollback available until {rollback_until}
```

## DEPLOYMENT_FAILED
```
🚨  {release_id} FAILED in {environment}
    Trigger  {trigger}
    Rollback {rollback_state}
    Next     {next_action}
```

Urgent. Goes to incidents, releases and announcements at once.

## Rules

- **A release message is never an approval.** It reports that a human approved in
  GitLab. Nobody approves by replying in chat.
- Always state which act this is. "Approved" without saying whether that means
  content or deployment is the ambiguity the split removed.
- Always state the rollback state. A deployment message without it is incomplete.
