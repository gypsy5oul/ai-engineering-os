# Project knowledge structure

Create these directories under the project's `knowledge.root` (default `docs/`).
Every artifact carries the front matter defined by
`schemas/artifact-header.schema.json`; see the `traceability` skill.

```
docs/
├── product/          Product context, personas, market or partner constraints
├── requirements/     PRDs, functional and non-functional requirements
├── architecture/     HLD, LLD, contracts, data models, deployment, capacity
├── adrs/             Architecture decision records (numbered, never renumbered)
├── design/           UX specifications, journeys, state and accessibility criteria
├── stories/          Epics, stories, tasks
├── test-plans/       Test strategy, scenarios, coverage matrices
├── qa/               Execution results, defect records
├── security/         Threat models, security requirements, exception records
├── release/          Release plans, migration and rollback plans, release notes
├── runbooks/         One per alert, written for someone woken at 03:00
├── incidents/        Incident records with timelines
├── rcas/             Root cause analyses
└── technical-debt/   Accepted debt with the reason and the trigger to repay it
```

## Identifier convention

`<KEY>-<TYPE>-<NNN>` — for example `SFTP-REQ-014`, `SFTP-ADR-003`, `SFTP-RCA-002`.

Sequential per type, never reused, never renumbered. `<KEY>` comes from
`project.key` in `.ai-engineering/project.yaml`.

## Index

`docs/README.md` holds the artifact index: identifier, title, status, owner and
path. It is maintained by `docs-writer` and is how a reader finds anything
without knowing the directory layout.
