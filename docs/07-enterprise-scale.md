# 7. From concept to enterprise-grade

**Issue:** what does zed-pkg need so a team of 50 developers can use it across
a monorepo — executing binaries, and not filling their hard drives?

Four capabilities, and where each stands:

## 1. Disk efficiency at scale (implemented)

One content-addressed store per machine ([1](01-cas-and-symlinks.md)); every
project symlinks in. 50 developers × N projects with heavy overlap store each
dependency **once** per machine. `zed store status` reports usage (store,
download cache, and build cache); `zed store prune` garbage-collects artifacts
no live project references (tracked in `refs.json`); `zed cache clean` drops
downloads; and `zed gc [--older-than 90d] [--dry-run]` is an age-aware LRU
sweep that removes store entries that are *both* unreferenced by a live
project *and* unused past the cutoff — tracked with a `.last-used` marker
alongside the immutable `pkg/` tree — plus stale build-cache entries and
download caches
([`Store::gc`](https://github.com/zed-pkg/zed-cli/blob/main/src/store.rs)).
Everything it removes is content-addressed and re-fetchable.

## 2. Deterministic, concurrent installs (implemented)

`--frozen` installs exactly the locked sha256s
([4](04-lockfile-and-tag-immutability.md)); process locking makes parallel CI
runners and multiple terminals safe ([6](06-process-locking.md)). Same lock →
same bytes on every machine.

## 3. Executing binaries (implemented)

Packages declare executables in a `[bin]` table (command name → a path inside
the package). On install, each is hoisted into the project's
`zed_modules/.bin/<name>`
([`hoist_bins`](https://github.com/zed-pkg/zed-cli/blob/main/src/ops.rs)) — a
relative symlink in symlink mode, a real file in copy mode, so it works inside
container layers too — and `zed run <name> [args]` executes it with that
directory prepended to `PATH` — npx-style, scoped to the project's resolved
versions and without polluting the OS `PATH`. Adapter-linked layouts
([2](02-store-project-bridge-oci.md)) additionally let native runners find
dependency binaries where they expect them. Planned: an opt-in global shim on
`PATH` so top-level tools run without the `zed run` prefix.

## 4. Governance (implemented core; SSO/teams planned)

- **Namespaces & RBAC:** orgs are claimed and tokens are org-scoped
  ([`zed org claim`](https://github.com/zed-pkg/zed-cli)); each token carries a
  **role** — `owner`, `publisher`, or `reader` — set with
  `create-token --org <slug> --role <role>`. Publishing enforces it: a
  `reader` token gets `403 insufficient_role`, a token for another org is
  rejected, and unscoped admin tokens publish anywhere (npm-style granular
  tokens). See
  [`api-server/src/rbac.rs`](https://github.com/zed-pkg/zed-api-server.rs).
- **Audit log:** every mutation of published state — `publish`, `yank`,
  `unyank`, `org_claim` — appends a row naming the *token* that acted (its
  name and role, never its secret), the subject (`org/name@version`), and for
  a publish the artifact digest. Read it with
  `zed org audit <slug> [--limit N]` or `GET /v1/orgs/{org}/audit`. It is
  **owner-only**, since the trail names who acted; a `publisher`/`reader`
  token gets `403 insufficient_role`. The actor id is deliberately *not* a
  foreign key and the name/role are denormalized, so the trail survives the
  token being revoked or deleted. Recording is best-effort *after* the
  mutation commits: a failed audit write is logged loudly rather than
  converting a successful publish into an error the client would retry
  against an immutable version. See
  [`api-server/src/audit.rs`](https://github.com/zed-pkg/zed-api-server.rs).
- **Self-hosting:** the whole registry is two small Rust services + Postgres +
  any S3 bucket, so a company runs a private registry behind its firewall
  ([zed-infra](https://github.com/zed-pkg/zed-infra)); `ZED_PKG_REGISTRY`
  (or a `file://` mirror) repoints the CLI.
- **Planned:** multi-user teams with per-member roles, SSO, mirror/proxy of
  the public registry, and per-org storage quotas.

## Monorepo ergonomics (implemented)

Workspace mode: a root `.zpkg.toml` declares member globs in `[workspace]`
(`members = ["packages/*", "apps/*"]`). `zed install` walks up to find the
enclosing workspace and expands the globs
([`find_workspace`/`collect_members`](https://github.com/zed-pkg/zed-cli/blob/main/src/ops.rs)),
then resolves any dependency that matches a member by symlinking straight to
the member's **source** directory instead of going through the registry — so
an edit in one member is visible to its consumers immediately, while
non-member deps still resolve normally against the shared store and lock, and
zed's "one version per package" rule holds workspace-wide. Planned: a single
top-level lock spanning every member (today each member install writes its
own `.zpkg.lock`) and workspace-wide `zed run`.
