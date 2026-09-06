# 1. Content-addressable storage + symlinks

**Issue:** decouple dependency *fetching* from the language-specific *build*
by treating dependencies as a filesystem problem — a global cache plus
symlinks — rather than a language-runtime problem (the "Nix-like, but backed
by Git hosts" idea).

## Design

Fetching and building are separate phases:

1. **Fetch (universal).** `zed install` resolves semver against registry
   metadata and downloads each artifact **once** into a content-addressed
   store keyed by sha256:

   ```
   ~/.zed-pkg/store/v1/<aa>/<sha256>/pkg/    extracted, immutable
   ~/.zed-pkg/cache/<sha256>.tar.gz          the archive
   ```

   The two-char shard (`<aa>`) keeps directories small. The store is
   append-only and immutable: the same sha256 is the same bytes forever, so
   any number of projects and versions share one physical copy.

2. **Link (per project).** Each project gets symlinks under `zed_modules/`
   pointing into the store — never copies:

   ```
   myapp/zed_modules/acme/http-kit -> ~/.zed-pkg/store/v1/9f/9f3a.../pkg
   ```

3. **Build (language-specific).** The toolchain compiles from the linked
   sources exactly as if they were vendored.

Because step 1 is language-agnostic and content-addressed, a monorepo with
heavy dependency overlap downloads and stores each dependency once, not once
per project — the pnpm/Nix disk-efficiency win, without a language runtime in
the loop.

## Implementation

- Store + sharding: [`zed-cli/src/store.rs`](https://github.com/zed-pkg/zed-cli/blob/main/src/store.rs),
  `store_entry_rel()` in [`zed-interfaces/src/paths.rs`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/paths.rs).
- sha256 verification on extract; extraction via temp dir + atomic rename.
- Resolution + linking: `zed-cli/src/ops.rs` (`install`).

See also [2 — store/project bridge under OCI](02-store-project-bridge-oci.md).
