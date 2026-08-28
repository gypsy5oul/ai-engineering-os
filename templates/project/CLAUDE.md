# <PROJECT NAME>

<One paragraph: what this system does and who depends on it.>

## AI Engineering OS

This project runs on the `ai-engineering-os` plugin. Organizational roles, SDLC
stages, review routing, model policy and safety guards come from the plugin and
are not repeated here.

- Approved technology, environments, security and testing requirements:
  `.ai-engineering/project.yaml`. That file is the record of human decisions.
  If something is not in it, it is not approved.
- To place work in the lifecycle: `/ai-engineering-os:sdlc-navigator`.
- Traceability identifiers use the prefix `<KEY>` (see `project.key`).

**Simplicity by default.** Build the simplest thing that satisfies the stated
functional, non-functional, reliability, security, scalability and operational
requirements. Not the smallest: a design that drops a stated requirement is
incomplete, not simple. Before introducing a component, dependency, abstraction
or service boundary, name the simplest alternative and the stated requirement it
fails; if none fails, the simpler option wins. Complexity is allowed and is
recorded, in the `complexity` ledger on the architecture artifact.
`/ai-engineering-os:engineering-simplicity` has the rule and what counts as
evidence.

## Repository map

<Where things live. Two or three lines. Keep it current or delete it.>

| Path | Contains |
| --- | --- |
| `src/` | |
| `tests/` | |
| `docs/` | Requirements, architecture, ADRs, test plans, releases, incidents |

## Working agreements specific to this project

<Only what an agent cannot derive from the code or from the plugin. Delete this
section rather than filling it with generic advice.>

- <e.g. "All timestamps are stored and compared in UTC; the display layer is the
  only place a local timezone appears.">
- <e.g. "Partner identifiers are opaque; never parse or infer meaning from them.">

## Commands

```bash
<build>
<test>
<lint>
```

## What requires a human here

The organization-wide list is in the plugin's approval policy. This project adds:

- <project-specific approvals, or "none">
