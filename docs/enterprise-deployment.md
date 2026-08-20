# Enterprise deployment

Installing the plugin makes the organization **available**. Making it
**non-bypassable** is a separate act, and it happens in managed settings — not in
the plugin, which by design cannot enforce anything about its own presence.

> Verify every key here against
> [the settings reference](https://code.claude.com/docs/en/settings) and
> [managed settings](https://code.claude.com/docs/en/server-managed-settings)
> before relying on it. These are platform controls that change independently of
> this plugin.

## The bypass this closes

Without managed settings, everything the plugin enforces can be undone locally:

| Bypass | Effect |
| --- | --- |
| `.claude/agents/code-reviewer.md` in a project | Shadows the plugin's reviewer. Project and user agents override same-named plugin agents. |
| A project hook in `.claude/settings.json` | Runs alongside the guards; a permissive rule can undo a denial's usefulness |
| `claude --plugin-dir ./my-copy` | Loads a modified copy of the plugin for that session |
| `claude --agents '{...}'` | Defines agents inline, ignoring the registry entirely |
| Not installing the plugin at all | The organization simply is not there |

None of these are attacks. They are the platform working as designed, for a
single engineer customising their own environment. In an enterprise, they mean
the controls are advisory.

## What to set

`templates/enterprise/managed-settings.json` is a starting point.

| Key | Why |
| --- | --- |
| `strictPluginOnlyCustomization` | Skills, agents, hooks and MCP servers may come only from plugins or managed settings. Closes the first two rows above. |
| `disableSideloadFlags` | Rejects `--plugin-dir`, `--plugin-url`, `--agents`, `--mcp-config`. Closes rows three and four. |
| `extraKnownMarketplaces` | Registers the marketplace centrally, so the name cannot be claimed by another source. |
| `enabledPlugins` | Rolls the plugin out rather than asking each engineer to install it. Closes row five. |
| `permissions.deny` | Structural credential denies. Stronger than the command guards: they stop the `Read` and `Write` tools directly, where a regex only sees shell strings. |

Deny is evaluated before ask and before allow, and **a deny rule cannot carry
allowlist exceptions** — a broad `Bash(aws *)` deny blocks a narrower
`Bash(aws s3 ls)` allow. Scope denies precisely.

## The pattern the platform recommends, and that this plugin relies on

> To run all Bash commands without prompts except for a few you want blocked,
> add `Bash` to your allow list and register a `PreToolUse` hook that rejects
> those specific commands.

That is exactly this plugin's design: `hooks/scripts/guard_bash.py` rejects a
named set and stays silent otherwise. Two consequences worth knowing:

- A **hook returning `allow` does not bypass a deny or ask rule.** The plugin's
  guards never return `allow`, so this does not arise — but it is why they never
  should.
- A **hook exiting with code 2 blocks before permission rules are evaluated**,
  so it overrides even an allow rule. The guards use the JSON
  `permissionDecision` form instead, which is the documented interface for a
  reasoned denial with a remediation message.

## Model availability changes what the policy can do

If `availableModels` excludes `opus`, Claude Code substitutes downward. Every
HIGH and CRITICAL role in `policies/agent-registry.json` then runs below the
floor in `policies/risk-classification.json`, and
`scripts/resolve_model.py --all` will still report `opus` because it resolves
policy, not availability.

**Check the allowlist against the floors before restricting models.** This is a
silent failure: nothing errors, the roles just get weaker.

## Agent teams

Experimental and disabled by default. The plugin works without them: four stages
declare a team, each with a `degraded_mode` stating what is lost. Set
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` deliberately, at the organization level,
after reading [`docs/execution.md`](execution.md) — one stage is
`TEAM_REQUIRED` and escalates rather than silently falling back.

## Rollout

1. Fork or mirror this repository into your GitLab.
2. Replace the placeholder URL in `.claude-plugin/marketplace.json`.
   `scripts/validate_plugin.py` warns while it still says `example.com`.
3. Name the humans in `GOVERNANCE.md`. An unnamed governance role is an
   ungoverned one, and several approval categories cannot be satisfied without
   one.
4. Tag a release. `claude plugin tag` produces `{plugin-name}--v{version}` —
   `ai-engineering-os--v0.7.0`, not `v0.7.0` — and the marketplace `ref` must
   name that exact tag.
5. Deploy managed settings.
6. Onboard one project with `/ai-engineering-os:project-onboarding` before
   rolling out widely. The first onboarding surfaces which decisions your
   organization has not actually made.

## What managed settings still cannot give you

- **Attestation.** Nothing reports which version of the OS each engineer is
  actually running. `claude plugin list --json` answers it per machine, not
  fleet-wide.
- **An organizational audit trail.** The plugin's audit log is local and not
  tamper-evident. GitLab is the trail.
- **Enforcement of behavioural rules.** "Never invent an availability target" is
  a contract tested by evaluation, not a control. See
  [`docs/limitations.md`](limitations.md).
