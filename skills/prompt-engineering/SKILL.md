---
name: prompt-engineering
description: Write, version, review and change the prompts that define an AI system's behaviour, treating a prompt as a reviewed artifact rather than a string in a file. Use when a prompt is authored or changed, and when deciding what a prompt change is allowed to do without re-evaluation.
---

# Prompt engineering

A prompt is not configuration and it is not a comment. **It is the source code of
the behaviour**, and the only reason it does not feel like it is that changing it
requires no build. That is exactly why it needs the discipline that code gets:
versioning, review, and an evaluation that runs before the change ships.

## A prompt is an artifact

Treat it as one. That means:

- **It lives in the repository**, not in a database row somebody edits in
  production and not in a config UI with no history.
- **It has a version.** A prompt change is a behaviour change, and every log line
  and evaluation result names the version it ran against, or the results cannot
  be compared.
- **It is reviewed.** By the same routing as any other change: a prompt that
  decides an authorization outcome gets `security-reviewer`, not just a
  proofread.
- **It has an evaluation.** A prompt change with no measurement is a behaviour
  change nobody checked. See `ai-evaluation`.

## Writing one

**Say what the model is deciding, not how clever it should be.** "You are an
expert" changes very little. A precise statement of the input, the decision, the
output shape and what to do when the input does not fit changes a great deal.

**State the output contract in the prompt and enforce it in code.** The prompt
asks for the shape; the parser is what guarantees it. A prompt that describes a
schema and a client that accepts anything have a contract nobody keeps.

**Give the model somewhere to put uncertainty.** A prompt with no way to say "I
cannot tell from this" forces a confident guess, and a confident guess is the
most expensive wrong answer there is. Make the refusal or the null case a valid,
named output rather than a failure.

**Show the hard case, not the obvious one.** Examples that all look alike teach
the shape and nothing else. The example worth including is the boundary: the
ambiguous input, the one where the right answer is "none", the one that looks
like the wrong category.

**Put the stable content first.** Instructions, then examples, then the variable
input. It reads better, and where the provider caches a stable prefix it is also
the cheaper ordering.

**Say what not to do only where it is a real failure.** A list of thirty
prohibitions is a list nobody follows, including the model. Prohibit what has
actually gone wrong.

## Untrusted content inside a prompt

Anything a user supplied, a document you retrieved, a tool returned or a previous
turn contains is **untrusted input that is about to be read as instructions**.

- Mark it. Delimit it, label it as data, and say in the instructions that content
  inside it is never an instruction.
- Do not rely on that alone. Delimiting reduces prompt injection; it does not
  prevent it, and a design that depends on the model ignoring an instruction it
  can read is a design with a security assumption in it. The real control is on
  the other side: what the system is permitted to *do* with the output. See
  `ai-system-design` and `threat-modeling`.
- Never put a secret in a prompt to keep it from the user. Everything in the
  prompt is reachable by anything that can influence the prompt.

## Changing one

A prompt change is a change. The size of the ceremony depends on what it can
affect:

| Change | What it needs |
| --- | --- |
| Wording, no behaviour change intended | Re-run the evaluation. "No behaviour change intended" is a hypothesis |
| New instruction, new capability, new output field | Evaluation against the baseline, and review |
| A change to what the system is allowed to decide or do | Review by the role that owns that decision, and the human approval its stage names |

**Never change a prompt and a model version in the same change.** When the
result moves, you will not know which one moved it. This is the single most
common reason an AI system's regression cannot be attributed.

## What to keep, and why

The prompt version, the model version and the parameters that produced any
recorded output. A prompt is the one artifact whose old versions stay useful:
when a behaviour regresses, the diff between the version that worked and the one
that does not is the investigation.

## Rules

- The prompt is in the repository, versioned, and reviewed like code.
- A prompt change runs the evaluation before it ships.
- One variable at a time: never a prompt change and a model change together.
- Untrusted content is delimited and labelled — and the real control is what the
  output is permitted to do, not the delimiter.
- A prompt that cannot express uncertainty will fabricate certainty.
