# 24. Deterministic Zed → Nix export bundles

**Status:** implementation contract for
[DEN-1508](https://linear.app/denman/issue/DEN-1508/zed-cli-nix-render-deterministic-standalone-flake-bundles-from-frozen).
Implementation is under review in
[`zed-pkg/zed-cli#69`](https://github.com/zed-pkg/zed-cli/pull/69), stacked on
the frozen planner in
[`zed-pkg/zed-cli#64`](https://github.com/zed-pkg/zed-cli/pull/64).
The reusable Nix helper boundary is independently ratcheted in
[`zed-pkg/zed-cli#73`](https://github.com/zed-pkg/zed-cli/pull/73), stacked
directly on the foundational fixed-output bridge in
[`zed-pkg/zed-cli#36`](https://github.com/zed-pkg/zed-cli/pull/36).
Nothing is shipped merely because it appears in this document.

This document narrows the Zed → Nix half of
[doc 23](23-nix-zed-interop.md) into an executable rendering contract. **Zed**
means the independent `zed-pkg` multi-language package manager, not the Zed text
editor.

## Decision

The export path is a sequence of separate authority boundaries:

```text
.zpkg.toml + .zpkg.lock
  -> frozen zed.nix-export-plan/v1
  -> pure zed.nix-flake-bundle/v1 rendering
  -> atomic no-clobber persistence
  -> locked Nix evaluation and realization
  -> final zed.nix-adapter/v1 evidence
  -> optional reviewed overlay or signed cache publication
```

Version 1 supports a strict, dependency-free, artifact-only package class. It
converts exact immutable Zed archive bytes into an ordinary Nix package. It does
not invoke Zed in a Nix builder, translate semver requirements, or infer a
source build.

The rules are:

1. `.zpkg.lock` remains the only resolution authority for a Zed-origin graph.
2. The planner decides eligibility; the renderer does not discover or resolve a
   workspace again.
3. Rendering is a pure function over explicit bytes. It performs no filesystem
   write, network request, registry access, credential lookup, Nix evaluation,
   store realization, or publication.
4. The approved `flake.lock` is copied exactly. Rendering never updates it.
5. A bundle receipt is not final Nix provenance. Final adapter evidence is
   emitted only after explicit realization.
6. Export and publication remain different commands and authorities.

## Inputs

The renderer accepts exactly three inputs.

### Frozen plan

The validated `zed.nix-export-plan/v1` carries exact package identity, package
class, Nix attribute, sorted systems, the single output `out`, artifact name,
format, SHA-256 and size, manifest and lock hashes, optional prebuilt-bin
mappings, an empty dependency list, and strict policy evidence.

The renderer revalidates structural and rendering-specific invariants, but does
not read `.zpkg.toml`, `.zpkg.lock`, a registry, or a project directory.

### Immutable artifact

The renderer receives the artifact bytes directly. They must be canonical
`tar.gz`, match the exact planned SHA-256 and size, use the filename
`<org>-<name>-<version>.tar.gz`, and contain regular payload files under the
archive root `package/`.

A prior stage may fetch or pack the bytes. The renderer retains no source URL or
transport credential.

### Approved Nixpkgs lock

Strict version 1 requires a version-7 `flake.lock` with canonical root `root`
and exactly one external input named `nixpkgs`. That input must identify
`github:NixOS/nixpkgs` at an exact lowercase hexadecimal revision, repeat that
revision in original and locked evidence, and include a valid SHA-256 SRI NAR
hash.

Mutable branches, indirect aliases, unlocked paths, extra inputs, divergent or
missing revisions, invalid hashes, unsupported versions, and ambiguous lock
shapes fail closed.

## Generated bundle

The pure renderer returns a lexically ordered map:

```text
flake.nix
flake.lock
package.nix
README.md
artifacts/<org>-<name>-<version>.tar.gz
metadata/plan.json
metadata/bundle.json
```

`flake.nix` imports only the pinned Nixpkgs input, creates packages for the
explicit systems, exposes the declared attribute plus a `default` alias, and
contains no resolver or registry lookup.

`flake.lock` preserves the supplied bytes exactly. Its byte SHA-256 and the
validated Nixpkgs revision and NAR hash are retained separately.

`package.nix` uses the immutable local archive as `src`, installs payload files
under `$out/share/zed-pkg/<org>/<name>/<version>`, and creates `$out/bin` links
only for declared files verified as regular, nonempty, and executable inside
the archive. It disables configure, build, fixup, stripping, and shebang
rewriting and runs no package-provided hook.

`metadata/plan.json` is exact canonical planner output.

`metadata/bundle.json` uses `zed.nix-flake-bundle/v1`. It records the exact plan
hash, exact lock hash, immutable Nixpkgs identity, a path-sorted SHA-256 and size
inventory for every generated file except itself, and one domain-separated
bundle hash.

The inventory excludes itself to avoid recursive hashing. The bundle hash covers
canonical paths, sizes, and raw file digests, not host ownership, permissions,
mtimes, output-directory names, or a platform-generated directory archive.

## Archive safety

Before rendering executable mappings, version 1 rejects:

- empty, absolute, non-UTF-8, NUL-containing, or backslash-containing paths;
- empty components, `.` and `..`, or entries outside `package/`;
- duplicate normalized paths;
- symlinks, hardlinks, devices, FIFOs, sockets, and unknown entry classes;
- unsupported special permission bits;
- excessive entry counts or declared unpacked size;
- an archive with no regular payload files;
- a planned bin absent from its exact path;
- an empty planned bin; and
- a planned bin without executable bits.

This is a structural installation-safety check, not a malware scanner. Package
trust still begins with publication policy and immutable artifact identity.

## Path and escaping policy

Generated paths and path-derived identity values use a conservative portable
ASCII subset. Version 1 rejects empty values, leading `.` or `-`, trailing `.`,
separators, traversal components, controls, whitespace, and shell
metacharacters.

Nix string values are escaped independently, including backslashes, quotes,
controls, and interpolation starts. Path validation is not a substitute for
string escaping.

## Reproducibility and privacy

Identical approved inputs must produce byte-identical maps on Linux and macOS.
Rendering must be independent of time, timezone, hostname, username, process
state, random state, workspace path, output path, file metadata, `$HOME`, XDG
state, the global Zed store, ambient registry settings, Nix store contents,
cache state, and environment secrets.

Adapter metadata is source-redacted. The renderer does not claim to remove
sensitive bytes intentionally placed inside a package payload; publication
policy must prevent that earlier.

## Persistence boundary

Persistence is deliberately later. The command layer must validate the complete
map, write through a restrictive sibling staging directory without following
links, flush required files and directories, verify the on-disk inventory, and
atomically rename to a previously absent destination. It must clean staging on
failure and never merge into or partially update an existing bundle.

An existing destination may be rejected or accepted only after proving it is
byte-identical. Silent overwrite is forbidden.

## Public Nix library evaluation boundary

The foundational install-shaped bridge exports reusable `fetchZedDeps` and
`mkZedPackage` helpers before the planner and pure renderer land. Their public
argument contract must remain executable and independently reviewable.

A flake-level evaluation check therefore:

- instantiates the default helper, an explicit credential-free HTTPS registry,
  an immutable path-valued registry, and explicit adapter/target routing;
- instantiates an ordinary `mkZedPackage` consumer and proves caller passthrough
  metadata and the exact verified dependency derivation remain exposed;
- rejects simultaneous `registry` and `registryPath` inputs;
- rejects adapter or target metadata containing `/nix/store/`; and
- uses a deliberately failing dummy Zed executable so `nix flake check
  --no-build` cannot silently cross from evaluation into execution.

This check is low-cost and pure. It is not evidence that the fixed-output
builder ran, that a recursive NAR hash matches, that an offline consumer built,
or that lock tampering was rejected. Those remain integration-canary duties.
Likewise, the fixed-output canary does not certify planner or renderer
reproducibility. Each layer owns one boundary.

## Nix execution boundary

After persistence, an explicit stage may prepare the already pinned Nixpkgs
input, then certify the bundle with lock updates disabled:

```console
nix flake archive --no-update-lock-file
nix flake check --offline --no-update-lock-file
nix build --offline --no-update-lock-file '.#<attribute>'
```

Production policy also requires pure evaluation, import-from-derivation
disabled, sandboxing, builder network disabled, no dirty source, explicit system
and output selection, and normalized machine-readable evidence.

The archive step is an explicit input-preparation boundary. The subsequent
checks must prove offline evaluation and realization.

## Final adapter evidence

`zed.nix-flake-bundle/v1` proves deterministic rendering, not realization. The
final `zed.nix-adapter/v1` record is created only after every selected
system/output has locked flake identity, derivation JSON digest, store path for
diagnostics, NAR hash and size, references, required signatures, Nix version,
store-info JSON version, source artifact identity, bundle digest, and strict
policy evidence.

These hashes identify different representations and are never substituted for
one another.

## Required tests

The implementation PR must use read-only CI with commit-pinned actions and no
branch-push or publication step.

The public helper layer first runs `nix flake check --no-build` on Linux and
macOS. It covers accepted argument forms, passthrough wiring, and fail-closed
assertions without executing Zed. The same workflow must then run the real
fixed-output canary so an evaluation-only success cannot mask a sandbox,
recursive-hash, retained-reference, offline-build, or tamper failure.

Pure renderer tests cover byte-identical repeated rendering, sorted unique
inventory, exact lock-byte preservation, data and prebuilt-bin package classes,
canonical JSON, escaping, no host or credential leakage, and inventory
revalidation.

Negative renderer tests cover artifact hash/size drift, unsupported formats,
dependency or source-build plans, outputs other than exactly `out`, unsorted
declarations, unsafe identities and paths, traversal, links, special entries,
archive limits, missing or non-executable bins, mutable or malformed locks,
unknown schemas, and post-render tampering.

Linux and macOS canaries render into temporary directories, prepare only the
pinned input, then run locked offline `nix flake check` and `nix build`. An
independent `zed-pkg-test` suite must later replay clean-room and tamper cases
outside the implementation repository.

## Merge order

1. Canonical shared adapter and manifest/lock types.
2. Foundational install-shaped fixed-output bridge.
3. Pure public-helper evaluation ratchet, kept orthogonal to the export stack.
4. Resolver-only frozen fetch and fixed-output artifact-bundle foundations.
5. Canonical export-plan schema and read-only planner.
6. Pure deterministic renderer.
7. Atomic persistence and existing-bundle verification.
8. Explicit realization and final adapter evidence.
9. Independent clean-room certification.
10. Reviewed overlay/index and signed-cache publication.

A passing child cannot compensate for a failing parent. When a parent moves,
stacked children are semantically synchronized and their exact-head gates rerun.
A test-only sibling should be retargeted after its parent lands instead of being
folded into an unrelated feature child merely to linearize the graph.

## Definition of done

DEN-1508 is complete only when code consumes the canonical planner contract,
all exact-head and inherited checks are terminal-successful, the renderer remains
side-effect-free, documentation and implementation agree, the PR is synchronized
and mergeable, and Linear links the issue, architecture document, implementation
PR, and test evidence.
