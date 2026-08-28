---
name: ai-system-design
description: Design a system whose behaviour comes from a model rather than from code you wrote. Use when a requirement is met by generation, extraction, classification, retrieval or an agent loop, and the design has to say what happens when the model is wrong. Technology-neutral - it names no provider.
---

# AI system design

An AI system is a system whose behaviour is **sampled, not specified**. Everything
else about designing it follows from that one difference, and the designs that
fail are the ones that treated it as an ordinary component with an unusual API.

Use this with `architecture-design`, not instead of it. Requirement coverage,
failure modes, data lifecycle and the complexity ledger all still apply.

## The difference that matters

| Ordinary component | Model-backed component |
| --- | --- |
| Same input, same output | Same input, a distribution of outputs |
| Fails loudly | Fails **plausibly** — a wrong answer looks like a right one |
| Correctness is tested | Correctness is *measured*, on a dataset, as a rate |
| Cost is capacity | Cost is per call, and grows with the input you send |
| A bug is reproducible | A bug is a rate, and reproducing it needs the seed, the prompt version and the model version |

The consequence that catches people: **you cannot design the happy path and add
error handling afterwards.** For a model-backed component, "wrong but confident"
is a normal output, not an error condition, and the design has to say what the
system does with it before anything is built.

## What the design must answer

**1. What is the model actually deciding?** State it as a contract: input, output
shape, and the decision the rest of the system makes from it. A component whose
output is "some helpful text" has no contract and cannot be evaluated.

**2. What happens when it is wrong?** For each way the output can be wrong —
wrong content, wrong shape, refusal, truncation, timeout, injected instruction —
say what the system does. "The model is usually right" is not an answer.

**3. Who checks it, and against what?** A human, a rule, a second model, or
nobody. If nobody, say so explicitly and name what that costs. This is the
decision that most often goes unrecorded and most often turns out to matter.

**4. What is the blast radius of a wrong answer?** A wrong summary shown to a
user is not a wrong action taken on their behalf. Autonomy is the axis that
decides how much of the rest of this matters:

| Autonomy | What a wrong answer costs | What the design owes |
| --- | --- | --- |
| Suggests to a human | A moment of confusion | Make the suggestion easy to reject |
| Writes something a human reads later | A wrong record | Provenance, and a way to correct it |
| Takes a reversible action | An undo | A recorded action log and the undo path |
| Takes an irreversible action | The thing you cannot take back | A human in the loop, or a very good reason recorded under AP-03 |

**5. What is the cost per unit of work?** Tokens in, tokens out, calls per
request, and what happens when the input grows. A design that is correct and
costs more per call than the thing it replaces is a finding, not a success.

**6. What is the evaluation, and does it exist yet?** An AI component without an
evaluation dataset has no definition of done that anybody can check. Design the
evaluation with the component — `ai-evaluation` — not after it.

## Deterministic first

The most reliable AI system design is the one that uses less of it.

Before designing a model-backed component, say what a rule, a lookup, a regex, a
database query or a form would fail to do. Often the honest answer is "nothing,
for the cases we have" — and the model is being reached for because it is
interesting rather than because it is needed. That is a
`${CLAUDE_PLUGIN_ROOT}/policies/simplicity-policy.json` finding, and it belongs in the complexity
ledger like any other.

Where a model genuinely is needed, the shape that survives contact with
production is usually: **deterministic scaffolding, model in the middle,
deterministic validation of what comes back.** Constrain the output shape, parse
it, and reject what does not fit rather than passing prose downstream.

## Boundaries the design has to draw

- **Trust boundary.** Anything the model reads is untrusted input, including
  retrieved documents, tool results and prior turns. A design that treats
  retrieved text as data and prompt text as instruction has one boundary; a
  design that concatenates them has none. See `threat-modeling`.
- **Data boundary.** What leaves the system in a prompt, where it goes, how long
  the provider keeps it, and whether that is compatible with the project's data
  classification. This is a real question with a real answer and it belongs in
  the design, not in a later panic.
- **Version boundary.** The model version, the prompt version and the retrieval
  index version are three inputs that change independently. A design that cannot
  say which three produced a given output cannot debug one.

## Rules

- Name what the model decides, or there is nothing to review.
- Every wrong-answer mode has a stated behaviour. "Unlikely" is not one.
- Autonomy is a human decision. An agent does not decide how much authority the
  system it builds should have.
- Design the evaluation with the component. A component whose quality nobody
  measured is a component nobody can change safely.
- The provider is a technology decision (AP-03), recorded in
  `.ai-engineering/project.yaml` like any other. Do not design against one that
  has not been approved.
