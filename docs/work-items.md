# Work items and the task graph

## Why this exists when Claude Code has a task list

Claude Code ships `TaskCreate`/`TaskGet`/`TaskUpdate`/`TaskList`, backed by real
files at `~/.claude/tasks/<listId>/<taskId>.json` with genuine `blocks` and
`blockedBy` edges. Building a second one would be exactly what this repository
refuses to do.

So this is not a second one. The two answer different questions, and the
difference is where they live:

| | Claude Code's task list | This work item |
| --- | --- | --- |
| Lives in | `~/.claude/tasks/`, on one machine | the project's own repository, in source control |
| Survives | a resume, and a session end | a machine loss, a clone, and everyone forgetting |
| Scope | one session by default | the change, for as long as it takes |
| Carries | subject, status, edges | intent, objective, risk, definition of done, approvals, evidence, decisions, history |
| Reviewable | no | it is a diff |

The repository's oldest rule is that the session is not the system of record:
*delete every Claude session, and another engineer must be able to reconstruct
the work.* A task list under `~/.claude/` fails that test — not because it is
badly built, but because it is execution state, and execution state is supposed
to be disposable.

**Use both.** Native tasks are how a session tracks what it is doing right now.
The work item is what the organization knows. They are joined by stamping the
work item's id into a native task's `metadata`, which the model can write and
only a hook or a script can read back.

## The shape

```
.ai-engineering/work/SFTP-FEAT-001/
    work-item.yaml     intent, objective, owner, risk, stage, DoD, approvals
    graph.yaml         the tasks, their dependencies, their state
    history.jsonl      append-only: what happened, and every superseded plan
```

## Intent and objective are kept apart

`intent` is what the human said, verbatim. `objective` is what the organization
understood. They are separate fields because a plan that solves the wrong problem
is invisible when the only record is the restatement — and both are given to
every agent, so the agent can notice the gap rather than inheriting it.

## The graph is generated, not fixed

The declarative workflow says **what must be true**. The graph says **how this
change gets there**. It is built per work item from the workflow's stages, and a
stage that declares `optional_when` is dropped with its reason recorded.

One judgement is worth stating. `optional_when` is prose — no planner can read
*"the change ships no running service"* out of a sentence of intent. On a LOW or
MEDIUM change, guessing wrong costs a stage nobody needed. On a HIGH or CRITICAL
one it costs the observability design for a service going to production. So the
default inverts with risk: above MEDIUM, optional stages are **kept** unless the
project has listed them as skippable, and dropping one becomes a decision someone
made rather than a default nobody saw.

## Every loop is bounded

`policies/control-loop-policy.json` owns the bounds, and `control_loop.py` reads
them rather than restating them — a limit written in a policy and a different
limit hardcoded in the code enforcing it is the failure this repository keeps
finding in itself.

| Bound | Default | On exhaustion |
| --- | --- | --- |
| Attempts per task | 3 | escalate |
| Replans per work item | 2 | escalate: two replans means the intake was wrong |
| The same failure twice | — | escalate without spending a third attempt |

That last one matters most. A different failure each time is progress; the same
failure twice is not, and retrying it only spends tokens to learn what is already
known.

## What the hooks do

Verified empirically against the installed CLI before either was built:

- **`SubagentStart`** returns `additionalContext`, and it reaches the subagent.
  This is undocumented and it works. `inject_context.py` uses it to hand each
  agent its work item and *its own* task — which is what lets the agent
  definitions stay small instead of carrying the project's whole configuration in
  thirty files that drift apart.
- **`SubagentStop`** carries `last_assistant_message`. `observe_subagent.py`
  records the result against the task, and says so when an agent stops having
  produced nothing — because a subagent that stops silently looks identical to one
  that succeeded, unless something outside it is watching.

**`TaskCreated` and `TaskCompleted` are deliberately unused.** They exist and they
fire, but they carry no dependency information and offer no `hookSpecificOutput` —
the only lever is an exit-2 veto. Building the loop on them would have produced
something that looks like control and cannot steer.

## What this does not do

- It does not schedule agents. Claude Code does that; reproducing it here would
  be the second runtime this repository exists not to build.
- It does not decide *which* rule applies to an observed failure. That is a
  judgement the model makes. The bounds on retrying and replanning are not.
- It does not verify that a task was really done. The definition of done answers
  that, and `check_dod.py` evaluates it.
