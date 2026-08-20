# Examples

The worked scenarios live in [`../../examples/`](../../examples/) so that the
files they reference are real files you can run against, not excerpts.

| Scenario | Workflow | Shows |
| --- | --- | --- |
| [Build an enterprise SFTP platform](../../examples/01-sftp-platform.md) | `WF-FEATURE` | Requirements, architecture, QA design, development, security, DevOps, release — including a stage skipped on purpose |
| [Fix a production authentication defect](../../examples/02-auth-defect.md) | `WF-INCIDENT` → `WF-DEFECT` → `WF-RELEASE` | Incident, investigation, RCA, defect, QA, expedited release |
| [Upgrade a backend dependency](../../examples/03-dependency-upgrade.md) | `WF-DEPENDENCY` | Impact analysis, security and licence, compatibility, merge request, release |

[`examples/run_demo.sh`](../../examples/run_demo.sh) runs the guards against the
exact commands these scenarios produce and prints the real decisions.
