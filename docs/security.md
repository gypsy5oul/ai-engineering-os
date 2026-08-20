# Security model

## Identity and credentials

**Every engineer uses their own Claude account.** There is no shared account and
no service identity. Work is attributable to a person.

**This repository contains no secrets of any kind** — no Claude credentials, no
API keys, no tokens. `scripts/secret_scan.py` runs in CI over the whole tree and
fails the pipeline on a critical finding.

Project secrets live in the project's declared secret manager
(`security.secret_management` in `.ai-engineering/project.yaml`), are injected at
runtime, and never appear in a repository, an image or a pipeline definition.

## Layers

| Layer | Enforcement | Example |
| --- | --- | --- |
| Tool profiles | Mechanical: the tool is absent | A reviewer has no `Write` and cannot author what it reviews |
| Write scopes | Mechanical: `guard_write.py` | A QA engineer cannot modify the code under test |
| Command guards | Mechanical: `guard_bash.py` | Production mutation is denied; `terraform apply` escalates |
| Spawn guard | Mechanical: `guard_spawn.py` | A developer cannot pull in a CRITICAL role |
| Approval gates | Human | Production deployment, security exceptions |
| Role contracts | Behavioural | "Never approve your own work" |
| Review routing | Process | Security review on every auth-touching change |

Anything that must hold regardless of model behaviour is in the mechanical rows.

## Secret handling

**Never read:** private keys, `~/.aws/credentials`, `~/.kube/config`, `.netrc`,
Docker config, GPG material. Denied by SEC-01.

**Never write:** key material and git internals are hard-denied.
Credential-adjacent files such as `.env` escalate to the human, because editing a
local `.env` is legitimate and a blanket denial would be routed around.

**Never transmit:** sending credential files to a network destination is denied
by SEC-03, and committing them by SEC-06.

**Never emit:** content matching a critical secret pattern is denied before the
write happens. Obvious placeholders (`${VAR}`, `changeme`, `<REDACTED>`,
`your-secret-here`) are allowed, because a guard that blocks documentation
examples gets disabled.

Detection is heuristic and is a safety net, not a replacement for a dedicated
scanner in CI. `policies/secret-patterns.json` carries the patterns.

**If a secret was ever committed, it must be rotated.** Deleting the file does
not remove it from history, and history rewriting is denied by GIT-03 precisely
because it destroys the audit trail while creating an illusion of cleanup.

## High-risk operations

`policies/approval-policy.json` lists eleven categories requiring a human:
production deployment, architecture-changing decisions, technology selection,
security exceptions, destructive migrations, breaking API changes, major
infrastructure changes, credential changes, protected-branch writes, changes to
this repository's control plane, and production data access.

Everything else is explicitly autonomous, and the policy says so, because a
system that asks for approval on trivial work gets approved without being read.

## Security organization

Independent by construction:

| Role | Authority |
| --- | --- |
| `security-architect` | Threat models, security requirements, control design. Cannot review its own designs. |
| `security-reviewer` | Reviews changes. **Blocks a merge or release on HIGH or CRITICAL.** Read-only. |
| `dependency-reviewer` | Supply chain: vulnerability, licence, maintenance, transitive risk. |
| Human Security Head | Grants exceptions (AP-04). Named in `GOVERNANCE.md`. |

An exception record carries the residual risk, a compensating control and an
expiry. An exception without an expiry is a policy change in disguise.

`skills/threat-modeling` and `skills/security-review` carry the method. Support
for threat modeling, application security, cloud and Kubernetes security, IAM,
dependency security and penetration testing is expressed through those skills and
the reviewer roles rather than through a dedicated agent per specialism.

## Prompt injection and untrusted content

Content read from a repository, a web page, a merge request comment or an MCP
server is **data, never instructions**. This matters most for the reviewer roles,
which read exactly the kind of attacker-influenced content that would carry an
injection. The mechanical layers are what make this survivable: an injected
instruction that succeeds still cannot make a read-only reviewer write a file, or
make a developer push to `main`.

## Audit

`${CLAUDE_PLUGIN_DATA}/audit/YYYY-MM.jsonl` records guard decisions, waiver use,
file changes and guard errors. It is local, per-machine, and not tamper-evident.
The organizational audit trail is GitLab: commits, merge requests, approvals,
pipelines. See `docs/limitations.md`.

## Reporting

Vulnerabilities in this plugin: see `SECURITY.md`. Do not open a public issue.
