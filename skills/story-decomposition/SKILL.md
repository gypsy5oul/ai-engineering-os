---
name: story-decomposition
description: Break approved architecture and requirements into epics, stories and tasks that can be implemented independently and verified objectively. Use after architecture review and QA test design, before implementation starts.
---

# Story decomposition

A story is a unit of work that one person can finish and another can verify without asking questions.

## Hierarchy

- **Epic** — a coherent slice of the capability, usually one architectural area. Delivers observable value.
- **Story** — one behaviour change, independently implementable, independently testable, independently reviewable.
- **Task** — a step inside a story that has no value on its own (for example "add the migration").

## Every story carries

1. **Business context** — why this exists, linked to a requirement identifier.
2. **Technical context** — the components involved, the contracts it touches, the architecture reference.
3. **Acceptance criteria** — testable, derived from the requirement, not invented here.
4. **Dependencies** — stories that must land first, and external dependencies.
5. **Non-functional requirements** that apply to this story specifically.
6. **Test expectations** — which levels, which scenarios from the QA baseline.
7. **Definition of done** — the project's standard plus anything specific to this story.
8. **Files or modules it owns** — as `owns_paths` in the header, the same name a
   task uses. It keeps parallel stories disjoint, and it is what
   `infer_dependencies.py` reads to order the work that is not.

## Sizing

Right-sized: a competent implementer finishes it in one sitting and the reviewer can hold the whole change in their head.

Too big: the acceptance criteria list has more than about five entries, or it touches three architectural areas, or you cannot describe it in one sentence.

Too small: it has no acceptance criteria of its own. That is a task, not a story.

## Parallelisation

Two stories may run in parallel only if they modify disjoint files. This is not a preference: parallel agents and teammates editing the same file overwrite each other. Record each story's owned paths and check for overlap before assigning.

Where an overlap is unavoidable, sequence the stories and say so.

## Shape

Prefer the decomposition with fewer handoffs and fewer integration points. A vertical slice that delivers one thin path end to end beats a horizontal set of layer stories that only becomes testable once all of them land.

Six stories because the design has six layers is a symptom of the design, not a plan. If the decomposition is only awkward because the architecture is more layered than the requirements need, that is an architecture finding — raise it rather than absorbing it into the backlog.

## Sequencing

Order by dependency, then by risk: the story that could invalidate the design goes first. Discovering an architecture problem in the last story is the expensive outcome.

## Definition of done (default)

- Acceptance criteria met and demonstrated by tests.
- Tests at the levels the project requires pass.
- Lint, type checks and static analysis pass.
- Routed reviews complete with no unresolved HIGH finding.
- Documentation updated where behaviour changed.
- Traceability identifiers present in commits and the merge request.

## Rules

- No story without an acceptance criterion.
- No acceptance criterion invented at this stage: it comes from the requirement. If the requirement does not support it, go back.
- No story that requires a decision nobody has made. Escalate the decision first.
- Record which stories are parallelisable explicitly; do not leave it to be inferred.
