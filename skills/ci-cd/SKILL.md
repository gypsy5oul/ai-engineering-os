---
name: ci-cd
description: Design and maintain pipelines, build reproducibility, artifact traceability and deployment mechanics. Use when creating or changing CI configuration, containerisation, or deployment automation. Technology-neutral - the platform comes from the project configuration.
---

# CI/CD

A pipeline exists to make the answer to "is this safe to ship" cheap and repeatable.

## Stage set

Order stages so the fastest, most likely failures run first:

1. **Lint and format** — seconds.
2. **Build** — must be reproducible from a clean checkout.
3. **Unit tests** — fast, on every commit.
4. **Static analysis and type checks**.
5. **Secret scan** — on the diff and on the full tree.
6. **Dependency audit** — vulnerabilities and licences.
7. **Integration tests** — real adapters, containerised infrastructure.
8. **Package** — artifact tagged with the commit SHA.
9. **Publish** — to the registry, on protected branches only.
10. **Deploy** — per environment, production behind human approval.

Which of these are required is a project decision recorded in `.ai-engineering/project.yaml`.

## Principles

- **Reproducible builds.** Same commit, same artifact. Pin versions, including base images and toolchains.
- **Traceable artifacts.** Every artifact records the commit, the pipeline and the build time. When something is running in production you must be able to name the commit.
- **Fail fast, fail clearly.** A failure message must say what failed and what to do. Engineers route around pipelines that produce unreadable failures.
- **Least privilege per stage.** The test stage does not need deployment credentials. The build stage does not need production access. Scope credentials to the job.
- **No secrets in the repository, the image or the pipeline definition.** Inject at runtime from the secret manager; mask in logs.
- **Keep the inner loop fast.** If the pre-merge pipeline takes longer than a coffee, people stop waiting for it. Move slow suites to post-merge or scheduled runs and say so explicitly.

## Containers

Multi-stage builds; the runtime image contains the artifact and its runtime dependencies, nothing else. Non-root user. Pinned base image with a documented update cadence. No build tools, no shells you do not need, no secrets in layers — a deleted file in an earlier layer is still in the image.

## Deployment

- Deploy the artifact that was tested. Never rebuild for production.
- Health-gate the rollout; an unhealthy instance stops the rollout rather than continuing.
- Keep the previous version deployable at all times.
- The rollback path is tested, not assumed. An untested rollback is a plan, not a capability.
- Production deployment is AP-01: a human approves it, every time.

## Environments

Configuration comes from the environment, secrets from the secret manager, and both are separate from the artifact. The same artifact runs in every environment; only configuration differs. Anything else means you tested something other than what you shipped.
