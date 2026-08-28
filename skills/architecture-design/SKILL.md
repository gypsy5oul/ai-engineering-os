---
name: architecture-design
description: Produce feasibility assessments, high- and low-level design, deployment, availability and capacity models for an approved requirement set. Use after requirements are approved and before implementation, and for any change that alters system structure. Stays inside the project's approved technology.
---

# Architecture design

Design to the requirements that exist, in the technology that is approved, and record why.

## Output set (produce what the change actually needs)

| Artifact | Produce when |
| --- | --- |
| Feasibility assessment | Always, before detailed design |
| High-level design | The change adds or alters a component or a boundary |
| Low-level design | For components this change touches, not the whole system |
| API contracts | Any interface changes; see `api-design` |
| Data model and migration strategy | Any persistent structure changes; see `database-design` |
| Deployment architecture | Deployment topology or runtime footprint changes |
| Availability and DR model | The requirements state availability, RPO or RTO |
| Capacity model | The requirements state volume, throughput or growth |
| Security architecture | Any trust boundary, identity or data-protection surface; with `security-architect` |
| Observability architecture | Any new failure mode; with `sre` |
| ADRs | Every significant decision; see `adr-management` |
| Risk register update | Always |

Producing artifacts nobody needs is a defect, not thoroughness. Say which you are not producing and why.

## Method

1. **Restate the requirements you are designing to**, with identifiers. If a requirement is unquantified and material, stop and send it back.
2. **Establish the current state** by reading the code, not by assuming the documentation is accurate.
3. **Identify the forces**: the requirements, constraints and existing decisions that limit the solution space.
4. **Design the simplest structure that satisfies the forces** — the simplest, not the smallest: a design that drops a stated requirement is incomplete, not simple. Then draw it again at half the components and name which stated requirement fails. If none does, remove them. Complexity added for imagined future requirements is a finding at review.
5. **Record the complexity ledger.** One entry per component, boundary or dependency the design introduces, each naming the requirement, measurement or constraint that forces it and the simpler alternative it beats. A design that introduces none records an empty ledger. The `engineering-simplicity` skill has the format and what does not count as evidence; `complexity_justified(ARCH)` reads it.
6. **Walk the failure modes.** For each component: what happens when its dependency is slow, unavailable, or returns wrong data? Write the answers down.
7. **Walk the data lifecycle**: created where, owned by whom, migrated how, retained how long, deleted by what.
8. **State the consequences**, including the ones you dislike. A design document that lists only benefits has not been thought through.

## Structure of a high-level design

- Context: what this system does and what it talks to.
- Components: each with a single stated responsibility.
- Interactions: the sequences that matter, especially the failure sequences.
- Boundaries: trust, transaction, ownership and deployment boundaries, which rarely coincide.
- Cross-cutting: identity, configuration, secrets, telemetry, error handling.
- Non-functional treatment: how each quantified NFR is met, with the mechanism named.
- Risks and the decisions that remain open.

## Rules

- Every technology named must appear in `.ai-engineering/project.yaml` as approved, or be accompanied by a technology-decision proposal (AP-03).
- Design for the stated targets. Designing for ten times the stated load is a decision that needs stating and costing, and an unquantified expectation of growth is not a target: send it back to requirements to be quantified rather than absorbing it into the design.
- You do not approve your own design. `architecture-reviewer` does, and it is a different agent.
- A breaking change to a public contract is AP-06: escalate before the design is finalised.
