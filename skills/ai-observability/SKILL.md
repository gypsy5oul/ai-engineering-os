---
name: ai-observability
description: See what an AI system did in production - tracing model and tool calls, cost and token metrics, quality signals, drift, and what may be logged given the data classification. Use when an AI feature is going to production or is being investigated there.
---

# AI observability

Ordinary observability answers "is it up and how fast". For an AI system both can
be green while it is confidently wrong, which is the failure that matters and the
one nothing here will page you about.

Use with `observability`. SLIs, SLOs, alerts and runbooks all still apply. This is
what is additionally true.

## The trace is the unit

An AI request is a tree — a model call, tool calls, retrieval, retries, sometimes
another model call — and the thing you need in an investigation is the **whole
tree for one request**, not a log line from the middle of it.

Every span carries:

| Field | Why |
| --- | --- |
| Request / conversation / turn id | To reassemble the tree |
| **Prompt version, model version, index version** | The three inputs that change independently. Without them a bug is not reproducible |
| Parameters | Temperature and sampling settings change the output distribution |
| Tokens in, tokens out | Cost, and the input-growth problem |
| Latency, split into model time and your time | So a slow feature has a cause |
| Outcome | Success, schema-invalid, refusal, timeout, retry |
| Tool calls: name, arguments, result, authority | What the system actually *did*, as opposed to said |

The version fields are the ones most often missing and most often needed. A
production incident that begins "it started answering wrongly on Tuesday" is
solved by the version diff or it is not solved.

## What may be logged

**This is a data-classification decision, not a debugging preference.** The
prompt usually contains user data; the response usually contains more of it; both
are about to be stored somewhere with a different retention policy from the
system of record.

Decide, record the decision, and implement it:

- What is captured in full, what is redacted, what is only counted.
- How long it is kept, and what deletes it.
- Who can read it — production model IO is frequently more sensitive than the
  database it came from, and frequently less protected.
- Whether the provider retains it too, which is a separate answer from whether
  you do.

Record the answer in `.ai-engineering/project.yaml` under
 `ai_system.data_in_prompts`, next to the provider that was approved under AP-03
 to receive it. A retention decision that lives only in the code that implements
 it is a decision nobody reviewed.

A common and defensible shape: metadata and versions always; content sampled,
redacted, and short-lived; full content only where a user consented or the data
is not sensitive. What is not defensible is logging everything by default because
it helps debugging.

## Cost as a first-class signal

Cost per request is a metric with the same standing as latency, and it moves for
reasons latency does not: a longer conversation, more retrieved documents, a
retry loop, a model change.

Alert on cost per request and on spend rate, not only on the monthly total. The
total tells you after the month.

## Quality in production

The dataset (`ai-evaluation`) tells you how the system performs on cases you
chose. Production tells you which cases you did not choose.

Signals worth having, cheapest first:

- **Deterministic failures** — schema-invalid responses, refusals, empty
  retrievals, tool errors, retry exhaustion. Free, and a rising rate is a real
  regression.
- **Implicit user signals** — retries, rephrasings, abandonment, edits to a
  generated output, escalation to a human. These say "wrong" without anyone
  filing anything.
- **Explicit feedback**, where the product has it. Sparse, biased, still useful.
- **Sampled offline scoring** — run the judge over a sample of real traffic and
  track it as a series.

Route the failures back into the dataset. Production is the source of the cases
you did not think of, and a system where that loop is not wired is a system whose
evaluation stops representing reality.

## Drift

Nothing changed and the numbers moved. Distinguish:

- **Input drift** — users ask different things than they did. Detectable from
  the input distribution, and the usual cause.
- **Corpus drift** — the retrieval index changed underneath.
- **Model drift** — the provider changed the model behind an unpinned version.
  Pin versions; this is why.

## Alerting

Alert on what a person can act on now:

- Deterministic failure rate above its normal band
- Cost per request or spend rate outside its band
- Latency, as with any service
- Refusal or empty-retrieval rate moving sharply
- A model or index version changing when no deployment happened

Do not alert on a quality score computed per request by a judge model. It is
expensive, noisy, and its own measurement error will page somebody at 3am.

## Rules

- Every trace names the prompt, model and index versions, or the bug is not
  reproducible.
- What is logged from model IO is a data-classification decision, recorded before
  it is implemented.
- Cost per request is a monitored metric, not a monthly discovery.
- Production failures become evaluation cases. Otherwise the dataset stops
  describing reality.
- Green latency and green error rate say nothing about whether the answers were
  right.
