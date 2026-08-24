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

`CURRENT` sits alongside those directories and names the work item this project
is on. Runtime hooks resolve the active work item from the session binding first
-- `control_loop.py open --session` writes it outside source control -- and fall
back to `CURRENT` only when there is no binding. That order matters: `CURRENT` is
one pointer per project, so with two sessions open the second one's agents would
be briefed on the first one's work. A session with neither is doing something
other than tracked work, which is a normal session and not an error.

## Driving one, end to end

Seven subcommands, all on `scripts/control_loop.py`, all taking `--project` and
(after `open`) `--item`.

```bash
# 1. Open it. Intent is quoted verbatim; nothing about the plan is decided yet.
python3 scripts/control_loop.py open --project . --type feature --risk HIGH \
    --intent "Partners time out on large transfers"

# 2. Plan it. The graph is generated from the workflow, the project's risk
#    posture and what each stage needs from the one before it.
python3 scripts/control_loop.py plan --project . --item ACME-FEAT-001

# 3. Ask what is runnable. Dependencies met, attempts left, surface free.
python3 scripts/control_loop.py next --project . --item ACME-FEAT-001

# 4. Do the work. Spawning an agent claims a task for it automatically --
#    SubagentStart hands it the work item and its own task, and SubagentStop
#    records what came back. Nothing here has to be done by hand.

# 5. Record an outcome. accepted | failed | rejected | blocked | escalated.
python3 scripts/control_loop.py observe --project . --item ACME-FEAT-001 \
    --task T-003 --outcome failed --failure-class test_failure \
    --detail "the token endpoint still rejects valid credentials"

# 6. Let the loop decide: retry, rework, replan or escalate.
python3 scripts/control_loop.py decide --project . --item ACME-FEAT-001 --task T-003

# 7. Look at the whole thing at any point.
python3 scripts/control_loop.py status --project . --item ACME-FEAT-001
```

`replan` is the eighth, and it is not part of the ordinary path: it is what the
loop reaches for when `decide` says the plan itself is wrong, and it is capped so
that replanning cannot become the way work avoids finishing.

Nothing in this sequence requires a session to stay alive. The store is the
system of record; a session that dies is resumed by reading it.

## Intent and objective are kept apart

`intent` is what the human said, verbatim. `objective` is what the organization
understood. They are separate fields because a plan that solves the wrong problem
is invisible when the only record is the restatement — and both are given to
every agent, so the agent can notice the gap rather than inheriting it.

## How dynamic this actually is

Worth stating plainly, because the word oversells easily:

| | Status |
| --- | --- |
| Risk-aware stage selection | implemented |
| Dependencies derived from artifact flow | implemented |
| Parallel execution where work is independent | implemented |
| Coupled surfaces sequenced automatically | implemented |
| Bounded replanning that carries accepted work forward | implemented |
| Task synthesis beyond the workflow's stages | **implemented**, one level, derived or proposed |
| Fan-out sized to the work (N stories, N tasks) | **partly** — a stage becomes 2 to 8 tasks; the number comes from the artifact model or from an agent's proposal, not from the story count |
| Dependencies inferred from the code being changed | **not implemented** |

So: the graph is generated per change, genuinely parallel, and a stage can now
become the several tasks it actually is. What it still does not do is read the
code being changed. Dependencies come from artifact flow and from a proposer's
judgement; nothing here inspects a call graph to discover that one task must
land before another.

## The graph is generated, not fixed

The declarative workflow says **what must be true**. The graph says **how this
change gets there**. It is built per work item from the workflow's stages, and a
stage that declares `optional_when` is dropped with its reason recorded.

Dependencies come from **artifact flow, not stage order**. A stage waits for
whatever produces the artifacts its definition of done names, so work that does
not depend on other work runs at the same time. Three things still sequence: a
consumer waits for its producer, everything waits for the human gate ahead of it,
and two stages touching the same coupled surface are ordered rather than
parallelised.

An earlier version made every task depend on the one before it. That is a pipeline
wearing a graph's schema: `runnable()` could only ever return one task, which left
the coupled-surface exclusion with nothing to exclude and the parallel execution
modes with nothing to run.

One judgement is worth stating. `optional_when` is prose — no planner can read
*"the change ships no running service"* out of a sentence of intent. On a LOW or
MEDIUM change, guessing wrong costs a stage nobody needed. On a HIGH or CRITICAL
one it costs the observability design for a service going to production. So the
default inverts with risk: above MEDIUM, optional stages are **kept** unless the
project has listed them as skippable, and dropping one becomes a decision someone
made rather than a default nobody saw.

## One stage is often several tasks

A stage is a unit of accountability. `DEV` on a payments change is one node in the
graph and five people's work in reality, and a graph that cannot say so cannot
schedule it, cannot run the independent parts at the same time, and cannot show
anyone where the change has got to.

Deciding which pieces, in what order, sharing which contracts, is judgement. This
repository does not simulate judgement, so the split is proposed and the
organization validates it — the same division as everywhere else here.

**Derived.** When the artifacts a stage produces are owned by more than one role,
the split is already written down in the artifact model and reading it is not
guessing:

```bash
python3 scripts/synthesize_tasks.py --project . --item ACME-FEAT-001 \
    --task T-008 --derive
```

```
T-008 decomposed into 2 task(s):
  T-020   qa-lead        QA test design: TP        TP
  T-021   qa-engineer    QA test design: TEST      TEST
```

When one role owns everything the stage produces, there is no split to derive and
this refuses rather than inventing one. It also refuses when the stage owns a
coupled surface: which piece of the work edits a shared contract is a judgement
the artifact model does not contain.

**Proposed.** Everything else. An agent produces a decomposition against
`schemas/task-proposal.schema.json` — the `task-synthesis` skill is the
instruction for that — and the organization validates all eight rules in
`policies/task-synthesis.json` before anything is written:

```bash
python3 scripts/synthesize_tasks.py --project . --item ACME-FEAT-001 \
    --from proposal.json --proposed-by solution-architect
```

A proposal that does not hold together is refused whole, with the rule that
refused it:

```
REFUSED: the decomposition of T-008 does not satisfy policies/task-synthesis.json.
  - TS-01: nothing produces TEST, which T-008 owes. A decomposition that drops an
    artifact turns a stage the organization owes into one nobody owes, and the
    parent's definition of done still passes.
```

The rules exist because each names something that fails silently: an artifact
nobody owes still passes the parent's gate; a task assigned to a role that cannot
write its output is a task nobody can do; a child that lowers its risk routes
around the model floor and the approval gates one level down; an invented
predicate is skipped by the evaluator, which makes it a definition of done that
always passes.

**The stage survives its own decomposition.** The parent keeps its definition of
done and comes to depend on all of its children, so the gate the rest of the
graph was promised still exists and every downstream edge still points at it.
What changes is that the stage cannot be worked until its pieces are:

```
T-008  QA test design                queued      <- the stage gate, waiting
  T-020  Write the test plan         queued
  T-021  Write the automated tests   queued      depends on T-020
```

Two limits worth knowing. One level of decomposition only: a stage needing more
is a work item that was scoped wrong, and saying so is more useful than
subdividing it. And a replan rebuilds the graph from the workflow, so a
decomposition does not survive one — deliberately, because a replan means the
plan was wrong, and a decomposition of a wrong plan is not worth carrying.

What is not checked is whether a decomposition is any *good*. The rules reject
one that is incoherent with the graph; they cannot reject one that is merely
poor. That is what the stage's reviewer is for.

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

## Two failures are the same when their identity matches

The loop escalates on a repeat, so the comparison decides between escalating work
that was still making progress and spinning on work that was not. Comparing the
observed text was wrong in both directions:

```
"API returns 401"                }  one failure,
"endpoint still returns 401"     }  read as two

"failed"                         }  two unrelated causes,
"failed"                         }  read as one
```

A failure now has a `class` and a `signature`, supplied by whoever observed it:

```bash
control_loop.py observe --project . --item ACME-FEAT-001 --task T-004 --outcome failed \
    --failure-class test_failure \
    --signature AUTH-401-MISSING-TOKEN \
    --evidence tests/auth/test_login.py \
    --detail "the token endpoint still rejects valid credentials"
```

When no signature is given, one is derived — conservatively. Only identifying
tokens survive: exception names, status codes, test paths, error identifiers.
Prose is discarded. When nothing identifying remains, the result is a signature
that **matches nothing, including another copy of itself**.

That asymmetry is deliberate. A wrong *"these are the same"* escalates work that
was making progress; a wrong *"these differ"* costs one more attempt inside a
bound that already exists. Only one of those is recoverable by waiting.

## Execution mode is chosen when the task runs

A stage declares its execution mode when the workflow is written, which is before
the situation exists. `execution: team` is good advice and a bad instruction in a
headless session, where teammates do not spawn at all.

Resolution happens on the claim path: when `SubagentStart` binds a task to an
agent, the answer is computed and written onto the task before the agent begins.
Reading it by hand, or re-recording it after the graph changes:

```bash
python3 scripts/resolve_execution.py --project . --item ACME-FEAT-001 --all
python3 scripts/resolve_execution.py --project . --item ACME-FEAT-001 --all --record
```

```
TASK    DECLARED       RESOLVED       WHY
T-004   team        -> subagent       CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not set
T-009   subagent    -> worktree       a sibling holds the database-schema surface
T-010   worktree    -> subagent       code-reviewer holds no write tools
```

The rules, in the order they apply:

| Fact | Resolves to | Because |
| --- | --- | --- |
| Teams unavailable | `subagent` | Nothing in the lifecycle may depend on a feature that is still experimental and off by default |
| Role holds no write tools | `subagent` | A worktree protects files the role could not have touched |
| CRITICAL risk, declared background | `subagent` | The point of the tier is that somebody is watching; background is where nobody is |
| A sibling holds the same coupled surface | `worktree` | The parallelism survives and integration becomes an explicit step |
| Writes files, siblings running | `worktree` | Parallel writers in one checkout produce a build output nobody owns |
| Nothing overruled it | the declared mode | |

Three values are kept, because they answer three different questions:

```yaml
execution:
  declared: team            # what the workflow asked for, before the situation existed
  resolved: subagent        # what the resolver decided at claim time
  actual: subagent          # what the runtime reported having done
  resolution_reason: "teams are not enabled in this environment"
  briefing_required: false  # an isolated spawn receives no injected context
```

Keeping only one of them means the organization cannot tell a policy it chose
from a degradation it accepted from a spawn that ignored both. With all three,
"how often does this organization ask for execution the environment cannot give
it" becomes a number rather than an impression.

**It resolves and records; it does not compel.** A `PreToolUse` hook can refuse a
spawn but cannot rewrite one, so nothing forces an agent to honour the answer --
which is exactly why `actual` is recorded separately at `SubagentStop` rather
than assumed to equal `resolved`. That limit is in the policy's
`not_enforceable`, not left to be discovered.

`briefing_required` marks the one case that would otherwise fail silently: an
isolated spawn does not receive `SubagentStart`'s `additionalContext`, so the
task briefing this plugin exists to deliver never arrives. When it is set, the
briefing has to travel in the spawn prompt instead.

## What the hooks do

Verified empirically against the installed CLI before either was built:

- **`SubagentStart`** returns `additionalContext`. This is a **declared field of
  the hook output schema**, not a discovered accident — an earlier version of this
  document called it undocumented, which was wrong. `inject_context.py` uses it to
  hand each agent its work item and *its own* task, which is what lets the agent
  definitions stay small instead of carrying the project's whole configuration in
  thirty files that drift apart.

  The agent is briefed on **one** task, claimed against its `agent_id`. Matching
  on role alone briefed an agent on every task its role owned, and two concurrent
  agents on the same one.
- **`SubagentStop`** carries `last_assistant_message`. `observe_subagent.py`
  records the result against the task, and says so when an agent stops having
  produced nothing — because a subagent that stops silently looks identical to one
  that succeeded, unless something outside it is watching.

- **`TaskCompleted`** refuses the completion when a bound task's definition of
  done has a failing predicate. This is the one place the definition of done stops
  being something the organization evaluates when asked and becomes something that
  must be true before a task can close.

  It is not the orchestrator. `TaskCreated` and `TaskCompleted` carry no dependency
  information and offer no `hookSpecificOutput`, so they cannot steer a loop — an
  earlier version of this document read that as a reason to ignore them entirely,
  which was too broad. An exit-2 veto is a poor engine and an excellent gate.

  Narrow on purpose: it blocks on a predicate that **fails**, never on evidence
  that is merely unavailable. "Not yet provable" is not "wrong", and a gate that
  cannot be satisfied offline is a gate people switch off.

## What this does not do

- It does not schedule agents. Claude Code does that; reproducing it here would
  be the second runtime this repository exists not to build.
- It does not decide *which* rule applies to an observed failure. That is a
  judgement the model makes. The bounds on retrying and replanning are not.
- It does not verify that a task was really done. The definition of done answers
  that, and `check_dod.py` evaluates it.
