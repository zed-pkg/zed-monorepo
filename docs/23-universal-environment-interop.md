# 23. Universal environment-manager interoperability

Status: RFC / implementation plan  
Linear: `DEN-1420`  
Related: `DEN-1411`, `DEN-1413`, `DEN-588`, `DEN-591`, `DEN-100`

Zed is the package-management plane for `.zpkg.toml`, `.zpkg.lock`, registry
resolution, immutable package artifacts, and publication provenance. It should
interoperate deeply with developer-environment managers and OCI runtimes, but it
must not turn those tools into competing resolvers for the Zed dependency graph.

This document defines that boundary for Flox, Devbox, mise, asdf, Docker, and
Podman. It also explains how the work composes with the separate Zed ↔ Nix
package-import/export design in `DEN-1411`.

## The boundary in one sentence

**Zed resolves packages; environment managers resolve toolchains and system
packages; OCI transports already-built outputs.**

A generated Flox or Devbox environment may run `zed install --frozen` during
activation. It must not translate every Zed dependency into a Flox, Devbox, or
Nix package and let a second resolver choose different versions. Likewise, mise
and asdf may select the exact Rust, Node.js, Zig, Python, Java, or other runtime
used by a Zed build, but they do not replace `.zpkg.lock`.

## Related interoperability surfaces

These surfaces share provenance primitives but have different semantics:

| Surface | Owner | Purpose |
| --- | --- | --- |
| Zed dependency graph | `.zpkg.toml` + `.zpkg.lock` | Resolve and install Zed packages |
| Native registry fan-out | `DEN-100`, doc 18 | Publish the same reviewed source to npm, crates.io, pub.dev, Maven, and other native registries |
| Nix package import/export | `DEN-1411` | Translate eligible immutable package artifacts and derivation outputs between Zed and Nix |
| Developer environments | `DEN-1420`, this document | Import/export exact toolchains and system packages for Flox, Devbox, mise, and asdf |
| OCI image export | `DEN-1420`, `DEN-588`, `DEN-591` | Package verified build outputs for Docker/Podman and OCI registries |
| Generated consumer manifests | `DEN-1413` | Make ordinary dependency installs durable by creating a minimal `.zpkg.toml` by default |

`zed env export devbox` and `zed export nix` therefore do not mean the same
thing. The first writes a development environment around a frozen Zed install.
The second, as designed in `DEN-1411`, exports a package or derivation boundary.

## Non-negotiable invariants

### One resolver per graph

- Zed requirements are resolved once and pinned in `.zpkg.lock`.
- Flox, Devbox, Nix, mise, and asdf never independently resolve Zed package
  requirements.
- Environment-manager package lists contain compilers, runtimes, linkers,
  system libraries, and developer tools—not copies of the Zed graph.
- A generated activation hook uses the fixed command `zed install --frozen`.
  The manifest cannot inject an arbitrary package-author shell command into an
  environment-manager activation path.

### Exact resolved toolchains

An author may express a range or compatibility requirement, but a reproducible
export records one exact resolved identity. Frozen output rejects unresolved or
moving selectors such as:

- `latest`, `stable`, or `lts` without a resolved immutable identity;
- version prefixes such as `3`, `22`, or `prefix:1.22` without a lock result;
- mutable VCS references such as `main`, `master`, or a branch name;
- `ref:` values that are not immutable commit identifiers;
- machine-local `path:` runtimes unless the path is explicitly marked local and
  the export is declared non-portable;
- manager configuration inherited from a user or system scope unless the user
  explicitly asks Zed to include it.

The requirement remains useful provenance. The lock records both values:

```text
requirement = "^22.0"
resolved    = "22.11.0"
```

### Immutable publication

A published `{org, name, version, target}` is immutable. A retry is idempotent
only when the source identity, artifact bytes, and all recorded hashes match.
A same-version upload with different bytes is rejected rather than replacing
the existing object.

Yanking changes fresh resolution visibility; it does not rewrite the artifact
that existing lockfiles reference.

### No hidden runtime dependency

- Ordinary `zed install`, `zed publish`, and `zed r2g` work without Flox,
  Devbox, mise, asdf, Nix, Docker, or Podman installed.
- An exported Nix package does not require Zed at application runtime.
- A scratch image does not require Zed or a shell at runtime.
- Manager-native validation is an optional adapter check, not a bootstrap
  dependency of the core CLI.

### Deterministic generated state

Generated files contain no timestamps, random IDs, host usernames, absolute
home paths, transient store paths, or secrets. Maps and set-like collections
are sorted. Repeating an export from the same normalized plan produces the same
bytes.

## Version policy

### Strict SemVer at interoperability boundaries

Zed currently supports `semver`, `calver`, and `opaque` package version schemes.
That remains useful for internal and non-SemVer ecosystems. Universal
interoperability does **not** require deleting CalVer or opaque versions from
Zed.

Instead, each adapter declares a version-eligibility profile:

- exports to npm, crates.io, and other SemVer-oriented destinations require a
  valid SemVer 2.0.0 package version;
- a calendar version is eligible only when its exact spelling is also valid
  SemVer and the destination accepts it without a lossy rewrite;
- an opaque version fails closed at a SemVer-only boundary;
- adapters must never silently invent a new public version to make an invalid
  value fit.

Dependency requirements from npm, Cargo, and other ecosystems may be preserved
as authored requirements, but `.zpkg.lock` records the exact selected version
and immutable artifact hash.

### Build metadata is not a platform key

SemVer build metadata does not participate in version precedence. Therefore:

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

Human-readable versions remain important for compatibility. Hashes and
immutable revisions establish byte identity.

## Shared environment model

`zed-interfaces` should define one schema-versioned `EnvironmentPlan` used by
the CLI, registry metadata, servers, SDKs, and tests. Individual adapters map
between their native files and this intermediate representation instead of
translating directly into one another.

A conceptual model is:

```rust
struct EnvironmentPlan {
    schema: u32,
    tools: Vec<ToolRequirement>,
    system_packages: Vec<SystemPackageRequirement>,
    activation: ActivationPolicy,
    platforms: Vec<PlatformConstraint>,
    provenance: Vec<EnvironmentSource>,
}

struct ToolRequirement {
    name: String,
    requirement: String,
    resolved_version: Option<String>,
    provider: Option<String>,
    backend: Option<String>,
    source: Option<ImmutableSource>,
    checksums: Vec<Checksum>,
    platforms: Vec<PlatformConstraint>,
}
```

The actual Rust types should use enums for known managers, source kinds,
checksum algorithms, activation policies, and platform families. Free-form
strings are retained only where an external ecosystem is open-ended.

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

This section is a proposal, not current schema. It describes portable intent.
It must not contain machine-specific resolved paths or secrets.

Resolved external identities belong in a backwards-compatible extension to
`.zpkg.lock` or in a dedicated lock section governed by the same transactional
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
fields may be backwards-compatible; a semantic change that old clients could
misinterpret requires a lockfile-version bump with an explicit migration.

### Canonical digest

`EnvironmentPlan::canonical_bytes()` provides one stable serialization for
hashing. It sorts keys and set-like lists, preserves order only where the order
has semantics, uses normalized platform and checksum spellings, and excludes
presentation-only comments.

`sha256(canonical_bytes)` is the environment-plan digest recorded beside each
generated adapter output. Verification compares normalized plans, not incidental
formatting in user-managed files.

### Activation policy is typed

Activation is not an arbitrary string. The initial enum is intentionally small:

```text
None
FrozenInstall
FrozenInstallIfLockPresent
```

The default generated policy is `FrozenInstall`, rendered as exactly:

```sh
zed install --frozen
```

Arguments that weaken integrity, allow mutable resolution, expose credentials,
or execute package-author hooks cannot be represented in the environment plan.

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
but they should delegate to `zed env export`. `zed init` primarily authors a
Zed package; environment import/export deserves a composable namespace of its
own.

### Import

Import reads manager files into an `EnvironmentPlan` and reports unresolved or
unsafe values. It does not write `.zpkg.toml` or `.zpkg.lock` unless the user
selects the documented write mode.

Important options:

```text
--from <path>             explicit project file/root
--write                   persist the normalized intent and resolved metadata
--include-parent-config   include checked-in parent-scope config
--include-global-config   include user/system config; non-portable and loud
--allow-local-paths       accept path runtimes; marks the plan non-portable
--frozen                  require every identity to be immutable and resolved
```

The normal default is project-local, portable, and side-effect free.

### Export

Export derives native manager files from the normalized plan. It creates a
missing file, or merges only fields Zed owns. It never truncates unrelated user
configuration.

Important options:

```text
--out <path>
--check          report drift without writing
--force          replace only a previously Zed-generated conflicting value
--no-hook        omit the fixed activation hook
```

`--force` is not permission to destroy unknown content. A conflict involving
user-owned data remains an actionable error.

### Verify

Verification parses the native files and their lock/provenance state, rebuilds
the normalized plan, and compares its canonical digest with the Zed lock. It
reports the exact tool, package, path, and competing values rather than a generic
"environment changed" message.

Manager-native validation runs when the executable is available:

- Devbox config/lock validation;
- Flox manifest validation and lock realization;
- `mise lock`/lock verification;
- asdf plugin and exact-version availability checks;
- Docker/Podman build and run for container fixtures.

Pure parser, generator, golden-output, and digest tests remain available without
those executables.

## Manager adapters

## mise

mise supports several project config paths and merges configuration from parent,
user, system, environment-specific, and local files. That is convenient for an
interactive shell and dangerous for a supposedly portable import.

The Zed adapter therefore:

1. discovers checked-in project files at and below the selected project root;
2. ignores `mise.local.toml`, home config, system config, environment variables,
   and parent directories above the selected root by default;
3. parses `[tools]`, explicit plugin sources, platform constraints, and relevant
   lock data;
4. treats `mise.lock` as the preferred exact-version/checksum source;
5. rejects unresolved fuzzy selectors in frozen mode;
6. records the source file and lock digests.

`mise.toml` is the preferred export because it can represent plugins, platforms,
and structured tool options. `.tool-versions` export is available as a narrower
compatibility format.

Example deterministic output:

```toml
[tools]
node = "22.11.0"
zig = "0.13.0"
rust = "1.82.0"
```

The adapter does not automatically import arbitrary mise tasks, `postinstall`
commands, environment-variable interpolation, or secrets. A future task adapter
requires a separate trust model.

## asdf

asdf standardizes runtime selection in `.tool-versions`, but that file alone
does not fully identify the plugin implementation that interprets a tool name.
Two developers can have the same version file and different plugin repositories
or revisions.

A frozen asdf import requires:

- exact release versions in `.tool-versions`;
- the plugin source URL;
- an immutable plugin commit;
- any tool-download checksum exposed by the plugin/backend;
- platform constraints where the resolved artifact is platform-specific.

Zed records plugin provenance in its environment lock. It may also emit a
Zed-owned sidecar for users who want an asdf-native bootstrap workflow, but a
sidecar never outranks `.zpkg.lock` as the integrity record.

`.tool-versions` values such as `latest`, a fuzzy major version, `ref:master`, or
`path:/home/alex/tool` fail frozen verification unless separately resolved to an
immutable and portable identity.

## Devbox

Devbox stores project configuration in root `devbox.json`. Its package list is
Nix-backed and supports package versions, platform restrictions, and flake
references. Its shell `init_hook` runs when a shell or script environment starts.

A generated file has this conceptual shape:

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

Package spelling is determined by a versioned mapping table and then locked by
Devbox. The illustrative `nodejs`/`zig` names are not permission to guess that
every runtime has a one-to-one Nix attribute or that a human version uniquely
identifies a Nix output.

The adapter must preserve the Devbox lock identity, selected Nixpkgs/flake
revision, package attribute, platform set, and output hashes. `latest` is never
emitted in frozen output.

Because JSON has no portable comment mechanism, generated ownership is recorded
in Zed lock metadata rather than hidden comments. A merge updates only package
and hook entries whose previous digest proves Zed generated them. Unknown
packages, environment variables, scripts, plugins, includes, and services are
left untouched.

## Flox

A path Flox environment stores its manifest and lock under `.flox/env/`.
`manifest.toml` is schema-versioned TOML; packages are declared in `[install]`,
and activation commands are declared under `[hook]`.

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

The Flox manifest lock, catalog identity, selected package outputs, supported
systems, and content/build hashes are part of adapter provenance. Zed does not
pretend that `pkg-path` plus a display version is a complete immutable identity.

When Flox is installed, export asks Flox to validate and realize the manifest so
its native lock is authoritative for Flox packages. Emit-only mode may write a
manifest for review, but the Zed environment plan remains unresolved until a
native lock is produced and verified.

The adapter never imports arbitrary Flox hook/profile/service code as trusted Zed
configuration. On merge, it recognizes only the exact fixed frozen-install hook
that Zed owns.

## Mapping tool names to Nix-backed packages

Flox and Devbox use Nix-derived package catalogs. Runtime names in `.zpkg.toml`,
`mise.toml`, or `.tool-versions` do not always equal Nix package attributes.
Examples include language distributions, split compiler/runtime packages,
version-suffixed attributes, and tools delivered by a flake rather than
Nixpkgs.

The mapping layer is therefore:

- explicit and schema-versioned;
- platform-aware;
- testable without network access through fixtures;
- overridable by an author with a pinned package/flake reference;
- recorded in adapter provenance;
- never inferred solely from a display name when more than one candidate exists.

A mapping update cannot silently change an existing lock. It affects a fresh
resolution or an explicit environment update.

## Container and OCI export

### Static verification before `scratch`

`FROM scratch` is correct only when every runtime requirement is copied into the
image. For the one-binary path, Zed first verifies the executable rather than
assuming that a Zig target string guarantees the final file is self-contained.

For a Linux ELF executable, the initial verifier requires:

- no `PT_INTERP` dynamic-loader segment;
- no `DT_NEEDED` shared-library entries;
- an architecture matching the requested target;
- executable permissions in the generated build context;
- no manifest-declared runtime files unless they are explicitly included.

A binary that needs CA certificates, timezone data, locale data, shared
libraries, a language runtime, shell scripts, or dynamically loaded plugins is
not eligible for the one-file scratch profile. The command fails with a list of
missing/declared runtime classes and suggests an explicit runtime bundle or a
minimal non-scratch base.

Mach-O and PE executables are not placed in a Linux scratch image. WebAssembly
is a separate OCI artifact/runtime profile rather than being mislabeled as a
native Linux executable.

### Deterministic Dockerfile

For a verified static executable, the generated Dockerfile is intentionally
small:

```dockerfile
FROM scratch
COPY app /app
USER 65532:65532
ENTRYPOINT ["/app"]
```

The build context contains only the verified executable and deterministic
metadata requested by the selected format. File mode, ownership, and modification
time are normalized before hashing.

### Multi-platform output

Cross-compilation produces one output per target tuple, for example:

```text
x86_64-linux-musl
 aarch64-linux-musl
```

Each output has its own digest and OCI platform descriptor. Zed creates one OCI
image index for the semantic release version. Docker and Podman consume the same
OCI model; runtime-specific command wrappers are adapters, not different image
identities.

### OCI provenance

Container metadata records:

- Zed package version and artifact SHA-256;
- source VCS URL, immutable commit, and tag;
- target tuple and detected binary architecture;
- environment-plan digest;
- per-platform layer/config/manifest digests;
- image-index digest;
- SBOM and attestation references when present.

A changed binary, Dockerfile, runtime bundle, platform descriptor, or provenance
record yields a different digest and cannot replace an existing same-version
publication.

## Import, merge, and conflict policy

### Generated-file ownership

Every adapter records:

- native file path;
- digest before and after generation;
- normalized entries Zed owns;
- manager lock path and digest;
- generator schema/version.

On the next export:

1. if the file is unchanged, update owned entries deterministically;
2. if unrelated fields changed, preserve them;
3. if a Zed-owned field changed to an equivalent normalized value, accept it;
4. if a Zed-owned field conflicts semantically, stop and show both values;
5. never resolve a conflict by blindly replacing the whole file.

This is the same semantic-merge principle used for repository conflicts: retain
user intent and combine compatible changes rather than choosing one side.

### Multiple managers in one repository

A repository may intentionally keep both mise and Devbox files. Zed does not
require one global winner. It verifies that their normalized toolchain plans are
compatible for overlapping tools and reports divergence such as:

```text
node:
  mise.toml   -> 22.11.0
  devbox.json -> 20.18.1
```

Non-overlapping capabilities are allowed. For example, mise can select runtimes
while Devbox supplies a system library. The merged plan records which manager
owns each resolved identity.

### Secrets and local state

Adapters never copy values from `.env`, Flox secrets, Devbox/Jetify secrets,
credential helpers, user-global environment variables, or shell history into
Zed manifests or locks. A generated file may preserve an existing secret-source
reference, but Zed treats the secret value as out of scope and redacts it from
diagnostics.

## Offline and cache behavior

A complete reproducible workflow separates resolution from restoration:

1. online resolution writes `.zpkg.lock` and manager-native lock data;
2. caches store artifacts by content hash;
3. frozen install verifies exact hashes and performs no graph re-resolution;
4. an offline canary restores both the environment and Zed packages from the
   populated caches;
5. deleting or changing one cached object proves tamper/missing-object failure.

A lock that names an object unavailable in the configured caches fails with the
missing identity. It never falls back to a newer compatible version.

## Security and trust model

Environment files can contain executable hooks, plugins, VCS sources, local
paths, and package-manager-specific extension points. Import is therefore data
parsing, not blanket trust.

Initial safe subset:

- exact tool and system-package requirements;
- immutable package/flake/plugin sources;
- platform constraints;
- checksums and native lock identity;
- the fixed Zed frozen-install activation policy.

Initial rejected or ignored subset:

- arbitrary hooks, profiles, tasks, services, and post-install scripts;
- secret values;
- mutable VCS refs;
- unpinned remote includes/plugins;
- local absolute paths in portable mode;
- network-dependent commands during frozen restore;
- configuration inherited invisibly from outside the project boundary.

Diagnostics distinguish "unsupported" from "unsafe" and "unresolved" so users
know whether to remove a construct, pin it, or wait for a typed adapter.

## Test matrix

## Shared interfaces

- schema serialization and JSON Schema snapshots;
- deterministic canonical bytes and digest;
- stable ordering across maps and platform sets;
- exact/floating/mutable-reference classification;
- SemVer eligibility and CalVer/opaque rejection at SemVer-only boundaries;
- build-metadata platform misuse rejection;
- old lockfile compatibility and explicit migration tests.

## Parser and generator tests

For each manager:

- minimal valid project;
- multiple tools in non-sorted input order;
- platform-specific entries;
- exact pins and lock provenance;
- fuzzy/latest/mutable/path values;
- unknown fields preserved during merge;
- semantic conflict diagnostics;
- deterministic repeated export;
- import → export → import normalized-plan equality;
- secrets and arbitrary hooks excluded;
- project-local versus parent/global scope behavior.

## Native-manager canaries

- Devbox validates and activates the generated project;
- Flox validates, locks, and activates the generated environment;
- mise generates/verifies its lock and selects exact runtimes;
- asdf installs exact versions from pinned plugin revisions;
- all invoke or permit `zed install --frozen` without re-resolving the Zed graph.

## OCI canaries

- static `x86_64-linux-musl` binary succeeds;
- static `aarch64-linux-musl` binary succeeds under matching/emulated runner;
- dynamically linked ELF fails before Docker/Podman build;
- static binary requiring an undeclared runtime data file fails its smoke test;
- explicit runtime bundle succeeds and changes the image digest;
- Docker and Podman produce equivalent OCI content for normalized inputs;
- multi-platform image index selects the correct architecture;
- changed binary, target metadata, or cached layer is rejected;
- exported image runs without Zed, a shell, or a package manager.

## CI shape

Pull-request CI is credential-free:

```text
interface tests
  -> parser/generator golden tests
  -> manager-native validation matrix
  -> static/dynamic binary inspection fixtures
  -> Docker/Podman scratch smoke tests
  -> offline restore and tamper canaries
```

External actions and tool installers are pinned to immutable revisions or
verified checksums. Networked resolution is isolated from offline restoration.
Release CI publishes only after repeating the same checks against an immutable
source tag.

## Delivery phases

### Phase 1: shared model and mise/asdf

- add `EnvironmentPlan`, source/checksum/platform types, validation, and digest;
- extend lock provenance compatibly;
- implement project-local mise and `.tool-versions` parsing;
- implement deterministic `mise.toml` and `.tool-versions` generation;
- add `zed env plan`, `import`, `export`, and `verify` command scaffolding;
- add flags-2-env, completion, README, schema, and golden tests.

### Phase 2: Devbox and Flox

- add versioned Nix-backed tool mapping;
- generate and semantically merge `devbox.json` and Flox `manifest.toml`;
- preserve manager-native lock provenance;
- run manager-native config/lock/activation canaries;
- prove the fixed frozen-install hook and unknown-field preservation.

### Phase 3: static scratch and OCI

- add ELF inspection and target verification;
- generate deterministic scratch build contexts and Dockerfiles;
- support Docker and Podman validation;
- generate OCI layouts and multi-platform image indexes;
- record per-platform digests, SBOMs, and attestations.

### Phase 4: shared provenance with Nix package interop

- reuse immutable source, platform, checksum, output, and attestation types from
  `DEN-1411`;
- keep `zed env export ...` separate from package/derivation import/export;
- prove that neither feature makes Nix mandatory for core Zed workflows.

### Phase 5: full E2E and rollout

- add fixtures in `zed-pkg-test` and `zed-e2e`;
- test Linux and macOS, x86-64 and ARM where runners permit;
- document Windows/WSL boundaries explicitly;
- add migration guidance for existing hand-maintained manager files;
- enable the adapters for client/SDK repositories after canaries pass.

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
