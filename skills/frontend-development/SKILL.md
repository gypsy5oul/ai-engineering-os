---
name: frontend-development
description: Implement client-side code, state, accessibility and tests against an approved story and UX contract. Use for UI implementation and user-facing defect fixes. Technology-neutral - the approved framework comes from the project configuration.
---

# Frontend development

The specification includes the states nobody demonstrates. Implement those too.

## Before writing code

1. Read the story, the UX specification and the accessibility criteria.
2. Read the API contracts you will consume. If a view needs data the contract does not provide, that is a contract gap, not a workaround.
3. Read `.ai-engineering/project.yaml` for the approved frontend stack and standards.
4. Read the design system and the existing components. Reuse before you create.

## Every view implements every state

Loading, empty, partial, error, permission-denied, offline or degraded where applicable, and success. A view that only handles success is half-implemented.

## Accessibility is acceptance criteria, not polish

- Every interactive element reachable and operable by keyboard, in a sensible order.
- Focus visible, and managed across route and modal transitions.
- Semantic elements before ARIA; ARIA only where semantics cannot express it.
- Labels on every control, including icon-only buttons.
- Contrast meeting the stated standard.
- Status changes announced to assistive technology, not only shown visually.
- Motion respects the user's reduced-motion preference.

Verify these; do not assume them.

## State and data

- Keep state as local as it can be. Global state is a coordination cost paid on every future change.
- Handle the asynchronous reality: race conditions between requests, stale responses arriving after newer ones, and the component unmounting mid-flight.
- Do not duplicate server state into client state without deciding how it is invalidated.
- Validate on the client for the user's benefit and on the server for correctness. Client validation is never a security control.

## Performance

Measure before optimising. The usual real causes: shipping too much code, rendering too many nodes, re-rendering on every keystroke, unoptimised images, and blocking the main thread. Bound list rendering.

## Tests

Test behaviour the user can observe, not implementation detail. Cover each specified state and each accessibility criterion. A test coupled to component internals breaks on every refactor and proves nothing.

## Escalate rather than improvise

- A missing state or accessibility criterion in the specification → `ux-designer`.
- An API that cannot serve a specified view → `solution-architect`.
- A design-system gap → `ux-designer`. Do not solve it with a local one-off style.
