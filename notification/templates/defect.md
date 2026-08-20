# Defect and CI template

## DEFECT_CREATED

```
🐞  {defect_id} — {summary}
    Severity   {severity}
    Found in   {subject}
    Validated  by qa-lead ({triage_outcome})
    Next       {next_action}
```

Only defects that survived QA triage reach here. A tester observing a failure is
not a product defect: `not-a-defect`, `test-defect` and `environment-defect`
outcomes never generate a notification to development.

## DEFECT_REOPENED

```
🔁  {defect_id} reopened — attempt {attempt}
    The original reproduction still reproduces.
```

Always immediate, whatever the severity. A reopened defect means a fix was
accepted that should not have been.

## DEFECT_FIXED

```
✅  {defect_id} fixed — verified against the original reproduction
```

Aggregated. Individually these are low signal; the count matters.

## CI_FAILED

```
⚙️  CI failed — {pipeline} / {stage} / {job}
    {subject}
    {failure_line}
```

Aggregated, and suppressed when the same job failed inside the window. A pipeline
that fails ten times in an hour is one problem, not ten notifications.

## Rules

- Quote the shortest decisive line from a failure, never a log dump.
- Never include an exploitation path or a credential in a defect message.
- Severity comes from the defect record, not from the wording.
