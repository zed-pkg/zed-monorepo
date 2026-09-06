# 11. Deploying the registry to Kubernetes (GitOps app-of-apps)

**Issue:** The registry is two long-running Rust services — the API server
([`zed-api-server.rs`](https://github.com/zed-pkg/zed-api-server.rs), REST +
artifacts) and the read-only web UI
([`zed-web-server.rs`](https://github.com/zed-pkg/zed-web-server.rs)) — plus a
Postgres and a blob store. They have to run *somewhere*, and "somewhere" is a
shared Kubernetes cluster with other tenants. That raises questions the code
alone can't answer: where do the manifests live, who owns the namespace, how do
secrets and images get in, and how do we know a deploy actually works before it
reaches production? This doc is the deployment contract and the operational
learnings that came out of proving it end to end.

## Layer split: platform vs app

Deployment follows the ORES `k8s-cluster` app-deploy contract, which splits
ownership in two:

- **Layer 1 (platform, in [`ORESoftware/k8s-cluster`](https://github.com/ORESoftware/k8s-cluster)).**
  The `zed` Namespace and its `ResourceQuota` / `LimitRange` /
  default-deny `NetworkPolicy` live in `remote/argocd/projects/zed.tenant.yaml`.
  The tenant is registered by the trio `zed.tenant.yaml` +
  `zed.appproject.yaml` (a strict `AppProject` with
  `clusterResourceWhitelist: []`) + `remote/argocd/apps/zed.applications.yaml`
  (the Argo CD `Application`s), mirroring the worked `daedalus` precedent.
- **Layer 2 (app-owned).** Each service repo carries its own **namespace-scoped**
  manifests under `k8s/` — `deployment.yaml`, `service.yaml`,
  `externalsecret.yaml`, `ingress.yaml`, `networkpolicy.yaml`,
  `kustomization.yaml`. No `Namespace`/`ClusterRole`/CRD may appear here; the
  strict `AppProject` would reject the sync.

**Submodules are inventory, never a render source.** The monorepo
([`zed-monorepo`](https://github.com/zed-pkg/zed-monorepo)) vendors every repo
under `apps/` so the Rust services can path-depend on `../zed-interfaces`, and
it is itself a submodule of `k8s-cluster`. But the Argo CD repo-server has
`enable.git.submodule=false`, so an `Application` pointed at a submodule path
renders **empty**. The `Application`s therefore set `repoURL` to each app repo
directly (`path: k8s`, `targetRevision: main`), with
`syncPolicy.automated{prune,selfHeal}` + `ServerSideApply=true`.

## Building the images

Both Dockerfiles are multi-stage (Rust build → `debian:12-slim` runtime, non-root
uid 10001, read-only rootfs, dropped caps). Three build facts are load-bearing
and were the difference between "compiles" and "crash-loops":

- **Toolchain floor.** The crates use `edition = "2024"` (needs Rust ≥ 1.85) and
  the `aws-sdk-*` family needs ≥ 1.94.1, so the build stage is pinned to
  `rust:1.97-slim-bookworm`.
- **No build-time toolchain download.** The repos carry
  `rust-toolchain.toml` with `channel = "stable"`; inside the pinned base that
  would re-download a full floating toolchain on every build (slow, and a
  build-time CDN dependency that intermittently failed). The Dockerfiles set
  `ENV RUSTUP_TOOLCHAIN=1.97.1` so the build uses the base image's toolchain and
  ignores the floating pin — reproducible, offline-friendly.
- **glibc parity.** The build stage must be the **`-bookworm`** variant, not the
  default (trixie): a trixie build links `GLIBC_2.39`, which the `debian:12-slim`
  (bookworm, 2.36) runtime does not provide, and the binary crash-loops at
  startup with a `version 'GLIBC_2.39' not found` error.

Build context is the parent directory (side-by-side `zed-interfaces` +
service checkout); the app repos have no `.dockerignore`, so tooling that builds
them should stage a source-only context (the e2e harness does — see
[doc 12](12-in-cluster-e2e.md)).

## Storage and secrets

- **Artifacts.** `STORAGE_BACKEND` selects `s3` (any S3-compatible endpoint —
  R2 in production) or `local` (an on-disk directory, `STORAGE_LOCAL_DIR`).
  There is no separate "in-memory" backend; the in-memory test profile is simply
  `local` pointed at a RAM-backed `emptyDir` (see [doc 12](12-in-cluster-e2e.md)).
- **Metadata.** Postgres is mandatory for the API server (SQLite is a test-only
  dev-dependency); the web server treats it as optional and degrades to an
  offline banner without it.
- **Secrets.** Production pulls `DATABASE_URL` and the R2 credentials from an
  External Secrets `ClusterSecretStore` (`dd-cluster-secrets`, path
  `dd/remote-dev/zed-secrets`). The `S3_ENDPOINT_URL` in the API Deployment is an
  account-scoped **placeholder that must be filled in** before a real R2 deploy.

## Migrations

Migrations are embedded in the API binary and run on boot when `AUTO_MIGRATE=true`
(`Migrator::up`). The production Deployment sets `AUTO_MIGRATE=false` (with
`replicas: 2`) so two replicas don't race the migrator at rollout — migrations
are applied out of band. The single-replica test profile flips it back to `true`
so the stack is self-migrating. Note: there is no migration `Job`/initContainer
in `k8s/`, so with `AUTO_MIGRATE=false` the migration must be applied
explicitly (or by momentarily running one migrating replica).

## Operational learnings (bugs the deploy surfaced)

Two correctness bugs were found by running the stack under a real cluster + the
in-cluster e2e ([doc 12](12-in-cluster-e2e.md)), and fixed:

- **Concurrent first-publish lost versions.** When several `zed publish` calls
  raced to create the *same new package*, only one or two of N distinct versions
  landed. `upsert_package` did find-then-insert, and the racers that lost the
  `(org_id, name)` unique index returned a conflict — which, inside the publish
  transaction, *aborts the transaction* and drops the racer's otherwise-valid
  version (the CLI does not retry). Fixed with an atomic
  `INSERT … ON CONFLICT (org_id, name) DO UPDATE`, which never violates the
  constraint and so never aborts the txn; a duplicate *version* still conflicts
  correctly at the version insert (immutability). Regression-guarded by
  `api-registry.spec.ts`.
- **Web server stuck offline after a cold start.** The web server connected to
  Postgres once at boot and, on failure, fell back to offline mode permanently.
  Because it never crashes, Kubernetes never restarts it — so a web pod that
  started before Postgres was ready served the empty-state banner forever. Fixed
  with a bounded retry on the initial connect (`DB_CONNECT_MAX_WAIT_SECS`,
  default 30s); once the pool exists, sqlx transparently re-establishes dropped
  connections. If Postgres is unreachable past the deadline the server still
  boots (degraded) rather than never binding. (The API server avoids this class
  of bug only because it *exits* on a failed connect and CrashLoopBackOff
  retries it.)

## Status: implemented

The Layer-2 `k8s/` manifests, the `k8s-cluster` tenant registration, and the
reproducible images all exist and have been deployed and driven end to end on a
throwaway cluster via the in-cluster e2e ([doc 12](12-in-cluster-e2e.md)) —
including an Argo CD app-of-apps sync, pod-failure recovery, and self-heal. The
production R2 endpoint and the ESO-backed secrets are the remaining
environment-specific wiring.
