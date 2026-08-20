# Liveness and limits

Two questions the state machines cannot answer about themselves.

## What if nothing happens?

Every state machine here says what may happen next. None says how long the wait
may be. A workflow can be perfectly correct and stall forever: a review nobody
picks up, an escalation nobody answers, a decision nobody makes. **Correctness
does not imply progress**, and an autonomous organization that waits politely and
indefinitely has failed just as surely as one that does the wrong thing.

`policies/sla-policy.json` sets how long an item may sit in one state before
someone is told, and who. `scripts/check_liveness.py` answers it:

```bash
python3 scripts/check_liveness.py --project /path/to/project
python3 scripts/check_liveness.py --project . --emit    # write events
```

```
ITEM                   STATE              AGE      THRESHOLD   TELL
ACME-STORY-002         IN_PROGRESS         51.0h      48.0h    lead
ACME-DEC-001           open                48.0h      36.0h*   human_owner
ACME-STORY-001         in-review           27.0h      24.0h    head

* a blocking decision is measured on half the stated threshold: work is
  stopped behind it.
```

Exit `1` when something is stale, so a caller can act on it.

### The ladder

`lead → head → human_owner`. Most staleness is a lead's to clear. The head is
reached when the lead has had time and it is still stuck. A human is reached only
for decisions no agent may take, or when the organization has had long enough that
the silence is itself the problem.

The most severe threshold an item has passed wins, so a review stuck 27 hours goes
to the head rather than generating two notifications.

### A blocking decision runs on a shorter clock

A `DEC` marked blocking halves every threshold. An ordinary open question can
wait; one with work stopped behind it is a different kind of waiting. A `DEC`
exists because an agent refused to guess — leaving it open turns that refusal into
the delay it was meant to prevent.

### This is not a scheduler

Claude Code has no persistent background process this plugin can rely on, so
**nothing here fires by itself**. It answers the question when it is run: from a
session, from CI, or from whatever timer the project already has. Saying otherwise
would be a watchdog that does not watch, and `policies/sla-policy.json` says so in
its own text rather than leaving it to be discovered.

### False positives are the real risk

A staleness report that fires on healthy work is one people learn to ignore, and
then it is worse than not having it. Accepted work, resolved decisions and
anything that moved recently are silent, and `tests/test_liveness.py` spends as
many cases proving that as proving detection.

## How much may one role run at once?

Spawn authority answers *whether* a role may delegate. It never answered *how
much*. `engineering-director` may spawn thirteen kinds of agent, and nothing
stopped it spawning thirteen for a one-line change — each one a full Claude
session.

`policies/concurrency-policy.json` caps it, and `guard_spawn.py` enforces it:

| Role | Concurrent | Why |
| --- | --- | --- |
| `engineering-director` | 6 | Forms cross-functional teams, so it legitimately fans out widest |
| `incident-commander` | 4 | An incident needing more than four investigators needs a second commander |
| `development-lead` | 4 | One worker per parallel stream |
| `qa-lead` | 3 | Test execution parallelises; test design does not |
| `product-manager` | 2 | Requirements and UX together |
| `security-architect` | 2 | Security and dependency review together |
| *any other role* | 2 | |
| **whole session** | **10** | Across every role at once |

**It escalates rather than denies.** A wide fan-out is sometimes correct, and the
person running the session is the one who can tell. What must not happen is that
sixteen sessions get spawned without anyone choosing it.

### The count is measured, not declared

`hooks/lib/ledger.py` records each allowed spawn and clears it when the work ends.
A hook is a fresh process every time, so this has to live on disk.

Entries **expire** after 30 minutes. The hook cannot reliably correlate a
subagent's end with its start, and a ledger that only cleared on an explicit close
would leak slots until a role could never delegate again. An expiring entry can
undercount; a leaking one eventually blocks everything. For a guardrail against
runaway fan-out, undercounting is the safer failure.

### What it does not see

- Teammate spawns Claude Code performs outside the `Agent` tool.
- Other sessions. The count is per session, so two sessions doing the same work
  do not see each other.
- A subagent that ends with no stop signal at all, until its entry expires.

### The hierarchy still wins

Being under the limit does not make a forbidden spawn allowed. The concurrency
check runs only after `may_spawn` has already permitted the edge.

## Both are fault-tested

`F-16` stalls a review for three days and requires it to be reported. `F-17` fans
a role out past its cap and requires the spawn to escalate. Both are
mutation-tested: disable the control and the fault must start failing.
