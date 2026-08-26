---
name: work-item
description: Open, plan and drive a unit of work through the control loop — the durable record that survives a session, hands each agent its task, and decides between retry, rework, replan and escalate. Use when starting any tracked change, and whenever you need to know what to do next or record what happened.
---

# Driving a work item

The work item is what the organization knows about a change. It outlives the
session that opened it: an agent that stops, a context that compacts and a
machine that reboots all leave it intact, because nothing about it lives in a
conversation.

Until one exists, the hooks that hand an agent its task and refuse a premature
completion have nothing to attach to and stay silent — correctly, because a
session with no work item is an ordinary session. That is the single most common
way to use this plugin and get nothing from it.

Everything below is `${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py`.

## Open it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py open --project . \
    --type feature --risk MEDIUM \
    --intent "what the requester actually said, in their words"
```

`--type` is one of feature, defect, incident, change, migration, dependency,
release, agent-change or onboarding — `sdlc-navigator` will tell you which if it
is not obvious. `--risk` defaults to MEDIUM and drives the model floor, the
approval gates and which optional stages survive.

**Quote the intent verbatim.** It is stored separately from the objective, which
is what the organization understood, and the two are compared when a plan turns
out to have solved the wrong problem. Paraphrasing at intake destroys the only
copy of what was asked for.

## Plan it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py plan --project . --item ACME-FEAT-001
```

The graph comes from the workflow, the project's risk posture, and what each
stage needs from the one before it — so work that genuinely does not depend on
other work can run at the same time. Stages the change does not need are dropped
with a reason recorded.

## Work it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py next --project . --item ACME-FEAT-001
```

That names what is runnable: dependencies met, attempts left, coupled surface
free. Then spawn the agent for that task's role. **You do not have to brief it** —
`SubagentStart` claims one task for it and injects the work item, the task, its
definition of done and any previous failure. If `next` says a task needs a
briefing in the prompt, it resolved to an isolated spawn that receives no
injected context; use `control_loop.py brief` and paste the result.

## Record what happened

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py observe --project . --item ACME-FEAT-001 \
    --task T-003 --outcome failed --failure-class test_failure \
    --detail "the token endpoint still rejects valid credentials"
```

`--outcome` is accepted, failed, rejected, blocked or escalated.

**`accepted` is not an observation, it is a claim**, and it is checked: the task's
definition of done is evaluated and the acceptance is refused if anything fails.
Everything else is recorded without argument, because a system that pushes back
on bad news stops being told any.

A failure carries a class and, ideally, a `--signature` — a stable token like an
error code or a test path. Two failures are "the same" when their identity
matches, not when their prose looks similar.

## Let it decide

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py decide --project . --item ACME-FEAT-001 --task T-003
```

Retry, rework, replan or escalate — from the rules in
`${CLAUDE_PLUGIN_ROOT}/policies/control-loop-policy.json`, not from judgement in
the moment. Every loop is bounded, and escalation is what the loop does when it
runs out of moves rather than an error path.

## Look at it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py status --project . --item ACME-FEAT-001
```

## When a stage is really several people's work

A stage is a unit of accountability, not a unit of work. Use `task-synthesis`
when one is genuinely several: it decomposes the stage, keeps the parent as the
gate, and asks the repository what order the pieces have to happen in.

## When the plan itself was wrong

`replan --reason` rebuilds the graph, carries accepted work forward and counts
against a cap — two replans means the intake was wrong, and a third plan is a new
work item rather than a better plan.

`plan --force` is not a second replan. It is a repair path for a graph that will
not parse, and it refuses on a graph that validates.

## What this is not

It does not run anything. It records what a change is, what it needs, who holds
what, and what happened — and it refuses to say something is done when the
evidence does not support it. The work is still done by agents and by you.
