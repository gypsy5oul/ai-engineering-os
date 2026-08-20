# Execution: inline, subagent or team

Every workflow stage declares how it runs. Left to model discretion this becomes
expensive and inconsistent, so `policies/execution-policy.json` defines the modes
and each stage picks one.

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
4. Would the workers edit the same files? → **not a team**, regardless of anything else.
5. Is the session non-interactive? → **not a team**; teammates do not spawn under `-p`.

Rule 4 is not a preference. Two teammates editing one file overwrite each other
and the loser's work vanishes silently.

**File disjointness is necessary and not sufficient.** A backend agent editing the
API implementation and a frontend agent editing the client both change the API
contract. Their files never collide; the contract does, and the result is a merge
that compiles and a system that does not work.

`policies/coupling-policy.json` names five coupled surfaces — api-contract,
database-schema, deployment-manifest, event-schema, shared-configuration — each
with **one owning role**. Stages declare the surfaces they touch, and validation
fails when two stages that may run in parallel declare the same one.

The pattern is always: the surface owner produces the contract → it is reviewed →
it reaches `approved` → only then do implementers work in parallel against it. An
implementer that finds the contract wrong raises it with the owner rather than
amending it.

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

Current levels: `WF-INCIDENT INVESTIGATE` is **REQUIRED**; `WF-FEATURE ARCH` and
`WF-RELEASE STAGING` are **PREFERRED**; `WF-FEATURE DEV` is **OPTIONAL** — a
single session implements the same stories with identical guarantees, just
slower.

Validation fails a `TEAM_REQUIRED` stage that falls back without human
acknowledgement.

## Where each is used

Resolve the whole picture with:

```bash
python3 scripts/resolve_model.py --all
```

Teams are used in exactly four places, and each says in its `actions` why the
parallelism is worth the multiplier:

| Stage | Why a team |
| --- | --- |
| `WF-FEATURE ARCH` | Security, operability and design must challenge each other rather than review in sequence |
| `WF-FEATURE DEV` | Only where stories own disjoint paths; otherwise they run sequentially in one session |
| `WF-INCIDENT INVESTIGATE` | Competing hypotheses; sequential investigation anchors on the first plausible theory |
| `WF-RELEASE STAGING` | QA, security and operability validate different things against the same candidate |

Everything else is `inline` or `subagent`. Validation fails a `team` stage with
fewer than two participants — a team of one is a subagent with extra cost.

## Platform constraints that shape this

- Agent teams are **experimental and disabled by default**; they need
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- Teammates spawn only in **interactive** sessions.
- **No nested teams**: depth is one level.
- A teammate's model is **fixed at spawn**. Permission mode is not: every teammate starts in the lead's mode, and individual teammate modes can be changed after spawning, but not set per teammate at spawn time.
- A subagent definition's `tools` and `model` apply to a teammate; its `skills`
  and `mcpServers` **do not**.
- Enabling teams converts *every* named subagent spawn in the main conversation
  into a teammate, including in the 24 stages that declare `execution: subagent`.
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
