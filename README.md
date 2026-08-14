# zed-monorepo

Pinned integration workspace for [zed-pkg](https://zpkg.tech). This repository
is both a Zed package envelope and a git-submodule workspace. The retained
repositories are pinned as real gitlinks under `apps/`, in the sibling layout
used by aggregate validation and parent-context container builds.

```
apps/
  zed-interfaces/       contract crate shared by the Rust services
  zed-lib-core/         canonical shared persistence and domain core
  zed-api-server.rs/    registry REST API
  zed-web-server.rs/    registry web UI (MASH)
  zed-clients/          seventeen maintained language targets, including C/C++/Zig, WASM, and TypeScript runtimes
  zed-sync/             offline-first sync engine
  zed-docs/             architecture and operator documentation
  zed-e2e/              browser and cross-service test suites
  zed-pkg.github.io/    marketing site (Astro)
```

The `zed-cli` and `zed-infra` repositories are independently owned release and
operations surfaces. They are deliberately **not** imported by this monorepo as
git submodules or Zed dependencies.

## One owner per repository

`.gitmodules` owns the retained sibling repositories. The root `.zpkg.toml`
therefore has no `[dependencies]` table: the same repository must never be
materialized once by Git and again by Zed. The Zed manifest supplies package
identity, install location, validation scripts, and publication policy without
creating a second dependency graph.

## Clone and synchronize

```sh
git clone --recurse-submodules https://github.com/zed-pkg/zed-monorepo.git
cd zed-monorepo

# After a plain clone, or whenever URLs change:
git submodule sync --recursive
git submodule update --init --recursive

# Zed understands and preserves the git-submodule ownership boundary:
zed install --git-submodules

# Use this only when intentionally reconciling an existing submodule checkout
# with Zed package metadata:
zed overtake --git-submodules
```

## Common tasks

```sh
make init       # sync and initialize every retained submodule
make pull       # advance retained submodules using their configured remotes
make validate   # enforce package, inventory, and gitlink invariants
make test       # run retained contract/service/client/sync tests
make build      # build the retained Rust services and TypeScript packages
make images     # build the api/web container images (parent-context)
make status     # show recursive pinned-submodule status
```

## Why siblings under `apps/`

The Rust services deliberately pin reviewed `zed-interfaces` and
`zed-lib-core` Git revisions in their Cargo manifests and lockfiles. The
monorepo gitlinks record the current exact portfolio release set without
silently rewriting those component-owned dependency pins. Keeping the sources
as siblings under `apps/` also supplies the parent-context inputs required by
the API container build:

```sh
make images
```

## Deterministic integration CI

Each component repo may test against the newest contract, but this monorepo is
the place that verifies one exact pinned combination. The integration workflow
initializes only the retained submodules, reports their SHAs, and tests the
contract, API server, and web server in their real sibling layout. CLI-driven
scenarios remain in the independently owned CLI/E2E release flow rather than
smuggling the CLI back into this workspace.

## Client matrix

`zed-clients` carries seventeen maintained language targets: C, C++, Dart,
Elixir, Erlang, Gleam, Go, Java, Kotlin, Node.js/TypeScript, PHP, Python, Ruby,
Rust, Swift, WASM, and Zig. The TypeScript package exposes explicit entry
points for Node.js, Deno, Bun, and edge runtimes.

## Portfolio inventory ratchet

`.gitmodules` is the executable source of truth for the exact sibling set.
[`scripts/check-portfolio-inventory.py`](scripts/check-portfolio-inventory.py)
verifies the README inventory, real `160000` gitlinks, the dependency-free Zed
package envelope, lockfile format, and the permanent exclusion of CLI/infra.

## License

MIT
