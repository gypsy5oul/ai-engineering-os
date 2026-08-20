# Example 02 — Fix a production authentication defect

`WF-INCIDENT` → `WF-DEFECT` → `WF-RELEASE`. The point of this example is the
separation between **mitigation and fix**, and between **incident command and
RCA**.

**Guards in action:** `./examples/run_demo.sh`

---

## 03:14 — Detection

An alert fires: authentication success rate has dropped from 99.8% to 61%.
`sre` states the symptom in user-visible terms:

> Since 03:02 UTC, roughly four in ten partner logins fail with
> `authentication timeout`. Established sessions are unaffected.

## 03:17 — Triage

`incident-commander` declares **SEV1** — a critical function partially lost, no
workaround — opens the record and notifies the human on-call owner. An agent
never runs an incident alone.

Then it asks what changed. Release 1.3.2 deployed at 02:55.

## 03:20 — Parallel investigation

Four teammates, four hypotheses, adversarially instructed to disprove each
other. Sequential investigation would have anchored on the first plausible
theory, which here was the wrong one.

| Teammate | Hypothesis | Outcome |
| --- | --- | --- |
| A | Release 1.3.2 changed the auth path | Rejected: the diff does not touch auth |
| B | Token validation is slow | **Supported:** validation p99 went from 12ms to 4.2s at 03:02 |
| C | An upstream identity provider is degraded | Rejected: provider latency is flat |
| D | Connection pool exhaustion | **Supported, and explains B:** pool saturated at 03:02 |

B and D converge. 1.3.2 added a background reconciliation job that opens a
connection per partner and holds it for the job's duration. It shares the pool
with the auth path.

The guards shape what investigation looks like: reading staging logs proceeds
without objection, `kubectl --context prod-eu get pods` escalates to the human
(AP-11), `kubectl delete pod auth-0 -n production` is denied outright, and
`cat ~/.kube/config` is denied. Investigation is read-only; mutation goes through
a person.

## 03:41 — Mitigation

`incident-commander` proposes, with blast radius and rollback:

> **Proposal:** disable the reconciliation job via its feature flag.
> **Blast radius:** reconciliation stops; no customer-visible effect for up to 24h.
> **Rollback:** re-enable the flag.
> **Alternative:** roll back 1.3.2 entirely — larger blast radius, reverts three
> unrelated fixes.
> **This requires human approval (AP-01).**

The human approves and applies it. **Mitigation is not the fix**: the pool is
still shared and the job still needs to run.

## 03:48 — Recovery

Success rate returns to 99.7%. Recovery is declared from a verified partner
login, not from the graph — and the incident commander says which check it ran.

## Next morning — RCA

`rca-analyst` is a different agent from `incident-commander`, deliberately: the
responder does not grade its own response.

**Trigger:** release 1.3.2 introduced a job that consumed pool connections.

**Root cause:** the connection pool is a single shared resource with no
partitioning between the request path and background work, and no saturation
alerting. Any background consumer can starve authentication.

Note what is *not* the root cause. The draft said "the developer did not consider
pool usage". `EVAL-SRE-002` tests exactly this rewrite: a system in which one
oversight causes a SEV1 is the finding.

**Detection gaps:**

| Stage | Could it have been caught? | Why it was not |
| --- | --- | --- |
| Architecture | Yes | Pool sharing was never an explicit decision, so it was never reviewed |
| Review | Yes | The reviewer saw a correct job; nobody asked what it consumed |
| Test | Yes | No test exercises the job and the auth path together |
| CI | No | The condition needs production concurrency |
| Monitoring | **Yes** | Pool utilisation was collected but never alerted on |

**Corrective actions**, each typed, owned and with an acceptance criterion:

| # | Action | Type | Acceptance criterion |
| --- | --- | --- | --- |
| 1 | Separate pool for background work | defect | Auth latency unaffected while the job saturates its own pool |
| 2 | Alert on pool utilisation above 80% | monitoring-improvement | Alert fires in a load test, runbook RB-14 exists |
| 3 | Integration test: job plus auth under concurrency | defect | Test fails against 1.3.2 |
| 4 | ADR recording resource-isolation boundaries | architecture-change | ADR accepted by the council |
| 5 | Add "what shared resources does this consume" to reliability review | process | Present in the reviewer's checklist |

Action 3 is the one that turns this from a story into a control.

## The fix — WF-DEFECT

Triage confirms the reproduction. `qa-engineer` writes the **failing test first**
and verifies it fails against the unfixed code — that verification is the whole
point of writing it first.

`backend-developer` implements the separate pool. The change is scoped to the
defect: the three unrelated improvements it noticed become `SFTP-DEBT-*` items.

`data-engineer` adds a migration for the job's checkpoint table. The
`ALTER TABLE ... ADD COLUMN` proceeds without objection; a `DROP TABLE` in the
same session would escalate (AP-05), which is the distinction the guard exists to
draw.

Review routes to `code`, `test`, `reliability` (RR-08: pool behaviour) and
`performance` (RR-07: concurrency).

`test-reviewer` returns one finding: the regression test asserts the job
completes, not that auth latency is unaffected while it runs. That would have
passed against the broken code. Fixed.

## Release

Severity justifies an expedited route, not a skipped one. Every gate still has a
verdict; the change window is waived by the same human who approves the release,
and the waiver is recorded.

`release-manager` produces the rollback plan and asks for approval (AP-01). It
cannot deploy: no execution tools.

---

## What this example demonstrates

| | |
| --- | --- |
| Parallel adversarial investigation | The first plausible theory was wrong |
| Mitigation ≠ fix | Flag off restored service; the pool was still shared |
| Read-only production investigation | Reading escalates, mutating is denied |
| Human approval on every production action | Including the mitigation |
| RCA independent of the responder | Different agent by design |
| "Human error" rejected | The systemic cause was found instead |
| Detection gaps per stage | Five stages examined, three gaps found |
| Typed, owned corrective actions | Each becomes a real backlog item |
| Regression test written first | Verified to fail against the unfixed code |
| Expedited ≠ skipped | Every gate kept its verdict |
