---
name: technology-selection
description: Run a structured technology decision when the approved stack does not cover a need. Use when a requirement cannot be met with approved technology, when adding a dependency outside the stack, or when a project has no declared technology for a layer. Produces a proposal for a human decision, never a decision.
---

# Technology selection

Technology choice is a human decision (AP-03). Your job is to make the decision easy and well-founded, then stop.

## When this is needed

- `.ai-engineering/project.yaml` has no entry for the layer in question.
- A requirement cannot be met with the approved stack.
- A dependency is proposed that introduces a new capability class (a database, a broker, a runtime), not just a library.

A library that does what an approved library already does is not a technology decision; it is a finding for `dependency-reviewer`.

## Procedure

**1. State the need as a requirement, not a technology.** "Ordered, durable delivery of events between two services with at-least-once semantics" — not "we need Kafka".

**2. State the constraints that actually bind.** Existing operational skills, deployment platform, licence obligations, data residency, budget, compliance, support model, hiring reality.

**3. Establish the option set, including the boring ones.** Always include:
   - Do nothing / meet the need with what is already approved.
   - Extend an already-approved technology.
   - Two or three genuine candidates.

   The first option is the one most often missing and most often correct.

**4. Compare on the dimensions that decide it.** Not a generic matrix: pick the four to six dimensions on which the options actually differ, and say why the others do not matter.

Typical: fit for the requirement, operational cost, failure modes, team familiarity, ecosystem maturity, licence, exit cost.

**5. State the total cost of ownership.** Not licence cost: the cost of running it, monitoring it, upgrading it, hiring for it and eventually leaving it.

**6. State the exit path.** How would the organization stop using this in two years? A technology with no exit path is a much bigger commitment than it looks.

**7. Recommend one option, and say what would change your mind.**

When more than one option satisfies the requirements, the `engineering-simplicity` rule decides: the one already approved, already on the platform, or already understood wins, and the recommendation names which stated requirement the simpler option would have to fail for the answer to change. Popularity, career value and unquantified future growth are not that requirement.

## Output

A technology-decision proposal containing: the need, the constraints, the options including "use what we have", the comparison, the TCO, the exit path, the recommendation, and the explicit statement that a human must decide.

When the human decides, record it as an ADR (`adr-management` skill) and update `.ai-engineering/project.yaml` with `status: approved` and the ADR identifier.

## Rules

- Never introduce a technology into an implementation and then propose it. The proposal comes first.
- Never present a single option. One option is an announcement, not a decision.
- Never recommend on popularity. Popularity is an input to ecosystem maturity, nothing more.
- If the honest recommendation is "the approved stack already does this, at some inconvenience", say so.
