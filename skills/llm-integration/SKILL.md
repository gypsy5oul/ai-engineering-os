---
name: llm-integration
description: Implement the code that calls a model - structured output, retries, timeouts, token budgets, streaming, idempotency and cost control. Use when writing or reviewing the client side of a model-backed feature. Technology-neutral; it names no provider and no SDK.
---

# LLM integration

The client code around a model call is ordinary code with three unusual
properties: the call is slow, the call costs money per invocation, and the
response is a string that claims to be a structure. Most integration defects come
from forgetting one of those.

Use with `backend-development`. Everything there still applies — bound
everything, set timeouts, handle failure paths deliberately. This is what is
additionally true.

## Structured output, or parsing prose

Ask for a structure and validate what comes back. A response is not a structure
because the prompt asked for one.

- **Validate against a schema, every time.** Not "when it looks wrong". The
  failure this prevents is the one where a field is absent for 2% of inputs and
  the consumer silently gets `None`.
- **Reject, do not repair.** Coercing a malformed response into the expected
  shape guesses at what the model meant. One retry with the validation error fed
  back is honest; a `try: int(x) except: 0` is a wrong answer with a default.
- **Never `eval` or `exec` a model response**, and never interpolate one into a
  query, a path, a shell command or a template without escaping. The response is
  untrusted input that arrived from your own system, which is what makes it easy
  to forget.

## Retries

Retry the things that are worth retrying and nothing else.

| Failure | Retry? |
| --- | --- |
| Timeout, rate limit, 5xx, connection reset | Yes, with backoff and jitter |
| Malformed or schema-invalid output | Once, with the error in the retry prompt |
| Refusal | No. It will refuse again. This is a prompt or a policy question |
| Bad request, context too long, auth | No. Retrying a deterministic error is a slow failure |

Bound the total: attempts, wall-clock, and spend. An unbounded retry loop against
a paid API is an incident with a bill attached.

**Make retries idempotent.** A call that has a side effect before the model
responds gets that side effect twice. Do the side effect after, keyed on
something stable.

## Timeouts and streaming

Set an explicit timeout on every call. The default is usually "wait", and a
hanging model call holds a connection, a worker and a user.

Streaming changes the failure model rather than removing it: a stream can end
mid-structure, so a streamed response is not valid until it is complete. Validate
at the end, not as it arrives, unless the consumer genuinely tolerates a partial
answer.

## Cost and token budgets

Cost is a function of what you send, and what you send usually grows without
anyone deciding to grow it — conversation history, retrieved documents, examples
added over time.

- Bound the input. Truncate deliberately, at a boundary you chose, and say which
  end you dropped.
- Bound the output. `max_tokens` is a correctness control as well as a cost one:
  an unbounded response can exhaust a context window that the next call needs.
- Count before you send, where the cost matters. Discovering the budget after the
  call is discovering the bill.
- Log tokens in, tokens out and model version per call. Without those, a cost
  regression is invisible until it is monthly.

## Caching

Identical input, identical prompt version, identical model version — the same
question does not need asking twice. The cache key has to include all three, or
a prompt change serves stale answers.

Where the provider offers prompt caching for a long stable prefix, the ordering
of the prompt becomes a cost decision: stable content first, variable content
last.

## Configuration and secrets

- The provider and the model are a **technology decision under AP-03**, recorded
  in `.ai-engineering/project.yaml` under `ai_system.model_providers` like any
  other approved component. Do not integrate against one that is not there.
- The model, the version and the parameters are configuration, not constants in
  the call site. A model version pinned in twelve files is twelve places to miss.
- **Pin the version.** "Latest" means the system's behaviour changes without a
  deployment, and the evaluation that passed was against something else.
- API keys come from the secret manager. Never in the repository, never in a
  log line, never in an error message that reaches a user.

## What to log, and what not to

Log the identifiers, the versions, the token counts, the latency and the
outcome. Whether to log the prompt and the response is a **data-classification
decision**, not a debugging preference: the prompt frequently contains user data
and the response frequently contains more of it. See `ai-observability`.

## Rules

- Validate every response against a schema. A response that does not validate did
  not succeed.
- One retry for malformed output, none for refusals, backoff for transport.
- Every call has a timeout, an output bound and a recorded cost.
- Pin the model version. An unpinned version invalidates every evaluation you ran.
- The response is untrusted input. Treat it the way you treat a request body.
