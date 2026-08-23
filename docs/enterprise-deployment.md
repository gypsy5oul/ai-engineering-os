# Enterprise deployment

Installing the plugin makes the organization **available**. Making it
**non-bypassable** is a separate act, and it happens in managed settings — not in
the plugin, which by design cannot enforce anything about its own presence.

> Every key named here was checked against the settings schema inside the
> installed Claude Code binary and against
> [the settings reference](https://code.claude.com/docs/en/settings) and
> [managed settings](https://code.claude.com/docs/en/server-managed-settings).
> Check again before you add one: these are platform controls that change
> independently of this plugin, and a setting that is merely plausible is a
> control that does nothing.

## The bypass this closes

Without managed settings, everything the plugin enforces can be undone locally:

| Bypass | Effect |
| --- | --- |
| `.claude/agents/code-reviewer.md` in a project | Shadows the plugin's reviewer. Project and user agents override same-named plugin agents. |
| A hook in `.claude/settings.json` | Runs alongside the guards; a permissive rule can undo a denial's usefulness |
| `claude --plugin-dir ./my-copy` | Loads a modified copy of the plugin for that session |
| `claude --agents '{...}'` | Defines agents inline, ignoring the registry entirely |
| `--dangerously-skip-permissions` | Every permission rule stops applying |
| Not installing the plugin at all | The organization simply is not there |

None of these are attacks. They are the platform working as designed, for a
single engineer customising their own environment. In an enterprise, they mean
the controls are advisory.

## The profile

[`templates/enterprise/managed-settings.json`](../templates/enterprise/managed-settings.json)
is a deployable file — valid JSON, no comment keys, nothing in it unverified.
[`templates/enterprise/README.md`](../templates/enterprise/README.md) explains
every key, the syntax traps in each, and the keys deliberately left out.

| Key | Closes | Notes |
| --- | --- | --- |
| `strictPluginOnlyCustomization: ["skills","agents","hooks","mcp"]` | Rows 1–2 | Blocks those surfaces from `~/.claude/`, project `.claude/`, `settings.json` hooks and `.mcp.json`. Plugin-provided and managed sources are **not** blocked, which is why this plugin still works under it. |
| `allowManagedHooksOnly: true` | Row 2, harder | Only managed hooks run — and plugin hooks only for plugins listed in the **managed** `enabledPlugins`. |
| `disableSideloadFlags: true` | Rows 3–4 | Rejects `--plugin-dir`, `--plugin-url`, `--agents`, `--mcp-config` at startup. Managed settings only. |
| `strictKnownMarketplaces` | Supply chain | The allowlist. Only these sources may be added as marketplaces; checked before download. **Registers nothing.** |
| `extraKnownMarketplaces` | Rollout | The registration. Pre-registers the marketplace so nobody adds it by hand. |
| `enabledPlugins` | Row 6 | `{"ai-engineering-os@ai-engineering": true}` — an object keyed by `plugin@marketplace`, not an array. |
| `permissions.deny` | Credential access | Structural. Stops the `Read` and `Edit` tools directly, where a command regex only sees shell strings. |
| `permissions.disableBypassPermissionsMode: "disable"` | Row 5 | The literal string `"disable"`. A boolean here is dropped. |

Two mistakes that look like they work:

- **`extraKnownMarketplaces` is not a gate.** It registers a marketplace; it does
  not stop another from being added. `strictKnownMarketplaces` is the gate, and
  it registers nothing. You need both.
- **`Write(...)` deny rules match nothing.** File permission checks recognise
  `Read(...)` and `Edit(...)` only; `Edit` already covers every file-editing
  tool and `Read` covers `Glob`. A `Write(//**/.ssh/**)` deny reads as
  protection and provides none.

Deny is evaluated before ask and before allow, and **a deny rule cannot carry
allowlist exceptions** — a broad `Bash(aws *)` deny blocks a narrower
`Bash(aws s3 ls)` allow. Scope denies precisely.

## Where the file goes, and what wins

| Platform | Path |
| --- | --- |
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Linux | `/etc/claude-code/managed-settings.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-settings.json`, or `HKLM\SOFTWARE\Policies\ClaudeCode` |

A `managed-settings.d/` directory beside the file is read too, so device
management can drop in fragments rather than owning the document.

Sources apply in the order `user → project → local → CLI flags → managed`.
Managed is last, which is the whole point.

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

Under `allowManagedHooksOnly`, none of that runs unless the managed settings
themselves enable this plugin. Enabling it only in project settings disarms the
guards silently.

## Model availability changes what the policy can do

If `availableModels` excludes `opus`, Claude Code substitutes downward. Every
HIGH and CRITICAL role in `policies/agent-registry.json` then runs below the
floor in `policies/risk-classification.json`, and
`scripts/resolve_model.py --all` will still report `opus` because it resolves
policy, not availability.

**Check the allowlist against the floors before restricting models.** This is a
silent failure: nothing errors, the roles just get weaker. `enforceAvailableModels`
extends the same constraint to the Default selection.

## Identity, and the two keys that lock people out

`forceLoginMethod` (`"claudeai"`, `"console"` or `"gateway"`) and
`forceLoginOrgUUID` (a UUID string, or an array of them) are the right control
for "only accounts in our organization". They are deliberately **absent** from
the template: a placeholder UUID applied unedited locks out everyone on the
device. Add them with your real UUID as a rollout step, not as a copy-paste.

`forceRemoteSettingsRefresh` makes startup fail closed — the CLI blocks until
remote managed settings are freshly fetched and exits if the fetch fails. That
is the correct posture once your settings endpoint has an availability target
you are willing to state, and an outage that stops all engineering work before
that.

## Agent teams

Experimental and disabled by default. The plugin works without them: five stages
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
   `ai-engineering-os--v0.17.0`, not `v0.17.0` — and both the marketplace `ref`
   and the `extraKnownMarketplaces` `ref` must name that exact tag.
5. Replace the two placeholder URLs and the `pluginTrustMessage` in
   `templates/enterprise/managed-settings.json`, add the identity keys, and
   deploy it to the paths above.
6. Verify on one machine before the fleet: `claude plugin list --json` shows the
   plugin, a `.claude/agents/code-reviewer.md` no longer shadows the plugin's
   reviewer, and `claude --plugin-dir .` is refused at startup. A managed
   settings file that parses is not evidence that it applied.
7. Onboard one project with `/ai-engineering-os:project-onboarding` before
   rolling out widely. The first onboarding surfaces which decisions your
   organization has not actually made.

## What managed settings still cannot give you

- **Coverage.** Managed settings bind the CLI on machines that have the file.
  A machine without it has no policy at all. Device management, not this
  document, is what makes coverage real.
- **`CLAUDE.md`.** Project and user memory are not a surface
  `strictPluginOnlyCustomization` covers. Local instructions can still be added.
- **Attestation.** Nothing reports which version of the OS each engineer is
  actually running. `claude plugin list --json` answers it per machine, not
  fleet-wide.
- **An organizational audit trail.** The plugin's event log is local and not
  tamper-evident. GitLab is the trail. What the log *does* give you is
  reconstructable order — see [communications](communications.md).
- **Enforcement of behavioural rules.** "Never invent an availability target" is
  a contract tested by evaluation, not a control. See
  [`docs/limitations.md`](limitations.md).
