# Execution and isolation

Two questions, and they are not the same one.

**Execution** is *how* the work runs: inline, as a subagent, in the background, or
as a team. **Isolation** is *where* it runs: the shared checkout, its own git
worktree, or a remote environment.

They used to share one field. `worktree` sat in the execution enum next to
`inline` and `subagent`, which meant the only way to isolate a task was to stop
calling it what it was — a team that needed its own checkout resolved to
`worktree`, and nothing downstream could still tell it had been a team. The two
dimensions are separate now, and the resolver answers them independently.

| | Values |
| --- | --- |
| **Execution** | `inline`, `subagent`, `background`, `team`, `dynamic-workflow` |
| **Isolation** | `shared-checkout`, `worktree`, `remote` |

Every combination is real:

| Execution | Isolation | What it means |
| --- | --- | --- |
| `inline` | `shared-checkout` | The session does the work where it stands. The default. |
| `subagent` | `shared-checkout` | A focused worker in the same checkout. Correct for anything read-only. |
| `subagent` | `worktree` | A writer alongside other writers. The isolation is about the files, not about how the worker runs. |
| `background` | `worktree` | Background sessions are worktree-isolated by default. |
| `team` | `shared-checkout` | Teammates who own disjoint paths. The usual team case. |
| `team` | `worktree` | Teammates who must touch the same file. **Still a team**; only its checkout changed. |

The rule underneath: isolating a task never changes how it runs, and changing how
it runs never decides where.

## The three modes

| Mode | What it is | Token cost |
| --- | --- | --- |
| `inline` | The current session does the work | baseline |
| `subagent` | A focused worker with its own context that reports its result back | moderate — the result is summarised into the caller's context |
| `team` | Independent Claude Code instances with their own contexts, direct messaging and a shared task list | high, roughly linear in teammate count |

## The decision rule

1. Can one role finish this without waiting on anyone? → **inline** or **subagent**.
2. Do I only need the answer, not the working? → **subagent**.
3. Do the workers need to talk to each other to reach the answer? → **team**.
4. Would the workers edit the same files? → only with **isolation `worktree`** and a
   declared integration step. In a shared checkout, no.
5. Would the workers run a build, a test suite or a formatter? → **isolation `worktree`**,
   even if their source files are disjoint: those write shared output.
6. Is the session non-interactive? → a team is still possible, and unverified
   here; prefer **subagent** unless the parallelism is the point. The version this
   was established against is in `policies/platform-capabilities.json`, which
   `scripts/check_platform_drift.py` re-checks against the installed binary —
   restating a version in prose is how a claim outlives the release it was true
   of.

Rule 4 is not a preference. Two workers editing one file in one checkout
overwrite each other and the loser's work vanishes silently. What has changed is
the remedy: it used to be "then don't", which in practice produced a smaller
plan or a silent overwrite. Now it is a separate working copy and a merge someone
owns. See [Working copies](#working-copies-shared-checkout-or-worktree).

**Neither disjoint files nor separate worktrees are sufficient.** A backend agent
editing the API implementation and a frontend agent editing the client both change
the API contract. Their files never collide; the contract does, and the result is a
merge that compiles and a system that does not work. Isolation makes the merge
mechanical — it does not make the contract agree.

`policies/coupling-policy.json` names five coupled surfaces — api-contract,
database-schema, deployment-manifest, event-schema, shared-configuration — each
with **one owning role**. Stages declare the surfaces they touch, and validation
fails when two stages that may run in parallel declare the same one.

The pattern is always: the surface owner produces the contract → it is reviewed →
it reaches `approved` → only then do implementers work in parallel against it. An
implementer that finds the contract wrong raises it with the owner rather than
amending it.

## Working copies: shared checkout or worktree

Execution mode says *who* does the work. Isolation says *which copy of the
repository they do it in*. `policies/execution-policy.json` defines both, and
`scripts/resolve_execution.py` resolves them separately: it returns
`(execution, isolation, why)` and writes a declared/resolved/actual triple for
each. Both can be overruled by runtime facts, and neither overrules the other.

| Mode | What the worker edits | When |
| --- | --- | --- |
| `shared-checkout` (default) | The session's working directory | Disjoint paths, or read-only work |
| `worktree` | Its own git worktree under `.claude/worktrees/`, on its own branch | The paths cannot be disjoint, or the worker builds, tests, formats, generates code or installs dependencies |
| `remote` | A remote environment rather than this machine | A long or heavy job. Always a background task, and availability is gated per account, so nothing in the lifecycle may depend on it. **Never run here** — it is in the enum because the platform has it, and a resolver that cannot name a mode has to call it something else. |

Three ways to get one, all verified against the installed Claude Code:

- `Agent(..., isolation: "worktree")` on a spawn. Mutually exclusive with `cwd`.
- `isolation: worktree` in an agent definition's frontmatter, for a role that
  should always be isolated. `worktree` is the only value valid for a
  plugin-shipped agent.
- `EnterWorktree` / `ExitWorktree` for the current session — only when a human
  asked for a worktree or project instructions require one.

A worker that changed nothing has its worktree removed automatically. A worker
that changed something returns `worktreePath` and `worktreeBranch`.

### The merge is a step

Isolated work is not in the repository until the lead merges it. The lead — never
a worker, which cannot see the other branches — collects each `worktreeBranch`,
merges them into the integration branch one at a time in a stated order, resolves
conflicts itself, and runs the build and full test suite **once after the last
merge**. Each worker's green run was against its own copy and proves nothing
about the union. Only the merged result is reviewed and approved.

A conflict between two workers is evidence the split was wrong, not just a merge
to resolve. A conflict on a coupled surface is a policy failure: that surface has
one owner, and a merge is not where it gets decided.

### Traps

- **`worktree.baseRef` defaults to `fresh`**, which branches from
  `origin/<default-branch>`. An isolated worker does **not** see the feature
  branch you are standing on, or any unpushed commit. Work that continues a
  branch needs `"worktree": {"baseRef": "head"}` in `.claude/settings.json`.
- A worker whose working directory was pinned at launch cannot *create* a
  worktree with `EnterWorktree`; it can only switch into an existing one by path.
- Background sessions are isolated already: `worktree.bgIsolation` defaults to
  `worktree` and blocks `Edit`/`Write` in the main checkout until
  `EnterWorktree` is called.

### What this repository can and cannot enforce

It can check its own files. No workflow stage declares an isolation mode yet, so
that check does not exist today; when a stage does, validation should require it
to declare the integration step and its owner in the same place. Until then the
only enforced part is coherence: `tests/test_execution_isolation.py` fails if the
policy, this document and `skills/team-patterns/SKILL.md` stop naming the same
mechanisms, or if the policy stops admitting what it cannot enforce.

It **cannot force a worktree.** A `PreToolUse` hook sees a spawn's `tool_input`,
including `isolation`, so it can refuse a spawn — but it cannot rewrite one to
add isolation, and it cannot tell from a spawn whether the workers were going to
collide. No hook fires at all when the model simply decides not to spawn workers,
which is the likelier failure. Isolation is also a default working directory, not
a sandbox: a worker can still write an absolute path back into the main checkout.
And nothing merges the branches — a stage that ends without integrating looks
finished.

So this is a rule for agents to follow and reviewers to check, exactly as the
file-ownership rule always was. Writing it down is what makes the omission
visible. `policies/execution-policy.json` says so in its own
`not_enforceable` list rather than implying a guarantee it does not have.

## How badly a stage needs a team

Falling back from `team` to `subagent` is not free, and pretending it is would be
the same mistake as the old blanket fail-open. Each team stage declares how
strongly it needs a team and what is lost without one.

| Level | Meaning | Fallback |
| --- | --- | --- |
| `TEAM_REQUIRED` | A single agent is **not** equivalent; the degradation is material | Escalate to a human, or run the declared degraded mode **with the loss acknowledged** |
| `TEAM_PREFERRED` | Fallback is acceptable with reduced independence | `subagent`, with the guarantees lost recorded |
| `TEAM_OPTIONAL` | Parallelism only; guarantees are identical | `inline` |

```yaml
# WF-INCIDENT INVESTIGATE
team_requirement: TEAM_REQUIRED
degraded_mode:
  fallback: escalate
  requires_human_acknowledgement: true
  guarantees_lost:
    - Competing hypotheses cannot be tested in parallel, so investigation anchors
      on the first plausible theory. This is the single largest cause of long incidents.
    - Nobody is positioned to refute anyone else's theory.
    - Investigation becomes serial, extending time to mitigation.
```

Current levels: `WF-INCIDENT INVESTIGATE` is **REQUIRED**; `WF-FEATURE ARCH`,
`WF-RELEASE STAGING` and `WF-MIGRATION REHEARSE` are **PREFERRED**;
`WF-FEATURE DEV` is **OPTIONAL** — a single session implements the same stories
with identical guarantees, just slower.

Validation fails a `TEAM_REQUIRED` stage that falls back without human
acknowledgement.

## Where each is used

Resolve the whole picture with:

```bash
python3 scripts/resolve_model.py --all
```

Teams are used in exactly five places, and each says in its `actions` why the
parallelism is worth the multiplier:

| Stage | Why a team |
| --- | --- |
| `WF-FEATURE ARCH` | Security, operability and design must challenge each other rather than review in sequence |
| `WF-FEATURE DEV` | Only where stories own disjoint paths; otherwise they run sequentially in one session |
| `WF-INCIDENT INVESTIGATE` | Competing hypotheses; sequential investigation anchors on the first plausible theory |
| `WF-MIGRATION REHEARSE` | Correctness, duration and operability have to be judged while the same run is happening; sequentially each discipline sees a different run |
| `WF-RELEASE STAGING` | QA, security and operability validate different things against the same candidate |

Everything else is `inline` or `subagent`. Validation fails a `team` stage with
fewer than two participants — a team of one is a subagent with extra cost.

## Platform constraints that shape this

- Agent teams are **experimental and disabled by default**; they need
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- **Spawning a teammate needs an interactive session.** Under `-p`, including
  SDK sessions, a subagent Claude names runs as an ordinary subagent even with
  teams enabled. v0.22 recorded the opposite here, on the strength of print-mode
  teammate lifecycle strings in the binary — but a print-mode session being able
  to *be* a teammate is not evidence that one can *spawn* one. The claim was
  wrong for four versions. Nothing detects this at runtime either: no
  environment variable separates interactive from `-p`, so the degradation is
  caught after the fact in `execution.actual` rather than prevented.
- **Teammates are not worktree-isolated.** Two of them editing one file overwrite
  each other, so work given to a team has to be partitioned by file. The resolver
  refuses `team` when the pieces declare overlapping `owns_paths`.
- **No nested teams**: depth is one level.
- A teammate's model is **fixed at spawn**. Permission mode is not: every teammate starts in the lead's mode, and individual teammate modes can be changed after spawning, but not set per teammate at spawn time.
- A subagent definition's `tools` and `model` apply to a teammate; its `skills`
  and `mcpServers` **do not**.
- Enabling teams converts *every* named subagent spawn in the main conversation
  into a teammate, including in the 32 stages that declare `execution: subagent`.
  Because an idle notification carries no output, such a stage stalls rather than
  failing. See [Agent teams](agent-teams.md) — this is why the environment
  variable is a session-level decision.
- A teammate's idle notification does **not** carry its output.
- `/resume` does not restore in-process teammates.

## Teams are an accelerator, not a dependency

A project that cannot enable agent teams sets
`ai.agent_teams_available: false` in `.ai-engineering/project.yaml`, and stages
declaring `team` fall back to `subagent`. Nothing about correctness changes,
because every stage's outputs land in a system of record regardless of how the
work was executed.

Any workflow that would break if agent teams were disabled tomorrow is wrongly
designed. `EVAL-AIG-005` asserts this.
