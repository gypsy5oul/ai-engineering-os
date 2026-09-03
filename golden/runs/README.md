# Certification run history

One file per run, named for the plugin version it ran against. Runs are kept
rather than overwritten: what the organization used to be able to prove is
evidence about how it matured, and a record that is edited to stay current is no
longer a record.

`golden/certification-run.json` at the repository root is the **canonical** run —
the one `docs/certification.md` describes and
`check_certification_doc_matches_the_run` holds that page to. A run is promoted
to canonical only when it is clean: one plugin version, one platform version, no
edits to the working tree while it ran.

## What each record must carry

The schema is `schemas/certification-run.schema.json`. Beyond the mechanics, a
run that was disturbed says so in `notes` — an environment limit, a version that
changed underneath it, a probe rule that has since been tightened. A reader who
cannot tell a defect in the organization from a limit of the machine it ran on
will draw the wrong conclusion from a perfectly accurate file.

## What a run cannot be edited into

A record is never rewritten to agree with a later probe rule. `v0.44.0.json`
reports `real_agent: fail` on a background job the platform never started; the
probe now calls that `not-run`, because a mechanism that did not run is
unexercised rather than broken. The note says so and the verdict stands as it was
produced. Certification was refused either way, which is the only thing the
distinction could have changed.

## The runs

| File | Plugin | Claude Code | Certified | What it is good for |
| --- | --- | --- | --- | --- |
| `v0.44.0.json` | 0.44.0 | 2.1.251 | no | The first multi-role walk: the organization convened a reviewer, an artifact owner, a department lead and a human for one stage. Straddles the v0.45.0 bump and hit the account's session limit, so it is history rather than a certification. |
| `v0.45.0.json` | 0.45.0 | 2.1.251 | no | The first clean single-version run. Worktree creation genuinely exercised (three created). Found two defects in the harness's own probes -- a running job reported as never started, and a dirty working tree accepted as integration evidence -- both corrected after it. |
| `v0.45.1.json` | 0.45.0 | 2.1.252 | no | First run with the native task tools enabled. The task probes still report not-run: the session limit was reached before the mechanisms ran, because the open-ended lifecycle walk went first. Mechanisms now run first. |
| `v0.45.1-mechanisms.json` | 0.45.1 | 2.1.252 | no | A `--mechanisms-only` run, not a certification. Four probes pass here that never had: the native task bound and its completion gated, background execution ran and wrote its artifact, and two worktrees were created. Worktree integration fails — the agent edited the main checkout directly, which the tightened evidence rule now refuses to read as integration. |
