---
name: delegated-execution
description: Decide which model does a piece of work in this repository, and delegate the rest rather than doing everything at the top tier. Use when starting any multi-step task, before spawning a subagent, when a chore is mechanical and verifiable, or when a session has been running long at high cost. Produces a delegation decision and a verification step, never an unchecked handoff.
argument-hint: [the task about to be started]
allowed-tools: Read, Grep, Glob
---

# Delegated execution

The rule is one sentence:

> **Do the judgement at the top tier and delegate everything whose answer can be
> checked.**

Everything below is that sentence applied.

## What this is not

This is not model routing for the organization's own roles. That already exists
and is not duplicated here: `${CLAUDE_PLUGIN_ROOT}/policies/model-policy.json` routes a *task* by risk,
complexity and reversibility — CRITICAL never de-escalates, MEDIUM plus novel
goes to opus, LOW plus routine plus reversible goes to haiku — and
`${CLAUDE_PLUGIN_ROOT}/policies/agent-registry.json` carries each role's default. A second copy of that
table would drift from it.

This is about the **session driving the work**: which model reads the files,
writes the code, runs the audit, and which model decides what any of it means.
Nothing here changes what a role is, what a workflow requires, or what a
definition of done demands.

## Why it exists

A working session drifted into doing every part of a large task at the top tier —
profiling a CI script, timing test files, grepping documents for stale counts —
none of which needs the most capable model. Two chores were then delegated to
Sonnet and both came back better than the time they cost, one of them
**disproving** an allegation the top tier had been about to accept.

The cost is not only tokens. A session that does its own mechanical work fills
its context with file dumps and timing tables, and the judgement it exists to
make is then taken with less room to make it in.

## The tiers

| Tier | Takes | Because |
| --- | --- | --- |
| **haiku** | Mechanical work with one right answer: counting, listing, formatting, moving files, applying a stated edit across many files, routine merge mechanics. | The answer is checkable by inspection, so a wrong one is cheap and visible. |
| **sonnet** | Implementation against a stated contract, profiling, measurement, research with a defined question, drafting documentation from a source of truth, auditing prose against a schema. | The work is bounded and its output can be verified against something. |
| **opus** | The final review. Architectural judgement. Deciding what evidence means. Any call that is expensive to reverse or hard to notice when wrong. | A wrong answer here is not visible in the output; it is visible three releases later. |

## What is never delegated

These stay with the reviewing tier however long the session runs:

- **The certification verdict.** What the evidence supports, and what it does not.
- **Approval decisions**, and anything that crosses a human gate.
- **Architectural corrections** — deciding that a policy, schema or resolver is
  wrong, as opposed to implementing a correction already decided.
- **Accepting a subagent's finding.** See below; this is the one that bites.
- **Deciding that a check may be weakened.** It may not.

## Verify what comes back

A delegated result is evidence, not a conclusion. Both delegations that shaped
this skill needed checking:

- A documentation audit reported five stale claims. Four were real. The fifth was
  **wrong** — the document matched the schema exactly, and the drift was in a
  different schema the audit had not read. Accepting it would have "fixed" a
  correct document.
- A profiling run named one function as the cost of the whole pipeline. That was
  right, and the fix it proposed was checked by measurement before it was made,
  not because the agent was unreliable but because the measurement was cheap.

So: **re-derive the load-bearing claim yourself.** Not every line — the one the
decision rests on. If a subagent says a file says something, open the file.

## How to delegate well

- **Say what the answer must contain**, not how to find it. A prompt that dictates
  method gets the method back and not the answer.
- **Give it the source of truth**, and say which files are authoritative. Most
  wasted subagent time is spent locating what could have been named.
- **Ask for the disconfirming case.** "Verify each of these as true or false with
  evidence" produced the one refutation; "find the stale claims" would not have.
- **Bound it.** A read-only audit says read-only. A measurement says do not edit.
- **Run independent work in parallel.** Two agents in one message, not two turns.
- **Do not delegate what you have already started.** Finishing it yourself is
  cheaper than briefing someone into the middle of it.

## What this cannot decide

- **Whether the delegated work was any good.** The tier picks who does it; only
  reading the result tells you if it is right, and that is why the verification
  step above is not optional.
- **The organization's own model routing.** A role's model comes from the registry
  and the model policy, and a session's convenience never overrides a task's risk
  class. Delegating your own chores to haiku is thrift; running a CRITICAL stage
  on haiku is a policy violation.
- **Whether a task is genuinely mechanical.** That judgement is itself judgement.
  When it is unclear, it is not mechanical.
