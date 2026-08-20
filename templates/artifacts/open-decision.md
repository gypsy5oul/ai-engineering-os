---
id: <KEY>-DEC-000
type: open-decision
title: <The decision, as a question>
status: open             # open | answered | withdrawn | superseded
owner: <the human who can answer this>
version: 1
created_at: <YYYY-MM-DD>
updated_at: <YYYY-MM-DD>
source: <the stage or artifact that surfaced it>
reviewers: []
approvals: []            # the answer, recorded as a human decision
dependencies: []
links: {}
question: <one sentence, answerable>
options: []              # each with what it costs and what it forecloses
impact: <what changes depending on the answer>
blocks: []               # artifact codes that cannot progress: [ARCH, ADR]
decided_option: null
decided_at: null
---

## Question

One sentence, answerable. "Which backend framework is approved?" — not "what
should we do about the backend?"

## Options

| # | Option | Cost | What it forecloses |
| --- | --- | --- | --- |
| 1 | | | |
| 2 | | | |
| 3 | Do nothing / use what is already approved | | |

Option 3 is always present. It is the one most often missing and most often
correct.

## Impact

What changes depending on the answer, and which artifacts cannot be produced
until it is given. Fill `blocks:` with the artifact codes.

## Why this is an artifact and not a question in a chat

An agent blocked by this names it once — "cannot continue ARCH: SFTP-DEC-001 is
open" — and stops. Without the artifact, every new session re-asks the same
question and the answer lives in a transcript nobody can find.

## Decision

| Answered by | Role | At | Option | Rationale |
| --- | --- | --- | --- | --- |

Once answered, set `status: answered`, fill `decided_option`, and record the
answer as an approval entry with `approver_id` and `approver_role`.
