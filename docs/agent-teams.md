# Agent teams

## Verify before you rely on this

Agent teams are experimental in Claude Code and disabled by default. Everything
below was checked against the current documentation; check again before building
on it.

- Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings or environment.
- Teammates are **not** interactive-only. `-p` carries a full teammate lifecycle
  and `--teammate-mode in-process` needs no TTY, so the earlier reading no longer
  holds at 2.1.241. It is a contract reading, not an end-to-end run here.
- **No nested teams.** A teammate cannot spawn teammates.
- A teammate's model is **fixed at spawn**. Permission mode is not: every teammate starts in the lead's mode, and individual teammate modes can be changed after spawning, but not set per teammate at spawn time.
- When a teammate uses a subagent definition, its `tools` and `model` apply, but
  **`skills` and `mcpServers` do not**.
- Teammates do not inherit the lead's conversation.
- An idle notification does **not** carry the teammate's output.
- `/resume` and `/rewind` do not restore in-process teammates.
- One team per session; the lead is fixed for the session's lifetime.
- A teammate cannot run background subagents. `background: true` in a definition
  errors, and `run_in_background` fails or silently runs in the foreground.
- Teammate permission prompts surface in the lead's session. Pre-approve the
  operations a team will need before spawning it.

## Enabling teams changes every stage, not only the team stages

This is the failure mode most likely to surprise you, and it runs in the opposite
direction to the one the workflows model.

With `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` set, **any subagent Claude names
from the main conversation launches as a teammate**, not only in the five stages
that declare `execution: team`. Forks are exempt, as is an explicit `isolation`
argument on the call.

That matters because an idle notification carries no output. A stage written as
an orchestration — spawn a reviewer, wait for its findings, act on them — becomes
a spawn whose result never returns, and the stage stalls rather than failing. The
32 stages that declare `execution: subagent` are all written that way.

So the environment variable is a project-level decision, not a per-stage one:

- Setting it for the whole session buys you teams in `ARCH`, `DEV`, `INVESTIGATE`,
  `REHEARSE` and `STAGING`, and exposes every other stage to conversion.
- The safer posture is to leave it unset by default and enable it for a session
  that is deliberately doing team work, which is what `ai.agent_teams_available`
  in `project.yaml` records.

If a stage appears to hang after a spawn, this is the first thing to check.

## There are no team definition files

`~/.claude/teams/{team}/config.json` is runtime state that Claude Code writes and
overwrites. Pre-authoring it would be a fiction that appears to work and does not.

Team composition is therefore expressed in the **spawn prompt**, which is why the
patterns in `skills/team-patterns/SKILL.md` are prompts rather than configuration.
Reusable roles come from the subagent definitions in `agents/`, referenced by name
in the prompt.

## When a team is worth it

A team costs several times a single session's tokens, because each teammate is a
full Claude Code instance with its own context.

| Situation | Use |
| --- | --- |
| One role, sequential work | The current session |
| A focused question where only the answer matters | A subagent |
| Independent workstreams that must also talk to each other | A team |
| Work touching the same files | A single session — parallel edits overwrite |
| Dense dependencies between pieces | A single session |

## Patterns

Four are shipped, with full spawn prompts, in
[`skills/team-patterns/SKILL.md`](../skills/team-patterns/SKILL.md):

| Pattern | Composition | Use for |
| --- | --- | --- |
| Feature engineering team | architect, backend, frontend, QA, security | Cross-functional feature with separable layers |
| Parallel review | security, performance, reliability | A large or high-risk merge request |
| Competing hypotheses | 4 investigators, adversarial | Incident or hard defect with an unclear cause |
| Release validation | QA, security, SRE | Assembling release evidence |

## Rules that matter in practice

**State file ownership in the prompt.** This is not tidiness. Two teammates
editing one file overwrite each other, and the loser's work vanishes silently.

**Put everything in the spawn prompt.** The teammate inherits none of your
conversation. A teammate spawned with "review the auth module" and no context
will review something, but not necessarily what you meant.

**Say which skills to invoke.** The `skills` frontmatter field does not apply to
teammates.

**Require teammates to report by message.** The idle notification tells the lead
that a teammate stopped, not what it found.

**Apply the model policy at spawn time.** The model cannot be changed afterwards.

**Three to five teammates.** Beyond that, coordination cost grows faster than
throughput.

## Teams are execution, never state

`policies/system-of-record.json` declares the agent-team task list authoritative
for **nothing**. It coordinates who is doing what right now. It must not record that a stage is
complete, must not record an approval, and must not be relied on to carry state
between sessions.

That last point is a rule, not a description of the storage. The task directory
under `~/.claude/tasks/` does persist locally, and a resumed session keeps its
tasks. What does not survive is the team itself: the team config directory is
removed at session end and in-process teammates are not restored. Combined with
task status that is known to lag, this makes the list a coordination surface and
nothing more. Business correctness must not depend on it.

A project that cannot enable agent teams sets `ai.agent_teams_available: false`
and every `team` stage falls back to `subagent`. Nothing about correctness
changes. See [execution](execution.md).

## Interaction with the spawn hierarchy

`guard_spawn.py` sees `Agent` tool calls. Whether a given call becomes a subagent
or a teammate is Claude Code's decision, and the guard constrains the delegation
either way when the caller is one of this OS's agents. What the guard does **not**
see is any teammate creation that happens outside the `Agent` tool. The
hierarchy is therefore a guardrail on delegation, not a complete authorization
boundary; see `docs/limitations.md`.
