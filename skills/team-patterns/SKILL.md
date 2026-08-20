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
| Work on the same files | A single session. Parallel edits overwrite each other. |
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

## Pattern: feature engineering team

Use for a cross-functional feature where backend, frontend, tests and infrastructure are separable.

```
Spawn a feature engineering team for <story set>. Use these teammates, each with
the named agent type:
- architect  (solution-architect): owns docs/architecture/**; produce the design and stop.
- backend    (backend-developer):  owns src/api/** and src/service/**.
- frontend   (frontend-developer): owns src/web/**.
- qa         (qa-engineer):        owns tests/**.
- security   (security-reviewer):  read-only; review each change as it lands.
Each teammate: read .ai-engineering/project.yaml first, invoke the skills your
role names, and report findings to the lead by message. Do not edit files
outside your ownership. Require plan approval before any teammate modifies code.
```

File ownership in the prompt is not decoration: it is what prevents overwrites.

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
- Disjoint file ownership, stated in the prompt.
- Spawn prompts carry the full context the teammate needs: it inherits none of your conversation.
- The lead does not implement while teammates work; it coordinates and synthesises.
- The spawn hierarchy in `${CLAUDE_PLUGIN_ROOT}/policies/agent-registry.json` still applies to what those teammates may delegate.
