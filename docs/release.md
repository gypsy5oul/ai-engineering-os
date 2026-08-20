# Releasing the plugin

## Versioning

Semantic versioning, on `version` in `.claude-plugin/plugin.json`. Claude Code
uses that field to decide whether users receive an update, so **a change that is
not version-bumped does not reach anyone**.

| Bump | For |
| --- | --- |
| **major** | An agent removed or renamed; a spawn edge withdrawn; a guard rule that now blocks previously allowed work; a schema change requiring project configuration edits; any organizational behaviour change requiring action from existing users |
| **minor** | A new agent, skill, workflow or guard rule that does not break existing usage; new policy fields with defaults |
| **patch** | Fixes, wording, documentation, additional evaluation cases |

A guard becoming stricter is a **major** change. It changes what people can do.

## Process

```
change → merge request → static validation → automated evaluation → agent review
      → human governance review where required → merge → version bump → release
```

1. **Merge request** against `main` with the standard description.
2. **Static validation** in CI: `validate_plugin.py`, `validate_schemas.py`,
   `secret_scan.py`, the test suite, `claude plugin validate` where available.
3. **Automated evaluation**: `run_evaluations.py` for the affected suites plus
   the governance suite. Critical or major failures block.
4. **Agent review** routed by RR-10: `agent-evaluator`, `ai-governance`,
   `security-reviewer`.
5. **Human governance review** for anything in the higher-risk list in
   `docs/governance.md`.
6. **Merge**, never by the author.
7. **Version bump** and `CHANGELOG.md` entry, with a migration note if
   organizational behaviour changed.
8. **Tag and release.**

## Cutting a release

```bash
git switch -c release/0.2.0
# bump .claude-plugin/plugin.json, marketplace.json entry, CHANGELOG.md
python3 scripts/validate_plugin.py && python3 -m unittest discover -s tests -q
claude plugin tag . --message "ai-engineering-os %s" --push
```

`claude plugin tag` derives the tag name from the manifest as
**`{plugin-name}--v{version}`** — so v0.7.0 is tagged `ai-engineering-os--v0.7.0`,
not `v0.7.0`. The `ref` in `.claude-plugin/marketplace.json` must name that exact
tag, or new installs resolve to a tag that does not exist.

**Two checks, and they cover different failures.** `scripts/check_release.py`
compares the ref against `CI_COMMIT_TAG`, so it only runs *on* a tag and says
nothing at all when no tag was ever created — which is exactly how this
repository shipped ten versions whose `ref` pointed at tags that did not exist.
Every one of them would have failed to resolve for anyone installing from the
marketplace. `check_marketplace_ref_exists()` in `scripts/validate_plugin.py`
closes that: it runs on every validation and fails when the ref names a tag the
repository does not have.

If you tag by hand rather than with `claude plugin tag`, the annotated form is:

```bash
git tag -a ai-engineering-os--v0.18.0 -m "ai-engineering-os--v0.18.0"
git push origin --tags
```

Then create the GitLab release from the tag and update the `ref` in
`.claude-plugin/marketplace.json` so new installs land on it.

## Migration notes

Required whenever existing users must do something. Format:

```markdown
### Migration: 0.1.0 → 0.2.0

**`qa-architect` removed.** Its responsibilities are in `qa-lead`.
Update any project CLAUDE.md or automation that names it.

**`data-engineer` write scope narrowed** to migrations and data-access paths.
Projects with data code outside `migrations/**` should add their paths to
`.ai-engineering/security.json` or move the code.
```

State what changed, who is affected, and what they must do. A migration note
that only says what changed leaves every reader to work out the second half.

## Rollback

Users pin to a version through the marketplace `ref`. To withdraw a release:
point the `ref` back to the previous tag, publish a patch release with the fix,
and say what happened in the changelog. Do not delete the tag — someone has
already installed it.

## Deprecation

A component moves to `deprecated`, stays for one minor release with a migration
note, and is removed in the next. Removing it in the same release that deprecates
it is a breaking change wearing a deprecation label.
