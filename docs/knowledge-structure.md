# Knowledge and traceability

Traceability answers two questions that otherwise cost hours: **why does this
exist**, and **what does changing it affect**.

V1 uses files, identifiers and conventions. Not a graph database — the convention
has to hold before a tool is worth building on top of it.

## Structure

Under the project's `knowledge.root` (default `docs/`):

```
docs/
├── product/          Product context, personas, constraints
├── requirements/     PRDs, functional and non-functional requirements
├── architecture/     HLD, LLD, contracts, data models, deployment, capacity
├── adrs/             Architecture decision records
├── design/           UX specifications, journeys, accessibility criteria
├── stories/          Epics, stories, tasks
├── test-plans/       Strategy, scenarios, coverage matrices
├── qa/               Execution results, defect records
├── security/         Threat models, security requirements, exceptions
├── release/          Release, migration and rollback plans, release notes
├── runbooks/         One per alert
├── incidents/        Incident records
├── rcas/             Root cause analyses
└── technical-debt/   Accepted debt with its repayment trigger
```

Write scopes in `policies/write-scope.json` map onto these directories, which is
how "the architect owns the architecture" becomes something the system enforces
rather than something the team remembers.

## Identifiers

`<PROJECT-KEY>-<TYPE>-<NNN>`, where the key comes from `project.key` in
`.ai-engineering/project.yaml`.

`REQ` `NFR` `EPIC` `STORY` `TASK` `ARCH` `ADR` `DES` `TP` `TEST` `DEF` `REL`
`INC` `RCA` `DEBT` `SEC`

Sequential per type, never reused, never renumbered. Renumbering breaks every
reference in commit messages, merge requests and prior artifacts.

## Two artifacts worth calling out

**`DEC` — open decision.** A decision nobody has made is a tracked object, not a
question an agent keeps re-asking. It carries the question, the options with what
each forecloses, the impact, the owner and `blocks: [ARCH, ADR]`. An agent
blocked by one says *"cannot continue ARCH: SFTP-DEC-001 is open"* once and
stops. Without the artifact, every new session re-asks and the answer lives in a
transcript nobody can find.

**`EVID` — evidence.** Collected and sealed **before** any destructive
remediation during an incident: logs, timestamps, deployment versions,
configuration snapshots, metrics, traces, and the investigation commands
themselves. Immutable — `may_modify: []` — because an evidence record that can be
rewritten is not evidence. `WF-INCIDENT MITIGATE` cannot complete without
`evidence_sealed()`.

## The artifact contract

`policies/artifact-model.json` defines 21 artifact types. Each declares the full
contract:

| Contract field | Answers |
| --- | --- |
| `owner_role` | Who **creates** it. Exactly one role. |
| `may_modify` | Who may change it after creation. Empty means immutable. |
| `may_review` | Who may record an **agent verdict** on it. |
| `may_approve` | Which **human** role may approve it, or `none`. Never an agent. |
| `storage` | Where it lives, aligned with `policies/write-scope.json`. |
| `required_fields` | The base contract plus type-specific fields. |
| `depends_on` / `consumed_by` | Which artifacts must exist first, and which consume it. |
| `immutable_after_creation` / `append_only` | Evidence is immutable; an incident record is appended to and never rewritten. |

Validation checks that every `owner_role` is a real agent, that no human approver
is an agent, that the dependency graph is closed, and that an owner can actually
write where its artifact lives. That last check found a real gap:
`development-lead` owned `DEBT` but its write scope did not include
`docs/technical-debt/`.

Every artifact carries these fields, validated by
`schemas/artifact-header.schema.json`:

| Field | Why it is required |
| --- | --- |
| `id`, `type`, `title`, `status`, `owner` | Identity and ownership |
| `version` | Incremented on every material change |
| `created_at`, `updated_at` | When, and when last touched |
| `source` | Where this came from. **An artifact with no source was invented.** |
| `reviewers` | **Agent** verdicts: who reviewed, what verdict, when, how many findings |
| `approvals` | **Human** decisions: who, which policy reference, where it is recorded |
| `dependencies` | Artifact ids this one cannot be completed without |
| `links` | Traceability edges |

`reviewers` and `approvals` are separate fields and never merge. That separation
is the artifact-level form of the rule in [approvals](approvals.md).

## Artifact header

Every artifact carries front matter validated by
`schemas/artifact-header.schema.json`:

```yaml
---
id: SFTP-STORY-042
type: story
title: Rotate host keys without dropping sessions
status: approved
owner: development-lead
created: 2025-11-03
links:
  requirements: [SFTP-REQ-012, SFTP-NFR-004]
  architecture: [SFTP-ARCH-002]
  adrs: [SFTP-ADR-005]
  tests: [SFTP-TP-007]
---
```

Templates for requirement, ADR, story, test plan, RCA and release notes are in
`templates/artifacts/`.

## The link model

```
REQ / NFR  ──►  STORY  ──►  commit / MR  ──►  RELEASE
    │             │              │               │
    ├──► ARCH ──► ADR            └──► TEST       └──► INC ──► RCA ──► REQ | DEF | DEBT
    └──► TEST
```

Links live on both artifacts where practical. One-directional links rot silently.

Outside documents, links live in commit bodies (`Refs: SFTP-REQ-012`), merge
request descriptions, test names, release contents and RCA follow-up items.

## Questions it answers

| Question | Path |
| --- | --- |
| Why does this code exist? | commit → story → requirement |
| What breaks if this requirement changes? | requirement → stories → tests → releases |
| Is this requirement tested? | requirement → tests; empty is a QA gap |
| Has this failure happened before? | incident → RCA → prior RCAs with the same cause |
| What went into this release? | release → stories and defects → requirements |

## Rules

- No artifact without an identifier.
- No story without a requirement link. If none exists, the requirement was never
  written; write it.
- No defect without a link to what it affects.
- No RCA action without a link to the work item it became.

## Index

`docs/README.md` in the project holds the artifact index — identifier, title,
status, owner, path — maintained by `docs-writer`. It is how a reader finds
anything without knowing the directory layout.
