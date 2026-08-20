---
name: test-automation
description: Implement reliable automated tests from an approved test design, and diagnose flaky or low-value tests. Use when writing test code, building a suite, or when tests fail intermittently.
---

# Test automation

A test suite is only worth its maintenance cost if a failure means something.

## Writing a test

- **One behaviour per test.** The name states the behaviour and the expected outcome, so a failure is diagnosable from the name alone.
- **Arrange, act, assert**, visibly separated.
- **Assert the observable outcome**, not the internal path taken. Tests coupled to implementation break on every refactor and pass through every real regression.
- **Every test would fail if the behaviour regressed.** Verify this: for a defect fix, run the new test against the unfixed code and watch it fail.
- **Independent**: no shared mutable state, no ordering dependency, no reliance on a previous test's leftovers.
- **Deterministic**: inject the clock, seed randomness, control identifiers. A test that depends on real time or real network is not a test, it is a probe.

## Test doubles

Mock at architectural boundaries, not between every pair of functions. Over-mocking produces tests that assert your mocks were called, which is true no matter how broken the system is. Prefer real implementations for anything cheap and deterministic.

For an external dependency, prefer a contract test against the real contract plus a fake, over a mock that encodes your assumption of the contract.

## Levels

- **Unit** — logic, boundaries, error handling. Fast, many.
- **Integration** — real adapters against real infrastructure (containerised where possible). Fewer, slower, catches wiring and serialization defects.
- **Contract** — verifies both sides of an interface against a shared definition. Cheap insurance against a breaking change.
- **End-to-end** — the few journeys whose failure would be unacceptable. Expensive and the most flake-prone; keep the set small and stable.

## Flakiness

A flaky test is a defect in the test, and it is a serious one: it trains the team to ignore failures. When a test flakes, do not add a retry. Find the cause, which is nearly always one of:

- Waiting on a timer instead of a condition.
- Shared state between tests or between parallel workers.
- Ordering assumptions about collections, maps or asynchronous completion.
- Real time, real network or real filesystem.
- Insufficient isolation of test data.

Quarantine it, raise it as a defect, fix the cause.

## In CI

Tests must run the same way locally and in CI. A suite that only passes on one machine has no authority. Keep the fast levels on every commit; run the slow levels on merge or on a schedule, and say which is which.
