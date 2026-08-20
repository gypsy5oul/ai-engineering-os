# Organizational freeze

**The agent set is frozen at 30** (29 at v0.3.0, plus `notification-agent` at v0.6.0). No new agents without an
`agent-architect` ADR and AI Architecture Council approval, per
[governance](governance.md).

## Why freeze now

The organization already covers every department in the SDLC. Every candidate
role considered and rejected is recorded in
[the catalogue](organization.md#roles-that-were-deliberately-not-created), and
none of the rejections has since proved wrong in use.

The remaining value is not in more roles. It is in making each existing role's
contract complete down the whole chain:

```
Agent
 ↓ role contract      15 sections, enforced by validation
 ↓ skills             preloaded, and named explicitly for teammates
 ↓ tools              one of six profiles, exactly
 ↓ permissions        write scope, spawn authority
 ↓ model policy       role default + risk + complexity, resolvable per stage
 ↓ artifacts          what it creates, modifies, reviews, approves
 ↓ gates              agent verdict with a stated purpose, human approval with an identity
 ↓ evaluation         a suite with at least one adversarial case
```

A new agent adds a row. Completing that chain for an existing agent adds a
control.

## Positions are not agents

v0.4.0 added the department execution cycle, which speaks of heads, leads,
workers and peer reviewers. None of those are new agents. They are **positions**
filled by the existing 29 plus the named humans in the project's `approval:`
section — see [department cycles](department-cycles.md).

That distinction is what let the hierarchy arrive without the org growing. A
"Backend Lead" reviewing a backend developer is the `peer_reviewer` position,
filled by `code-reviewer`, which has the advantage of holding no write tools.
A "Development Head" is the `engineering-owner` human who receives the rollup.

## What the freeze does not stop

- **Skills.** A capability several roles share is a skill, and skills are not
  frozen. Most requests for "a new agent" are skill requests.
- **Reviewers gaining a dimension.** An existing reviewer covering a new class of
  finding is a skill and a routing rule, not a role.
- **Policy.** Risk classes, routing, model policy and approval categories evolve
  on their own cadence.
- **Deprecation.** Removing a role that proves redundant is still open, through
  the same lifecycle.

## The freeze has been exercised once

**v0.6.0 added `notification-agent`, taking the set to 30.** The four-part test,
applied honestly:

| Test | Verdict |
| --- | --- |
| Authority no existing role has | Yes. Formatting the organization's outbound voice. |
| Inputs no existing role receives | Yes. Routing decisions and the event log. |
| Outputs no existing role produces | Yes. Chat messages and digests. |
| A conflict structure cannot resolve | **Yes.** Giving this to `docs-writer` would mean the documentation role also holds the organization's outbound voice. A mistake there — a leaked secret, an exploitation path — reaches everyone and cannot be recalled. Separating "writes documentation" from "speaks to the organization" is worth a role. |

Note what the role deliberately *cannot* do: it holds no `Bash`, so it cannot
send; routing and recipients are computed by `scripts/route_event.py`; dispatch is
a separate credentialed act. It writes, and nothing else. That narrowness is why
the addition is defensible rather than a precedent for adding managers.

## The test for unfreezing

A new agent is justified only when all four hold:

1. It has authority no existing role has.
2. It has inputs no existing role receives.
3. It has outputs no existing role produces.
4. Giving the work to the nearest existing role would create a conflict of
   interest that structure cannot resolve.

Points 1 to 3 are usually arguable. Point 4 is the one that actually justifies a
role: `architecture-reviewer` exists because an architect approving its own
design is a conflict no amount of instruction fixes.

If a proposal fails point 4, it is a skill, a routing rule, or a task.

## Current shape

| Department | Agents |
| --- | --- |
| Executive and governance | 1 |
| AI governance | 1 |
| AI / agent engineering | 3 |
| Product | 2 |
| Architecture | 2 |
| UX / design | 1 |
| Engineering | 4 |
| Data engineering | 1 |
| QA | 4 |
| Security | 3 |
| Platform / DevOps | 1 |
| Release management | 1 |
| SRE and incident management | 4 |
| Documentation / knowledge | 1 |
| Engineering communications | 1 |
| **Total** | **30** |

Five of those are independent specialist reviewers holding no write tools. That
ratio — roughly one independent check for every five producers — is the property
worth preserving as the organization changes.
