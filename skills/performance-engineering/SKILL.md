---
name: performance-engineering
description: Establish baselines, design load, stress and soak tests, analyse capacity and find performance regressions. Use when performance requirements exist, when a change touches hot paths or data access, and when investigating a slowdown. Risk-based - not every change needs a performance test.
---

# Performance engineering

Measure, then change. A performance change made without a measurement is a guess with extra confidence.

## Decide whether this is needed at all

Performance work is warranted when: a quantified performance requirement exists, the change touches a hot path, data access patterns change, concurrency or batching changes, or production telemetry shows a trend. It is not warranted for documentation, configuration or isolated logic changes. Say which applies.

## Baseline first

Without a baseline there is no regression, only opinion. Capture: latency at p50/p95/p99, throughput, error rate, and resource use (CPU, memory, connections, I/O) under a defined load, on a defined environment, with defined data volumes.

Record the conditions. A baseline without its conditions is not comparable to anything.

## Load profile

Derive it from the requirement and from production reality, not from a round number. Include: request mix, concurrency, arrival pattern (steady, bursty, diurnal), payload sizes, data volume, and cache state.

## Test types

- **Load** — expected peak, sustained. Answers: do we meet the requirement.
- **Stress** — beyond peak until something breaks. Answers: where is the limit and how does it fail. Graceful degradation or collapse?
- **Soak** — expected load for hours. Answers: do we leak memory, connections, file handles or disk.
- **Spike** — sudden multiplication of load. Answers: does autoscaling or queueing cope, and does recovery happen.

## Analysis

Find the bottleneck before optimising anything. The usual order of real causes:

1. Doing work repeatedly that could be done once (N+1 queries, recomputation, missing cache).
2. Doing work that is not needed (over-fetching, unbounded result sets).
3. Doing work serially that could be concurrent, or concurrently in a way that contends.
4. Waiting: unindexed queries, lock contention, chatty network calls, synchronous calls to slow dependencies.
5. Allocation and garbage pressure.

Profile to find it. Optimising the second-slowest thing changes nothing.

## Capacity

Model headroom against growth: at the current trend, when does the current configuration stop meeting the requirement? State the assumption behind the trend. Capacity conclusions without stated assumptions are unusable six months later.

## Regression protection

Once a performance requirement exists, add a check that fails when it is violated, and run it where it will be noticed. A performance test nobody looks at is a cost with no benefit.

## Reporting

State the requirement, the conditions, the numbers, the bottleneck, the change, and the numbers after. Include what you did **not** measure.
