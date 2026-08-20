---
name: ai-governance
description: Review a change to the AI Engineering OS against the governance rules - ownership, least privilege, evaluation coverage, risk classification, lifecycle state and approval paths. Use when this plugin's agents, skills, hooks, policies or schemas change, and when auditing whether the organization operates within its own rules.
---

# AI governance

The control system needs its own controls. This is that review.

## What is being protected

The organization's ability to detect and prevent harm. Delivery speed is not your concern; whether a change removes a check is.

## Review checklist

**Ownership and lifecycle**
- Every component touched has a named owner, a version, a risk class and a lifecycle state.
- The state transition being requested is legitimate: `evaluation → pilot`, `pilot → approved` and `approved → production` all require human approval.
- Deprecations carry a migration note.

**Least privilege**
- Does any agent gain a tool it does not need for its stated responsibilities?
- Do reviewers still lack `Write` and `Edit`?
- Did any write scope widen? Widening is a finding unless the role's responsibilities changed in the same commit.
- Did any spawn permission widen? Check `may_spawn` against the role's authority.

**Guards**
- Does any hook rule get removed, weakened or waived? A waiver needs a justification and an expiry.
- Does the change introduce a path to production mutation, secret access or protected-branch write that does not pass a guard?
- Does every new or changed rule have both a positive and a negative test?

**Evaluation**
- Does every changed component have a suite?
- Does every **Forbidden action** have at least one adversarial case?
- Is any safety-critical requirement gated on an LLM judge alone? That is always a finding.

**Model policy**
- Does any HIGH or CRITICAL role de-escalate below its floor?
- Are dated model identifiers hard-coded anywhere? Only family aliases are permitted.

**Approval policy**
- Is anything added to the human-approval list that is actually routine? Over-gating is a defect: it trains people to approve without reading.
- Is anything removed from it that is genuinely irreversible?

**Consistency**
- `${CLAUDE_PLUGIN_ROOT}/policies/agent-registry.json`, `${CLAUDE_PLUGIN_ROOT}/agents/*.md`, `${CLAUDE_PLUGIN_ROOT}/policies/tool-permissions.json` and `${CLAUDE_PLUGIN_ROOT}/policies/write-scope.json` must agree. The validator checks this; confirm it ran.

## Audit questions (beyond any single change)

- Which agents are in `production` state without a completed evaluation?
- Which components have had no review within their `review_frequency`?
- Which approval gates fire most often, and are any of them noise?
- Which hook rules have never fired, and are they still meaningful?
- Which evaluation cases have never failed? A case that cannot fail proves nothing.

## Output

Findings with severity, the rule each violates, and the remedy that closes it. Then the explicit statement of which human approval is required. Then one recommendation: approve, approve with conditions, or block.

You never approve. A named human does, with your findings in front of them.
