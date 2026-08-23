# Governance

The full model is in [`docs/governance.md`](docs/governance.md). This file names
the people.

## Named roles

Replace these placeholders before adopting the plugin. An unnamed governance role
is an ungoverned one.

| Role | Holder | Responsibility |
| --- | --- | --- |
| AI Engineering Director | *unassigned* | Accountable for the OS as a product. Approves model and approval policy. |
| AI Architecture Council | *unassigned* | Approves organizational design, risk classes, spawn hierarchy. Minimum three members. |
| AI Governance Owner | *unassigned* | Approves component promotion and control-plane changes. |
| Security Head | *unassigned* | Approves security exceptions (AP-04). |
| Plugin Maintainers | *unassigned* | Merge rights on this repository. |

Agent owners are named per agent in `policies/agent-registry.json`.

## Decision rights

| Decision | Approver |
| --- | --- |
| Add, remove or merge a core agent | AI Architecture Council |
| Change a CRITICAL agent | AI Governance Owner plus a second human |
| Change a security hook or rule | Security Head and AI Governance Owner |
| Change model policy | AI Engineering Director |
| Change a tool profile, write scope or spawn edge | AI Governance Owner |
| Change the approval policy | AI Engineering Director |
| Change evaluation standards | AI Governance Owner |
| Promote a component to production | AI Governance Owner |
| Grant a security exception | Security Head |
| Add a skill | Plugin maintainer |
| Documentation | Plugin maintainer |

## Component status

Every agent and critical skill carries an owner, a version, a risk class, a
lifecycle status, a review frequency and an evaluation suite in
`policies/agent-registry.json`. `scripts/validate_plugin.py` fails if any is
missing.

**All 30 agents are currently at `pilot`.** Promotion to `production` requires a
human decision per the lifecycle in `docs/governance.md`.

## Review cadence

| Risk | Frequency |
| --- | --- |
| CRITICAL | monthly |
| HIGH | quarterly |
| MEDIUM / LOW | quarterly |

A component past its review date is a governance finding.

## Escalation

Disagreement between an agent and its reviewer escalates to the reviewer's
department owner. Disagreement between departments escalates to the AI
Engineering Director. Anything touching the ability to detect or prevent harm
escalates to the AI Governance Owner immediately, ahead of the merge request it
was found in.
