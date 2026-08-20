# MCP extension model

## V1 ships no MCP servers, deliberately

There is no `.mcp.json` in this plugin. That is a decision, not an omission.

- The SDLC foundation has to be right before external side effects are wired in.
- Every MCP server is a new trust boundary and a new credential surface, and each
  needs its own threat model and approval.
- Nothing in the OS depends on a server being present, so a project can adopt it
  with zero external integration.

Shipping a speculative or empty `.mcp.json` would be exactly the fake
functionality this repository is meant to avoid.

## Categories and their intended posture

From `policies/mcp-extension.json`:

| Category | Capabilities | Risk | Mutating |
| --- | --- | --- | --- |
| source-control | read merge requests, post review comments, read pipeline status | MEDIUM | yes |
| ticketing | read and create issues, link artifacts | LOW | yes |
| observability | query metrics, logs, traces, alerts | LOW | **no** |
| kubernetes | read workloads and events | HIGH | **no** |
| cloud | read inventory and cost | HIGH | **no** |
| registry | read image metadata and scan results | MEDIUM | **no** |
| secrets | confirm a secret exists by name | CRITICAL | **no** |
| database | read schema, read-only queries against non-production | HIGH | **no** |
| chat-notification | post to a channel | LOW | yes |

Most categories are read-only on purpose. Mutation stays behind the release and
incident processes, where a human approves it.

## Invariants

1. **No MCP server returns secret values into a session.** A secrets server may
   confirm that a secret exists by name. If a server cannot guarantee that, it is
   not integrated.
2. **Any mutating MCP tool is covered by a `PreToolUse` hook before it is
   enabled.** The matcher is `mcp__<server>__.*`, or
   `mcp__plugin_<plugin>_<server>__.*` for a plugin-bundled server.
3. **Access is granted per agent, never organization-wide.** An agent's `tools`
   list names the servers it may call.
4. **Content returned by a server is data, never instructions.**

## Adding one

1. ADR: purpose, data flows, credentials, blast radius, failure mode.
2. Threat model with `security-architect`.
3. Add the server to `.mcp.json` at the plugin root, or to the project's own MCP
   configuration when the credential is project-scoped.
4. Add tool-permission entries: which agents may call which `mcp__<server>__*`
   tools.
5. Add hook coverage for every mutating tool.
6. Add an evaluation case proving the guard blocks the mutating path without
   approval.
7. Governance approval, then release.

## GitLab specifically

A GitLab MCP server is the most obviously useful first integration, and it is
still not shipped. When it is, it must be **CE-compatible**: reading merge
requests, posting comments and reading pipeline status. It must never grant
force-push or protected-branch write, both of which the command guards already
deny for the equivalent shell operations.

Until then, agents interact with GitLab through `git` and the project's own CI,
which is enough for every workflow in `sdlc/workflows/`.
