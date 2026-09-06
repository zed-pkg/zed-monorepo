# 23. Nix–Zed interoperability: sealed adapters and one resolution authority

**Status:** proposal for [DEN-1411](https://linear.app/denman/issue/DEN-1411/zed-pkg-nix-design-and-implement-bidirectional-package-publishing-and).
Nothing in this document is implemented merely because it is specified here.
The implemented foundations are the immutable Zed artifact/lock model, native
release planning and preflight, `zed develop` composition with a repository
flake, and pinned Nix development environments in selected repositories.

This document is about the **zed-pkg multi-language package manager**. It is
not a design for Zed Editor extensions, Home Manager's Zed Editor module, or
language-server installation inside the editor.

## Decision summary

The first interoperable release is intentionally asymmetric at the source
level and symmetric at the **immutable artifact boundary**:

- **Zed → Nix** exports an already resolved Zed package/release set as a
  deterministic standalone flake. Nix receives fixed artifact URLs and hashes;
  it does not re-run Zed's version resolver.
- **Nix → Zed** imports one explicitly selected, already realized Nix output by
  sealing its content and provenance into a normal immutable Zed artifact.
  Zed does not evaluate Nix during ordinary install.
- A normalized, versioned adapter record connects the two identities: Zed's
  artifact SHA-256 and Nix's output NAR hash. Neither hash substitutes for the
  other because importing or exporting is a content transformation.
- Nix is **not** added to `NativeRegistry`. Nix is a build/evaluation/store
  ecosystem with multiple outputs and systems, not one upload registry with a
  single package identity.
- The default policy is fail-closed. Mutable refs, missing locks, impure
  evaluation, dirty release inputs, unselected outputs, runtime store
  references, unknown adapter schema versions, or hash drift are errors.
- Ordinary Zed use never requires Nix, and a Nix package generated from a Zed
  artifact never requires Zed at runtime.

This gives both ecosystems a professional integration without pretending that
arbitrary Nix expressions and `.zpkg.toml` are equivalent languages.

## Existing invariants retained

The bridge must preserve, not replace, the existing contracts:

1. Zed installs are determined by immutable artifact bytes pinned in
   `.zpkg.lock`; installs do not follow mutable VCS refs. See
   [doc 4](04-lockfile-and-tag-immutability.md).
2. A polyglot release has one reviewed source commit and one release version,
   with isolated Zed targets and separately validated native package routes.
   See [doc 18](18-multi-registry-release-fanout.md).
3. Release planning is credential-free and deterministic; fixed preflight
   adapters do not accept arbitrary manifest commands.
4. Copy mode is the portable ownership boundary for containers and generated
   artifacts. A Nix build must never depend on the caller's mutable
   `$HOME/.zed-pkg` store.
5. The shared contract belongs in `zed-interfaces`; the CLI, registry, server,
   SDKs, and tests must consume one schema rather than inventing parallel
   metadata.

## Terminology

**Resolution authority** is the package manager whose lock decides a dependency
graph. Zed is the authority for a Zed-origin export. Nix is the authority for a
Nix-origin import. The adapter never lets both managers independently resolve
the same graph.

**Adapter record** is canonical JSON describing one translation, its inputs,
outputs, policy, hashes, system, selected output, and provenance. It contains no
arbitrary code or shell command.

**Sealing** means producing a deterministic Zed artifact from a realized Nix
output, then recording both the original NAR identity and the resulting Zed
artifact identity.

**Artifact export** packages immutable bytes for Nix without attempting a
source rebuild. It is the only required Zed → Nix mode in version 1.

**Source-build export** maps a source package to a typed Nix builder such as a
Rust or Node builder. It is useful, but it is a later adapter class because it
introduces another dependency lock and another build semantics boundary.

**Portable Nix output** is a selected output whose installed bytes do not refer
to other `/nix/store` objects at runtime. Version 1 Nix → Zed import supports
only this class.

## Goals

- Deterministic, reviewable Zed → Nix flake generation from frozen Zed inputs.
- Pinned, pure, policy-controlled Nix → Zed import with no mutable references.
- Schema-level mapping of identity, version, source, hashes, systems, outputs,
  licenses, dependencies, install layout, and provenance.
- Reproducible clean-room replay on Linux and macOS.
- Explicit binary-cache trust and signature metadata.
- Tamper detection across source locks, generated adapter metadata, Zed
  artifacts, Nix derivations, Nix outputs, and repacked artifacts.
- Useful diagnostics that explain exactly which portability or trust invariant
  failed.

## Non-goals for version 1

- Translating arbitrary Nix expressions into `.zpkg.toml`.
- Reimplementing the Nix evaluator, store, or build sandbox in Zed.
- Inferring a Nix source builder merely because a repository contains
  `Cargo.toml`, `package.json`, or another native manifest.
- Importing a runtime closure that still depends on arbitrary `/nix/store`
  paths.
- Silently choosing one output from a multi-output derivation.
- Treating a Nix store path as a portable content hash.
- Automatically opening an upstream Nixpkgs pull request.
- Accepting a mutable branch, channel, registry alias, dirty worktree, or
  unlocked local path in a reproducible release.
- Making a public Zed package from Nix metadata whose license and source
  availability are unknown.

## Why Nix is not a native registry route

`[publish.native]` and `[targets.<name>.native]` represent a canonical package
format and destination such as npm or crates.io. The native manifest remains
authoritative for package identity and version, and the route answers “where is
this already-defined package published?”

Nix has different dimensions:

- an installable is selected by flake reference and attribute path;
- evaluation produces a derivation graph;
- a derivation may produce multiple outputs;
- output availability depends on a target system and builders/substituters;
- binary caches distribute NARs but are not the only publication mechanism;
- overlays, standalone flakes, and Nixpkgs contributions have different review
  and maintenance policies.

Forcing this into `NativeRegistry` would lose systems, outputs, derivation
identity, lock provenance, and cache trust. The manifest therefore gains a
separate typed Nix export intent, while lock and publish metadata gain a
separate normalized Nix adapter record.

## The two one-way pipelines

### Zed → Nix

```text
.zpkg.toml + .zpkg.lock
          │
          │ zed interop nix plan export --frozen
          ▼
validated release/install plan
          │
          │ exact Zed artifacts, SHA-256, size, VCS provenance
          ▼
canonical adapter record
          │
          │ zed interop nix export
          ▼
standalone flake + locked nixpkgs input + fixed artifact derivations
          │
          ├── nix flake check --no-update-lock-file
          └── nix build --no-update-lock-file
```

Zed remains the resolution authority. Every Zed dependency must already be in a
valid lockfile. The exporter converts each locked package to a fixed artifact
input and emits a deterministic assembly plan. It must never translate a Zed
semver requirement into a Nix lookup.

### Nix → Zed

```text
immutable flake lock + exact attribute + system + output
          │
          │ pure evaluation under strict policy
          ▼
derivation identity
          │
          │ sandboxed realization or trusted substitution
          ▼
store output + NAR hash + references + signatures
          │
          │ portability and metadata gates
          ▼
deterministic Zed pack + canonical adapter record
          │
          ├── zed publish (optional)
          └── zed install --frozen (no Nix required)
```

Nix remains the resolution authority. Zed records the locked Nix input graph and
realized output identity; it does not flatten Nix dependencies into Zed semver
requirements.

## Normalized adapter model

The first implementation belongs in `zed-interfaces` as additive, versioned
Rust types with generated JSON schemas. A conceptual record follows. Field
names may change during contract review, but their semantics must not.

```json
{
  "schema": "zed.nix-adapter/v1",
  "direction": "nix-to-zed",
  "package": {
    "org": "acme",
    "name": "tool",
    "version": "1.2.3",
    "target": null
  },
  "nix": {
    "locked_ref": "<immutable locked flake reference>",
    "flake_lock_sha256": "<sha256 of exact flake.lock bytes>",
    "attribute": "packages.x86_64-linux.tool",
    "system": "x86_64-linux",
    "output": "out",
    "derivation_json_sha256": "<sha256>",
    "store_path": "/nix/store/<diagnostic-path>",
    "nar_hash": "sha256-<base64>",
    "nar_size": 12345,
    "references": [],
    "signatures": [],
    "nix_version": "<version>",
    "store_info_json_version": 2
  },
  "artifact": {
    "format": "tar.gz",
    "sha256": "<lowercase hex>",
    "size": 1234
  },
  "policy": {
    "profile": "strict-v1",
    "pure_evaluation": true,
    "import_from_derivation": false,
    "sandbox_required": true,
    "builder_network": "disabled",
    "dirty_source": false
  }
}
```

The Zed → Nix variant replaces the `nix` origin block with a `zed` origin block
containing registry, package, version, target, artifact SHA-256/size, VCS tag,
VCS commit, and the exact Zed lock hash. It then records the generated flake
bundle hash and, after verification, the resulting Nix output NAR hash for each
system.

### Canonical serialization

Adapter records are security inputs. The implementation must define one
canonical byte representation:

- UTF-8 and LF line endings;
- lexicographically sorted object keys and deterministically sorted arrays where
  order is not semantic;
- integers only for sizes and versions; no floating-point numbers;
- no wall-clock timestamp in the hashed core record;
- absent optional fields omitted rather than serialized as environment-specific
  empty values;
- lowercase hexadecimal for Zed SHA-256 and SRI form for Nix hashes;
- one explicit schema identifier and parser rejection of unknown major versions.

A human-facing attestation may add a timestamp outside the hashed core. The
core's digest is stored in publication metadata and `.zpkg.lock` adapter
provenance.

### Identity rules

- `org/name@version` remains the public Zed identity.
- A Nix attribute is an adapter selector, not a replacement package identity.
- Nix attribute normalization is deterministic and collision-checked. The
  generated flake exposes `packages.<system>.<normalized-name>` and retains the
  exact Zed identity under `passthru.zed`.
- Nix → Zed import requires explicit `--as <org>/<name>@<version>`. Metadata from
  Nix may validate that choice but cannot silently claim an organization.
- `store_path` is retained for diagnostics only. `nar_hash` is the portable
  content identity of a realized Nix output.

## Metadata mapping

| Zed concept | Nix representation | Rule |
| --- | --- | --- |
| `package.org` + `package.name` | generated attribute + `passthru.zed.package` | normalize only the attribute; preserve exact identity in metadata |
| `package.version` | `pname` / `version` and passthru | exact string after Zed validation; never infer from a tag |
| repository URL + VCS commit/tag | `passthru.zed.source` | preserve all three; commit is the immutable anchor |
| Zed artifact SHA-256 | fixed file hash | convert to the Nix hash representation without changing the bytes |
| `.zpkg.lock` | generated fixed inputs | one derivation per locked artifact; no Nix re-resolution |
| `package.license` | `meta.license` where mapped + exact passthru string | an unknown mapping is explicit; upstream mode fails until resolved |
| description/keywords | `meta.description` and passthru | presentation only, not identity |
| `bin` entries | `$out/bin` | paths must already satisfy Zed's safe-relative-path rules |
| target language/ecosystem | `passthru.zed.target` | no builder inference in artifact mode |
| declared systems | `packages.<system>` / `meta.platforms` | systems must be explicit; never claim all platforms from one successful build |
| Nix output name | imported adapter record | explicit `--output`; no first-output fallback |
| Nix NAR hash/size/references | imported origin provenance | query after realization and verify before packing |
| cache signatures | adapter trust evidence | record key identity and verification result, never private keys |

## Zed → Nix export contract

### Required inputs

A reproducible export requires:

- a validated `.zpkg.toml`;
- a valid `.zpkg.lock` when the package has dependencies;
- `--frozen`, with no manifest/lock drift;
- exact source commit and matching release tag for publishable output;
- explicit target system(s);
- an approved, committed Nixpkgs lock template or exact immutable Nixpkgs
  revision plus NAR hash;
- a clean output directory.

Manifest-only dependency resolution is forbidden. A dependency-free package may
export without a lock only when the plan proves the graph is empty.

### Version 1 export classes

1. **Data/archive package — supported.** Install the exact artifact tree under
   `$out/share/zed-pkg/<org>/<name>`.
2. **Prebuilt executable package — supported.** Install the exact artifact tree
   and expose validated manifest `bin` entries under `$out/bin`.
3. **Zed dependency graph — staged support.** Convert every locked artifact to a
   fixed input and assemble the same copy-mode layout without a mutable user
   store or network access in the builder.
4. **Native source build — deferred.** Rust, Node, Dart, and other builders need
   typed, ecosystem-specific lock mappings. Presence of a native manifest is
   insufficient.
5. **Package with an arbitrary `[build]` shell command — reject in strict
   artifact export unless the published artifact already contains the required
   built output.** The exporter does not copy an unchecked command into Nix.

### Generated standalone flake

The generated bundle contains, at minimum:

```text
flake.nix
flake.lock
nix/package.nix
zed-nix-adapter.json
README.md
```

Properties:

- no timestamp, hostname, username, absolute workspace path, or random value;
- immutable Nixpkgs input in `flake.lock`;
- fixed artifact URLs and hashes only;
- `packages.<system>.<attribute>` and `packages.<system>.default`;
- `checks.<system>` that validate adapter metadata and installed layout;
- `passthru.zed` containing exact identity and provenance;
- no dependency on the Zed CLI in the installed output;
- no network access in the derivation after fixed inputs are fetched;
- byte-identical generated files for identical inputs.

A Zed-managed overlay may import these generated packages later. The standalone
flake is the primary artifact because it is reviewable, independently testable,
and does not require a centralized index.

### Publication destinations

`export` and `publish` remain distinct operations:

- **standalone flake:** write a local/repository bundle;
- **Zed overlay/index:** add a reviewed generated entry to a maintained flake;
- **binary cache:** copy successfully built outputs to an explicitly configured
  store and record signatures/cache policy;
- **Nixpkgs:** generate a review aid only. Licensing, source availability,
  maintainership, style, supported systems, and upstream review remain human
  gates.

No command automatically submits to Nixpkgs in version 1.

## Nix → Zed import contract

### Accepted selectors

A strict import names all of these:

- immutable locked flake reference or an already realized store path with a
  separate immutable provenance record;
- exact attribute;
- exact Nix system;
- exact output name;
- explicit Zed `org/name@version` destination;
- explicit metadata source: a validated `passthru.zedInterop` record or CLI
  fields for repository, license, description, and source revision.

Registry aliases, channels, branch-only refs, missing `flake.lock`, and implicit
current-system selection are rejected for publishable imports.

### Evaluation and realization policy

The strict profile requires:

- pure evaluation; never pass `--impure`;
- `allow-import-from-derivation = false`;
- no automatic acceptance of flake-provided Nix configuration;
- no dirty source tree for a publishable record;
- no lockfile update (`--no-write-lock-file` / `--no-update-lock-file` where the
  command supports it);
- sandboxed builds according to the platform's Nix implementation;
- builder network disabled;
- an explicit trust policy for substituted outputs and cache signatures;
- capture of the Nix version and JSON format version because several new-CLI
  JSON interfaces remain versioned/experimental.

Fetching immutable, hash-identified inputs is a separate preparation phase.
Clean-room CI must then replay evaluation/build with the lock unchanged and, for
its offline canary, with all required inputs already present and substituter
network access disabled.

### Realization evidence

After the selected output exists, the importer records:

- exact `flake.lock` bytes hash and locked reference;
- canonical hash of `nix derivation show` JSON for the selected derivation;
- selected system and output;
- store path for diagnostics;
- `narHash`, `narSize`, references, and signatures from versioned
  `nix path-info --json` output;
- configured substituter and trusted-key identities when a substitute was used;
- metadata source and its canonical hash;
- tool versions and strict-policy result.

Nix documents `narHash` as the hash of the filesystem object serialized as a
Nix Archive. That is the Nix-origin content identity. The Zed artifact SHA is
computed only after the output is translated into Zed's deterministic archive
format.

### Portability gate

A realized Nix output can contain hard-coded references to other Nix store
objects. Copying only that output into a Zed artifact would produce a package
that installs successfully but fails at runtime.

Version 1 therefore accepts only outputs whose runtime reference set is empty
after any documented self-reference is removed. The importer fails with the
exact referenced paths and suggests one of these follow-ups:

- choose a self-contained/static output;
- select another explicit output;
- add a future typed closure-bundling adapter;
- keep the package in Nix rather than claiming a portable Zed import.

The importer does not rewrite store paths, patch binaries heuristically, or hide
a closure in an opaque wrapper.

### Multi-output derivations

Every import requires one output name. A derivation with multiple outputs is not
an error by itself, but an omitted output is. Each selected output is evaluated
against the portability gate independently. Cross-output runtime references
fail in version 1.

The E2E fixture for a multi-output package must prove both behaviors: omission
fails with an actionable list of outputs, while an explicitly selected portable
output can proceed (or is rejected for its concrete references, not because the
adapter guessed).

### Metadata and licensing gate

Nix derivation metadata is not guaranteed to contain the legal/source fields a
public Zed registry requires. A publishable import requires:

- package version;
- repository/source URL and immutable source revision where applicable;
- license identifier or reviewed license expression;
- source-availability statement;
- selected systems and outputs;
- attribution/notice files preserved in the artifact.

A package may provide this through a simple JSON-compatible
`passthru.zedInterop` contract. Otherwise the importer requires explicit CLI
metadata and records its source. Missing or contradictory metadata fails before
publication. A development-only local pack may be allowed under a visibly
non-publishable policy profile, never by silently inventing values.

## Manifest and lockfile shape

The exact TOML spelling is finalized in `zed-interfaces`, but the separation of
intent and realization is normative.

### Export intent in `.zpkg.toml`

Illustrative single-package form:

```toml
[publish.nix]
mode = "artifact"
attribute = "acme-tool"
systems = ["x86_64-linux", "aarch64-linux", "aarch64-darwin"]
```

A polyglot target uses `[targets.<target>.nix]`. This section contains only
author intent: mode, attribute override, systems, and declared outputs. It does
not contain realized store paths, NAR hashes, commands, credentials, or cache
keys.

### Realization provenance in `.zpkg.lock`

The lock gains optional adapter records keyed by package/target/direction. Each
record includes the canonical adapter digest and the immutable origin fields
needed for frozen replay. Existing lockfiles without adapter records remain
valid. `zed install --frozen` never creates or refreshes an adapter record.

### Publication metadata

A published package may carry the adapter record and signed attestation as
metadata alongside the ordinary Zed artifact. The artifact SHA remains the
install identity. Registry APIs are additive; a registry that does not support
adapter metadata must still serve/install ordinary packages correctly.

## Proposed CLI surface

Use one explicit namespace rather than adding several unrelated top-level
verbs:

```text
zed interop nix plan export
zed interop nix export
zed interop nix plan import
zed interop nix import
zed interop nix verify
zed interop nix publish
```

`plan` is read-only and supports `--json`. `export` writes a deterministic
standalone flake. `import` realizes/seals a selected output and writes or
publishes a Zed artifact. `verify` validates hashes, policy, layout, and optional
clean-room replay. `publish` distributes an already verified export to an
explicit overlay/cache destination; it never combines planning, credential
lookup, lock updates, builds, and publication in one opaque step.

Representative strict workflows:

```sh
zed interop nix plan export --frozen --system x86_64-linux --json
zed interop nix export --frozen --system x86_64-linux \
  --nixpkgs-lock ./policy/nixpkgs.lock --out ./dist/nix
nix flake check ./dist/nix --no-update-lock-file
nix build ./dist/nix --no-update-lock-file
```

```sh
zed interop nix plan import '<locked-flake-ref>#<attribute>' \
  --system x86_64-linux --output out --as acme/tool@1.2.3 --json
zed interop nix import '<locked-flake-ref>#<attribute>' \
  --system x86_64-linux --output out --as acme/tool@1.2.3 \
  --out ./dist/acme-tool.zpkg.tar.gz
zed interop nix verify ./dist/acme-tool.zpkg.tar.gz --replay
```

Command names are part of the RFC review, but these behavioral boundaries are
not optional.

## Trust, signatures, provenance, and SBOMs

The adapter attestation has at least four digest subjects when both directions
have been exercised:

1. original Zed artifact SHA-256;
2. canonical adapter-record SHA-256;
3. generated flake-bundle digest and/or realized Nix output NAR hash;
4. repacked Zed artifact SHA-256 for Nix → Zed.

The statement also records source lock hashes, source revision, package
identity, system/output, tool versions, policy profile, and verification
results. Signing is separate from hashing. A future Sigstore/in-toto envelope
may sign the canonical statement without changing its core fields.

Binary-cache signatures are evidence only under an explicit trusted-key policy.
The adapter records key identities and verification outcomes, never signing
secrets. A substituted result without an acceptable signature is rejected when
the configured policy requires one.

Existing SPDX or CycloneDX documents are preserved and their hashes included.
The bridge must not label a file inventory as a complete dependency SBOM. Nix
closure metadata and a Zed dependency lock can inform a later merged SBOM, but
version 1 reports precisely which evidence was available.

## Failure matrix

| Condition | Strict behavior |
| --- | --- |
| mutable branch/channel/registry alias | reject before evaluation |
| missing or changed `flake.lock` | reject |
| dirty source for publishable operation | reject |
| Nix expression requires `--impure` | reject |
| import-from-derivation required | reject |
| build requires network | reject strict realization |
| flake requests unreviewed config | do not auto-accept; reject if required |
| output omitted on multi-output derivation | reject and list outputs |
| output has runtime store references | reject and list references |
| unsupported/unknown system | reject before build |
| Zed manifest/lock drift under `--frozen` | reject |
| Zed artifact hash mismatch | reject before Nix evaluation/build |
| NAR hash changes during replay | reject and mark provenance invalid |
| repacked Zed artifact hash changes | reject deterministic-pack failure |
| adapter record or schema is unknown/tampered | reject |
| missing license/source metadata | reject public publication |
| cache signature does not satisfy policy | reject substituted output |
| native Windows invocation in version 1 | reject with WSL/Linux guidance |

No case silently downgrades from strict to development mode.

## Systems and remote builders

Initial support is Linux and macOS. Native Windows is outside version 1; WSL is
treated as a Linux environment and produces a Linux system output.

An export may generate attributes only for systems explicitly declared by the
package and requested by policy. A local machine does not prove support for
other systems. Cross-system verification requires an appropriate local/remote
builder or a trusted substitute. The adapter records the system for every NAR
hash; hashes from different systems are distinct evidence, not interchangeable
variants.

## Testing strategy

### Shared-contract tests (`zed-interfaces`)

- parse/round-trip export intent and adapter records;
- canonical serialization and digest golden vectors;
- strict validation of systems, outputs, hashes, immutable refs, and schema
  versions;
- backward compatibility for manifests/locks without Nix metadata;
- generated JSON-schema drift checks;
- rejection of arbitrary command/config fields.

### CLI unit/integration tests (`zed-cli`)

- byte-identical generated flake bundle from identical inputs;
- stable attribute normalization and collision diagnostics;
- exact conversion between Zed hex SHA-256 and Nix SRI hash;
- frozen graph export without semver lookup;
- no credentials or inherited mutable registry state in plans;
- strict command construction: no `--impure`, no lock updates, IFD disabled;
- versioned parsing of Nix JSON and fail-closed unknown versions;
- explicit output selection and reference portability gate;
- dual-hash verification after repacking;
- clean error messages with no token/cache credential leakage.

### E2E fixtures (`zed-pkg-test` / `zed-e2e`)

At minimum:

1. no-build data package: Zed → Nix → build and Nix → Zed → frozen install;
2. self-contained Rust CLI: executable survives both translations and runs from
   a clean environment;
3. Node/TypeScript package: Zed → Nix artifact export, without pretending a
   native source rebuild has been implemented;
4. multi-output or platform-constrained Nix fixture: omitted output fails and
   explicit selection is evaluated correctly;
5. intentionally impure/unlocked expression: fails before a publishable adapter
   record exists;
6. closure-bearing dynamic binary: fails with exact runtime references;
7. tampered flake lock, derivation record, NAR, adapter JSON, Zed lock, and Zed
   artifact: each fails at its own boundary.

### CI evidence

A pinned, read-only workflow runs:

```text
contract/schema tests
  -> deterministic export twice and compare
  -> nix flake check --no-update-lock-file
  -> nix build --no-update-lock-file
  -> capture/verify NAR metadata
  -> strict import and deterministic pack twice
  -> local Zed publish
  -> zed install --frozen in a clean consumer
  -> remove mutable caches and repeat offline from approved caches
  -> tamper matrix
```

Linux and macOS canaries are separate because sandbox/build behavior and systems
differ. PR validation uses no publishing credentials. Cache publication is a
protected, post-verification release job with narrowly scoped credentials.

## Delivery order

1. **RFC and threat model** — this document; resolve command/schema naming and
   version-1 portability boundary.
2. **Contract first** — add export intent, adapter/provenance records, canonical
   serialization, validation, and JSON schemas in `zed-interfaces`.
3. **Read-only planning** — add `zed interop nix plan export/import` without
   builds, writes, credentials, or publication.
4. **Zed → Nix artifact export** — data and prebuilt-bin classes, deterministic
   standalone flake, Linux/macOS checks.
5. **Nix → Zed closure-free import** — strict evaluation/realization, metadata
   and portability gates, deterministic repack, frozen install.
6. **E2E and tamper canaries** — all required fixtures and offline replay.
7. **Overlay/cache publication** — reviewed Zed overlay plus explicit signed
   binary-cache policy.
8. **Typed source-build adapters** — one ecosystem at a time, each with a lock
   mapping and independent conformance tests.

The registry/server API changes only after the adapter record is stable and only
for metadata/attestation storage. Core Zed install/publish remains independent
of Nix throughout.

## Rollback and compatibility

- New manifest and lock fields are additive and optional.
- No existing release route changes meaning.
- A CLI without interop support continues ordinary Zed operations; it must not
  erase unknown adapter records when rewriting a newer lock format.
- Generated flakes are standalone outputs. Deleting one does not alter the Zed
  registry artifact or lock.
- Imported packages remain ordinary immutable Zed artifacts. Disabling future
  adapter APIs does not make already locked bytes unavailable.
- Registry migrations store adapter metadata separately from the artifact blob
  and can be rolled back without changing artifact identity.
- Any schema-major incompatibility requires an explicit migration command; no
  automatic reinterpretation.

## Review questions before contract implementation

These are the remaining decisions that must be closed in the RFC review rather
than improvised in code:

1. exact TOML names for export intent and lock adapter records;
2. canonical JSON algorithm and test vectors;
3. approved Nixpkgs lock governance and update cadence;
4. Nix attribute normalization and reserved-name policy;
5. minimum supported Nix version and accepted store-info JSON versions;
6. binary-cache trusted-key configuration and registry policy;
7. whether version 1 stores only deterministic tar output or also retains a NAR
   as an attached provenance artifact;
8. exact metadata required for development-only local imports versus public
   publication.

Everything else in the version-1 boundary—one resolution authority, immutable
locks, explicit system/output selection, closure-free portable imports, dual
hashes, no implicit impurity, and no runtime dependency on the other package
manager—is a normative decision of this proposal.
