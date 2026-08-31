# Certification

The deterministic suite proves the organization is coherent with itself. It does
not prove that Claude Code ever calls any of it. Those are different claims, and
for most of this repository's life only the first was ever checked.

Certification is the path that checks the second, and the whole design of it is
about never letting the two be confused.

```bash
python3 scripts/certify.py                        # synthetic: no model, offline, runs in CI
python3 scripts/certify.py --live --model opus    # real sessions, real hooks
python3 scripts/certify.py --live --out run.json  # write the record
```

## The Golden Project

`golden/` is a real project, not a fixture that gestures at one: a retention
window service with working code, thirteen tests that pass, a threat model, and
a `.ai-engineering/project.yaml` that validates with no warnings.

It is deliberately small and deliberately boring. One deployable, no database, no
queue, standard library only — a project that would fail its own
`complexity_justified(ARCH)` if it introduced anything else, because nothing in
its requirements asks for it. Certifying against a sprawling project would prove
less, not more: every extra component is a place for the certification to pass
for reasons that have nothing to do with the organization.

The harness never runs against `golden/` itself. It copies it to a throwaway
directory and `git init`s there, because certification writes work items,
artifacts and history, and a certification path that dirties what it certifies
cannot be run twice.

## The two paths

| | Synthetic | Live |
| --- | --- | --- |
| What drives it | The organization drives itself | Real `claude -p` sessions |
| Model in the loop | None | Yes |
| Runs in CI | Yes, on every change | No: needs a model and a network |
| What it can prove | The project opens, plans from a real workflow, and every predicate on every stage has an evaluator | That Claude Code actually calls the hooks, and what happens when it does |
| What it cannot prove | That the lifecycle can be completed — no stage is executed | Nothing about stages no session drove |

**The synthetic path deliberately claims very little.** Its stages report
`incomplete`, not `pass` and not `fail`: a stage nobody executed has not failed
its definition of done, it has not been attempted, and reporting the two the same
way trains a reader to discount both. What it does check is that every predicate
on every stage of a real project has an evaluator at all — an `unsupported`
entry is a contract that could never be satisfied even by an agent that did the
work perfectly.

Whether the process *can* be completed is `simulate_sdlc.py`'s question, and it
answers it against ten scenarios elsewhere.

## Probes

A probe asks one question about an integration point and answers it **from
durable evidence** — the audit log, the work item's history, the task record in
the graph, a file on disk. Never from a session's account of its own behaviour,
which is the thing under test.

There is exactly one exception, and it is safe for a specific reason.
`the-agent-knew-what-was-not-in-its-prompt` reads what the agent said, because
the test is whether a value the prompt never contained came back. A model cannot
report a string it was never given, so the report is evidence about the injection
rather than about the model's honesty.

Probes are **tri-state**. `not-run` is a real answer and it is not a failure: a
path nothing exercised has not broken. An earlier version could only say pass or
fail, so it reported a defect in `bind_task.py` when what had actually happened
was that the session never created a native task.

## The verdict

```
synthetic  : pass | fail | not-run
real_agent : pass | fail | partial | not-run
certified  : true | false
```

One rule, and the file exists to enforce it:

> **`real_agent` is never derived from synthetic units, and `certified` is never
> true without it.** A run where every synthetic stage passed and no session ever
> started is `real_agent: not-run`, `certified: false`.

`partial` means probes passed and real agents did not drive every required stage.
Partial evidence is not certification, and the verdict names the stages that are
missing rather than rounding up.

## What the last live run actually found

`golden/certification-run.json` is a real run, kept in the repository so the
claims here can be checked rather than believed. The numbers below are the run
record's own, and `check_certification_doc_matches_the_run` fails the build when
this page and that file disagree.

9 of 14 probes passed against a live session on Claude Code 2.1.251, plugin 0.43.0:

| Probe | Evidence |
| --- | --- |
| `session-start-self-test` | 114 audit record(s), 54 deny |
| `context-injection-reaches-the-model` | session wrote injected.txt |
| `write-guard-refuses-out-of-scope` | 19 write-guard refusal(s) recorded |
| `subagent-is-briefed-on-its-own-task` | T-001 claimed by engineering-director; evidence: SubagentStart fired for a8f1013bcdf982bfd |
| `subagent-result-is-attributed` | 14 subagent stop(s), 7 attributed to a task |
| `execution-actual-is-observed-not-assumed` | T-001 declared inline, resolved inline, actual subagent (SubagentStart fired for a8f1013bcdf982bfd) |
| `the-agent-knew-what-was-not-in-its-prompt` | the agent reported GOLD-FEAT-001 and its intent, neither of which was in the prompt beyond the id |
| `background-execution-was-actually-dispatched` | job 4475730d: kind background, state blocked; produced no artifact |
| `execution-modes-were-exercised-not-just-named` | subagent (T-001, T-002) |

5 probes never ran, and `not-run` is not a quiet `pass` — each names a mechanism
this harness cannot reach, so certification is refused:

| Probe | Why it did not run |
| --- | --- |
| `task-binding-recorded` | no native task was created, so TaskCreated never fired |
| `task-completion-is-gated` | no native task completed, so TaskCompleted never fired |
| `worktree-isolation-was-actually-used` | no worktree was created, so isolation stayed at shared-checkout and the WorktreeCreate hook never fired |
| `worktree-work-was-integrated-not-just-isolated` | no worktree was created, so there is nothing to integrate |
| `a-team-stage-carried-its-skills` | no stage ran as a team, so teammate skill propagation is unmeasured |

The execution one is the load-bearing result. `actual` is only worth recording if
it can disagree with `resolved` — a run where the two always match is consistent
with `actual` being copied from `resolved` and never observed at all. Here they
disagreed, from platform evidence, and the divergence was recorded.

The most interesting results are not probes. The organization **refused its own
work**: acceptance was refused on REQ, the control loop decided `REWORK` twice and
then `ESCALATE`, and the task never reached `accepted`. And the walk **convened**
— when the stage owner could not satisfy the definition of done alone, the roles
its unmet predicates named were called in: the artifact's owner, the gate
reviewer, the department lead, and a human for the approval no agent may sign.

## What is still not certified

`certified: false`, and the run says why: real agents drove IDEA and REQ — not the 6 stages
certification requires.

- **REQ, ARCH, QADESIGN, DEV, REVIEW, CI** driven end to end by real agents.
- **The task gates.** `TaskCreated` and `TaskCompleted` need the native task
  tools; the live sessions did not use them, so `task-binding-recorded` reports
  `not-run`. Their payload shape and their place in the blocking set are read out
  of the binary by `check_platform_drift.py`; that Claude Code ever calls the
  hooks is a separate claim and it is still untested.
- **Agent teams** and **worktree isolation**, which need an interactive session
  and an experimental flag.
- **The 28 LLM-judged evaluation cases**, which are reported pending and never
  auto-passed.

## Related

- [production-readiness.md](production-readiness.md) — the synthetic end-to-end proof and the four defects it found
- [limitations.md](limitations.md) — what is not enforced, and what has never run
- [evaluation.md](evaluation.md) — the suites, and why an LLM-judged case is never auto-passed
