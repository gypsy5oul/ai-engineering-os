---
name: threat-modeling
description: Build or update a threat model for a system or change - assets, trust boundaries, entry points, threats and controls. Use during architecture for anything handling credentials, identity, untrusted input, sensitive data or external exposure, and when the attack surface changes.
---

# Threat modeling

Four questions: what are we building, what can go wrong, what are we doing about it, and did we do a good enough job.

## 1. What are we building

Draw the data flow: external actors, processes, data stores, and the flows between them. Mark the **trust boundaries** — every point where data crosses from a less trusted context into a more trusted one. Boundaries are where the controls belong.

Name the **assets**: what an attacker would want. Usually data, credentials, availability, integrity of a business process, or the ability to act as someone else.

## 2. What can go wrong

Walk each element with STRIDE and keep only what is plausible here:

| Threat | Question |
| --- | --- |
| Spoofing | Can someone claim an identity that is not theirs? |
| Tampering | Can data or code be modified in transit or at rest? |
| Repudiation | Can an action be denied because nothing records it? |
| Information disclosure | Can data reach someone who should not see it? |
| Denial of service | Can availability be removed cheaply? |
| Elevation of privilege | Can someone do more than their role allows? |

Then add the ones STRIDE misses: abuse of legitimate functionality, business-logic flaws, insider misuse, supply-chain compromise, and the failure modes of the controls themselves.

For each threat: the attacker, the entry point, the path, the impact.

## 3. What are we doing about it

For each threat: the existing control, or the control to be added, or an explicit decision to accept the risk. Every control becomes a **testable security requirement** handed to `qa-lead`. A control with no test is an intention.

Prefer, in order: eliminate the surface, prevent, detect, contain, recover.

## 4. Did we do a good enough job

- Does every trust boundary have a control?
- Does every asset have an owner and a stated protection level?
- Would detection notice the exploitation of each unmitigated threat?
- Which controls are single points of failure?
- What did we decide to accept, who accepted it, and when does that expire?

## Keeping it alive

A threat model is updated when the architecture changes, when a new integration is added, when data classification changes, and after any security incident. A model that is a year old and unchanged has stopped describing the system.

## Output

Store in `docs/security/` with an artifact header. Reference it from the architecture and from every security review of the affected area.
