# What V1 cannot do

Every item here is a real limit. None is worked around with something that looks
like it works.

## Platform limits

**Agent teams are experimental.** Disabled by default, no nested teams, no session resumption for in-process teammates, model and
model fixed at spawn, and `skills`/`mcpServers` frontmatter not applied to
teammates. Team composition therefore lives in prompts, not configuration.

**There is no team definition format.** `~/.claude/teams/*/config.json` is
runtime state that Claude Code writes and overwrites.

**A plugin-root `settings.json` supports only `agent` and
`subagentStatusLine`.** Organization-wide permissions, environment variables or
hook settings cannot be shipped in the plugin; they belong in the project's or
the engineer's own settings, or in managed settings.

**Approval does not persist in-session.** A hook can escalate a single tool call.
It cannot record that a human approved a *plan* and let the next twelve calls
through, and it cannot carry an approval across sessions. Durable approval is a
GitLab artifact, which is why every `human_gate` names where the decision is
recorded. See [approvals](approvals.md).

**Hooks see one tool call at a time.** They cannot reason about a sequence, so a
dangerous outcome assembled from individually innocuous commands is not detected.

**`guard_spawn` sees only the requested and calling agent types.** It cannot
verify intent, it cannot see teammate creation outside the `Agent` tool, and it
does not apply to the human-driven main session by design. It is a guardrail on
delegation, not an authorization boundary.

**Write scoping depends on `agent_type` being present in the hook payload.** Work
performed by the main session is unscoped, which is correct — a human is driving —
but it means the scope is a constraint on agents, not on everyone.

## Deliberate non-implementations

**No MCP servers.** Categories, invariants and the approval path are in
`docs/mcp.md`.

**No production deployment agent.** Production deployment is AP-01 and is done by
a human or by CI under human approval. An agent for it would be a CRITICAL actor
with no compensating control.

**No headless or scheduled execution.** Everything assumes an interactive session
with a human who can answer an escalation. In `-p` mode escalations have nobody
to escalate to, and teammates do not spawn.

**No technology-specific skills** beyond `kubernetes-basics`, which declares its
own applicability. Baking a stack into the company layer would contradict
technology neutrality.

**No graph database for traceability.** Identifiers and file conventions first;
a tool once the convention demonstrably holds.

**No control plane.** See below.

## Weak spots, named

**Most of this has now run for real, and some of it never has.** Until 0.27.1
every hook had been tested by feeding hand-written JSON to a Python script:
547 tests validated the plugin against itself and none of them proved Claude
Code would ever call any of it. A live run in a throwaway project confirmed the
spine — SubagentStart claims a task and the briefing reaches the agent,
SubagentStop attributes the result and releases the lease, an unowned spawn is
recorded as unattributed, a real execution divergence was detected, and
`guard_bash` escalated a protected-branch push with the refusal reaching the
model and the command never running.

What has still never run: **agent teams**, **worktree isolation** and therefore
the `briefing_required` path, the **TaskCompleted gate** (it needs the native
task tools), the **23 LLM-judged evaluations**, and **any complete work item** —
one task has been briefed and observed; no change has been driven from intake to
acceptance by real agents. Treat those as designed and unproven.

**Behavioural rules are not enforcement.** "Never invent an availability target"
is a contract, not a guarantee. The evaluation suite tests it; the suite does not
run on every session.

**A guard cannot protect against `python3` being absent.** The tiered failure
path covers a broken guard, not an absent interpreter: without `python3` the hook
never starts, Claude Code records the failure, and the call proceeds. The session
self-test catches a broken guard, not a missing one.

**Definition-of-done predicates split three ways.** `repo` and `project`
predicates are evaluated by `scripts/check_dod.py`. `gitlab` predicates —
pipeline results, human approvals — report `REQUIRES-EVIDENCE` and name where the
evidence lives. They are never counted as passing, but nothing in a session can
confirm them either.

**LLM-judged evaluations do not run in CI.** 23 of 68 cases require a model run
and are reported as pending. That is honest, and it is still a coverage gap.

**Secret detection is heuristic.** `policies/secret-patterns.json` catches common
shapes. A high-entropy string with no recognisable prefix passes. Use a dedicated
scanner in CI as well.

**The audit log is local and not tamper-evident.** It is evidence for the
engineer who ran the session. The organizational trail is GitLab.

**"The author must not approve" is a setting plus discipline on GitLab CE**, not
an enforced rule. Enforcement needs Premium approval rules.

**The guards require `python3` on `PATH`.** Without it they fail to start and
calls proceed — fail-open, by design, but worth knowing.

**Windows is untested**, and one thing is known to differ rather than merely
untried: `fcntl` is absent, so concurrent claims are not serialised. See above.

**What ran is only as observable as the payload allows.** `execution.actual` is
recorded from `SubagentStart`, which carries an agent id and an agent type and
nothing else. Where agent teams are enabled that does not distinguish a teammate
from a subagent, so the task records `actual_undetermined` rather than a mode.
`TeammateIdle` carries a teammate name and no agent id, so a teammate is matched
to a task lease by name and only an unambiguous single match is acted on.
`WorktreeCreate` and `WorktreeRemove` carry no task at all, so they are recorded
as evidence that isolation happened during a change and never bound to a task.

**The resolver records and does not compel.** A `PreToolUse` hook can refuse a
spawn and cannot rewrite one, so a resolved execution mode is a decision with
evidence, not a mechanically enforced one. The divergence is recorded when it
happens, which is the most the platform allows.

**Concurrent claims are serialised only where `fcntl` exists.** Two agents
spawning at once are two processes reading and writing one graph, and
`scripts/lib/workitem.py` serialises that with `fcntl.flock`. Where the import
fails the lock is a no-op and the work proceeds unserialised, because a lease
that blocks a spawn is worse than one that occasionally races -- but that is a
real behavioural difference between platforms, not a detail. On a host without
`fcntl`, run one agent at a time or set the concurrency limits to 1. Windows is
untested.

**Write scoping through the shell is best-effort, not airtight.** `guard_write`
covers `Write`, `Edit` and `NotebookEdit` and denies an out-of-scope path
outright. Shell writes are a second route, and for ten versions they were not
scoped at all: `sed -i` reached any path, while four documents called the scoping
mechanical. `WS-SHELL` now applies the same write scope to the obvious shell
forms -- redirection, `tee`, `sed -i`, `cp`, `mv`, `install`, `truncate`,
`dd of=` -- and escalates rather than denying, because the path is inferred from
a regex over a shell command. A command that constructs its target, writes from a
here-doc into a variable path, or goes through an interpreter will not be caught.
Withholding `Bash` is the only complete answer, and six of the seven reviewers
need it to read diffs.

**Cycle acceptance is re-checked, but not entirely determinable.** Every cycle
declares `determined_by: scripts/check_dod.py`, and until v0.22 that determiner
was never consulted: acceptance was whatever the lead wrote into the rollup.
`cycle_accepted` now re-evaluates the cycle's own conditions and refuses to
accept over any it can see is false, and it reads `rollup.streams` so a cycle
cannot be declared accepted with work still in `CHANGES_REQUESTED`. What remains:
a condition needing evidence from outside the repository — a pipeline result — is
still the head's word. The predicate says so in its own output rather than
counting it as satisfied.

**A task lease expires after an hour; it is not a liveness signal.** An agent that
crashes never releases its task, and a leased task is skipped, so one dead session
would strand everything behind it. The lease now expires and `next` names whoever
is holding a task. An hour is a compromise: shorter risks handing a live agent's
task to a second one, longer leaves the graph stuck. Nothing observes the agent
itself.

**Agent counts are a judgement.** 30 agents is an argued optimum, not a proven
one. Some boundaries will turn out wrong, and `docs/organization.md` records
which roles were deliberately not created so the argument can be reopened.

## What would justify a control plane

Not "it would be nice". Specifically:

1. **Durable approval state** — an approval that survives a session and binds a
   later action. GitLab holds this for merges; it does not for in-session
   operations.
2. **Cross-session assignment** — work handed from one engineer's session to
   another's, with state. Today that is a merge request and a conversation.
3. **An authoritative audit trail** — tamper-evident, organization-wide,
   queryable. GitLab covers the merge path; it does not cover in-session actions.
4. **Fleet-wide policy distribution with attestation** — knowing which version of
   the OS each engineer is actually running.

Until several of these bite in practice, a control plane would compete with
GitLab and lose. The limits are recorded here so the decision is revisited with
evidence rather than enthusiasm.

## Roadmap

**V1 (this release)** — organization, lifecycle, guards, policies, evaluations,
project configuration, GitLab CI, documentation.

**V1.1** — LLM-judged evaluations wired into a reviewed cadence; more adversarial
cases from real use; per-project skill extension pattern; a worked example per
project archetype.

**V2** — a GitLab MCP server, CE-compatible and read-mostly; observability MCP
for the SRE roles; richer traceability tooling over the file conventions; agent
promotion beyond `pilot` based on accumulated evidence.

**Future control plane** — only against the four criteria above.

**Future headless execution** — requires an approval model that works without a
human present, which is a policy problem before it is a technical one.
