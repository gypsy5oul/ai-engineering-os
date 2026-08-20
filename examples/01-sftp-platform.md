# Example 01 — Build an enterprise SFTP platform

A greenfield capability through `WF-FEATURE`. The interesting parts are the two
places the organization refuses to proceed, and the stage it skips on purpose.

**Configuration:** [`sftp-platform/.ai-engineering/project.yaml`](sftp-platform/.ai-engineering/project.yaml)
**Guards in action:** `./examples/run_demo.sh`

---

## Stage 0 — Intake

```
> We need a managed SFTP platform so partners can drop files for us
  instead of emailing them.
```

`session_context.py` has already reported that no `.ai-engineering/` exists.
`sdlc-navigator` therefore reports:

> **Workflow:** WF-FEATURE. **Entry condition failed:** no project configuration.
> Before requirements can be approved, the project's approved stack, environments,
> security and testing requirements must be recorded by a human.
> **Next action:** `/ai-engineering-os:project-onboarding`.

This is the first refusal, and it is the important one. Without it every
downstream agent would invent a stack.

## Stage 0.5 — Onboarding

`WF-ONBOARDING` discovers an empty repository, so there is nothing to observe and
everything to ask. The human answers; the result is the shipped configuration.

Two answers shape everything after:

```yaml
project: { key: SFTP, tier: 1 }
security: { data_classification: confidential }
technology:
  backend: { language: go, framework: standard-library, status: approved }
  # No frontend layer: this platform has no user interface.
```

One question has no answer yet:

```yaml
open_decisions:
  - id: SFTP-OD-001
    question: What is the required RPO and RTO for the audit log store?
    owner: Integration Platform Team lead
    blocking: true
```

## Stage REQ — Requirements

`product-manager` produces the PRD; `requirements-analyst` decomposes it.

```
SFTP-REQ-001  Partners authenticate with SSH public keys, one key set per partner.
SFTP-REQ-002  Each partner sees only its own directory. Path traversal is impossible.
SFTP-REQ-003  Every transfer is recorded with partner identity, filename, size,
              SHA-256 digest and timestamp, in an append-only log.
SFTP-REQ-004  Host keys can be rotated without dropping established sessions.
SFTP-NFR-001  99.5% of partner transfers succeed, measured over 30 days.
SFTP-NFR-002  Session establishment p95 under 800ms.
SFTP-NFR-003  Audit records are retained for 7 years.
SFTP-NFR-004  RPO/RTO for the audit store — OPEN, blocks HA/DR design (SFTP-OD-001).
```

`SFTP-NFR-004` is the second refusal. The analyst does not write "RPO 1 hour"
because it sounds reasonable; it records an open question that blocks the
disaster-recovery portion of the architecture. `EVAL-REQ-001` is the evaluation
case for exactly this behaviour.

Everything else proceeds. The blocked item blocks one section, not the project.

## Stage ARCH — Architecture

`solution-architect` produces the design and the ADRs.

```
SFTP-ADR-001  Go with the standard library SSH implementation
              — the alternative of an off-the-shelf SFTP server was rejected
                because SFTP-REQ-003's digest-and-audit requirement would have to
                live outside the transfer path.
SFTP-ADR-002  PostgreSQL for the audit log, with append-only constraints
SFTP-ADR-003  Per-partner chroot-equivalent path confinement in the server itself
SFTP-ADR-004  Host key rotation via a key set with an overlap window
SFTP-ARCH-002 High-level design
SFTP-ARCH-003 HA/DR — INCOMPLETE, blocked on SFTP-OD-001
```

`security-architect` produces `SFTP-SEC-001`, the threat model. Its trust
boundary analysis adds two security requirements that become acceptance criteria:
partner credentials never reach application logs, and the audit log is
append-only at the database level rather than by convention.

`architecture-reviewer` — a different agent, with no write tools — reviews and
returns:

> **Requirement coverage:** SFTP-REQ-001…004 covered. SFTP-NFR-001, 002, 003
> covered. **SFTP-NFR-004 not covered**, blocked on SFTP-OD-001.
> **Findings:** 1 major — SFTP-ADR-004's overlap window has no stated duration,
> so SFTP-REQ-004 is not verifiable. 2 minor.
> **Verdict:** approve with conditions.

The architect adds the duration. The reviewer checks that one finding, not the
whole design again.

## Stage UX — Skipped

Recorded, not silent:

```yaml
sdlc:
  skipped_stages:
    - stage: UX
      reason: The platform has no user interface. Partner-facing behaviour is protocol behaviour.
```

## Stage STORY — Decomposition

`development-lead` produces the breakdown, with owned paths so parallel work
cannot collide:

| Story | Owns | Depends on |
| --- | --- | --- |
| SFTP-STORY-001 SSH transport and key auth | `src/transport/**` | — |
| SFTP-STORY-002 Path confinement | `src/vfs/**` | 001 |
| SFTP-STORY-003 Audit log writer | `src/audit/**`, `migrations/**` | — |
| SFTP-STORY-004 Host key rotation | `src/keys/**` | 001 |
| SFTP-STORY-005 Deployment and pipeline | `deploy/**`, `.gitlab-ci.yml` | — |

001, 003 and 005 run in parallel; their paths are disjoint.

## Stage QADESIGN — Test design, before code

`qa-lead` derives scenarios from the requirements and the architecture risks:

| Requirement | Risk | Scenario | Level |
| --- | --- | --- | --- |
| SFTP-REQ-002 | Path traversal | `../` and symlink escape attempts, absolute paths, unicode normalisation | integration, security |
| SFTP-REQ-003 | Audit gap | Transfer interrupted mid-stream: is a record written, and is it marked incomplete? | integration |
| SFTP-REQ-004 | Session drop | Rotate keys with 50 sessions established; assert zero drops | e2e |
| SFTP-NFR-002 | Latency | p95 session establishment under load profile | performance |

The path-traversal scenario exists because the threat model named it, not because
someone remembered it after a penetration test.

## Stage DEV — Development

A team is worth it here: three stories, disjoint paths, different disciplines.
The spawn prompt from `skills/team-patterns` names the file ownership explicitly.

The guards are quiet through almost all of it — `go test ./...`,
`git switch -c feature/SFTP-STORY-042-key-rotation`, pushing the feature branch,
`terraform plan` all proceed with no objection. That is the design working: a
guard that interrupts ordinary work gets disabled.

They are not quiet here:

```
devops-engineer writes deploy/values.yaml with registryToken: "glpat-…"
  → DENY  [WS-SECRET] content looks like live secret material (SP-03)
```

The token moves to a masked CI variable, and `registryToken: "${REGISTRY_TOKEN}"`
writes without objection.

## Stage REVIEW — Routed, not ceremonial

`policies/review-routing.json` produces different reviewer sets per story:

| Story | Reviewers | Why |
| --- | --- | --- |
| 001 transport | code, test, **security** | RR-04: authentication |
| 002 path confinement | code, test, **security**, **architecture** | RR-04 and RR-03 |
| 003 audit log | code, test, **data-engineer**, **architecture** | RR-06: migration |
| 005 pipeline | code, **devops**, **security** | RR-09: CI configuration |

Story 004 gets `code` and `test` only. Not every change needs every reviewer.

`security-reviewer` returns one HIGH finding on story 002: the confinement check
runs on the requested path before symlink resolution, so a symlink inside the
partner directory escapes it. The exploitation path is stated concretely, which
is what makes it actionable. Back to DEV.

## Stage RELEASE — Approval

`release-manager` assembles the evidence and finds a gap: `SFTP-ARCH-003` is
still incomplete because `SFTP-OD-001` is unanswered.

> **Recommendation:** release to production with a single-region deployment and
> the DR gap recorded as accepted risk, **or** hold for the RPO/RTO decision.
> **This is a human decision.** The release manager has no execution tools and
> does not approve.

The human answers the RPO/RTO question, DR design completes, and the release
proceeds through staging validation, human approval (AP-01), deployment by
`devops-engineer`, and post-deployment verification.

---

## What this example demonstrates

| | |
| --- | --- |
| Refusal on missing configuration | The stack is never inferred |
| Refusal on an unquantified NFR | 99.9% is never invented |
| Deliberate skip, recorded | UX, with a written reason |
| Independent architecture review | Different agent, no write tools |
| QA before code | Scenarios from requirements and threats |
| Risk-based review routing | Four different reviewer sets |
| Structural least privilege | Write scopes, not instructions |
| Human approval where it belongs | Technology, DR risk, production |
