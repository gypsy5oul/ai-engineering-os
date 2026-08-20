---
name: traceability
description: Assign artifact identifiers and maintain the links between requirements, stories, architecture, ADRs, tests, defects, merge requests, releases, incidents and RCAs. Use when creating any project artifact, and when answering "why does this code exist" or "what does this change affect".
---

# Traceability

Traceability answers two questions that otherwise cost hours: **why does this exist**, and **what does changing it affect**. It is built from identifiers and links, not from a database.

## Identifiers

Format: `<PROJECT-KEY>-<TYPE>-<NNN>`, where the key comes from `.ai-engineering/project.yaml` under `project.key`.

| Type | For |
| --- | --- |
| `REQ` | Functional requirement |
| `NFR` | Non-functional requirement |
| `EPIC`, `STORY`, `TASK` | Work breakdown |
| `ARCH` | Architecture artifact |
| `ADR` | Architecture decision record |
| `DES` | UX/design specification |
| `TP`, `TEST` | Test plan, test case |
| `DEF` | Defect |
| `REL` | Release |
| `INC` | Incident |
| `RCA` | Root cause analysis |
| `DEBT` | Technical debt |
| `SEC` | Security finding or exception |

Sequential per type, never reused, never renumbered.

## Artifact header

Every artifact carries YAML front matter validated by `${CLAUDE_PLUGIN_ROOT}/schemas/artifact-header.schema.json`:

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

## The link model

```
REQ / NFR  ──►  STORY  ──►  commit / MR  ──►  RELEASE
    │             │              │               │
    ├──► ARCH ──► ADR            └──► TEST       └──► INC ──► RCA ──► REQ | DEF | DEBT
    └──► TEST
```

Every edge is stated on **both** artifacts where practical. One-directional links rot silently.

## Where links live outside documents

- **Commits**: `Refs: SFTP-REQ-012, SFTP-STORY-042` in the body.
- **Merge requests**: identifiers in the description, plus `Closes #n` for the issue.
- **Tests**: the identifier in the test name or a docstring, so a failing test names the requirement it defends.
- **Releases**: the list of story and defect identifiers included.
- **RCAs**: links to the incident, and to every follow-up item created.

## Using it

- *"Why does this code exist?"* — commit → story → requirement.
- *"What breaks if we change this requirement?"* — requirement → stories → tests → releases.
- *"Is this requirement tested?"* — requirement → tests; an empty result is a QA gap.
- *"Has this failure happened before?"* — incident → RCA → prior RCAs with the same cause.

## Rules

- No artifact without an identifier.
- No story without a requirement link. If none exists, the requirement was never written; go and write it.
- No defect without a link to what it affects.
- No RCA action without a link to the work item it became.
- V1 deliberately uses files and conventions, not a graph database. The convention has to hold before a tool is worth building.
