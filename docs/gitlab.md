# GitLab

GitLab is the source of truth: for this plugin, and for every project that uses
it. Durable approval, review history and release records live there, not in a
Claude Code session.

## GitLab CE compatibility

**Every core workflow works on GitLab CE.** Paid-tier features are optional
enhancements, never hard dependencies. A project declares its edition in
`.ai-engineering/project.yaml` under `repository.edition`.

| Capability | CE | Paid tier |
| --- | --- | --- |
| Merge requests, approval count | yes | multiple approval rules, enforced code owners (Premium) |
| Protected branches | yes | finer push/merge rules (Premium) |
| CI/CD pipelines | yes | multi-project pipeline visualisation (Premium) |
| Container and package registry | yes | — |
| Issues, milestones | yes | epics, roadmaps (Premium) |
| Dependency and container scanning | run your own scanners in CI | integrated dashboards (Ultimate) |
| SAST / DAST | run your own in CI | vulnerability management (Ultimate) |
| Compliance frameworks, audit events | limited | full (Premium/Ultimate) |

Where the OS depends on a control that Ultimate would provide — "the author must
not approve" — the CE path is a project setting
(`repository.merge_request.author_may_approve: false`, validated as an error if
true) plus human discipline. That is a weaker control than an enforced rule, and
`docs/limitations.md` records it as such.

## Repository structure for this plugin

```
ai-engineering-os/          the plugin, and its own marketplace
├── .claude-plugin/         plugin.json, marketplace.json
├── agents/ skills/ hooks/  Claude Code components
├── policies/ schemas/      governance data
├── sdlc/ evaluations/      lifecycle and evaluation
├── templates/ scripts/ tests/ docs/
└── .gitlab-ci.yml
```

Protected: `main` and `release/*`. Merge requests only.

## Distribution

The repository is both the plugin and a private marketplace.
`.claude-plugin/marketplace.json` points at the repository itself with a `url`
source pinned to a tag.

**Before first use, replace the placeholder URL.** `validate_plugin.py` warns
while it still says `gitlab.example.com`.

```bash
claude plugin marketplace add https://gitlab.example.com/ai-engineering/ai-engineering-os.git
claude plugin install ai-engineering-os@ai-engineering
```

For a private repository, configure a git credential helper. GitLab over HTTPS:

```
https://oauth2:YOUR_TOKEN@gitlab.example.com/ai-engineering/ai-engineering-os
```

An SSH remote with a key in `ssh-agent` also works and, unlike HTTPS, keeps
working for the background marketplace refresh.

If the organization runs a self-hosted GitLab, an administrator can allow all
marketplaces from that host through managed settings rather than having every
engineer add it by hand.

## Merge request policy

| | |
| --- | --- |
| Source branch | `feature/*`, `defect/*`, `hotfix/*`, `chore/*` |
| Target | `main` |
| Approvals | at least one, never the author |
| Reviewers | routed per `policies/review-routing.json`, rule RR-10 for this repository |
| Required pipeline | must pass |
| Description | what, why, how verified, risk, rollback, traceability identifiers |

A merge request that does not say how it was verified is not ready for review.

## CI

`.gitlab-ci.yml` runs four stages on Python 3 with no installed dependencies:

| Stage | Job | Fails on |
| --- | --- | --- |
| validate | `plugin-structure` | Manifest, frontmatter, registry/policy drift, hook wiring |
| validate | `schemas` | Invalid JSON or YAML, policy/schema mismatch, invalid shipped template |
| validate | `contracts` | An unknown definition-of-done predicate, model routing that does not resolve for a stage, an unreachable cycle state, an event that does not route |
| validate | `strict-structure` | Warnings, on the default branch and on a tag: a placeholder marketplace URL, a hook script that is not executable |
| validate | `claude-plugin-validate` | Claude Code's own structural check, when the CLI is available |
| validate | `markdown-links` | A link between documents that does not resolve |
| security | `secret-scan` | Any critical secret finding |
| security | `guard-failure-behaviour` | The tiered failure path, exercised on every pipeline because it matters most when something else has already gone wrong |
| security | `hook-permissions` | A hook script that is not executable, or is world-writable |
| test | `unit-tests` | Guard, library and repository tests |
| evaluate | `sdlc-simulation` | A workflow that cannot be completed end to end |
| evaluate | `fault-injection` | A fault the controls no longer stop; also runs the liveness checker |
| evaluate | `deterministic-evaluations` | Any critical or major deterministic case |
| evaluate | `llm-evaluation-bundle` | Emitting the bundle on the default branch and on tags. It never scores a case |
| evaluate | `release-readiness` | Tag only: `check_release.py` |

The pipeline fails fast on a malformed component: `validate` runs before anything
else, because a broken manifest makes every later result meaningless.

`claude-plugin-validate` is `allow_failure: true` on merge requests and feature
branches, because the Claude Code CLI is not guaranteed to be present on a
runner. On the default branch and on a tag it is mandatory: shipping a plugin
that Claude Code's own validator rejects is the one failure this repository
cannot argue its way out of. When the CLI is absent the job exits non-zero and
says so rather than passing silently.

## Releases

Semantic versioning. The version in `.claude-plugin/plugin.json` is what
Claude Code uses to decide whether users receive an update, so a change that is
not version-bumped does not reach anyone.

```bash
# on a release branch, after the version bump and CHANGELOG entry
claude plugin tag . --message "ai-engineering-os %s" --push
```

`claude plugin tag` derives the tag name from the manifest as
**`{plugin-name}--v{version}`** — so v0.7.0 is tagged `ai-engineering-os--v0.7.0`,
not `v0.7.0`. The `ref` in `.claude-plugin/marketplace.json` must name that exact
tag, or new installs resolve to a tag that does not exist.
`scripts/check_release.py` checks both.

Then create the GitLab release from the tag and update the `ref` in
`.claude-plugin/marketplace.json`.

## Issues and traceability

Link merge requests to issues with `Closes #n` / `Refs #n`. Keep artifact
identifiers (`SFTP-REQ-012`) in the text as well: they survive across systems in
a way issue numbers do not. Milestones map to releases.
