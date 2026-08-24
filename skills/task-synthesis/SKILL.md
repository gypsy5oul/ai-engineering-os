---
name: task-synthesis
description: Decompose one stage of a work item into the several concrete tasks it actually is, as a proposal the organization validates and grafts into the task graph. Use when a stage in the graph is one node and several people's work, before that stage starts.
---

# Task synthesis

A stage is a unit of accountability. `DEV` on a payments change is one node in
the graph and five people's work in reality. A graph that cannot say so cannot
schedule the work, cannot run the independent parts at the same time, and cannot
show anyone where the change has actually got to.

Deciding which pieces, in what order, sharing which contracts, is judgement.
That is your part. Validating the result against the graph and recording it is
the organization's part, and it will refuse a decomposition that does not hold
together. Nothing you propose is trusted because it parsed.

## Before you propose anything

Read the stage you are decomposing:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/control_loop.py status --project . --item ACME-FEAT-001
```

You need four things from it: what the stage **produces**, its **risk**, whether
it owns a **coupled surface**, and its **definition of done**. Then check whether
the split is already implied by the artifact model, in which case you should not
be inventing one:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/synthesize_tasks.py --project . --item ACME-FEAT-001 \
    --task T-009 --derive --dry-run
```

If that produces a sensible split, use it. It read the artifact owners rather
than guessing, and a derived split is one fewer thing anyone has to review.

## What a good decomposition is

**One task is one person's work, finishable and verifiable without asking you a
question.** If a task needs a conversation to hand over, it is two tasks or it is
badly drawn.

**Split along what makes the pieces independent**, not along what makes them
equal. Three tasks of very different sizes that can run at once beat four even
ones that cannot. The reason to decompose at all is to expose the parallelism
that the single node was hiding — if every child depends on the one before it,
you have written a pipeline and changed nothing.

**Name the contract before the work that depends on it.** When several pieces
build against one interface, designing that interface is its own task and
everything else depends on it. That is the shape that makes the rest parallel.

**Say which files each piece will edit.** `owns_paths` is what lets the
repository check your ordering. Two tasks naming the same file get sequenced;
a task whose file imports another task's file waits for it. Declaring paths is
how a split proves its pieces are independent rather than asserting it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/infer_dependencies.py \
    --project . --item ACME-FEAT-001
```

Run it before you hand the proposal over. If it finds an ordering you did not
intend, one of you is wrong, and it is usually not the import graph.

**Say which piece owns a shared surface.** If the stage owns one, exactly one
child owns it. Giving it to everybody serialises the split away; giving it to
nobody deletes the guarantee at the moment the work becomes parallel, which is
exactly when it starts to mattering.

## The shape

```json
{
  "parent": "T-004",
  "rationale": "The API contract and the data model are designed by different people against different criteria; the threat model needs both and blocks neither.",
  "children": [
    {"key": "api", "title": "Design the activation API contract",
     "role": "solution-architect", "produces": ["ARCH"],
     "coupled_surface": "api-contract",
     "owns_paths": ["docs/architecture/activation.md", "src/api/activation.yaml"],
     "definition_of_done": ["artifact_status(ARCH, approved)"]},
    {"key": "decisions", "title": "Record the activation design decisions",
     "role": "solution-architect", "produces": ["ADR"], "depends_on": ["api"],
     "definition_of_done": ["artifact_status(ADR, accepted)"]},
    {"key": "threat", "title": "Threat model the activation credentials",
     "role": "security-architect", "produces": ["SEC"], "depends_on": ["api"],
     "definition_of_done": ["artifact_exists(SEC)"]}
  ]
}
```

`key` is local: it exists so siblings can refer to each other. The organization
assigns the real task ids.

Hand it over, and read what comes back:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/synthesize_tasks.py --project . --item ACME-FEAT-001 \
    --from proposal.json --proposed-by solution-architect
```

## What will be refused, and why

The rules are in `${CLAUDE_PLUGIN_ROOT}/policies/task-synthesis.json`, each with its reasoning. The
ones that catch real proposals:

| | |
| --- | --- |
| **The children must produce exactly what the stage owed** | Drop one and the stage still passes its definition of done, because that is evaluated on the parent. The artifact simply stops existing and nobody notices. |
| **A role must be able to write what you assign it** | A reviewer holds no write tools; a developer cannot write `docs/architecture/`. A task nobody is permitted to do is not a task. |
| **Risk may be raised, never lowered** | Decomposing HIGH work into LOW pieces routes around the model floor, the approval gates and the concurrency limits, one level down where nobody is looking. |
| **Children depend only on siblings** | The parent already carries the change's outside dependencies. Reaching past it rewires the graph from inside a stage. |
| **Predicates must be real** | An unknown predicate is skipped by the evaluator, so an invented one is a definition of done that always passes. |
| **Two to eight children, one level** | A stage needing more than this is a work item that was scoped wrong. Say so instead. |

What is **not** checked is whether the decomposition is any good. The rules
reject one that is incoherent with the graph; they cannot reject one that is
merely poor. That is what the stage's reviewer is for.

## What happens to the stage

The parent stays. It keeps the stage's definition of done, and it comes to depend
on all of its children — so the stage gate the rest of the graph was promised
still exists, and everything downstream still waits for it. What changes is that
the stage cannot be worked until its pieces are.

A replan rebuilds the graph from the workflow, and a decomposition does not
survive it. That is deliberate: a replan means the plan was wrong, and a
decomposition of a plan that was wrong is not worth carrying forward.

## Related

- `story-decomposition` — breaking requirements into epics and stories, which are
  **artifacts** the organization delivers. This skill breaks a **graph task**
  into graph tasks. A story often becomes a task here; they are not the same
  object.
