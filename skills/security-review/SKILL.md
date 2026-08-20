---
name: security-review
description: Review a change for vulnerability classes, secret exposure, authorization gaps and supply-chain risk, with severity and an exploitation path per finding. Use on any change touching authentication, authorization, cryptography, input handling, dependencies, infrastructure or data access.
---

# Security review

Report defects with an exploitation path. A finding without one is a style opinion.

## Start with the change's surface

What does this change let an untrusted party influence? Follow that input to every place it reaches. Most real findings are on that path.

## Classes to check, by surface

**Input handling**: injection into SQL, shell, template, LDAP, XPath or log; deserialization of untrusted data; path traversal; XML external entities; unbounded input causing resource exhaustion; parser differentials between validation and use.

**Authorization**: missing check; check on the wrong object (IDOR); check that trusts a client-supplied identity; authorization at the controller but not at the data access; privilege retained after a role change; horizontal access between tenants.

**Authentication and session**: predictable or non-rotating tokens; missing expiry; tokens in URLs or logs; session fixation; missing revocation path; timing-sensitive comparison of secrets.

**Cryptography**: home-made schemes; ECB; static or absent IV/nonce; MD5 or SHA-1 for anything security-relevant; unsalted or fast password hashing; keys in code; missing certificate validation.

**Secrets**: values in code, configuration, tests, fixtures, logs, error messages, or committed history.

**Outbound requests**: server-side request forgery via user-controlled URLs; redirect following into internal networks; missing egress restrictions.

**Web surface**: cross-site scripting through unescaped output or unsafe HTML sinks; cross-site request forgery on state-changing requests; missing or wrong security headers; permissive CORS; cookie flags.

**Supply chain**: new or upgraded dependencies, their transitive additions, install-time scripts, and unpinned versions.

**Infrastructure**: over-broad IAM, public storage, permissive network rules, privileged containers, secrets in environment variables that end up in logs.

## Verify what you claim

Read the code path rather than pattern-matching. For each finding, state: where it is, who can reach it, what they achieve, and what fixes it. If you cannot state who can reach it, say so and mark the finding as needing confirmation rather than asserting an impact you have not established.

## Severity

- **Critical** — remote exploitation with material impact, or secret exposure, on a reachable path.
- **High** — exploitation requires a precondition that a realistic attacker can obtain.
- **Medium** — real weakness, limited impact or difficult path.
- **Low** — defence in depth, no exploitation path established.

Critical and High block the merge. A finding that will not be fixed becomes an exception record with residual risk, compensating control and expiry, approved by a human (AP-04).

## Output

State which controls you verified, not only what you found. "No findings" without a list of what was checked is not a review.
