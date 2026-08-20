# Security

## Reporting a vulnerability

Report privately to the Security Head named in `GOVERNANCE.md`, or to the
organization's security contact. **Do not open a public issue.**

Include: what the weakness is, how it is reached, what it achieves, and the
version or commit. A report without a reachability path is still welcome; say
that you have not established one.

Acknowledgement within two working days; an assessment with severity and a
remediation plan within five.

## Scope

**In scope:** a guard that can be bypassed; a path from an agent to secret
material, production mutation or a protected branch that does not pass a gate; a
permission wider than the role requires; anything in this repository that makes
another repository less safe.

**Out of scope:** issues in Claude Code itself (report to Anthropic); a
misconfigured project's own `.ai-engineering/` (report to that project); a guard
that produces a false positive — that is a defect, and belongs in the issue
tracker.

## No secrets here

This repository contains no credentials of any kind. Every engineer uses their
own Claude account; there is no shared account and no service identity.

`scripts/secret_scan.py` runs in CI over the whole tree and fails the pipeline on
a critical finding. If a secret is ever committed here, **it must be rotated** —
history rewriting is denied by rule GIT-03 because it destroys the audit trail
while creating an illusion of cleanup.

## Security model

See [`docs/security.md`](docs/security.md) for the layered model, secret handling,
the approval categories, and the security organization.

## Known weaknesses

Named honestly in [`docs/limitations.md`](docs/limitations.md). The ones that
matter most:

- Behavioural rules in role contracts are contracts, not guarantees.
- Secret detection is heuristic; use a dedicated scanner in CI as well.
- The audit log is local and not tamper-evident.
- "The author must not approve" is a setting plus discipline on GitLab CE.
- Hooks evaluate one tool call at a time and cannot reason about a sequence.
- The spawn guard is a guardrail on delegation, not an authorization boundary.

## Changing a security control

Any change to a hook, a rule, a tool profile, a write scope or the approval
policy is AP-10: governance review, security review, and human approval. The
governance review asks one question first — does this remove or weaken a check —
and if it does, the compensating control must be in the same change.
