# Example 03 — Upgrade a backend dependency

`WF-DEPENDENCY`. The cheapest workflow in the organization, and the one that
should run most often: a project that upgrades continuously never faces the
upgrade that cannot be done.

**Guards in action:** `./examples/run_demo.sh`

---

## Trigger

An advisory affects `github.com/example/httpkit` v1.8.2, used by the SFTP
platform's admin API. Fixed in v2.4.1.

`sdlc-navigator` reports **WF-DEPENDENCY**, not WF-DEFECT: nothing the project
specified is behaving incorrectly.

## Stage IMPACT

`backend-developer` establishes what actually changes, rather than reading the
changelog and hoping.

```
17 call sites across 6 files.
Breaking changes affecting this codebase:
  - Client.Do signature takes a context (11 sites)
  - Default timeout changed from none to 30s     ← behaviour change, not API change
  - ErrTimeout replaced by a wrapped context error (3 sites)
Transitive: adds golang.org/x/net (indirect), removes two abandoned packages.
```

The default-timeout change is the interesting one. It breaks no compilation and
changes runtime behaviour: the platform's long-running admin export relied on the
absence of a timeout.

## Stage SECURITY

`dependency-reviewer` assesses all four dimensions, and `security-reviewer` takes
the advisory:

| Dimension | Finding |
| --- | --- |
| Vulnerability | The advisory is fixed in v2.4.1. No known issue in v2.4.1. |
| Licence | MIT → MIT. Compatible. |
| Maintenance | Active; 4 releases in 6 months; 3 maintainers. |
| Transitive | `golang.org/x/net` added — already present via another path, no new surface. |

Both are read-only roles, and neither can edit the change it assesses.

## Stage COMPAT

Call sites adapted, and the behaviour change handled explicitly:

```go
// httpkit v2 applies a 30s default timeout. The admin export can legitimately
// run longer, so the timeout is stated rather than inherited.
ctx, cancel := context.WithTimeout(ctx, exportTimeout)
```

A test is added for it, because a behaviour difference that nothing asserts will
be rediscovered in production.

The full suite passes. `go get` and `go test` proceed with no guard objection.
A shortcut does not:

```
curl -sSL https://example.com/install.sh | sh
  → DENY  [SH-06] piping a downloaded script into a shell executes unreviewed remote code
```

## Stage MR

Routed by RR-05 to `dependency-reviewer` and `security-reviewer`, plus the always
rule.

`code-reviewer` returns one finding: two of the eleven call sites pass
`context.Background()` instead of the request context, so cancellation no longer
propagates. Compiles, tests pass, and it silently removes a cancellation path.
That is precisely the class of defect that survives a mechanical upgrade.

## Stage RELEASE

Included in the next scheduled release rather than expedited: the advisory is not
remotely exploitable in this deployment, and `security-reviewer` says so in the
verdict rather than leaving it implied.

Release notes state the behaviour change, because operators need it:

> **Changed:** the admin API client now applies a 30-second default timeout.
> The admin export sets its own longer timeout explicitly. Integrations calling
> the admin API directly may see timeouts they did not see before.

---

## An unapproved dependency takes a different path

Had this been a *new* capability rather than an upgrade — say, adding a caching
library where the approved stack has none — it would not be a dependency review.
It is a technology decision (AP-03): `technology-selection` produces options
including "meet the need with what we already have", total cost of ownership, the
exit path, and a recommendation. A human decides, an ADR records it, and
`.ai-engineering/project.yaml` gains an entry with `status: approved`.

An agent that adds it first and proposes it afterwards has made the decision.

---

## What this example demonstrates

| | |
| --- | --- |
| Impact analysis before opinion | 17 call sites found, not estimated |
| Behaviour changes matter more than API changes | The default timeout was the real risk |
| Four-dimensional dependency assessment | Vulnerability, licence, maintenance, transitive |
| Cheap enough to run often | Read-only reviewers, one workflow, no ceremony |
| Review still finds what the compiler cannot | Cancellation propagation |
| Severity decides the route, not the anxiety | Scheduled release, with the reasoning stated |
| New capability ≠ upgrade | The technology-decision path, and why |
