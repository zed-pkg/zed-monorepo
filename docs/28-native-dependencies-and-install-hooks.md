# 28. Native dependencies and staged install hooks

**Status:** manifest contract implemented; CLI execution under current-main review.  
**Interface implementation:** `zed-pkg/zed-interfaces#16`, merged as
`e7b9e277dd2729811f293d5405a8fff38c026eaf`.  
**CLI implementation under review:** `zed-pkg/zed-cli#48`.  
**Original documentation review:** `zed-pkg/zed-docs#22`.

Zed packages sometimes need host-native tools or libraries before package-local
build steps can run: `pkg-config`, OpenSSL headers, a C compiler, Java, or a code
generator. Those requirements are distinct from Zed package dependencies and
must not be hidden inside an opaque build command.

This contract separates four concerns:

1. declarative native prerequisites;
2. explicit consent for host mutation;
3. package-controlled lifecycle hooks in writable staging; and
4. deterministic cache and Nix behavior.

The manifest shape and validation rules are merged. The CLI lifecycle described
below remains a promotion gate until its current-main implementation and
independent acceptance suite are green.

## Manifest contract

A package declares native prerequisites by supported host package manager:

```toml
[native-dependencies]
apt = ["pkg-config", "libssl-dev"]
apk = ["pkgconf", "openssl-dev"]
brew = ["pkg-config", "openssl@3"]
nix = ["pkg-config", "openssl"]

[hooks]
pre-install = ["./scripts/pre-install.sh"]
post-install = ["./scripts/post-install.sh"]
```

A polyglot target may append target-specific requirements and hooks:

```toml
[targets.nodejs]
dir = "clients/node"

[targets.nodejs.native-dependencies]
apt = ["nodejs"]
brew = ["node"]

[targets.nodejs.hooks]
pre-install = ["./scripts/prepare-node.sh"]
post-install = ["./scripts/check-node-install.sh"]
```

Package-level entries apply to every target. Target package lists append and are
de-duplicated in declaration order. Package hooks execute before target hooks in
each phase.

Canonical keys use kebab case. Compatibility aliases such as
`native_dependencies`, `pre_install`, and `post_install` may be read, but
canonical serialization uses `native-dependencies`, `pre-install`, and
`post-install`.

## Native package-manager identifiers

The version-one manifest contract recognizes:

```text
apk apt brew choco dnf nix pacman pkg port scoop winget xbps yum zypper
```

A manifest names packages, never an installer command. Zed owns the mapping from
a manager identifier to a fixed executable and argument template. Package
specifications are passed as separate argv values and are never interpolated
into a shell command.

Validation fails closed on unknown managers, duplicate or empty specifications,
option-shaped specifications, whitespace/control characters, NUL bytes, empty
hooks, and oversized declarations. Shell metacharacters remain ordinary argv
characters; a native manager may reject the package name, but it cannot become a
shell pipeline because no shell parses the argument.

## Independent consent boundaries

Native package installation, lifecycle hooks, and package builds are separate
trust decisions. The planned CLI surface is:

```console
zed install \
  --allow-native-deps \
  --allow-install-hooks \
  --allow-build
```

The corresponding environment identities are:

```text
ZED_PKG_ALLOW_NATIVE_DEPS=1
ZED_PKG_ALLOW_INSTALL_HOOKS=1
ZED_PKG_ALLOW_BUILD=1
```

A caller may pin manager selection through `--native-manager` or
`ZED_PKG_NATIVE_MANAGER`. The CLI must preflight the complete resolved graph and
all three permissions before invoking a host package manager or executing
package-controlled code. A later missing permission must never be discovered
after host mutation has begun.

## Graph-wide manager selection

Zed resolves the complete runtime dependency graph before choosing a native
manager. It computes the intersection of managers supported by every package
that declares native requirements.

For example, when one package supports `apt` and `brew`, while another supports
`apt` and `apk`, only `apt` satisfies the graph. An explicitly selected manager
must belong to that intersection and be available on the host.

Once selected, requirements from the complete graph are de-duplicated in stable
order and installed once per transaction. An empty effective requirement set
requires neither native-install consent nor a manager executable.

## Transaction lifecycle

The intended install transaction is:

1. resolve the complete Zed dependency graph;
2. read and validate every artifact manifest;
3. preflight native-install, lifecycle-hook, and build permissions;
4. select one compatible native manager for the graph;
5. de-duplicate and install native prerequisites once;
6. copy each immutable source artifact into writable staging;
7. run package and selected-target `pre-install` hooks;
8. run the effective build command when declared and permitted;
9. validate declared build outputs;
10. run package and selected-target `post-install` hooks;
11. promote finalized staging into the platform lifecycle cache; and
12. materialize the cached artifact into the consumer project.

Hooks and builds never use the immutable source store or consumer project as
their working directory. A hook, build, or output-validation failure prevents
cache promotion and project materialization. Host package managers are a
separate transaction boundary: Zed generally cannot undo a host package that a
manager installed before a later phase failed.

## Cache identity

The finalized lifecycle cache includes every declared input capable of changing
output:

- immutable source artifact identity;
- effective language target and platform/build target;
- selected native manager and de-duplicated native requirement set;
- lifecycle hook definitions;
- build command and declared outputs; and
- relevant environment and toolchain identities.

A verified cache hit may skip repeated hook/build execution. It must not bypass
graph preflight or silently reuse output after any relevant declaration changes.
Source artifacts remain immutable and are never replaced by staged output.

## Hook environment

Hooks receive explicit Zed metadata for the package, target, platform, staging
root, dependency materialization root, selected manager, and managed native
profile when present. Managed-profile tools may extend `PATH`; conventional
discovery variables such as `PKG_CONFIG_PATH`, `CMAKE_PREFIX_PATH`, `CPATH`, and
`LIBRARY_PATH` may be extended when appropriate.

The environment is additive and inspectable. Zed does not monkey-patch a
language runtime or infer arbitrary compiler/linker flags from package names.

## Nix behavior

### `nix shell` and `nix develop`

When `nix` is selected outside a derivation, Zed may use a content-addressed,
Zed-owned profile rather than mutating the user's default profile:

```text
$ZED_PKG_HOME/native/nix/v1/<requirements-hash>/profile
```

The profile is reusable only when its recorded package inventory matches the
requested set. `NIX_STORE` alone does not prove derivation execution because it
may also be present in `nix shell` or `nix develop`.

### Nix derivations

Inside an actual derivation (`NIX_BUILD_TOP`), Zed must not invoke `apt`, `brew`,
`nix profile install`, or another host mutator. The derivation supplies native
requirements through `nativeBuildInputs` and `buildInputs`, then explicitly
acknowledges that boundary with:

```text
ZED_PKG_NATIVE_DEPS_PROVIDED=1
```

For cross compilation, build-machine tools belong in `nativeBuildInputs`;
libraries linked into the target belong in cross `buildInputs` such as
`pkgsCross`. Native manager selection is not a substitute for target-architecture
libraries.

## Security invariants

The implementation and acceptance suites must preserve these properties:

- native installation requires explicit consent;
- lifecycle hooks require separate consent;
- build commands retain independent consent;
- manager executables and option templates are controlled by Zed;
- package names are separate argv entries, not shell fragments;
- all permissions are checked before host mutation;
- source CAS contents remain immutable;
- package code runs only in bounded writable staging;
- failures cannot promote partial lifecycle cache entries;
- Nix derivations remain pure with respect to host package-manager mutation; and
- logs/evidence do not expose credentials or secret environment values.

Enabling lifecycle hooks authorizes package-controlled code execution. The
permission must remain visible in terminal output, automation policy, and code
review; declarative syntax does not make a hook trusted.

## Promotion requirements

The CLI slice is not complete merely because manifest parsing is merged. Before
it is marked shipped, exact-head product and external acceptance must prove:

- Linux, macOS, and Windows manager selection and argv construction;
- full-graph permission preflight before any host mutation;
- deterministic de-duplication and manager intersection;
- source-store immutability and writable staging;
- hook/build order, output validation, cache reuse, and rollback;
- workspace behavior;
- managed Nix profile reuse and derivation no-mutation behavior;
- flags-to-environment synchronization; and
- no weakening of ordinary install, frozen replay, OCI, Nix, or development
  environment contracts.
