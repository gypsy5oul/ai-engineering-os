---
name: database-design
description: Design schemas, indexes, migrations and data lifecycle within the project's approved data platform. Use for any persistent structure change, migration, backfill or query-performance work. Destructive or irreversible migrations require human approval.
---

# Database design

Data outlives code. Design so that the next migration is possible.

## Schema

- Model the domain, not the current screen. Entities, relationships, cardinality and the invariants that must always hold.
- Put invariants in the database where the database can enforce them: not-null, unique, foreign keys, check constraints. Application-only invariants are eventually violated.
- Choose types deliberately: precision for money, timezone-aware timestamps, explicit lengths, and enumerations that can grow.
- Name consistently. A column called `status` in three tables should mean the same kind of thing.
- Record what each table is for. A schema with no description becomes folklore.

## Indexes

- Index for the queries that exist, not for every column.
- Composite index column order follows the query's equality-then-range pattern.
- Every index costs write throughput and storage. State the query each index serves.
- Look for the absent index that turns a join into a scan, and the redundant index that is a prefix of another.

## Migrations

Always expand → migrate → contract:

1. **Expand**: add the new structure, nullable or defaulted, deployable alongside the current code.
2. **Migrate**: backfill in bounded batches, with progress visible and the ability to stop.
3. **Contract**: remove the old structure only after the old code is gone everywhere.

For every migration state: expected row count, expected duration, locking behaviour, whether it is online, how it is verified, and how it is reversed.

**Irreversible steps** — dropping a column, dropping a table, a destructive backfill — are AP-05. They need human approval, a verified backup, and an explicit acknowledgement that the data cannot be recovered by rolling back code.

Backfills run in batches with a bound on rows and a bound on time. An unbounded `UPDATE` on a large table is a production incident waiting for a deployment window.

## Data lifecycle

Retention, archival, deletion and the legal basis for each. Classify personal data explicitly and record where it flows. A field added today without a retention answer becomes a compliance finding later.

## Query performance

Read the plan rather than guessing. Look for: sequential scans on large tables, N+1 access patterns from the application, unbounded result sets, lock contention on hot rows, and queries whose cost grows with total table size rather than result size.

## Review checklist

- Compatibility strategy stated and deployable in the project's rollout model.
- Rollback tested, or irreversibility acknowledged by a human.
- Backfill bounded and observable.
- Indexes justified by named queries.
- Constraints enforce the invariants the design claims.
- Personal data classified with a retention answer.
