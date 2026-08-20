---
name: kubernetes-basics
description: Work safely with Kubernetes for projects whose deployment platform is Kubernetes - workload configuration, health, resources, rollout and safe read-only investigation. Use only when the project configuration declares Kubernetes; it is not assumed anywhere else.
---

# Kubernetes basics

**Applicable only when `.ai-engineering/project.yaml` declares `deployment.platform: kubernetes`.** Nothing in the AI Engineering OS assumes Kubernetes.

## Workload configuration that matters

- **Resource requests and limits** on every container. No requests means the scheduler is guessing; no memory limit means one workload can evict its neighbours. CPU limits cause throttling — set them deliberately, not reflexively.
- **Liveness, readiness and startup probes** are three different questions: is it broken (restart me), can it serve (send traffic), is it still starting (do not judge me yet). Getting readiness wrong sends traffic to an instance that cannot serve it; getting liveness wrong restarts a healthy but slow instance and turns load into an outage.
- **Graceful shutdown**: handle SIGTERM, stop accepting new work, finish in-flight work within `terminationGracePeriodSeconds`. Without this, every rollout drops requests.
- **PodDisruptionBudget** so that voluntary disruptions (node drains, upgrades) cannot take the whole service.
- **Security context**: non-root, read-only root filesystem where possible, no privilege escalation, dropped capabilities.
- **Secrets** from the cluster's secret mechanism or an external secret manager, never in the manifest, never in the image.

## Rollout

Use the deployment strategy the project declared. Health-gate it: a rollout that continues past failing readiness is an automated outage. Keep the previous ReplicaSet available so a rollback is one command.

## Investigating safely (read-only)

```
kubectl get pods -n <ns>
kubectl describe pod <pod> -n <ns>
kubectl logs <pod> -n <ns> --previous
kubectl get events -n <ns> --sort-by=.lastTimestamp
kubectl top pods -n <ns>
```

`describe` and `events` answer most "why will this not start" questions: image pull failures, resource pressure, probe failures, volume mounting.

## What the guards block

Mutating a production namespace (`delete`, `drain`, `scale`, `rollout undo`, `exec`) is denied. Deleting a namespace, PVC or CRD is escalated anywhere. Printing secret values is escalated. Kubernetes access against a production context is escalated (AP-11).

These exist because a mistyped namespace is the difference between a test and an outage. Production changes go through the release process with human approval.

## Common failure signatures

| Symptom | Usual cause |
| --- | --- |
| `CrashLoopBackOff` | Application exits at startup; read logs with `--previous` |
| `ImagePullBackOff` | Wrong tag, missing pull secret, registry unreachable |
| `Pending` | No node satisfies requests, affinity or taints |
| `OOMKilled` | Memory limit below real usage, or a leak |
| Traffic to a bad instance | Readiness probe passes before the app can serve |
| Requests dropped on deploy | No graceful shutdown, or preStop missing |
