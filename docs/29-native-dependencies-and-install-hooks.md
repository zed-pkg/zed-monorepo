# Native dependencies and install hooks

Status: manifest contract implemented in `zed-interfaces`; installer lifecycle implementation remains under review in `zed-cli` PR 48.

Zed packages may need host-native tools or libraries before package-local build steps can run. Examples include `pkg-config`, OpenSSL headers, a C compiler, Java, or a code generator. These requirements are distinct from Zed package dependencies and must not be hidden inside an opaque `[build]` command.

This document defines the package contract, execution lifecycle, consent boundary, cache behavior, and Nix integration for native prerequisites and install hooks.

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

Package-level entries apply to every target. Target package lists append and are de-duplicated in declaration order. Package hooks execute before target hooks in each phase.

The canonical keys use kebab case. Zed reads `native_dependencies`, `pre_install`, and `post_install` as compatibility aliases but serializes `native-dependencies`, `pre-install`, and `post-install`.

## Native package-manager identifiers

The version-one contract recognizes:

```text
apk apt brew choco dnf nix pacman pkg port scoop winget xbps yum zypper
```

A manifest names packages, never an installer command. Zed owns the mapping from a manager identifier to a fixed executable and argument template. Package specifications are passed as separate argv values and are never interpolated into a shell command.

Unknown managers, duplicate specifications, option-shaped specifications, whitespace, control characters, empty hooks, NUL bytes, and oversized declarations fail manifest validation.

Shell metacharacters in a package specification remain ordinary argv characters. The native manager may reject such a package name, but it cannot become a shell pipeline because no shell parses the argument.

## Independent consent boundaries

Native package installation, lifecycle hooks, and package builds are separate trust decisions:

```console
zed install \
  --allow-native-deps \
  --allow-install-hooks \
  --allow-build
```

Equivalent environment variables are:

```text
ZED_PKG_ALLOW_NATIVE_DEPS=1
ZED_PKG_ALLOW_INSTALL_HOOKS=1
ZED_PKG_ALLOW_BUILD=1
```

A caller may pin native manager selection for CI and reproducibility:

```console
zed install --allow-native-deps --native-manager apt
```

or:

```text
ZED_PKG_NATIVE_MANAGER=apt
```

Zed performs the complete permission preflight before invoking a native package manager or running package-controlled code. A later missing permission must not be discovered after host mutation has already begun.

## Graph-wide native-manager selection

Zed resolves the complete runtime dependency graph before installing native prerequisites. It computes the intersection of managers supported by every package that declares native requirements.

For example:

```toml
# Package A
[native-dependencies]
apt = ["libssl-dev"]
brew = ["openssl@3"]

# Package B
[native-dependencies]
apt = ["pkg-config"]
apk = ["pkgconf"]
```

Only `apt` satisfies both packages. Zed must not select `brew` or `apk` merely because one package lists it.

Once selected, package specifications from the full graph are de-duplicated and installed once. An explicitly requested manager must belong to the graph-wide intersection and be available on the host.

## Transaction lifecycle

One install transaction follows this order:

1. Resolve the complete Zed dependency graph.
2. Read and validate every artifact's `.zpkg.toml`.
3. Preflight native-install, lifecycle-hook, and build permissions.
4. Select one compatible native manager for the graph.
5. De-duplicate and install native prerequisites once.
6. Copy each immutable source artifact into a writable staging tree.
7. Run package and selected-target `pre-install` hooks.
8. Run the effective `[build]` command when declared and allowed.
9. Validate declared build outputs.
10. Run package and selected-target `post-install` hooks.
11. Promote the finalized staging tree into the platform build cache.
12. Materialize the cached artifact into the consumer project.

Hooks and builds never use the immutable source store or consumer project as their working directory. This preserves content-addressed source integrity and prevents package scripts from modifying unrelated project files.

A hook, build, or output-validation failure prevents cache promotion and project materialization. Host package managers are a separate transactional boundary: Zed cannot generally uninstall packages that a host manager successfully installed before a later phase failed.

## Cache identity

The finalized artifact cache includes all inputs that can affect lifecycle output, including:

- source artifact identity;
- effective language target;
- effective build target and platform where applicable;
- native requirement set;
- lifecycle hook definitions;
- build command and declared outputs.

A cache hit skips repeated hook and build execution. Source artifacts remain immutable and are never replaced by staged output.

## Hook environment

Hooks receive stable Zed metadata for the current package, target, platform, source staging root, dependency materialization root, native manager, and managed native profile when one exists. Native tools installed into a managed profile are added to `PATH`; conventional discovery variables such as `PKG_CONFIG_PATH`, `CMAKE_PREFIX_PATH`, `CPATH`, and `LIBRARY_PATH` are extended when appropriate.

The environment is additive and explicit. Zed does not monkey-patch a language runtime or infer arbitrary compiler and linker flags from package names.

## Nix behavior

### `nix shell` and `nix develop`

When `nix` is the selected native manager outside a derivation build, Zed installs requirements into a content-addressed, Zed-owned profile rather than mutating the user's default profile:

```text
$ZED_PKG_HOME/native/nix/v1/<requirements-hash>/profile
```

The profile can be reused when its recorded package inventory matches the requested set.

The presence of `NIX_STORE` alone does not prove that Zed is inside a derivation; it may also be set in `nix shell` or `nix develop`.

### Nix derivations

Inside an actual derivation build, identified by `NIX_BUILD_TOP`, Zed must not invoke `apt`, `brew`, `nix profile install`, or another host mutator. The derivation supplies native prerequisites:

```nix
nativeBuildInputs = [
  pkgs.pkg-config
  pkgs.zig
];

buildInputs = [
  pkgs.openssl
  pkgs.zlib
];
```

The derivation acknowledges that it supplied the declared prerequisites with:

```text
ZED_PKG_NATIVE_DEPS_PROVIDED=1
```

For cross compilation, tools that execute on the build machine belong in `nativeBuildInputs`; libraries linked into the target artifact belong in cross `buildInputs` from `pkgsCross` or an equivalent cross derivation. Native package-manager selection is not a substitute for target-architecture libraries.

## Security properties

The contract deliberately provides these guarantees:

- native installation requires explicit consent;
- lifecycle hooks require separate explicit consent;
- package build commands retain their independent consent;
- installer executable and option templates are controlled by Zed;
- package names are separate argv entries, not shell fragments;
- all permissions are checked before host mutation;
- source CAS contents remain immutable;
- package code runs only in writable staging;
- failed lifecycle execution cannot promote partial cache artifacts;
- Nix derivation builds remain pure with respect to host package-manager mutation.

This does not make package hooks trusted. A caller who enables lifecycle hooks is authorizing package-controlled code execution, which must remain visible in review and automation policy.
