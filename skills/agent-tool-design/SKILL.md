---
name: agent-tool-design
description: Design the tools an AI agent is given - the interface, the description, the error messages and the authority - understanding that the description is a prompt and the caller cannot be trusted to call correctly. Use when building an agentic feature, not when designing an API for humans or services.
---

# Agent tool design

A tool given to a model is an API whose **documentation is part of the runtime**
and whose **caller will get it wrong in ways no human would**. Those two facts
make it a different design problem from `api-design`, which assumes a caller that
reads the docs once and then writes correct code.

## The description is a prompt

The tool description is not documentation about the tool. It is the instruction
that decides whether the tool is called, when, and with what. It is the highest-
leverage text in an agentic system and it is usually written last, by whoever
wrote the function.

- **Say when to use it and when not to.** The second half is what stops a tool
  being called for everything adjacent to its name.
- **Name the boundary with its neighbours.** Two tools whose descriptions do not
  distinguish them will both be called, or the wrong one will.
- **Describe the parameters in terms of what the caller knows**, not in terms of
  the schema. `user_id` is obvious to a schema and useless to a model that has a
  name and an email.
- **Write it for a reader who has never seen the system.** That is the actual
  situation.

## Design for a caller that gets it wrong

The model will call the tool with a missing argument, a plausible invented id, a
value from the wrong turn, or three times in a row. Design accordingly.

- **Make illegal calls impossible in the schema**, not merely documented. Enums
  over free strings, required over optional, one shape over a union.
- **Fewer, larger tools beat many small ones.** Twenty tools is a menu the model
  must choose from every turn, and choosing is where it errs. Combine tools that
  are always used together.
- **No tool whose correct use depends on calling another one first**, unless the
  dependency is enforced. A sequencing requirement that lives only in the
  description is a requirement that will be skipped.
- **Idempotent where possible**, because retries and duplicate calls are normal
  rather than exceptional.

## Errors are inputs, not outputs

An error message from a tool goes straight back into the model's context and
becomes the basis for its next attempt. It is a prompt.

| Bad error | What it causes | Better |
| --- | --- | --- |
| `400 Bad Request` | A blind retry, identically | `start_date must be YYYY-MM-DD; got "last Tuesday"` |
| `Not found` | Invention of a different id | `No project with key "ACME". Known keys: ACME-1, ACME-2` |
| A stack trace | Context burned, nothing learned | One line saying what to do differently |
| `Permission denied` | Repeated attempts | `Not permitted for this user. This needs a human with the release-approver role` |

The test: **could the model fix its next call from this message alone?** If not,
the error is going to cost a retry loop.

Do not leak internals in the attempt to be helpful. An error is read by a model
that may be relaying it to a user.

## Authority

The tool is where an AI system's authority actually lives. A model can only do
what some tool lets it do, which makes the tool list the real permission
boundary — not the prompt.

- **Give the least authority the task needs.** Read-only wherever reading is
  enough. This is the same principle as `${CLAUDE_PLUGIN_ROOT}/policies/tool-permissions.json` applies
  to this organization's own roles, for the same reason.
- **Separate read from write into different tools**, so the difference is visible
  in the trace and refusable independently.
- **Anything irreversible needs a human**, and the human decision must not be
  something the model can satisfy by calling another tool. See
  `docs/approvals.md`: an agent verdict is not an approval, in a product for the
  same reason as in this organization.
- **Bound the loop.** Maximum calls per turn, per task and per unit time. An
  agent that can call a tool without limit is a denial-of-service against your
  own system, with a bill.

## What to record

Every call: which tool, the arguments, the result summary, the outcome, and
whose authority it ran under. A trace that shows what the model *said* it did
rather than what the tools *did* is a transcript, not an audit.

## Rules

- The description says when not to call it, or it will be called for everything.
- Every error message tells the caller what to do differently.
- Authority lives in the tool list, never in the prompt asking it to be careful.
- Read and write are different tools.
- The loop is bounded, in calls and in spend.
