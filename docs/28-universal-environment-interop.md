# 28. Universal environment-manager interoperability

**Status:** RFC and staged implementation plan for `DEN-1420`.<br>
**Related:** `DEN-1411`, `DEN-1413`, `DEN-588`, `DEN-591`, `DEN-100`.<br>
# 24. Universal environment-manager interoperability

**Status:** RFC and staged implementation plan for `DEN-1420`.  
**Related:** `DEN-1411`, `DEN-1413`, `DEN-588`, `DEN-591`, `DEN-100`.  
**First implementation slice:** `zed-interfaces` PR #10 introduces the shared
`EnvironmentPlan` contract and validation model; it is not considered shipped
until that PR and its generated-schema/lock follow-ups are reviewed and merged.

Zed is the package-management plane for `.zpkg.toml`, `.zpkg.lock`, registry
resolution, immutable package artifacts, and publication provenance. It should
interoperate deeply with developer-environment managers and OCI runtimes, but it
must not turn those tools into competing resolvers for the Zed dependency graph.

This document defines that boundary for Flox, Devbox, mise, asdf, Docker, and
Podman. The separate [Nix–Zed package interoperability design](23-nix-zed-interop.md)
remains authoritative for importing and exporting Nix packages and derivation
outputs.

## The boundary in one sentence

**Zed resolves packages; environment managers resolve toolchains and system
packages; OCI transports already-built outputs.**

A generated Flox or Devbox environment may run `zed install --frozen` during
activation. It must not translate every Zed dependency into a Flox, Devbox, or
Nix package and let a second resolver choose different versions. Likewise, mise
and asdf may select the exact Rust, Node.js, Zig, Python, Java, or other runtime
used by a Zed build, but they do not replace `.zpkg.lock`.

## Related interoperability surfaces

| Surface | Authority | Purpose |
| --- | --- | --- |
| Zed dependency graph | `.zpkg.toml` + `.zpkg.lock` | Resolve and install Zed packages |
| Native registry fan-out | `DEN-100`, doc 18 | Publish the same reviewed source to npm, crates.io, pub.dev, Maven, and other native registries |
| Nix package import/export | `DEN-1411`, doc 23 | Translate eligible immutable package artifacts and derivation outputs between Zed and Nix |
| Developer environments | `DEN-1420`, this document | Import/export exact toolchains and system packages for Flox, Devbox, mise, and asdf |
| OCI image export | `DEN-1420`, `DEN-588`, `DEN-591` | Package verified build outputs for Docker/Podman and OCI registries |
| Generated consumer manifests | `DEN-1413` | Make ordinary dependency installs durable by creating a minimal `.zpkg.toml` by default |

`zed env export devbox` and a Nix package export therefore do not mean the same
thing. The first writes a development environment around a frozen Zed install.
The second exports a package/derivation boundary with its own sealed adapter
record.

## Non-negotiable invariants

### One resolver per graph

- Zed requirements are resolved once and pinned in `.zpkg.lock`.
- Flox, Devbox, Nix, mise, and asdf never independently resolve Zed package
  requirements.
- Environment-manager package lists contain compilers, runtimes, linkers,
  system libraries, and developer tools—not copies of the Zed graph.
- A generated activation hook uses the fixed command `zed install --frozen`.
  Package authors cannot inject arbitrary shell commands into this adapter path.

### Exact resolved toolchains

An author may express a compatibility range, but a reproducible export records
one exact manager-native result. Frozen output rejects unresolved or moving
selectors such as:

- `latest`, `stable`, or `lts` without an immutable lock result;
- version prefixes such as `3`, `22`, or `prefix:1.22` without a lock result;
- mutable VCS references such as `main`, `master`, or a branch name;
- `ref:` values that are not immutable commit identifiers;
- machine-local `path:` runtimes unless the plan is explicitly local and
  non-portable;
- user or system configuration that was inherited without an explicit opt-in.

The authored requirement remains useful provenance. The environment lock keeps
both values:

```text
requirement = "^22.0"
resolved    = "22.11.0"
```

### Immutable publication

A published `{org, name, version, target}` is immutable. A retry is idempotent
only when source identity, adapter plan, output bytes, and recorded hashes match.
A same-version upload with different bytes is rejected rather than replacing the
existing object.

Yanking changes fresh-resolution visibility; it does not rewrite the artifact
that existing lockfiles reference.

### No hidden runtime dependency

- Ordinary `zed install`, `zed publish`, and `zed r2g` work without Flox,
  Devbox, mise, asdf, Nix, Docker, or Podman installed.
- An exported Nix package does not require Zed at application runtime.
- A scratch image does not require Zed or a shell at runtime.
- Manager-native validation is an adapter check, not a bootstrap dependency of
  the core CLI.

### Deterministic generated state

Generated files contain no timestamps, random IDs, host usernames, absolute
home paths, transient store paths, or secrets. Maps and set-like collections are
sorted. Repeating an export from the same normalized plan produces the same
bytes.

## Version policy

### Strict SemVer at interoperability boundaries

Zed currently supports `semver`, `calver`, and `opaque` package version schemes.
That remains useful for internal and non-SemVer ecosystems. Universal
interoperability does **not** delete CalVer or opaque versions from Zed.

Each adapter instead declares a version-eligibility profile:

- exports to npm, crates.io, and other SemVer-oriented destinations require a
  valid SemVer 2.0.0 package version;
- a calendar version is eligible only when its exact spelling is also valid
  SemVer and the destination accepts it without a lossy rewrite;
- an opaque version fails closed at a SemVer-only boundary;
- adapters never invent a new public version to make an invalid value fit.

Dependency requirements from npm, Cargo, and other ecosystems may be preserved
as authored requirements, while `.zpkg.lock` records the exact selected version
and immutable artifact hash.

### Build metadata is not a platform key

SemVer build metadata does not participate in precedence. Therefore:

```text
1.4.2+linux-arm64
1.4.2+linux-x86_64
```

are not safe registry-level identities for two platform artifacts. Zed records
platform identity separately:

```text
version  = "1.4.2"
platform = "aarch64-linux-musl"
digest   = "sha256:..."
```

A registry may expose architecture-specific package names when its native
convention requires that pattern, but the coordinated release still has one
semantic version. OCI uses per-platform descriptors and an image index. A
release-assets registry uses one release with separate target-named assets.

### Artifact identity is stronger than a version string

At minimum, an interoperable lock entry records:

- package or tool identity;
- authored requirement;
- exact resolved version;
- source URL and immutable revision when source-built;
- source/content checksum;
- platform constraints;
- selected adapter/provider/backend;
- generated-manifest digest;
- output digest for built or containerized results.

Human-readable versions express compatibility. Hashes and immutable revisions
establish byte identity.

## Shared environment model

`zed-interfaces` defines one schema-versioned `EnvironmentPlan` consumed by the
CLI, registry metadata, servers, SDKs, and tests. Individual adapters map between
their native files and this intermediate representation instead of translating
directly into one another.

The first contract slice has this shape conceptually:

```rust
struct EnvironmentPlan {
    schema: u32,
    tools: BTreeMap<String, ToolRequirement>,
    system_packages: BTreeMap<String, SystemPackageRequirement>,
    platforms: Vec<String>,
    activation: ActivationPolicy,
    sources: Vec<EnvironmentSource>,
}

struct ToolRequirement {
    requirement: String,
    resolved: Option<String>,
    provider: Option<String>,
    backend: Option<String>,
    source: Option<ImmutableSource>,
    checksums: Vec<Checksum>,
    platforms: Vec<String>,
}
```

Known managers, checksum algorithms, activation behavior, and validation modes
are typed enums. Free-form strings remain only where an external ecosystem is
open-ended.

### Desired state versus resolved state

`.zpkg.toml` may gain an optional author-facing section for desired toolchains:

```toml
[environment]
schema = 1

[environment.tools]
node = "^22.0"
zig = "0.13.0"
rust = "1.82.0"

[[environment.system-packages]]
name = "pkg-config"
requirement = "0.29.2"
```

This is proposed syntax, not the current manifest schema. It describes portable
intent and contains no machine-specific paths or secrets.

Resolved external identities belong in a backwards-compatible extension to
`.zpkg.lock` or a dedicated lock section governed by the same transactional
writer. For example:

```toml
[[environment.tool]]
name = "node"
requirement = "^22.0"
resolved = "22.11.0"
manager = "mise"
backend = "core"
platforms = ["aarch64-darwin", "x86_64-linux"]
sha256 = "..."

[[environment.source]]
manager = "mise"
path = "mise.toml"
lock_path = "mise.lock"
digest = "sha256:..."
```

The final schema must preserve old version-1 package lockfiles. Adding optional
fields may be backwards-compatible; a semantic change that an old client could
misinterpret requires a lockfile-version bump and migration.

### Canonical digest

`EnvironmentPlan::canonical_json_bytes()` returns a stable compact
serialization. It sorts map keys and set-like lists, preserves order only where
order has semantics, normalizes checksum spelling, and excludes comments and
presentation-only state.

`sha256(canonical_json_bytes)` is the environment-plan digest recorded beside
each generated adapter output. Verification compares normalized plans, not
incidental formatting.

### Validation modes

The shared contract distinguishes:

- `Authoring`: requirements may be ranges and resolved identities are optional;
- `FrozenPortable`: every identity is exact and immutable; local paths fail;
- `FrozenLocal`: every identity is exact and immutable, while explicit local
  paths are allowed and make the plan non-portable.

This prevents an authoring-time convenience from silently becoming release
provenance.

### Activation policy is typed

Activation is not an arbitrary string. The initial enum is intentionally small:

```text
None
FrozenInstall
```

`FrozenInstall` renders exactly:

```sh
zed install --frozen
```

Arguments that weaken integrity, permit mutable resolution, expose credentials,
or execute package-author hooks cannot be represented.

## CLI contract

The intended command family is:

```text
zed env import mise|asdf|devbox|flox
zed env export mise|asdf|devbox|flox
zed env verify [--manager mise|asdf|devbox|flox]
zed env plan [--json]

zed export container \
  --target aarch64-linux-musl \
  [--runtime docker|podman] \
  [--format dockerfile|oci-layout]
```

`zed init --devbox` or `zed init --flox` may later be compatibility shortcuts,
but they should delegate to `zed env export`. `zed init` authors a Zed package;
environment import/export deserves a composable namespace of its own.

### Import

Import reads manager files into an `EnvironmentPlan` and reports unresolved or
unsafe values. It does not write `.zpkg.toml` or `.zpkg.lock` unless the user
selects a documented write mode.

```text
--from <path>             explicit project file/root
--write                   persist normalized intent and resolved metadata
--include-parent-config   include checked-in parent-scope config
--include-global-config   include user/system config; non-portable and loud
--allow-local-paths       accept path runtimes; marks plan non-portable
--frozen                  require every identity to be immutable and resolved
```

The normal default is project-local, portable, and side-effect free.

### Export

Export derives native manager files from the normalized plan. It creates a
missing file or merges only fields Zed owns. It never truncates unrelated user
configuration.

```text
--out <path>
--check          report drift without writing
--force          replace only a previously Zed-generated conflicting value
--no-hook        omit the fixed activation hook
```

`--force` is not permission to destroy unknown content. A conflict involving
user-owned data remains an actionable error.

### Verify

Verification parses native files and lock/provenance state, rebuilds the
normalized plan, and compares its canonical digest with the Zed lock. It reports
the exact tool, package, path, and competing values rather than a generic
"environment changed" message.

Manager-native checks run when the executable is available:

- Devbox config/lock validation;
- Flox manifest validation and lock realization;
- mise lock generation/verification;
- asdf plugin and exact-version availability checks;
- Docker/Podman build and run for container fixtures.

Pure parser, generator, golden-output, and digest tests remain available without
those executables.

## Manager adapters

### mise

mise supports several project config paths and merges configuration from parent,
user, system, environment-specific, and local files. That is convenient for an
interactive shell and dangerous for a supposedly portable import.

The Zed adapter therefore:

1. discovers checked-in project files at and below the selected project root;
2. ignores `mise.local.toml`, home config, system config, environment variables,
   and parents above the selected root by default;
3. parses `[tools]`, explicit plugin sources, platform constraints, and lock
   data;
4. treats `mise.lock` as the preferred exact-version/checksum source;
5. rejects unresolved fuzzy selectors in frozen mode;
6. records source-file and lock digests.

`mise.toml` is the preferred export because it represents plugins, platforms,
and structured tool options. `.tool-versions` export is a narrower compatibility
format.

```toml
[tools]
node = "22.11.0"
zig = "0.13.0"
rust = "1.82.0"
```

The adapter does not automatically import arbitrary mise tasks, `postinstall`
commands, environment interpolation, or secrets. A future task adapter needs a
separate trust model.

### asdf

asdf standardizes runtime selection in `.tool-versions`, but that file alone
does not fully identify the plugin implementation interpreting a tool name. Two
developers can have the same version file and different plugin repositories or
revisions.

A frozen asdf import requires:

- exact release versions in `.tool-versions`;
- plugin source URL;
- immutable plugin commit;
- any tool-download checksum exposed by the plugin/backend;
- platform constraints for platform-specific artifacts.

Zed records plugin provenance in its environment lock. A Zed-owned sidecar may
support an asdf-native bootstrap workflow, but it never outranks `.zpkg.lock` as
the integrity record.

`.tool-versions` values such as `latest`, a fuzzy major, `ref:master`, or
`path:/home/user/tool` fail portable frozen verification unless separately
resolved to an immutable identity.

### Devbox

Devbox stores project configuration in root `devbox.json`. Its package list is
Nix-backed and supports versions, platform restrictions, and flake references.
Its shell `init_hook` runs when a shell or script environment starts.

Conceptual generated output:

```json
{
  "packages": [
    "nodejs@22.11.0",
    "zig@0.13.0"
  ],
  "shell": {
    "init_hook": [
      "zed install --frozen"
    ]
  }
}
```

Package spelling is determined by a versioned mapping table and locked by
Devbox. The illustrative names do not imply that every runtime has a one-to-one
Nix attribute or that a display version uniquely identifies an output.

The adapter preserves Devbox lock identity, selected Nixpkgs/flake revision,
package attribute, platform set, and output hashes. `latest` is never emitted in
frozen output.

Because JSON has no portable comment mechanism, generated ownership is recorded
in Zed lock metadata. A merge updates only package and hook entries whose prior
digest proves Zed generated them. Unknown packages, environment variables,
scripts, plugins, includes, and services are preserved.

### Flox

A path Flox environment stores its manifest and lock under `.flox/env/`.
`manifest.toml` is schema-versioned TOML; packages are declared in `[install]`,
and activation commands under `[hook]`.

Conceptual output:

```toml
version = 1

[install]
node.pkg-path = "nodejs_22"
node.version = "22.11.0"
zig.pkg-path = "zig"
zig.version = "0.13.0"

[hook]
on-activate = '''
  zed install --frozen
'''
```

The Flox manifest lock, catalog identity, selected outputs, supported systems,
and content/build hashes are adapter provenance. `pkg-path` plus a display
version is not treated as complete immutable identity.

When Flox is installed, export asks Flox to validate and realize the manifest so
its native lock is authoritative for Flox packages. Emit-only mode may write a
manifest for review, but the environment plan remains unresolved until a native
lock is produced and verified.

The adapter never imports arbitrary Flox hook/profile/service code as trusted
Zed configuration. During merge it recognizes only the exact fixed
frozen-install hook that Zed owns.

## Mapping tool names to Nix-backed packages

Flox and Devbox use Nix-derived catalogs. Runtime names in `.zpkg.toml`,
`mise.toml`, or `.tool-versions` do not always equal Nix package attributes.
Language distributions may be split across packages, version-suffixed, or
provided by flakes rather than Nixpkgs.

The mapping layer is therefore:

- explicit and schema-versioned;
- platform-aware;
- testable offline through fixtures;
- overridable with a pinned package/flake reference;
- recorded in adapter provenance;
- never inferred from a display name when multiple candidates exist.

A mapping update cannot silently change an existing lock. It affects fresh
resolution or an explicit environment update.

## Container and OCI export

### Static verification before `scratch`

`FROM scratch` is correct only when every runtime requirement is copied into the
image. Zed verifies the executable rather than assuming that a Zig target string
guarantees the final file is self-contained.

For Linux ELF, the initial verifier requires:

- no `PT_INTERP` dynamic-loader segment;
- no `DT_NEEDED` shared-library entries;
- architecture matching the requested target;
- executable permissions in the generated build context;
- no undeclared runtime files.

A binary needing CA certificates, timezone/locale data, shared libraries, a
language runtime, shell scripts, or dynamic plugins is not eligible for the
one-file scratch profile. The command fails with missing runtime classes and
suggests an explicit runtime bundle or minimal non-scratch base.

Mach-O and PE executables are not placed in Linux scratch images. WebAssembly is
a separate OCI artifact/runtime profile, not a native Linux executable.

### Deterministic Dockerfile

For a verified static executable:

```dockerfile
FROM scratch
COPY app /app
USER 65532:65532
ENTRYPOINT ["/app"]
```

The build context contains only the verified executable and deterministic
metadata requested by the selected format. Mode, ownership, and modification
time are normalized before hashing.

### Multi-platform output

Cross-compilation produces one output per target tuple:

```text
x86_64-linux-musl
aarch64-linux-musl
```

Each output has its own digest and OCI platform descriptor. Zed creates one OCI
image index for the semantic release version. Docker and Podman consume the same
OCI model; runtime wrappers are adapters, not different image identities.

### OCI provenance

Container metadata records:

- Zed package version and artifact SHA-256;
- source VCS URL, immutable commit, and tag;
- target tuple and detected architecture;
- environment-plan digest;
- per-platform layer/config/manifest digests;
- image-index digest;
- SBOM and attestation references when present.

A changed binary, Dockerfile, runtime bundle, platform descriptor, or provenance
record yields a different digest and cannot replace a same-version publication.

## Import, merge, and conflict policy

### Generated-file ownership

Every adapter records:

- native file path;
- digest before and after generation;
- normalized entries Zed owns;
- manager lock path and digest;
- generator schema/version.

On the next export:

1. unchanged files receive deterministic updates to owned entries;
2. unrelated fields are preserved;
3. equivalent normalized edits are accepted;
4. semantic conflicts stop with both values shown;
5. files are never replaced wholesale merely to avoid a merge.

### Multiple managers in one repository

A repository may intentionally keep both mise and Devbox files. Zed does not
require one global winner. It verifies overlapping tools and reports divergence:

```text
node:
  mise.toml   -> 22.11.0
  devbox.json -> 20.18.1
```

Non-overlapping capabilities are allowed. mise may select runtimes while Devbox
supplies a system library. The plan records ownership of each resolved identity.

### Secrets and local state

Adapters never copy values from `.env`, Flox secrets, Devbox/Jetify secrets,
credential helpers, user-global variables, or shell history into Zed manifests
or locks. Existing secret-source references may be preserved, but secret values
are out of scope and redacted from diagnostics.

## Offline and cache behavior

A complete workflow separates resolution from restoration:

1. online resolution writes `.zpkg.lock` and manager-native locks;
2. caches store artifacts by content hash;
3. frozen install verifies hashes without graph re-resolution;
4. an offline canary restores environment and Zed packages from populated
   caches;
5. removing or mutating one object proves missing-object/tamper failure.

A missing locked object never falls back to a newer compatible version.

## Security and trust model

Environment files can contain executable hooks, plugins, VCS sources, local
paths, and extension points. Import is data parsing, not blanket trust.

Initial safe subset:

- exact tool/system-package requirements;
- immutable package/flake/plugin sources;
- platform constraints;
- checksums and native lock identity;
- fixed Zed frozen-install activation.

Initial rejected or ignored subset:

- arbitrary hooks, profiles, tasks, services, and post-install scripts;
- secret values;
- mutable VCS refs;
- unpinned remote includes/plugins;
- local absolute paths in portable mode;
- network-dependent commands during frozen restore;
- config inherited invisibly from outside the project boundary.

Diagnostics distinguish unsupported, unsafe, and unresolved inputs.

## Test matrix

### Shared interfaces

- serialization and generated JSON Schema snapshots;
- deterministic canonical bytes and digest;
- stable ordering across maps/platform sets;
- exact/floating/mutable-reference classification;
- SemVer eligibility and CalVer/opaque rejection at SemVer-only boundaries;
- versions differing only in build metadata detected;
- old lockfile compatibility and migration tests.

### Parser and generator tests

For every manager:

- minimal valid project;
- non-sorted input order;
- platform-specific entries;
- exact pins and lock provenance;
- fuzzy/latest/mutable/path values;
- unknown fields preserved during merge;
- semantic conflict diagnostics;
- deterministic repeated export;
- import → export → import normalized equality;
- secrets and arbitrary hooks excluded;
- project-local versus parent/global scope behavior.

### Native-manager canaries

- Devbox validates and activates generated projects;
- Flox validates, locks, and activates generated environments;
- mise creates/verifies its lock and selects exact runtimes;
- asdf installs exact versions from pinned plugin revisions;
- each permits `zed install --frozen` without re-resolving the Zed graph.

### OCI canaries

- static `x86_64-linux-musl` succeeds;
- static `aarch64-linux-musl` succeeds under a matching/emulated runner;
- dynamically linked ELF fails before build;
- undeclared runtime-data dependency fails its smoke test;
- explicit runtime bundle succeeds and changes image digest;
- Docker and Podman produce equivalent normalized OCI content;
- image index selects the correct architecture;
- changed binary, metadata, or cached layer is rejected;
- exported image runs without Zed, a shell, or package manager.

## CI shape

Pull-request CI is credential-free:

```text
interface tests
  -> schema generation and drift check
  -> parser/generator golden tests
  -> manager-native validation matrix
  -> static/dynamic binary inspection fixtures
  -> Docker/Podman scratch smoke tests
  -> offline restore and tamper canaries
```

External actions/installers are pinned to immutable revisions or verified
checksums. Networked resolution is isolated from offline restoration. Release CI
publishes only after repeating checks against an immutable source tag.

## Delivery phases

### Phase 1: shared model and mise/asdf

- add `EnvironmentPlan`, source/checksum/platform types, validation, and
  canonical bytes;
- publish generated JSON Schema and cross-language fixtures;
- extend lock provenance compatibly;
- implement project-local mise and `.tool-versions` parsing;
- generate deterministic `mise.toml` and `.tool-versions`;
- add `zed env plan`, `import`, `export`, and `verify` scaffolding;
- add flags-2-env, completions, README, schema, and golden tests.

### Phase 2: Devbox and Flox

- add versioned Nix-backed tool mapping;
- generate and semantically merge `devbox.json` and Flox `manifest.toml`;
- preserve manager-native lock provenance;
- run native config/lock/activation canaries;
- prove fixed-hook and unknown-field preservation.

### Phase 3: static scratch and OCI

- add ELF inspection and target verification;
- generate deterministic scratch contexts/Dockerfiles;
- support Docker and Podman validation;
- generate OCI layouts and multi-platform indexes;
- record per-platform digests, SBOMs, and attestations.

### Phase 4: shared provenance with Nix package interop

- reuse immutable source, platform, checksum, output, and attestation types from
  doc 23 / `DEN-1411`;
- keep `zed env export ...` separate from package/derivation import/export;
- prove neither feature makes Nix mandatory for core Zed workflows.

### Phase 5: E2E and rollout

- add fixtures in `zed-pkg-test` and `zed-e2e`;
- test Linux/macOS and x86-64/ARM where runners permit;
- document Windows/WSL boundaries;
- publish migration guidance for hand-maintained manager files;
- enable adapters in client/SDK repositories after canaries pass.

## Decisions

1. Zed remains the only resolver for the Zed package graph.
2. Environment-manager interop uses a shared normalized IR and explicit
   adapters.
3. Strict SemVer is enforced where an external publishing contract requires it,
   not by deleting Zed's CalVer/opaque capabilities globally.
4. Build metadata never distinguishes platform artifacts.
5. Human versions are not immutable identity; revisions and hashes are recorded.
6. Project-local config is the default import boundary.
7. Arbitrary external hooks and tasks are not trusted or translated.
8. Scratch export fails closed unless runtime independence is proven or every
   required file is explicitly bundled.
9. Multi-platform OCI output uses one semantic release plus per-platform
   descriptors and digests.
10. Existing native files are merged semantically and never replaced wholesale.
