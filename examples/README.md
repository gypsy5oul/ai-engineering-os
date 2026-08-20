# Worked examples

Three end-to-end scenarios. Each one names the workflow, the stages, the agents,
the artifacts, the guard decisions and the human approvals — and each includes at
least one place where the organization deliberately refuses to proceed.

| | |
| --- | --- |
| [01 — Build an enterprise SFTP platform](01-sftp-platform.md) | Greenfield capability through `WF-FEATURE` |
| [02 — Fix a production authentication defect](02-auth-defect.md) | `WF-INCIDENT` → `WF-DEFECT` → `WF-RELEASE` |
| [03 — Upgrade a backend dependency](03-dependency-upgrade.md) | `WF-DEPENDENCY` |

## Run the demonstration

```bash
./examples/run_demo.sh
```

It feeds the guards the exact commands these scenarios produce and prints the
real decisions — no simulation. Every line of output comes from
`hooks/scripts/*.py` evaluating `policies/hook-policy.json`.

## Sample project

[`sftp-platform/.ai-engineering/project.yaml`](sftp-platform/.ai-engineering/project.yaml)
is a complete, valid project configuration for the scenario in example 01. It
validates:

```bash
python3 scripts/validate_project_config.py examples/sftp-platform/.ai-engineering/project.yaml
```

Note what it does **not** contain: a frontend layer, because the platform has no
user interface, and a UX stage, which is recorded in `sdlc.skipped_stages` with
its reason. It also carries a blocking `open_decision` for an unanswered RPO/RTO
question — which is what an honest configuration looks like partway through
onboarding.
