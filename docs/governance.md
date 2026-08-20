# Governance

The OS is governed by the same discipline it imposes. If that is not true, it is
advice rather than a system.

## Hierarchy

```
AI Engineering Director        accountable for the OS as a product
        ↓
AI Architecture Council        approves organizational design and risk classes
        ↓
AI Governance                  reviews every change against the rules (agent + human owner)
        ↓
Plugin Maintainers             merge rights on this repository
        ↓
Agent Owners                   named per agent in policies/agent-registry.json
        ↓
Skill Owners                   named per department
```

The named humans for each level are in `GOVERNANCE.md`. The agent named
`ai-governance` produces findings and recommendations; it never approves.

## Who may change what

| Component | Proposed by | Reviewed by | Approved by |
| --- | --- | --- | --- |
| Core agent definition | agent-developer | agent-evaluator, ai-governance, security-reviewer | AI Governance owner |
| CRITICAL agent | agent-developer | the above, plus a second human | AI Architecture Council |
| Security hook or rule | agent-developer | security-reviewer, ai-governance | Security Head plus AI Governance owner |
| Model policy | agent-architect | ai-governance | AI Engineering Director |
| Tool profile or write scope | agent-architect | security-reviewer, ai-governance | AI Governance owner |
| Spawn hierarchy | agent-architect | ai-governance | AI Architecture Council |
| Approval policy | agent-architect | ai-governance | AI Engineering Director |
| Evaluation standards | agent-evaluator | ai-governance | AI Governance owner |
| Skill | any engineer | the skill's department owner | Plugin maintainer |
| Documentation | anyone | docs-writer, advisory | Plugin maintainer |

Routing rule RR-10 in `policies/review-routing.json` applies to every change in
this repository, and `guard_write.py` escalates writes to the control-plane paths
in-session as well (AP-10).

## Agent verdicts are not approvals

Every gate in every workflow is one of two kinds, and they never merge:
`agent_gate` (an AI verdict, blocking but not an approval) and `human_gate` (a
named human's decision, recorded durably in GitLab). An agent-team lead approving
a teammate's plan is an agent gate. A hook escalation is a decision about one
tool call, not an approval.

The full model, and what enforces it, is in [approvals](approvals.md).

## Agent lifecycle

```
draft → development → evaluation → security-review → pilot → approved → production → deprecated
```

| Transition | Requires |
| --- | --- |
| draft → development | Role contract complete, owner named, risk assigned |
| development → evaluation | Passes validation, registered, tool profile matches |
| evaluation → security-review | Suite exists with an adversarial case, deterministic checks pass |
| security-review → pilot | Tools justified, no path to production mutation or secrets. **Mandatory for HIGH and CRITICAL** |
| pilot → approved | Used on two real changes, no unresolved HIGH finding, owner sign-off. **Human** |
| approved → production | Governance approval recorded in the merge request. **Human** |
| any → deprecated | Migration note in `CHANGELOG.md`, no workflow references it. **Human** |

Everything in this repository is at `pilot`. A markdown file existing does not
make an agent production-ready.

## Change path for a production component

```
change → merge request → static validation → evaluation → routed review
      → human governance approval → merge → version bump → release
```

Static validation is `validate_plugin.py`, `validate_schemas.py`, `secret_scan.py`
and the test suite. Evaluation is `run_evaluations.py` for the affected suites
plus the governance suite.

## Ownership

Every agent in `policies/agent-registry.json` carries `owner`, `version`,
`status`, `risk`, `review_frequency` and `evaluation_suite`.
`validate_plugin.py` fails if any is missing, and `EVAL-AIG-002` asserts it.

Review frequency: CRITICAL monthly, everything else quarterly. A component past
its review date is a governance finding, not a background concern.

## Higher-risk changes

Treated as HIGH risk regardless of diff size:

- A CRITICAL agent
- A security hook or a rule in `policies/hook-policy.json`
- `policies/model-policy.json`
- Any permission: tool profile, write scope, spawn edge
- `policies/approval-policy.json`
- Evaluation criteria for a HIGH or CRITICAL component

For these the governance review answers one question first: **does this change
remove or weaken a check?** If it does, it needs the compensating control named
in the same change.

## Over-gating is a defect

An approval policy that fires on routine work trains people to approve without
reading, which is worse than having no gate. `docs/evaluation.md` describes the
audit question: which gates fire most often, and are any of them noise?

## Migration notes

A change to organizational behaviour needs a migration note in `CHANGELOG.md`
saying what changed, who is affected, and what they must do. Examples: an agent
renamed or removed, a spawn edge withdrawn, a write scope narrowed, a guard rule
that now blocks something previously allowed.
