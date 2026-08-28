# Simplicity by default

A core architectural principle of the AI Engineering OS. Every project built with
this plugin inherits it.

> **Build the simplest thing that satisfies the functional, non-functional,
> reliability, security, scalability and operational requirements that have
> actually been stated and approved.**

## Why this is a first-class capability and not advice

Advice loses to schedule pressure and to the first idea. This principle is a
capability because it has the same four parts every other rule in this repository
has:

| Part | Where |
| --- | --- |
| The reusable capability roles load | [`skills/engineering-simplicity/SKILL.md`](../skills/engineering-simplicity/SKILL.md) |
| The machine-readable rule | [`policies/simplicity-policy.json`](../policies/simplicity-policy.json) |
| The lifecycle gate | `complexity_justified(ARCH)` in the ARCH stage of `WF-FEATURE` |
| The proof it works | [`evaluations/simplicity-evaluation/`](../evaluations/simplicity-evaluation/) |

The skill and the policy are two halves of one rule. The skill is what an agent
reads; the policy is what the checker reads. `scripts/check_dod.py` loads the
required justification fields from the policy rather than hard-coding them, so
the instruction and the check cannot drift apart.

## The rule, precisely

It is **not** "always choose the smallest solution". A design that drops a stated
requirement is not simple, it is incomplete, and calling it simple is the most
common way this principle gets abused. `EVAL-SIMP-007` is the case for exactly
that abuse.

It is **not** a prohibition on complexity. Some systems need a queue. The rule is
that complexity is **bought with a requirement**, and the purchase is written
down. `EVAL-SIMP-008` is the case where the purchase is legitimate and the
reviewer must accept it.

It is **not** a veto. Nothing here blocks a tool call. See *What is not enforced*
below.

## The two questions

Every design choice reduces to two questions, asked in order:

1. **What is the simplest thing that satisfies the requirements?** Name it
   concretely, even if you will not choose it.
2. **Which stated requirement does that simpler thing fail?** Name the identifier
   and the number.

If no stated requirement fails, the simpler option wins and the extra complexity
is a **major** finding: it is unrequested work that somebody will operate forever.

Both degenerate answers matter:

- *No simpler option was named.* The comparison never happened; the first idea
  won by default.
- *The simpler option fails a requirement nobody wrote down.* That is a
  prediction, not a requirement. It goes back to requirements to be quantified
  and approved, or it is dropped. `EVAL-SIMP-009` is that case.

## Preference order

1. Do nothing.
2. Use what the project already has (`.ai-engineering/project.yaml`).
3. Use what the platform already gives you.
4. Extend something already approved.
5. Add a boring, well-understood component.
6. Build something new.

Do not descend a rank without naming the requirement that forced it. Each step
down costs more to build, more to operate, more to hire for and more to leave.

## What counts as evidence

| Kind | What it is |
| --- | --- |
| **Requirement** | A quantified, approved requirement the simpler option demonstrably misses |
| **Measurement** | A number from this system, a load test, a benchmark or a production metric |
| **Constraint** | An external, documented obligation: residency, a partner protocol, a licence term |

Not evidence: "we might need to scale", "it is the industry standard", "it is
more flexible", "it is cleaner", "we will need it later". The full list, with the
reason each one fails, is in the policy's `not_evidence` field.

## The complexity ledger

The written output, carried on the architecture artifact in a `complexity` field:

```yaml
complexity:
  - component: message-broker
    driver: NFR-004
    simpler_alternative: >-
      Poll the existing PostgreSQL table with SELECT ... FOR UPDATE SKIP LOCKED.
    why_rejected: >-
      Measured at 40 jobs/s on the approved instance class against a stated
      requirement of 500 jobs/s sustained (NFR-004).
    evidence: measurement
    evidence_ref: docs/architecture/ACME-ARCH-002-load-test.md
    operational_cost: >-
      One more component to run, monitor, upgrade and back up. Adds a failure
      mode to a path that had none.
    reversible: >-
      Yes at moderate cost while the producer interface stays the same.
```

A design that introduces nothing writes `complexity: []`. **An empty ledger
passes. An absent one fails**, because it means the question was never asked.
That asymmetry is the whole design of the predicate: the honest answer must be
the cheap one, or every architect learns to invent an entry.

`complexity_justified(ARCH)` checks that the justification exists and is
complete. It never checks whether the judgement was right — that is
`architecture-reviewer`'s finding and the human's decision under AP-02. A
predicate that tried to answer "was the queue really necessary" would either pass
everything or block legitimate engineering.

## Where it applies

| Stage | What it means there |
| --- | --- |
| Requirements | Challenge unquantified, speculative and gold-plated requirements. Scope is the requester's decision: surface the cost, never drop it silently. |
| Architecture | The two questions on every component and boundary. Produce the ledger. |
| Technology selection | "Use what we have" is already a mandatory option; it wins unless a named requirement fails. |
| Story decomposition | Fewer handoffs and fewer integration points. Vertical slices over horizontal layers. |
| Development | No interface for one implementation, no configuration for one value, no framework inside a feature. Delete what the change makes dead. |
| Infrastructure | Count components, not features. Everything introduced is run, patched and carried on-call. |
| Performance | Baseline before optimizing. Prefer removing work to doing the same work faster. |
| Release | One deployable over a coordinated release; a reversible change over a forward fix. |

The `engineering-simplicity` skill is loaded at each of these stages by the role
that owns it, and preloaded in the frontmatter of the fifteen roles that make or
review these decisions.

## What is not enforced

No hook blocks a design, a dependency or a component on simplicity grounds, and
none ever will. A guard cannot tell a justified queue from an unjustified one.
One that tried would either block legitimate engineering — at which point the
organization routes around the rule and it protects nothing — or pass everything,
at which point it is theatre.

So the enforcement is exactly two mechanisms, both of which produce a record a
human can overrule:

- **A definition-of-done predicate** that checks the ledger exists and is
  complete.
- **A review route** (`RR-11`) that sends any change introducing a component,
  boundary or dependency class to `architecture-reviewer`, blocking, with
  `simplicity` as the named dimension. The route explicitly never returns "too
  complex" as a verdict on its own.

`EVAL-SIMP-004` is the case that tries to break this: it fails if the policy ever
grows a ban list, claims enforcement it does not have, or if any hook script
starts reading it.

## Reading the ledger as a reviewer

The reviewer's job is to check the purchase, not to prefer the smaller design.
Concretely:

- Is the simpler alternative named concretely enough to have been built?
- Does the rejection name a requirement identifier and a number?
- Does the evidence reference exist, and does it say what the ledger claims?
- Does the arithmetic work? 40 measured against 500 required decides it; "would
  not scale" does not.
- Is anything introduced that has no ledger entry at all?

A justified introduction passes. An unjustified one is a major finding, recorded
for the human who decides under AP-02 or AP-03.

## Related

- [`skills/engineering-simplicity/SKILL.md`](../skills/engineering-simplicity/SKILL.md) — the capability itself
- [`skills/technology-selection/SKILL.md`](../skills/technology-selection/SKILL.md) — when the approved stack does not cover a need
- [`skills/architecture-review/SKILL.md`](../skills/architecture-review/SKILL.md) — the proportionality section of the review checklist
- [approvals.md](approvals.md) — why a reviewer's finding is not a decision
- [limitations.md](limitations.md) — what is written down and followed rather than enforced
