---
name: engineering-simplicity
description: Choose the simplest solution that satisfies every stated requirement, and justify complexity when it is genuinely needed. Use when designing a system, selecting technology, adding a component or dependency, decomposing stories, implementing a change, sizing infrastructure, or tuning performance. Produces a complexity justification, never a prohibition.
---

# Engineering simplicity

The rule is one sentence:

> **Build the simplest thing that satisfies the functional, non-functional, reliability, security, scalability and operational requirements that have actually been stated and approved.**

Everything below is that sentence applied.

## What this is not

It is **not** "always choose the smallest solution". A design that drops a stated
requirement is not simple, it is incomplete, and calling it simple is the most
common way this principle gets abused.

It is **not** a prohibition on complexity. Some systems need a queue. Some need
partitioning. Some need a service boundary. The rule is that complexity must be
**bought with a requirement**, and the purchase must be written down.

It is **not** a veto. This produces findings and justifications. Humans decide
(AP-02, AP-03).

## The two questions

Every design choice, at every stage, reduces to two questions asked in order:

**1. What is the simplest thing that satisfies the requirements?**

Name it concretely, even if you will not choose it. "A single process with a
table and a `WHERE claimed_at IS NULL` update" is concrete. "Something simpler"
is not. If you cannot name the simpler option, you have not looked for one.

**2. Which stated requirement does the simpler thing fail?**

Name the requirement identifier and the number. If no stated requirement fails,
the simpler option wins and the extra complexity is a finding.

The failure modes of this test are both worth naming:

- **No simpler option named.** The comparison never happened; the first idea won.
- **The simpler option "fails" a requirement nobody wrote down.** That is not a
  requirement, it is a prediction. Send it back to requirements to be stated and
  quantified, or drop it. See *Evidence* below.

## Preference order

When several options satisfy the requirements, prefer in this order:

1. **Do nothing.** The requirement is already met, or does not justify a change.
2. **Use what the project already has.** An approved database, an approved
   framework, an existing service, an existing table.
3. **Use what the platform already gives you.** The language's standard library,
   the runtime's scheduler, the database's transactions, the framework's
   validation, the cloud's managed equivalent of the thing you were about to run.
4. **Extend something already approved.** One more table, one more endpoint, one
   more column.
5. **Add a boring, well-understood component**, chosen for how well it is
   understood by the people who will operate it at 3am.
6. **Build something new.**

Each step down costs more to build, more to operate, more to hire for and more to
leave. Do not descend a step without saying which requirement forced it.

## Complexity that needs a justification

These are not banned. Each one, when introduced, needs a written justification
(the format is below). The machine-readable list lives in
`${CLAUDE_PLUGIN_ROOT}/policies/simplicity-policy.json`; this is the same list in prose.

**Infrastructure and runtime components**

- A new datastore, or a second datastore of a kind the project already has
- A message queue, broker or event bus
- A cache as a separate component
- A search index separate from the primary store
- A workflow or scheduling engine
- A service mesh, sidecar, operator or custom controller
- A new long-running process, daemon or worker tier

**Structure**

- Splitting one deployable into several (microservices)
- Introducing a distributed transaction, consensus or leader election
- Introducing asynchrony where a synchronous call satisfies the requirement
- Introducing eventual consistency where the requirement is transactional
- A new network hop on a path with a stated latency budget

**Code**

- A new abstraction layer, plugin system, or framework-within-the-framework
- A design pattern introduced for a second implementation that does not exist yet
- A custom implementation of something the platform, the language or an approved
  dependency already does correctly
- A configuration surface for something that has exactly one value in every
  environment

**Dependencies**

- Any new runtime dependency
- A dependency that overlaps an approved one
- A framework adopted to solve one problem inside it

**Capacity**

- Sharding, partitioning, read replicas or autoscaling introduced ahead of a
  measured or quantified need
- An optimization that costs readability, before a measurement showing the
  unoptimized version misses a stated target

## Evidence

A justification stands on evidence. There are exactly three kinds that count:

| Kind | What it is | Example |
| --- | --- | --- |
| **Requirement** | A quantified, approved NFR or functional requirement that the simpler option demonstrably misses | `NFR-004: p99 ≤ 200ms at 4,000 rps`; the single-process option was measured at 900ms |
| **Measurement** | A number from this system, a load test, a benchmark or a production metric | The nightly job takes 6h against a 4h window |
| **Constraint** | An external, documented obligation | Data residency in two regions; a partner protocol that is push-only; a licence term |

What does **not** count as evidence:

- "We might need to scale." Unquantified growth is not a requirement. Quantify it
  in the NFR set and approve it, or design for what is stated.
- "This is the industry standard." Popularity is a proxy for ecosystem maturity
  and nothing else.
- "It is more flexible." Flexibility that no stated requirement uses is cost with
  no buyer.
- "It is cleaner." Say what it makes cheaper, and for whom.
- "We will need it later." Later has an option value; state it as a date or a
  trigger condition, or leave it out.

## The complexity justification

The written output. One entry per item of complexity introduced. Keep it in the
architecture artifact or the ADR, in a `complexity` field, so
`complexity_justified(ARCH)` can read it:

```yaml
complexity:
  - component: message-broker
    driver: NFR-004                       # requirement, measurement or constraint
    simpler_alternative: >-
      Poll the existing PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED.
    why_rejected: >-
      Measured at 40 jobs/s on the approved instance class against a stated
      requirement of 500 jobs/s sustained (NFR-004).
    evidence: measurement
    evidence_ref: docs/architecture/ACME-ARCH-002-load-test.md
    operational_cost: >-
      One more component to run, monitor, upgrade and back up. Adds a failure
      mode (broker unavailable) to a path that had none.
    reversible: >-
      Yes at moderate cost while the producer interface stays the same; the
      migration back is one adapter and a drain.
```

A change that introduces no complexity says so explicitly:

```yaml
complexity: []
```

An empty list is a real answer and passes the check. An **absent** field does
not: it means the question was never asked.

## Applying it by stage

**Requirements.** Simplicity starts here, because the cheapest way to build a
simple system is to be asked for one. Challenge requirements that are
unquantified, speculative or gold-plated: an unquantified NFR becomes an
unbounded design. Ask "what breaks if this number is 10× smaller?" Requirements
are the requester's decision — surface the cost, do not silently drop scope.

**Architecture.** The two questions, on every component and every boundary. Draw
the design at half the components and say which requirement fails. Produce the
`complexity` ledger.

**Technology selection.** The `technology-selection` skill already forces "use
what we have" into the option set. This skill says what to do with it: it wins
unless a named requirement fails. Total cost of ownership and exit path are part
of the comparison, not an afterthought.

**Story decomposition.** A story split into six because the design has six layers
is a symptom, not a plan. Prefer the decomposition with fewer handoffs and fewer
integration points. Vertical slices over horizontal layers.

**Development.** Do not add an interface for one implementation. Do not add
configuration for one value. Do not build a framework inside the feature. Use the
standard library. Delete code that the change makes dead — reduction is the
cheapest simplification available and it is almost always skipped.

**Infrastructure design.** Every component runs, gets monitored, gets patched,
gets on-call. Count components, not features. A design with fewer moving parts
that meets the SLO is better than one that meets it more elegantly.

**Performance work.** Measure first, always. An optimization with no baseline is
complexity with no evidence. Prefer the fix that removes work over the fix that
does the same work faster; prefer the fix that stays readable.

**Release design.** Prefer one deployable unit over a coordinated multi-service
release. Prefer a reversible change over one needing a forward fix. A rollback
that requires a runbook with eleven steps is a design finding, not a release
finding.

## What "simple" means, precisely

Simple is not "few lines" and not "few concepts". Optimize for **total system
complexity**, measured as:

- **Maintainability** — how long it takes someone who did not write it to change
  it correctly.
- **Operability** — how many things must run, be monitored, be patched and be
  on-call.
- **Debuggability** — how many hops, queues and asynchronous boundaries stand
  between a symptom and its cause at 3am.
- **Cognitive load** — how much a person must hold in their head to be correct.
- **Exit cost** — what it takes to undo this in two years.

A design that moves complexity somewhere else has not removed it. Say where it
went.

## Rules

- Name the simpler option before rejecting it. An unnamed alternative was never
  considered.
- Reject a simpler option by naming a requirement, with its identifier and its
  number. Not a feeling, not a forecast.
- Complexity with no requirement behind it is a **major** finding: it is
  unrequested work that someone will operate forever.
- An unquantified requirement is a requirements finding, not a licence to design
  for the worst case you can imagine.
- Never present this principle as a reason to skip a stated non-functional,
  reliability or security requirement. That is not simplicity, it is a defect
  with a slogan attached.
- The principle guides and evaluates. It does not block. A human decides
  (AP-02 for architecture, AP-03 for technology), and a decision to accept
  complexity that was properly justified is a legitimate engineering decision.
