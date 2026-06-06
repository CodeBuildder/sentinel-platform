<!--
Sentinel Platform — GitOps & Integration Layer
Copyright (c) 2026 Kaushikkumaran
Original work — see NOTICE for details
Commit history: https://github.com/CodeBuildder/sentinel-platform/commits/main
-->

<h1 align="center">Sentinel Platform</h1>

<p align="center">
  The GitOps and integration layer for the Sentinel platform — the shared event schema,
  Helm umbrella chart, and deployment harness that wire
  <a href="https://github.com/CodeBuildder/argus-k8s">Argus</a>,
  <a href="https://github.com/CodeBuildder/phoenix">Phoenix</a>, and
  <a href="https://github.com/CodeBuildder/sentinel">Sentinel</a>
  into one autonomous infrastructure stack.
</p>

<p align="center">
  <a href="docs/ARCHITECTURE.md"><strong>Architecture</strong></a>
  ·
  <a href="https://github.com/CodeBuildder/sentinel-platform/milestones"><strong>Roadmap</strong></a>
</p>

## What this repo is

Three autonomous agents — Argus (security), Phoenix (resilience/chaos), and Sentinel
(orchestration) — need to speak one language and deploy as one stack. This repo is that
contract:

- **`/schemas`** — the shared event JSON schema every agent publishes against
  (`event_type`, `source_agent`, `severity`, `component`, `causality`, `timestamp`, `payload`)
- **`/helm`** — umbrella chart referencing the argus, phoenix, and sentinel subcharts
- **`/manifests`** — k3s namespaces, the Redis-streams event bus, and the Chaos Mesh install
- **`/docs`** — architecture diagrams and the cross-agent integration specs
- **`Makefile`** — `make up` / `make down` / `make demo` for the whole stack

## Architecture

```
                        ┌─────────────────────────────┐
                        │          SENTINEL           │
                        │   Master Orchestrator + UI  │
                        │   (LangGraph supervisor)    │
                        │  - aggregates sub-agents    │
                        │  - daily reports            │
                        │  - fleet risk scoring       │
                        └──────────┬───────┬──────────┘
                                   │       │
                  reports up       │       │      reports up
                ┌──────────────────┘       └──────────────────┐
                ▼                                              ▼
     ┌─────────────────────┐                       ┌─────────────────────┐
     │       ARGUS         │                       │      PHOENIX        │
     │  Security Analysis  │                       │ Resilience / Chaos  │
     │  - Falco / Kyverno  │                       │  - chaos injection  │
     │  - Cilium eBPF      │                       │  - failure detect   │
     │  - threat detection │                       │  - self-healing     │
     │  - C2 dashboard     │                       │  - human approval   │
     └─────────────────────┘                       └─────────────────────┘
                │                                              │
                └──────────────────┬───────────────────────────┘
                                   ▼
                   ┌───────────────────────────────┐
                   │  Shared k3s cluster (3-node)  │
                   │  Prometheus / Grafana / Loki  │
                   │  Cilium eBPF · Claude API     │
                   └───────────────────────────────┘
```

Argus and Phoenix each run their own agent and dashboard, publishing events onto a shared
Redis-streams bus in the common schema. Sentinel subscribes, normalizes, scores fleet risk,
and produces the daily report. The full data flow lives in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Status

Bootstrapping — see the [milestones](https://github.com/CodeBuildder/sentinel-platform/milestones)
for the build sequence. M0 (this repo's own scaffolding: event schema, Helm chart, event
bus, namespaces) lands first; every other repo's agent depends on the contract it defines.

## Related repos

| Repo | Role |
|---|---|
| [argus-k8s](https://github.com/CodeBuildder/argus-k8s) | Security agent — eBPF threat detection, policy enforcement, AI reasoning |
| [phoenix](https://github.com/CodeBuildder/phoenix) | Resilience agent — chaos injection, synthetic provisioning, self-healing |
| [sentinel](https://github.com/CodeBuildder/sentinel) | Master orchestrator — fleet risk scoring, daily reports, command-center UI |

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
