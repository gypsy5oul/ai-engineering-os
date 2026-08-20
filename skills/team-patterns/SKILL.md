---
name: team-patterns
description: Choose between a single agent, subagents and an agent team, and spawn the right team with the right context. Use when work spans several disciplines, when parallel investigation would help, or when deciding whether a team is worth its token cost.
---

# Team patterns

Agent teams cost significantly more tokens than a single session, because each teammate is a full Claude Code instance with its own context. Use one when parallel independent work genuinely helps, and not otherwise.

## Choosing

| Situation | Use |
| --- | --- |
| One role, sequential work | The current session |
| A focused question whose answer is all you need | A **subagent** |
| Several genuinely independent workstreams that must also talk to each other | An **agent team** |
| Work on the same files | Separate worktrees plus a merge step, or a single session. Never parallel workers in one checkout. |
| Workers that build, test, format or install dependencies | Separate worktrees, even when their source files are disjoint |
| Many dependencies between the pieces | A single session; coordination overhead exceeds the benefit |

## Availability and limits (verified against current Claude Code behaviour)

- Agent teams are **experimental and disabled by default**. They require `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings or environment.
- Teammates spawn only in **interactive** sessions. In non-interactive (`-p`) runs a named subagent runs as an ordinary subagent.
- **No nested teams.** A teammate cannot spawn teammates. Team depth is one level.
- A teammate's **model is fixed at spawn time**. Apply the model policy when spawning, not afterwards. Permission mode is inherited from the lead at spawn and can be changed per teammate afterwards.
- When a teammate uses a subagent definition, its `tools` and `model` apply, but **`skills` and `mcpServers` in that definition are not applied**. Tell the teammate which skills to invoke in the spawn prompt.
- Teammates do **not** inherit the lead's conversation. Everything they need goes in the spawn prompt.
- A teammate's idle notification does not carry its output. Require teammates to report by message or by updating the shared task list.
- `/resume` does not restore in-process teammates.

There are no team definition files: `~/.claude/teams/*/config.json` is runtime state that Claude Code writes and overwrites. Team composition is expressed in the prompt, which is why the patterns below are prompts.

## Isolated working copies

File ownership is the cheap answer to parallel edits and it does not always exist. When two workers genuinely must touch the same file, or when a worker runs a build, a test suite, a formatter, a code generator or a dependency install — all of which write shared output regardless of who owns which source file — give them separate working copies.

- **Spawning:** pass `isolation: "worktree"` on the `Agent` call. The worker gets its own git worktree under `.claude/worktrees/`, on its own branch, and is told so. It is mutually exclusive with `cwd`.
- **Always-isolated roles:** `isolation: worktree` in an agent definition's frontmatter. `worktree` is the only value valid for a plugin-shipped agent.
- **This session:** `EnterWorktree` moves the current session into a worktree, `ExitWorktree` with `action: keep` or `action: remove` leaves it. Use these only when a human asked for a worktree or project instructions require one — not on your own initiative.
- **Results:** a worker that changed nothing has its worktree deleted automatically. A worker that changed something returns `worktreePath` and `worktreeBranch`. Those are what you merge.

Do **not** isolate read-only workers. Every reviewer and every investigation pattern below stays in the shared checkout: a reviewer in a worktree reviews a copy, and you have paid for a checkout to gain nothing.

### Traps verified against current Claude Code behaviour

- **`worktree.baseRef` defaults to `fresh`**, which branches from `origin/<default-branch>`. An isolated worker therefore does **not** see the feature branch you are standing on, or any unpushed commit. For work that continues a branch, set `"worktree": {"baseRef": "head"}` in `.claude/settings.json` first, or the workers build against the wrong base.
- A worker whose working directory was pinned at launch (isolated, or given an explicit `cwd`) **cannot create** a worktree with `EnterWorktree`. It can only switch into an existing one of the same repository by `path`.
- `ExitWorktree` only touches a worktree that `EnterWorktree` created in this session, and refuses to remove one with uncommitted changes unless `discard_changes` is set.
- Isolation is a default working directory, not a sandbox. A worker can still write an absolute path back into the main checkout. Say so in the spawn prompt.
- Background sessions are isolated already: `worktree.bgIsolation` defaults to `worktree`, which blocks `Edit` and `Write` in the main checkout until `EnterWorktree` is called.
- In a large repository, set `worktree.sparsePaths` and `worktree.symlinkDirectories` in `.claude/settings.json` before concluding that a checkout per worker is too slow.

### The merge is a step, not a hope

Isolated work is not in the repository until someone merges it. Nothing merges it for you, and a stage that ends without merging looks finished while the work sits on branches. The lead owns integration — never a worker, which cannot see the other branches:

1. Collect `worktreeBranch` from every worker result. A worker that returned none changed nothing.
2. Merge the branches into the integration branch one at a time, in a stated order, so a conflict names one worker.
3. Resolve conflicts yourself, in the integration branch. Do not hand a conflict back to a worker whose worktree no longer reflects the merged state.
4. Run the build and the full test suite **once, after the last merge**. Each worker's green run was against its own copy and proves nothing about the union.
5. Only then produce the stage output. Review and approval apply to the merged result.

A conflict between two workers is evidence the split was wrong, not just a merge to resolve — say so in the report, or the same split gets proposed again. A conflict on a coupled surface named in `${CLAUDE_PLUGIN_ROOT}/policies/coupling-policy.json` is a policy failure: that surface has one owner, and a merge is not the place to decide it.

## Pattern: feature engineering team

Use for a cross-functional feature where backend, frontend, tests and infrastructure are separable.

```
Spawn a feature engineering team for <story set>. Use these teammates, each with
the named agent type:
- architect  (solution-architect): owns docs/architecture/**; produce the design and stop.
- backend    (backend-developer):  owns src/api/** and src/service/**.
- frontend   (frontend-developer): owns src/web/**.
- qa         (qa-engineer):        owns tests/**.
- security   (security-reviewer):  read-only; review each merged change.
Each teammate: read .ai-engineering/project.yaml first, invoke the skills your
role names, and report findings to the lead by message. Do not edit files
outside your ownership. Require plan approval before any teammate modifies code.

Spawn backend, frontend and qa with isolation: "worktree" — they run the build
and the test suite, which write shared output whatever the source ownership
says. Nothing they write is visible outside their own worktree, so use only
paths relative to your own working directory. architect and security stay in
the shared checkout: one writes docs only, the other writes nothing. I will
merge the worktree branches in the order backend, frontend, qa, run the full
suite once on the merged result, and only then give security something to
review — a reviewer in the shared checkout cannot see unmerged worktrees.
```

File ownership in the prompt is not decoration: it is what prevents overwrites in a shared checkout. Where ownership cannot be made disjoint, say `isolation: "worktree"` in the spawn and name who merges, in the same breath.

## Pattern: parallel review

Use on a large or high-risk merge request.

```
Spawn three teammates to review <MR>, each with one lens and no overlap:
- security   (security-reviewer):   auth, input handling, secrets, dependencies.
- performance(performance-reviewer): data access, hot paths, unbounded work.
- reliability(reliability-reviewer): failure modes, retries, rollback safety.
Each reports findings with severity and an exploitation or failure path. Do not
edit anything. I will synthesise.
```

## Pattern: competing hypotheses (incident or hard defect)

```
Production symptom: <one sentence>. Spawn four teammates, each investigating a
different hypothesis, read-only. Have them message each other to try to disprove
each other's theories. Each must state what evidence would refute its own
hypothesis. Report the surviving theory with its evidence.
```

Adversarial structure is the point. Sequential investigation anchors on the first plausible answer.

## Pattern: release validation

```
Spawn a release validation team for release <version>:
- qa       (qa-lead):           execute the staging validation plan.
- security (security-reviewer): verify security verdicts for every included change.
- sre      (sre):               operational readiness and rollback verification.
Each reports a verdict with evidence. Nobody deploys; the release manager
assembles the evidence for human approval.
```

## Rules for any team

- 3–5 teammates. More produces coordination cost, not throughput.
- Disjoint file ownership, stated in the prompt — or `isolation: "worktree"` where it cannot be disjoint.
- Every spawn that isolates also names the integration step and its owner. An isolated worker's output is not in the repository until the lead merges it, and nothing will do that automatically.
- Count the merge before choosing parallelism. A checkout per worker plus a merge the lead must run and test is real cost, not a rounding error.
- Spawn prompts carry the full context the teammate needs: it inherits none of your conversation.
- The lead does not implement while teammates work; it coordinates and synthesises.
- The spawn hierarchy in `${CLAUDE_PLUGIN_ROOT}/policies/agent-registry.json` still applies to what those teammates may delegate.
