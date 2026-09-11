# 5. Source caching vs build caching

**Issue:** source code is universal, but compiled artifacts are tied to OS and
CPU architecture. Extracting a tarball is not enough when a package has a C
extension or native code — it has to be built for `linux-x64` in the
container but `darwin-arm64` on the laptop.

## Two distinct caches

zed-pkg deliberately separates them:

1. **Source store (implemented).** `~/.zed-pkg/store` is
   content-addressed by the **source artifact** sha256 and is
   platform-independent. This is what `zed install` populates and symlinks.
   It never contains compiled output, so it is safe to share across machines,
   architectures, and OCI base images.

2. **Build cache (implemented).** A package's optional `[build]` step
   (a `command` plus the `outputs` to keep) runs after extraction, and its
   compiled output is keyed by `(source sha256, platform)` — where `platform`
   is the `os-arch` pair from
   [`current_platform`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/paths.rs)
   — and stored separately at `~/.zed-pkg/builds/v1/<platform>/<sha>/pkg`
   ([`build_entry_rel`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/paths.rs)).
   A cache miss triggers a build; a hit reuses it. Because the key includes
   the platform, `linux-x86_64` and `macos-aarch64` results never collide, and
   a CI container and a laptop maintain independent build caches over the
   *same* source store.

## Why keep them separate

- The source store stays universal and reproducible — the disk-efficiency and
  provenance guarantees ([1](01-cas-and-symlinks.md),
  [4](04-lockfile-and-tag-immutability.md)) depend on source bytes being the
  same everywhere.
- Build outputs are inherently non-portable; mixing them into the source
  store would break cross-machine sharing and bloat images.
- It maps cleanly onto multi-stage Docker: restore the build cache with
  `--mount=type=cache,target=/root/.zed-pkg/builds/v1/<platform>`, install with
  copy-mode source ([2](02-store-project-bridge-oci.md)).

## Status: implemented

Both caches exist. The source store is content-addressed and
platform-independent, as before. `zed install --allow-build` (or a standalone
`zed build [--force]`) runs a dependency's `[build]` step inside an isolated
staging copy of its source
([`build_artifact`](https://github.com/zed-pkg/zed-cli/blob/main/src/ops.rs)),
installs its `[build-dependencies]` into that staging dir only (never into the
consumer's `zed_modules/`), then promotes the result into the build cache via
a temp dir and atomic rename. The cache is keyed by `(platform, source sha256,
build command)` under `~/.zed-pkg/builds/` — folding in the command means a
consumer override never collides with the package's own build — and the
immutable source store is never mutated. A per-`(platform, key)` lock
([`Store::build_lock`](https://github.com/zed-pkg/zed-cli/blob/main/src/store.rs))
serializes concurrent builds of the same artifact.

Builds run arbitrary package-author code, so they are opt-in behind
`--allow-build` (`ZED_PKG_ALLOW_BUILD=1`); without it the pristine source is
linked and a warning explains how to enable it. A consumer can replace or
supply a broken dependency's build with `[overrides.build."org/name"]`. Tests
assert the build runs once (the second install is a cache hit) and that a
consumer override replaces the upstream build. Planned: folding the toolchain
version and declared build inputs into the cache key.
