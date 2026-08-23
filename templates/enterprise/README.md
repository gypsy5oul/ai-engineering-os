# Managed settings, key by key

`managed-settings.json` in this directory is a deployable profile: valid JSON,
no comment keys, nothing in it that was not verified against a real Claude Code
build. Copy it, replace the two placeholder URLs and the trust message, deploy
it, and read [what it does not prevent](#what-this-profile-does-not-prevent)
before you tell anyone it is enforced.

Comment keys are deliberately absent. A local `managed-settings.json` silently
drops keys it does not recognise, but the same document delivered through
server-managed settings is rejected with `unknown settings key`, so a `_comment`
key is a file that works until the day you centralise it.

## Where it goes

| Platform | Path |
| --- | --- |
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Linux | `/etc/claude-code/managed-settings.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-settings.json`, or the `Settings` value under `HKLM\SOFTWARE\Policies\ClaudeCode` |

A `managed-settings.d/` directory beside that file is also read, which is how a
device-management tool can drop in fragments without owning the whole document.

Settings sources are applied in the order
`userSettings → projectSettings → localSettings → flagSettings → policySettings`.
Managed settings are `policySettings`: last, so nothing below can override them.

## Every key in the profile

### `strictPluginOnlyCustomization: ["skills", "agents", "hooks", "mcp"]`

Blocks those four surfaces from non-plugin sources: `~/.claude/{surface}/`,
`.claude/{surface}/` in a project, `hooks` in any `settings.json`, and
`.mcp.json`. It does **not** block managed settings or plugin-provided
customizations — which is exactly why this plugin keeps working under it while
a hand-written `.claude/agents/code-reviewer.md` stops shadowing its reviewer.

The four values are the only ones recognised; unknown entries are silently
ignored for forwards compatibility. `true` locks all four. An invalid value is
rescued to "unset", so a typo here fails open — check the file after editing.

### `allowManagedHooksOnly: true`

User, project and local `settings.json` hooks stop running. Plugin hooks are
filtered too, and this is the part worth understanding before deploying: a
plugin's hooks survive only if that plugin appears as `"<plugin>@<marketplace>": true`
in the **managed** `enabledPlugins`. That is why `enabledPlugins` below is not
merely a convenience — under `allowManagedHooksOnly` it is what keeps
`hooks/guard_bash.py` and the rest of the guards alive. Enable the plugin only
in project settings and this key silently disarms it.

It also disables command-sourced plugins by implication: `disableCommandPluginSources`
follows `allowManagedHooksOnly` when it is not set explicitly.

### `disableSideloadFlags: true`

Rejects `--plugin-dir`, `--plugin-url`, `--agents` and (non-SDK) `--mcp-config`
at startup. Without it, every line above is a one-flag bypass for a single run.
Honored only from managed settings.

It does not gate other MCP entry points — the SDK's `setMcpServers`,
`claude mcp add`, and `.mcp.json` are unaffected. Use `allowedMcpServers` /
`deniedMcpServers` for those.

### `strictKnownMarketplaces` and `extraKnownMarketplaces`

These do different jobs and the profile needs both.

- `strictKnownMarketplaces` is the **gate**: when set in managed settings, only
  these sources may be added as marketplaces at all. The check runs before
  download, so a blocked source never reaches the filesystem. It registers
  nothing.
- `extraKnownMarketplaces` is the **registration**: it makes the marketplace
  available on the machine so nobody has to add it by hand.

The `source` values are a tagged union. `"source": "url"` means a direct URL to
a `marketplace.json` file; a clone URL ending in `.git` needs `"source": "git"`,
which is what the profile uses. Getting this wrong produces a marketplace that
never resolves rather than an error at deploy time.

`ref` pins the marketplace to one tag. `claude plugin tag` produces
`{plugin-name}--v{version}` — `ai-engineering-os--v0.17.0`, not `v0.17.0`.

### `enabledPlugins`

An object keyed by `plugin@marketplace`, not an array:

```json
{ "enabledPlugins": { "ai-engineering-os@ai-engineering": true } }
```

Rolls the plugin out rather than asking each engineer to install it, and — see
`allowManagedHooksOnly` above — is what admits the plugin's hooks under a
managed-hooks-only policy.

### `pluginTrustMessage`

Appended to the trust warning shown before a plugin is installed. Managed
settings only. Replace the placeholder with something true about your review
process, or drop the key.

### `permissions.deny`

Structural credential denies. Stronger than the plugin's command guards, because
they stop the `Read` and `Edit` tools directly where a regex only sees a shell
string.

Two syntax points that are easy to get wrong:

- A leading `//` marks an absolute path — `Read(//**/.ssh/**)`, `Edit(//etc/*)`.
  Without it the pattern is relative to the workspace.
- File permission checks only recognise `Read(...)` and `Edit(...)`. A
  `Write(...)`, `MultiEdit(...)` or `NotebookEdit(...)` rule matches nothing;
  `Edit(...)` already covers every file-editing tool, and `Read(...)` covers
  `Glob`. The CLI warns about this, and the profile therefore uses `Edit`, not
  `Write`.

Deny is evaluated before ask and before allow, and a deny rule cannot carry
allowlist exceptions: a broad `Bash(aws *)` deny blocks a narrower
`Bash(aws s3 ls)` allow. Scope denies precisely.

### `permissions.disableBypassPermissionsMode: "disable"`

The literal string `"disable"`, not `true` — it is an enum with one value, and
a boolean is dropped. Stops `--dangerously-skip-permissions` and the
`bypassPermissions` mode. `permissions.disableAutoMode: "disable"` does the same
for auto mode if you want it.

### `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`

Agent teams are experimental and off by default. Set it deliberately: the plugin
works without them, and one stage is `TEAM_REQUIRED` and escalates rather than
silently degrading. See [`docs/execution.md`](../../docs/execution.md).

## Worth adding, deliberately not in the profile

| Key | Why it is not in the default file |
| --- | --- |
| `forceLoginMethod`, `forceLoginOrgUUID` | The right control for "only our org's accounts", but a placeholder UUID locks out everyone who applies the file unedited. `forceLoginMethod` is `"claudeai"`, `"console"` or `"gateway"`; `forceLoginOrgUUID` is one UUID string or an array of them. Add both, with your real UUID, before rollout. |
| `forceRemoteSettingsRefresh` | Blocks startup until remote managed settings are freshly fetched, and **exits if the fetch fails**. Fail-closed is the point; it also means an outage in your settings endpoint stops all work. Turn it on only once that endpoint has an availability target you are willing to state. |
| `allowManagedPermissionRulesOnly` | Ignores every `allow`/`deny`/`ask` rule from user, project, local and CLI sources. It also nullifies the per-project allow list in `templates/project/settings.json`, so the ordinary read-only commands start prompting again and the guards' escalations stop standing out. Adopt it only with a managed allow list to replace them. |
| `availableModels`, `enforceAvailableModels` | Restricting models changes what the plugin's model policy resolves to. See the warning in [`docs/enterprise-deployment.md`](../../docs/enterprise-deployment.md). |
| `allowedMcpServers`, `deniedMcpServers`, `allowManagedMcpServersOnly` | The right controls if MCP servers are in scope. Entries are objects with exactly one of `serverName`, `serverCommand` or `serverUrl`. Deny beats allow. |
| `blockedMarketplaces` | A blocklist is the wrong shape when `strictKnownMarketplaces` already gives you an allowlist. Useful alongside it for `{"source": "skills-dir"}`, which turns off the `~/.claude/skills/` auto-load. |
| `disableAllHooks`, `disableSkillShellExecution` | Both would break this plugin. `disableAllHooks` removes the guards. `disableSkillShellExecution` replaces inline shell in skills and slash commands with a placeholder — including **plugin** skills, not only user and project ones. |

## What this profile does not prevent

- **Not installing Claude Code from somewhere else.** Managed settings bind the
  installed CLI. A second copy under a user's home directory reads the same
  managed path on that machine, but a different machine with no managed file has
  no policy at all. Device management, not this file, is what makes coverage
  real.
- **Editing `CLAUDE.md`.** Project and user memory are not a customization
  surface `strictPluginOnlyCustomization` covers. Instructions can still be added
  locally.
- **Anything about model behaviour.** "Never invent an availability target" is a
  contract tested by evaluation, not a control. See
  [`docs/limitations.md`](../../docs/limitations.md).
- **Attestation.** Nothing here reports which version of the OS each engineer is
  running. `claude plugin list --json` answers it per machine, not fleet-wide.
- **A tamper-evident audit trail.** The plugin's event log is local and
  append-only by convention. GitLab is the trail.

## How these were verified

Every key above was checked against the settings schema embedded in the
installed Claude Code binary at `2.1.237` — its declared type, its accepted
values, and the code that reads it — and cross-checked against
[the settings reference](https://code.claude.com/docs/en/settings) and
[managed settings](https://code.claude.com/docs/en/server-managed-settings).
`policies/platform-capabilities.json` has since moved to `2.1.241`, and the keys
here have not been re-checked against it. The capability model and this settings
list are therefore at different versions, which is worth knowing before relying
on either: a key that was accepted at 2.1.237 is not thereby accepted now.

Do the same before adding a key: these are platform controls that change
independently of this plugin, and a setting that is merely plausible is a
control that does nothing.
