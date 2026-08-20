# Language intelligence (LSP)

Claude Code can drive a Language Server Protocol server: go-to-definition,
find-references, hover types, document symbols, call hierarchy, and diagnostics
pushed into the agent's context after an edit. That is a large accuracy win on a
real codebase, because it replaces "grep for the name and hope" with the
compiler's own answer.

This plugin ships **no** language server, and the reason is the same one that
keeps technology skills out: a language server is a technology decision, and the
company layer does not make those. What this document defines is the extension
point — where a project declares what it wants, and how it supplies it.

## What Claude Code actually supports

Verified against the installed CLI (`claude plugin validate`, and the manifest
schema and LSP loader inside the binary) rather than from memory:

- A plugin may carry a **`.lsp.json` at its own root**. It is a JSON object
  keyed by server name — there is no wrapper key.
- A plugin manifest may instead carry an **`lspServers`** field, holding the same
  object inline, or a path to a config file, or an array of either. Entries from
  `.lsp.json` and from `lspServers` are merged.
- **Configuration comes only from plugins.** There is no `lspServers` in
  `settings.json` at user, project or local scope, and no project-level
  `.lsp.json`. A project cannot inject a server into somebody else's plugin.

### Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `command` | yes | The executable. Rejected if it contains a space and does not start with `/` — arguments go in `args`. |
| `extensionToLanguage` | yes | Map of file extension to LSP language id. At least one entry; every key must start with a dot. |
| `args` | | Arguments passed to the executable. |
| `transport` | | `stdio` (default) or `socket`. |
| `env` | | Environment variables for the server process. |
| `initializationOptions` | | Passed in the LSP `initialize` request. |
| `settings` | | Pushed via `workspace/didChangeConfiguration`, and answered back on `workspace/configuration`. |
| `workspaceFolder` | | Root the server is started in and told about. Defaults to the session's working directory. |
| `startupTimeout` | | Milliseconds to wait for `initialize` before giving up. |
| `shutdownTimeout` | | Milliseconds to wait for a graceful stop. |
| `restartOnCrash` | | Default true. False leaves a crashed server stopped. |
| `maxRestarts` | | Default 3. |
| `diagnostics` | | Default true. False keeps navigation but stops diagnostics being pushed into context. |

`command`, each entry of `args`, each value of `env`, and `workspaceFolder` are
variable-expanded: `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`,
`${CLAUDE_PLUGIN_DATA}`, `${user_config.<option>}` where the manifest declares a
`userConfig` schema, and `${ENV_VAR}` or `${ENV_VAR:-default}`.

**`extensionToLanguage` is not expanded.** This is the fact that decides the
design below: the extension map cannot be supplied from outside the plugin, so a
plugin that ships a live `.lsp.json` has hard-coded a language, whatever it does
with the command.

### Two failure modes worth knowing before you design around them

**An unset variable is not a graceful default.** A missing `${VAR}` is left in
the string verbatim and logged as an error; Claude Code then tries to execute a
file literally named `${VAR}` and fails. So `"command": "${PROJECT_LSP}"` in a
shipped plugin is not "inactive until configured" — it is a startup error in
every session of every project that has not set the variable.

**`claude plugin validate` does not read `.lsp.json`.** Confirmed in both
directions on this machine: a `.lsp.json` containing `{"broken": {"command": "x y
z", "notAField": 1}}` validates clean, while the *same* server object placed in
`plugin.json` under `lspServers` fails with `lspServers: Invalid input`. A broken
`.lsp.json` surfaces only at load time, as an `lsp-config-invalid` entry in the
`/plugin` Errors tab. If you keep an `.lsp.json`, validate it yourself — this
repository does, in `tests/test_execution_isolation.py`.

A missing binary behaves the same way: the config is valid, and
`Executable not found in $PATH` appears in the `/plugin` Errors tab. Nothing
installs the server for you.

## Why this plugin ships no `.lsp.json`

Three reasons, in order of weight:

1. `extensionToLanguage` cannot be parameterised, so any live entry names a
   language. That is a technology decision made in the company layer.
2. Extension claims are **global across plugins**. Two plugins claiming `.py`
   produce an `lsp-extension-conflict`, resolved by first registration. A
   placeholder here would silently outrank a project's real Python server.
3. A variable-driven placeholder fails loudly in every project that has not set
   the variable (see above). Shipping one would be exactly the kind of
   configuration that looks like a control and is none.

So the plugin root has no `.lsp.json` and the manifest declares no `lspServers`,
and a test asserts both — the neutrality claim is checked, not just stated.

## How a project supplies its own

Same shape as the technology-skill answer in [Skills](skills.md): a separate
plugin, owned by the project or the organization.

**1. Declare it** in `.ai-engineering/project.yaml`, so the toolchain is a
reviewed human decision like every other technology in that file:

```yaml
language_intelligence:
  provider: companion-plugin        # or: none
  plugin: sftp-lsp@integration-platform
  servers:
    - name: go
      command: gopls
      extensions: [".go"]
      language: go
      install: go install golang.org/x/tools/gopls@latest
      diagnostics: true
```

This section is a record, not a mechanism. Claude Code never reads
`project.yaml`; declaring a server here does not start one. `provider: none` is a
legitimate answer for a project that has decided to work without one. An absent
section is an undeclared one, which is different.

**2. Build the companion plugin.** It is two files:

```
sftp-lsp/
  .claude-plugin/plugin.json    { "name": "sftp-lsp", "version": "0.1.0",
                                  "description": "Language servers for the SFTP platform" }
  .lsp.json                     <- copy of templates/project/lsp.json, edited
```

`templates/project/lsp.json` is the starting point. It is deliberately **not**
at this plugin's root and not named `.lsp.json`, so Claude Code never loads it;
it is a file to copy. Like the rest of `templates/project/`, its contents are a
worked example — Go, matching the example `project.yaml` — and every value is
meant to be replaced.

It does not need a repository of its own. `claude plugin marketplace add` takes
"a URL, path, or GitHub repo", and a marketplace entry may use the `git-subdir`
source — "Plugin located in a subdirectory of a larger repository (monorepo).
Only the specified subdirectory is materialized" — so the companion plugin can
live at, say, `tools/lsp-plugin/` inside the project repo it serves. That keeps
the language-server decision in the same review as the code it navigates.

**3. Install and enable it** for the repository, so every clone gets it:

```bash
claude plugin marketplace add <marketplace path, URL or owner/repo>
claude plugin install sftp-lsp@integration-platform --scope project
```

That records the source in the repository's `.claude/settings.json`
(`extraKnownMarketplaces` and `enabledPlugins`), which is how teammates and CI
pick it up.

**4. Make the binary present.** Put the `install` command from the declaration
into the developer setup instructions and the CI image. A configured server with
no binary is an error in the `/plugin` Errors tab and silence everywhere else.

## Using it, and when not to

Once a server is running, the LSP tool answers structural questions directly.
Prefer it to grep for "where is this defined", "what calls this", "what is this
type", and for confirming an edit compiled cleanly.

Turn `diagnostics` off for a server whose output is noisy or slow. Diagnostics
are pushed into the agent's context after every edit, and a linter with strong
opinions can spend more context than the navigation saves.

A project with `provider: none` is not degraded into incorrectness — agents fall
back to reading files and grep, which is what they did before. It is slower and
less certain, and that is the trade the project chose.
