# 12. In-cluster e2e (kind + in-memory profile + Argo CD)

**Issue:** [Doc 10](10-e2e-testing.md) boots the servers as local processes —
enough to prove the API/web/CLI agree on one contract, but it never touches
Kubernetes. The things that actually break a deploy live *below* the
application: image builds, the GitOps wiring, secret plumbing, probe behavior,
pod-failure recovery, storage backends. Those need the stack running **inside a
cluster**, driven by the same suites. The `cluster/` harness in
[`zed-e2e`](https://github.com/zed-pkg/zed-e2e/tree/main/cluster) is that: a
throwaway [kind](https://kind.sigs.k8s.io) cluster running the registry with
**artifacts in memory** and no external dependencies, testable in one command.

## What it stands up

`cluster/manifests/` is a self-contained kustomization in namespace `zed`:

- **`zed-postgres`** — ephemeral Postgres (metadata only) on an `emptyDir`; db
  `zed_e2e` to match the harness DSN.
- **`dd-zed-api-server`** — the `:dev` image, `STORAGE_BACKEND=local` pointed at
  an **`emptyDir{medium: Memory}`** volume, so artifact blobs live in RAM (128Mi
  tmpfs, `noswap`) — the "store artifacts in memory for now" profile, no S3/R2.
  `AUTO_MIGRATE=true`, `ZED_VERIFY_TAGS=off` (fixtures have no real VCS tags),
  `NodePort 30080`.
- **`dd-zed-web-server`** — the `:dev` image pointed at the API NodePort,
  `NodePort 30081`.

`kind.yaml` maps host `48080→30080` and `48081→30081`, so the servers answer on
`http://127.0.0.1:48080` (API) and `:48081` (web) — the **same URLs the
local-process harness uses**, which is why the [doc 10](10-e2e-testing.md)
suites run unchanged against the cluster (`ZED_E2E_API_URL`/`ZED_E2E_WEB_URL`).

This is a deliberate **test profile**, not the production source of truth. Its
differences from the app repos' `k8s/` ([doc 11](11-kubernetes-deployment.md))
are exactly the throwaway-cluster adaptations: local `:dev` images
(`imagePullPolicy: IfNotPresent`, `kind load`ed — no registry), a plain `Secret`
instead of External Secrets, in-memory `local` storage instead of R2, an
ephemeral in-cluster Postgres instead of Supabase-over-egress, a single replica,
and `NodePort` instead of an nginx `Ingress`.

## The GitOps path

`cluster/up.sh --argocd` additionally installs Argo CD and deploys the stack
through an **app-of-apps** (`cluster/argocd/`): a root `Application` renders the
child `zed-inmemory` `Application`, which syncs `cluster/manifests` from GitHub.
It mirrors the production tenant shape ([doc 11](11-kubernetes-deployment.md))
with two test relaxations — the source repo is `zed-e2e` (it carries the
in-memory overlay), and the `AppProject` whitelists the `Namespace` cluster
resource because the overlay creates its own `zed` namespace (in production that
namespace is Layer-1). Argo CD is installed with `--server-side` apply: the
`ApplicationSet` CRD exceeds the client-side annotation size limit.

## Running

Prereqs on `PATH`: `docker`, `kind`, `kubectl`, `cargo` (+ `npm` for the full
suite). From `zed-e2e`:

```bash
npm run cluster:up          # build+load images, create kind, deploy, wait ready
npm run cluster:test-cli    # standalone CLI smoke against the cluster registry
npm run cluster:e2e         # the full doc-10 suite (Playwright+Puppeteer+Selenium+CLI)
npm run cluster:up:argocd   # instead of cluster:up — deploy via the Argo CD app-of-apps
npm run cluster:down        # delete the cluster
```

`cluster:test-cli` mints an org-scoped token **inside the cluster**
(`kubectl exec` into the API pod, which holds `DATABASE_URL`) and drives the
real publish lifecycle: publish → duplicate-publish rejected (immutability) →
find → install (materializes `zed_modules/` + a pinned `.zpkg.lock` from a
RAM-served artifact) → yank. `cluster:e2e` port-forwards the cluster Postgres to
`55432` so the harness's `create-token` (a local binary) mints tokens in the
cluster DB, then runs every doc-10 suite against the NodePorts.

## What it proves that local processes can't

- **Images build and run.** The Rust build + glibc-parity + toolchain-pin facts
  from [doc 11](11-kubernetes-deployment.md) are exercised for real; a
  regression there fails `cluster:up`.
- **GitOps reconciles.** `cluster:up:argocd` drives the app-of-apps to
  Synced/Healthy from GitHub, and Argo CD **self-heals** — deleting the web
  `Service` out from under it is restored within seconds.
- **Failure recovery.** Killing the API pod recovers to `db:true` with package
  metadata intact (Postgres survives), while the RAM artifact store comes back
  empty — the honest, expected trade-off of the in-memory profile: metadata is
  durable, artifact blobs are ephemeral (a pod restart loses them until
  re-published; production uses `s3`/R2 for durability).
- **Concurrency under a real database.** The `api-registry` suite's concurrent
  first-publish test found the package-creation race fixed in
  [doc 11](11-kubernetes-deployment.md), and guards it: before, a 4-way
  concurrent first-publish landed 1–2/4; after, 4/4.
- **Circular dependencies resolve, they don't loop.** The `circular-deps` suite
  publishes a genuine mutual pair — `pkg-a` ⇄ `pkg-b` (each depends on the
  other, publishable because publish does not validate dependency existence) —
  plus a transitive leaf `pkg-b → pkg-c`. `zed install` from either side of the
  cycle terminates, materializes all three into the flat content-addressed
  `zed_modules/`, and pins each exactly once in `.zpkg.lock`. The flat store
  (not recursively-nested `zed_modules`) is what makes the cycle a graph-dedup
  problem rather than an infinite directory walk.

## Status: implemented

The `cluster/` harness, the in-memory manifests, and the Argo CD app-of-apps all
exist and run green: the standalone CLI smoke, plus the full doc-10 suite
(Playwright + Puppeteer + Selenium + CLI lifecycle, now including
`cli-advanced`, `api-registry`, `api-validation`, and `circular-deps`) against
the cluster-hosted, GitOps-deployed stack.
