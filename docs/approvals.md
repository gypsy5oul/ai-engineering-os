# Approval authority

The single most dangerous confusion in an AI engineering organization is letting
an AI verdict pass as a human approval. The system then looks governed while
governing nothing.

## Two kinds of gate, never the same field

| | `agent_gate` | `human_gate` |
| --- | --- | --- |
| Produced by | An AI reviewer that did not author the artifact | A named human |
| Can block | Yes | Yes |
| Can approve on the organization's behalf | **No** | Yes |
| Durable | No | Yes |
| Recorded in | The merge request or the artifact, as a verdict | GitLab MR approval, GitLab release, or the project decision log |
| Means | Independent review found, or did not find, defects | The organization has accepted the consequences |

**An agent gate never satisfies a human gate.** A stage that needs both declares
both. Enforced by `scripts/validate_plugin.py` and asserted by
`EVAL-GOV-004` and `tests/test_repository.py`.

In artifacts the same split exists as two separate front-matter fields:
`reviewers` (agent verdicts) and `approvals` (human decisions). They never merge.

## Agent-team lead plan approval

Claude Code lets an agent-team lead approve or reject a teammate's plan, and the
lead decides autonomously — the operator is not asked.

That is an **agent gate**. It may satisfy a stage's `agent_gate` where the lead
is not the stage owner. It may never satisfy a `human_gate`, and it must never be
recorded against an `AP-nn` category. The only operator influence over it is the
criteria written into the spawn prompt.

## Hook escalation is not approval either

A `PreToolUse` hook returning `escalate` makes Claude Code ask the operator about
**one tool call**. It creates no record, binds no later action, and does not
survive the session.

Treating that as an AP-01 production approval would mean production deployment
was approved by whoever happened to be at the keyboard, with no record of what
they approved. Durable approval is a GitLab artifact; see
[system of record](#where-approval-lives).

## The approval categories

Eleven, in `policies/approval-policy.json`, each with an id, a reason and the
mechanism that enforces it. A stage that names an `AP-nn` must carry a
`human_gate`; validation warns when it does not.

The policy also carries an explicit list of what stays **autonomous**. That list
matters as much as the gates: a system that asks for approval on routine work
trains people to approve without reading, and then the gates that matter get the
same reflex.

## An approval must be attributable

`schemas/artifact-header.schema.json` requires the identity structurally:

```yaml
approvals:
  - id: AP-01-9283               # unique instance, not the category
    policy_ref: AP-01
    approver_id: gitlab:jchen    # a person
    approver_role: release-approver   # a HUMAN role, never an agent name
    at: 2025-11-14T09:12Z
    recorded_in: gitlab-release
    decision: approved
    comment: Rollback verified against the 1.3 schema.
```

`approver_role: release-manager` is invalid, because `release-manager` is an
agent. The named humans come from `.ai-engineering/project.yaml` under
`approval:`, and a category with no named human cannot be satisfied — validation
says so rather than letting it pass.

## Release: three acts, not one

`policies/release-authority.json` splits what 0.2.0 collapsed:

| Act | Who | Release state | Grants |
| --- | --- | --- | --- |
| **Release approval** | A named human accepts the *content* | `in-review → approved` | Nothing about deployment |
| **Deployment authorization** | The named release approver, **at deployment time** | `approved → authorized` | Permission to deploy, now |
| **Deployment execution** | devops-engineer or CI | executes against `authorized` | — |
| **Verification** | release-manager with sre, never the executor alone | `authorized → done` | — |

In 0.2.0 approval and authorization were one act, so a release approved on Monday
carried standing permission to deploy on Friday against a production that had
since changed. `AUTHORIZE` is a separate stage in both deploying workflows, and a
rollback needs the same authorization.

The two acts now carry **different approval ids**. Until 0.9.0 both were `AP-01`,
which meant the release approval already satisfied the authorization's own
definition of done: the separation the table describes existed in prose and not
in anything a machine checked. Content approval is `AP-01`; authorizing
deployment now is `AP-14`.

**Execution is not a third decision.** `DEPLOY` used to carry its own human gate
with the same approver and the same policy reference as `AUTHORIZE`, deciding
nothing that had not just been decided. It now depends on the authorization
being recorded, and the production commands themselves still reach the human
through `guard_bash`. A gate that asks a question whose answer is already
determined teaches people to approve without reading, and then the gates that
matter get the same reflex.

## Where approval lives

`policies/system-of-record.json` states it plainly:

- **GitLab** is authoritative for approvals, review history, pipelines, releases.
- **Repository artifacts** are authoritative for requirements, architecture,
  tests, incidents and RCAs.
- **The agent-team task list, the session transcript and the local audit log are
  authoritative for nothing.**

The resumability test: delete the session and the task list. Can another
engineer, from GitLab and the repository alone, say what stage the change is in,
what is missing, and who owes what? If not, the artifact contract is incomplete —
not the tooling.
