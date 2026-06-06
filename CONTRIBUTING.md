# Contributing to Sentinel Platform

## Branch naming

| Type | Pattern | Example |
|---|---|---|
| New feature | `feat/m{N}-description` | `feat/m0-event-schema` |
| Bug fix | `fix/short-description` | `fix/helm-values-typo` |
| Documentation | `docs/short-description` | `docs/architecture-diagram` |
| Chore | `chore/short-description` | `chore/update-makefile` |

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add event.schema.json with causality field
fix: correct redis stream name in values.yaml
docs: add data-flow diagram to architecture.md
chore: bump helm chart version
```

## Pull requests

- Every PR must reference an issue: `Closes #N` in the description
- Set the milestone (`M0`–`M7`) and add a type label (`infrastructure`, `schema`,
  `event-bus`, `integration`, `docs`, `ci`) at creation time
- Keep PRs focused — one issue per PR where possible

## Labels

- `infrastructure` — cluster, Helm charts, manifests, deploy harness
- `schema` — shared event schema and cross-agent contracts
- `event-bus` — Redis streams / pub-sub plumbing
- `integration` — cross-repo wiring (Argus/Phoenix reporting clients, demo scenario)
- `docs` — architecture docs, diagrams, specs
- `ci` — CI/CD pipeline

Milestones (`M0`–`M7`) track which phase of the platform build an issue belongs to —
see the [milestones page](https://github.com/CodeBuildder/sentinel-platform/milestones)
for the current sequence and scope of each.
