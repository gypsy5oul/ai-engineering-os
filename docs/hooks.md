# Hooks

Hooks are the only part of this system that holds regardless of what the model
decides. Everything else is a contract the model follows; a hook is a rule the
model cannot argue with.

## What is registered

`hooks/hooks.json`:

| Event | Matcher | Script | Purpose |
| --- | --- | --- | --- |
| `PreToolUse` | `Bash` | `guard_bash.py` | Destructive, production, secret and protected-branch commands |
| `PreToolUse` | `Write\|Edit\|NotebookEdit` | `guard_write.py` | Forbidden paths, role write scope, secret content |
| `PreToolUse` | `Agent` | `guard_spawn.py` | Organizational spawn hierarchy |
| `PostToolUse` | `Write\|Edit\|NotebookEdit` | `audit_log.py` | Records what actually changed |
| `SubagentStart` | — | `inject_context.py` | Briefs the agent on the one task claimed against its `agent_id`, so the role definition does not have to carry the project's context |
| `Stop` | — | `check_artifacts.py` | Artifacts written this session parse and validate |
| `SubagentStop` | — | `observe_subagent.py` | Records what the agent produced against its task, from `last_assistant_message`, rather than trusting the agent to report it |
| `SubagentStop` | — | `check_artifacts.py` | The same check when a delegated task ends |
| `TaskCompleted` | — | `gate_task_completion.py` | Exit 2 blocks a task closing while its definition of done is unmet |
| `TeammateIdle` | — | `teammate_idle.py` | Refuses idle while the teammate still holds an unaccepted task, when the name matches exactly one lease |
| `WorktreeCreate` / `WorktreeRemove` | — | `record_worktree.py` | Records that isolation happened during this change; the payload names no task, so it is not bound to one |
| `SessionStart` | `startup\|resume\|clear\|compact\|fork` | `session_context.py` | Organization presence and project configuration status |

## The one place the lifecycle is enforced

Stage order, definitions of done and the department cycles are followed because
the model reads them and chooses to. `docs/limitations.md` says so plainly. The
`Stop` and `SubagentStop` hooks are the exception, and they were chosen for the
one part of the contract that needs **no session state to check**.

An artifact header either satisfies `schemas/artifact-header.schema.json` or it
does not. The audit log already records which files a session wrote, so the hook
needs no stage marker, no correlation id, and nothing the model has to maintain
truthfully about itself. If a session wrote an artifact that will not parse, it
is held open with the specific faults, because an artifact no predicate can read
is work that does not count.

Two deliberate limits:

- **It blocks on a structural fact, never on judgement.** A hook that argued
  about whether work was good would be a hook sessions learn to fight.
- **It fails open.** `stop_hook_active` is honoured so it cannot loop, and any
  internal error exits silently. This hook adds a check; it is not a safety
  boundary, and a broken check must never trap a session.

## Four decisions

The policy's vocabulary is not the wire protocol. Claude Code's `PreToolUse`
schema accepts exactly `allow`, `deny`, `ask` and `defer`; anything else is
discarded, **and a discarded decision means the tool call proceeds**. The
organization's `escalate` tier is therefore translated to `ask` in
`hooks/lib/hooklib.py`. `tests/test_repository.py` drives every guard and
asserts that what comes out is a value the platform accepts — the check that
was missing when the guards emitted `escalate` verbatim and every escalate-tier
rule silently allowed the command it described.


| Decision | Effect | Used for |
| --- | --- | --- |
| `deny` | Blocked. Claude is told why and what to do instead. | Operations with no legitimate agent use: `rm -rf /`, reading a private key, exfiltrating a credential, rewriting history, disabling the permission system. |
| `escalate` | Emitted on the wire as `ask`. Claude Code asks the human, even in permissive permission modes. | Operations that are legitimate but need a decision: pushing to a protected branch, `terraform apply`, `DROP TABLE`, editing `.env`. |
| `warn` | Allowed with a message to the operator. | Available in the policy; currently unused. |
| `audit` | Allowed silently, recorded. | File changes via `PostToolUse`. |

**The guards never emit `allow`.** Emitting `allow` would override the user's own
permission rules, so a guard with a bug could quietly widen permissions rather
than narrow them. When a guard has nothing to say it stays silent and Claude
Code's normal flow applies.

## Three design rules

**1. Fail closed, in tiers.** A blanket fail-open is wrong: the moment a guard
breaks is exactly the moment it is needed. A blanket fail-closed is also wrong: a
guard that cannot evaluate anything blocks every command and gets disabled, after
which it protects nothing. So the failure path itself is tiered, and the top tier
cannot be broken.

| Tier | When | Decision | Mechanism |
| --- | --- | --- | --- |
| **0 Catastrophic** | Always, before the policy engine | **deny** | `hooks/lib/failsafe.py` — pure regex, no file I/O, no policy load. Holds when `hook-policy.json` is missing, unparseable or wrong. |
| **1 High-risk on failure** | Full evaluation failed and the action looks dangerous | **deny** | A blunt screen for production, secret and destructive shapes. Denying costs one report; allowing costs whatever the command does. |
| **2 Unclassified on failure** | Full evaluation failed, action does not match tier 1 | **escalate** | Fail closed to a human, not to a blocked session. |
| **3 Advisory guard** | The guard enforces organizational structure, not a safety boundary | **allow** with a loud notice | `guard_spawn`. Its failure is a defect, not an exposure. |

A corrupt policy file does **not** degrade to "no rules apply". Guards load their
policy with `policy_required()`, which raises rather than returning an empty
document, so a broken rule file triggers the tiered path instead of silently
opening the guard.

Observed behaviour with `hook-policy.json` deliberately corrupted in a sandbox:

```
rm -rf /                                 -> DENY      (tier 0)
kubectl delete deploy api -n production  -> DENY      (tier 0)
terraform destroy                        -> DENY      (tier 1)
psql -c "DROP TABLE users;"              -> DENY      (tier 1)
npm test                                 -> ESCALATE  (tier 2)
```

**Self-test at session start.** `session_context.py` runs three known-dangerous
payloads through the safety guards. If any fails to deny, the session opens with
`SAFETY GUARDS ARE NOT WORKING` and the specific guard named. A safety system
that is silently broken is worse than none, because the team stops thinking about
the risk it was covering.

**2. Every denial says what to do instead.** `validate_plugin.py` fails on a rule
with no `remediation`. A denial with no alternative teaches people to route
around the guard.

**3. Every rule has two tests.** One proving it blocks the dangerous case, one
proving it does **not** block the ordinary case that resembles it. The
false-positive tests are the more important half.

That rule earned its keep during development. Four defects were found by the
false-positive tests rather than by the true-positive ones:

| Rule | Defect | Fix |
| --- | --- | --- |
| SH-01 | Denied `rm -rf /tmp/my-project-cache`, and missed `rm -fr ~` | Target must terminate at the dangerous path; flag order made irrelevant |
| SEC-02 | Fired on `docker run --env`, `cat .env.example` and `printenv PATH` | Only a bare, unfiltered dump matches; SEC-07 added for the exfiltration case |
| PRD-01/02/06 | `myproduct` and `liveness` contain `prod` and `live` | Production markers now respect word boundaries |
| GIT-04 | Case-insensitive matching made `-d` identical to `-D`, catching routine cleanup | Rule made case-sensitive |

Each is now a permanent test.

## The command rules

45 rules in `policies/hook-policy.json`, by category:

| Category | Rules | Behaviour |
| --- | --- | --- |
| Destructive filesystem | SH-01…SH-05 | Recursive deletes of root/home/wildcard, block devices, `mkfs`, world-writable permissions, filesystem-wide deletes |
| Supply chain | SH-06, SH-07, SH-08 | Piping a download into a shell; executing the output of a download through command substitution or process substitution; downloading to a file and running it |
| Protected branch | GIT-01, GIT-02, GIT-04 | Force push, remote branch deletion, force-deleting an unmerged local branch |
| History rewrite | GIT-03, GIT-06 | `filter-branch`, `reflog delete`, `reset --hard` |
| Untracked file loss | GIT-07 | `git clean`, which deletes files git never showed you |
| Review bypass | GIT-05 | `--no-verify` |
| Secret access | SEC-01, SEC-02, SEC-04, SEC-05 | Credential stores, environment dumps, secret values, live tokens. SEC-01 covers any reader, not a fixed few, and absolute as well as `~` paths |
| Secret exfiltration | SEC-03, SEC-06, SEC-07, SEC-09, SEC-10 | Sending or committing credential material; piping the environment to a network command; redirecting a secret file into a network command; embedding one in a URL through command substitution |
| Production access | PRD-01, PRD-06 | Production contexts, hosts and cloud profiles |
| Production mutation | PRD-02…PRD-05, PRD-07 | Kubernetes mutation, namespace/PVC/CRD deletion, `terraform apply`/`destroy`, Helm mutation, image promotion |
| Destructive data | DB-01…DB-03 | `DROP`, `TRUNCATE`, unqualified `DELETE`, migration rollback |
| Control tampering | OS-01…OS-05 | Rewriting Claude Code settings, `--dangerously-skip-permissions`, modifying hook scripts, writing to any governed directory through the shell rather than the Write tool, and arbitrary work smuggled into an interpreter one-liner |
| Cloud resource deletion | CLD-01 | Bucket, instance, database, IAM and resource-group deletion across AWS, GCP and Azure |
| Credential rotation | CLD-02, SEC-08 | Creating or rotating access keys and service-account keys; `chmod` on credential material |
| Registry deletion | REG-01 | Deleting container images, which breaks every rollback depending on them |
| Production config and service | PRD-08, PRD-09 | In-place `kubectl edit/patch` on production; stopping or restarting a production service |

Push and commit on a protected branch are not among those rules. Branch
protection is evaluated against the live branch instead: `guard_bash.py` resolves
the current branch and parses the push refspec rather than pattern-matching the
word "main", and reports the escalation under the synthesized ids `GIT-00` and
`GIT-00b`, which exist only in the guard and not in the policy file.

## Regexes are a net, not a wall

`hook-policy.json` carries a `structural_enforcement` section naming the
boundaries that should **not** be enforced by a command regex, because Claude
Code can enforce them structurally:

| Boundary | Structural mechanism | What the regex adds |
| --- | --- | --- |
| Reading credential files | `permissions.deny Read(//**/.ssh/**)` and friends | Only catches shell reads; the deny rule also stops the `Read` tool |
| Writing outside a role's scope | Tool profiles plus `write-scope.json`, denied outright | `WS-SHELL`: the same scope, applied to shell writes (`>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `dd of=`), escalated rather than denied because the path is inferred from the command |
| An agent approving its own work | Reviewers hold no `Write` or `Edit` | Nothing |
| Spawning above one's authority | `Agent(role-a, role-b)` allowlist plus `guard_spawn` | Nothing |
| Production mutation | **Credentials the session does not hold** | Second line only |

The strongest control on production is not a hook: a session without a production
credential cannot mutate production however the command is spelled.
`templates/project/settings.json` ships 16 structural deny rules for the project
to adopt.

Shell remains the one surface where an agent can express an arbitrary action, so
the command guard cannot be removed. It is a net, and the false-positive tests
exist because a net with holes in the wrong places gets taken down.

## Write guard order

1. **Hard deny** — private key material, git internals. No engineering task needs
   an agent to write these.
2. **Escalate** — credential-adjacent files such as `.env`. Editing a local `.env`
   is a legitimate development action, so a human confirms rather than the guard
   refusing.
3. **Escalate** — the control plane: `agents/`, `hooks/`, `policies/`,
   `.ai-engineering/`. This is AP-10.
4. **Role write scope** — allow-mode or deny-mode per `policies/write-scope.json`.
5. **Secret content** — critical patterns deny; weaker signals escalate, with
   obvious placeholders (`${VAR}`, `changeme`, `<REDACTED>`) allowed.

## Project overrides

`.ai-engineering/security.json` in the project. **Additive only:**

- `protected_branches`, `extra_protected_paths`, `extra_deny_patterns`,
  `production_markers` — tighten freely.
- `allow_rule_ids` — a waiver requires both a `justification` and an `expires`
  date. A waiver missing either is ignored and reported in the decision message,
  and every use of a live waiver is written to the audit log.

Loosening is possible, because a policy that cannot be adapted gets bypassed
wholesale. It is never silent.

## Audit log

JSONL under `${CLAUDE_PLUGIN_DATA}/audit/YYYY-MM.jsonl`, falling back to
`~/.claude/ai-engineering-os/audit/`. Records guard decisions, waiver use, file
changes and guard errors. Writing never raises: a failed audit write must not
break a session.

This is local and per-machine. It is evidence for the engineer who ran the
session, not an organizational audit trail — that is GitLab. See
`docs/limitations.md`.

## Changing a rule

1. Edit `policies/hook-policy.json`. Rules are data; the scripts only evaluate.
2. Add both tests to `tests/test_guard_bash.py`.
3. Run `python3 -m unittest discover -s tests` and
   `python3 scripts/run_evaluations.py`.
4. `EVAL-DEV-002` must still pass. If your new rule broke it, your rule is too
   broad.
5. Hook changes are AP-10: governance review plus human approval.

## Requirements and failure modes

The guards need `python3` on `PATH`. If Python is absent the hook fails to start,
Claude Code records the failure, and the tool call proceeds — the same fail-open
posture, for the same reason. Check with `claude --debug` or the `/hooks` browser
if you suspect a guard is not running.
