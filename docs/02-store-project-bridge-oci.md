# 2. The store <-> project bridge, and OCI

**Issue:** the symlink directory structure must bridge a global system cache
and an isolated project environment, satisfy multi-language publishing, and
survive OCI/container constraints.

## The bridge

```
GLOBAL (per machine)                     PROJECT (per checkout)
~/.zed-pkg/store/v1/<aa>/<sha>/pkg  <──  zed_modules/<org>/<name>   (symlink)
```

- The **store** is content-addressed, immutable, shared by every project.
- **`zed_modules/`** is the project's isolated view: only the packages this
  project resolved, at the versions its `.zpkg.lock` pins.
- Context-aware adapters additionally project the store into the layout a
  toolchain expects — `node_modules/@org/name` for Node, a generated
  `.zed/classpath` for the JVM — so native tools resolve dependencies
  without knowing zed exists. See
  [`zed-cli` adapters](https://github.com/zed-pkg/zed-cli/blob/main/src/ops.rs)
  (`--adapter auto|node|java`).

## OCI / containers

Symlinks into `$HOME` **break** when image layers are copied between stages
of a multi-stage build (the target of the link isn't in the layer). zed-pkg
handles this with an install mode:

```dockerfile
RUN --mount=type=cache,target=/root/.zed-pkg \
    zed install --frozen --install-mode copy
```

- `--install-mode copy` materializes real files into `zed_modules/` so the
  layer is self-contained across `COPY --from=…`.
- `--mount=type=cache` still deduplicates downloads across builds.
- `--frozen` replays `.zpkg.lock` exactly for reproducible layers.
- Artifacts are pre-pruned at publish time (no tests/CI/README), so images
  stay small without extra cleanup.

The CLI test suite asserts copy-mode installs contain **zero** symlinks and
runs the whole flow inside a clean container
([`scripts/container-smoke.sh`](https://github.com/zed-pkg/zed-cli/blob/main/scripts/container-smoke.sh),
`copy_mode_is_container_safe`).

## Multi-language publishing

One `.zpkg.toml` describes any package; pruning rules are language-aware
(strip `__tests__`, `*_test.go`, `src/test/**`, etc.) so a Node, Python, Go,
Rust, or JVM package all publish lean. See
[`zed-interfaces/src/excludes.rs`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/excludes.rs).
