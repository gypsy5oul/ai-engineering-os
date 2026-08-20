---
name: git-workflow
description: Branch, commit and manage history according to the organization's branching policy and the project's overrides. Use for any git operation, when naming a branch, writing a commit message, or when a git command was blocked by a guard.
---

# Git workflow

The defaults are in `${CLAUDE_PLUGIN_ROOT}/policies/branch-policy.json`. The project may tighten them in `.ai-engineering/project.yaml` under `repository.branching`; the project value wins.

## Branches

| Type | From | Into | Naming |
| --- | --- | --- | --- |
| `feature/*` | main | main | `feature/<story-id>-<slug>` |
| `defect/*` | main | main | `defect/<defect-id>-<slug>` |
| `hotfix/*` | release/* | release/* and main | `hotfix/<incident-id>-<slug>` |
| `release/*` | main | main | `release/<version>` |
| `chore/*` | main | main | `chore/<slug>` |

Protected by default: `main`, `master`, `develop`, `release/*`, `hotfix/production/*`.

```
git switch -c feature/PROJ-STORY-142-key-rotation
```

## Commits

```
<type>(<scope>): <subject>

<body: what changed and why, not how>

Refs: PROJ-REQ-012, PROJ-STORY-142
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`, `ci`, `revert`.

Every commit carries at least one traceability identifier. A commit whose message is "fix" costs the next reader an hour.

Commit in logical units. One commit that does three things cannot be reverted independently.

## What the guards block, and why

| Blocked | Decision | Why |
| --- | --- | --- |
| Push to a protected branch | escalate | Bypasses review (AP-09) |
| Commit while on a protected branch | escalate | The same, one step earlier |
| Force push | escalate | Rewrites shared history |
| Remote branch deletion | deny | Removes shared work |
| `filter-branch`, `filter-repo`, `reflog delete` | deny | Destroys the audit trail |
| `reset --hard` | escalate | Discards uncommitted work irreversibly |
| `clean -fdx` | escalate | Deletes untracked files you were never shown |
| `--no-verify` | escalate | Skips the project's own checks |
| Committing `.env`, keys or credential files | deny | Committed secrets must be rotated, not removed |

When a guard fires, the message says what to do instead. Do that rather than looking for a way around it: the way around it is the finding.

## Reverting

Revert with a new commit (`git revert`). Do not rewrite history on a shared branch to make a mistake disappear; the mistake is already in someone's clone.

## Before opening a merge request

- Rebase or merge the target branch and resolve conflicts deliberately.
- Run the full local gate: tests, lint, type checks.
- Read your own diff. Remove debug output, commented-out code and unrelated changes.
