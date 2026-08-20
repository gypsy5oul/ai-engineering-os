# Contributing

Read [`docs/development.md`](docs/development.md) first; it has the mechanics.
This file is the expectations.

## Before you open a merge request

```bash
python3 scripts/validate_plugin.py
python3 scripts/validate_schemas.py
python3 scripts/secret_scan.py .
python3 -m unittest discover -s tests
python3 scripts/run_evaluations.py
claude plugin validate .
```

CI runs the same things. Running them locally is faster than finding out twice.

## What gets rejected

- **A new agent that duplicates an existing role.** If it has the same authority,
  inputs and outputs, it is that role. See `docs/agent-model.md`.
- **A guard rule without both tests.** One that it blocks, one that it does not
  block the ordinary case that resembles it.
- **A guard rule without a remediation.** Validation fails on it; a denial with
  no alternative teaches people to route around the guard.
- **A hard-coded technology in the company layer.** Technology is a project
  decision.
- **A dated model identifier.** Aliases only.
- **Fake functionality.** If the platform cannot do it, document the limitation.
  A documented extension point beats something that looks like it works.
- **A new approval gate on routine work.** Over-gating is a defect.
- **An agent, skill or workflow without evaluation coverage.**
- **Placeholder text.** `TODO` in a shipped role contract fails review.

## Merge request description

What, why, how verified, risk, rollback, and traceability identifiers. A merge
request that does not say how it was verified is not ready for review.

## Review

Routed by `policies/review-routing.json`. Every change here matches RR-10:
`agent-evaluator`, `ai-governance` and `security-reviewer`, plus a human.

**The author never approves.** Not on this repository, and not on any project
using it.

## Writing style

The documentation and the role contracts are read by people under time pressure
and by models with finite context. Both are served by the same thing: say what
matters, say it once, and be specific.

- Prefer the concrete over the general. "Bound the query" beats "consider
  performance".
- State the limitation. A document that lists only benefits has not been thought
  through.
- Do not restate general good practice. A skill that could apply to any project
  in any language is costing context and changing nothing.
- Give the reason when the rule is not obvious. People follow rules they
  understand and route around rules they do not.

## Reporting a defect in a guard

A false positive is a defect and matters more than most: a guard that fires on
normal work gets disabled, and a disabled guard protects nothing. Open an issue
with the exact command or path, the rule id from the message, and why the case is
legitimate.

## Security

See [`SECURITY.md`](SECURITY.md). Report vulnerabilities privately.
