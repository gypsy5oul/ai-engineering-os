# Troubleshooting

## The plugin does not load

Check the structure first. `agents/`, `skills/` and `hooks/` belong at the plugin
root; only `plugin.json` goes inside `.claude-plugin/`.

```bash
claude plugin validate .
python3 scripts/validate_plugin.py
```

Then `/plugin` and open the **Errors** tab. After editing anything other than a
`SKILL.md`, run `/reload-plugins`.

## A skill does not appear

Plugin skills are namespaced: `/ai-engineering-os:change-review`, not
`/code-review` — the bare name would collide with the bundled skill.

The install summary can report `0 skills` because that count covers only
`commands/` directories. It is not evidence that the skills failed to load; check
`/help` under custom commands, or `claude plugin details ai-engineering-os`.

## A hook does not fire

1. `python3 --version`. The guards need `python3` on `PATH`; without it they fail
   to start and the call proceeds.
2. `/hooks` shows what is registered.
3. `claude --debug` records which hooks matched and how they exited.
4. Test the guard directly:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | python3 hooks/scripts/guard_bash.py
```

Silence means "no decision", which is correct for anything the guard does not
object to. The guards never emit `allow`.

## A guard blocks something legitimate

This is a defect in the rule, not in your work. Do not route around it.

1. Read the message: it names the rule id and what to do instead.
2. If the alternative is genuinely wrong for your case, fix the rule in
   `policies/hook-policy.json` and add a false-positive test.
3. If it is a project-specific need, add a waiver in
   `.ai-engineering/security.json` with a justification and an expiry. A waiver
   missing either is ignored and reported.

Using `--no-verify` or `--dangerously-skip-permissions` is itself blocked, and
that is deliberate.

## "Role X may not spawn Y"

The spawn hierarchy is in `policies/agent-registry.json` under `may_spawn`. The
denial message names the escalation target. If the boundary is wrong, that is an
organizational design change: `agent-architect` proposes, governance approves.

## "Role X may write only to..."

Write scopes are in `policies/write-scope.json`. Getting this on legitimate work
usually means the work belongs to a different role. If the scope really is wrong,
widening it is a governance change (AP-10) — `EVAL-AIG-004` exists because
"widen my own scope to unblock myself" is exactly the request that must not
succeed.

## Agents behave inconsistently across sessions

Check what actually loaded: `/context` lists custom agents, and
`claude plugin details ai-engineering-os` lists the component inventory.

Project and user `.claude/agents/` definitions override same-named plugin agents.
If someone has a local `code-reviewer.md`, that is what runs.

## Teammates are not appearing

Agent teams are experimental and off by default. Set
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Interactivity is not the constraint it
was once read as: at 2.1.241 `-p` carries a full teammate lifecycle, and
`--teammate-mode in-process` needs no TTY. See `docs/agent-teams.md`.

A teammate row that vanished has been hidden after going idle, not stopped.

## A teammate ignores its skills

Expected. Claude Code does not apply the `skills` frontmatter field to teammates.
Name the skills in the spawn prompt.

## The project configuration will not validate

```bash
python3 scripts/validate_project_config.py
```

The common errors are semantic rather than structural:

| Error | Meaning |
| --- | --- |
| production environment with `deployment_approval: none` | Production deployment is AP-01 |
| confidential data with no `secret_management` | State where secrets live |
| `test_data: production-copy` with regulated data | Regulated data moved into test environments |
| `author_may_approve: true` | Removes the only independent check on the merge |
| blocking open decision with no owner | Nobody can close it |

## Evaluations report "requires a model run"

Correct behaviour. LLM-judged cases are never auto-passed. Produce the bundle
with `--emit-llm-bundle`, score it, and feed it back with `--llm-results`.

## Agents ask for approval too often

That is a defect in `policies/approval-policy.json`, and it should be fixed
rather than tolerated: a gate that fires on routine work trains people to approve
without reading. Check the audit log for which decisions dominate, and raise it
as a governance finding.

## Something in this repository disagrees with itself

```bash
python3 scripts/validate_plugin.py
python3 -m unittest discover -s tests
```

Between them they check registry/file agreement, tool profiles, model floors,
write scopes, review routing, workflow owners, evaluation coverage and catalogue
completeness. If both pass and something is still inconsistent, that is a missing
check — add it.
