# 27. Durable manifests on first dependency install

**Linear:** DEN-1413  
**Implementation:** `zed-pkg/zed-cli` PR #88, merged as
`436af9240c4a3808d4c22253a56710004189037b`  
**Validated implementation head:**
`fe4b4662fb252166b18c48f9c048f5888ec8df44`  
**Independent certification:** `zed-pkg-test/zed-pkg-e2e` PRs #34 and #35,
merged as `a19f22865d2967f04800062cc8157e5a2015ac9e` and
`a0286ee1c9d0751cc88b29fed7490afd5b972e78`

A project should not become permanently dependent on an invisible, in-memory
configuration merely because its first Zed command was convenient. A normal
dependency-bearing first install now adopts the project into Zed explicitly:

```bash
zed install acme/http-kit@^1
```

When no `.zpkg.toml` exists, Zed creates a small deterministic consumer
manifest at the inferred project root, records the requested direct dependency,
then resolves, locks, and materializes the graph through the ordinary installer.
The previous synthetic-manifest behavior remains available only when the caller
asks for it:

```bash
zed install acme/http-kit@^1 --do-not-write-new-manifest
```

This document records the shipped user contract, generated metadata, failure
and concurrency semantics, compatibility policy, and independent certification
boundary.

## Shipped and certified state

The final product head passed all 13 repository workflows before merge,
including ordinary CI, the dedicated Ubuntu/macOS durability and concurrency
matrix, Nix fetch/export/interop, development-shell, OCI, manifestless
polyglot, repository hardening, agents policy, browser-report, and formal
review.

Independent certification then passed all nine workflows on the exact product
head:

- the complete Node durable/ephemeral/rollback contract on Ubuntu 24.04 and
  macOS 15;
- Go, Python, and Rust durable-manifest canaries on both operating systems;
- full fixture lifecycle and fixture install boundaries;
- recursive graph and stress suites;
- browser E2E against the registry stack;
- mise runtime compatibility; and
- lifecycle source-map validation.

Linux and macOS are the certified platform boundary for this feature. Native
Windows and WSL remain separate platform work; this document does not imply a
Windows certification result.

## Why the default changed

The original manifestless path was useful for experimentation and CI canaries,
but it had a hidden-state problem: `.zpkg.lock` could survive while the direct
requirements that produced it existed only in invocation history. A lockfile
records the complete resolved graph and cannot reliably distinguish packages
the user chose from transitive dependencies. That makes later updates, reviews,
automation, and Nix/OCI exports less truthful than they should be.

Creating `.zpkg.toml` by default gives the project a durable declaration of
intent:

- direct requirements are reviewable in version control;
- `zed install --frozen` has an unambiguous manifest/lock pair;
- humans and agents see the same project state;
- adapters and target selection can be reproduced on another machine;
- release, Nix, SBOM, provenance, and policy tooling have a stable input; and
- uninstall/reinstall cycles do not depend on shell history.

The escape hatch remains important for throwaway sandboxes, one-shot tooling,
and explicit lock-only restoration.

## Command behavior

### Missing manifest with one or more package operands

```bash
zed install acme/http-kit@^1 acme/log-kit@=2.0.0
```

Zed:

1. infers the project root using the same conservative native-manifest,
   lockfile, and directory-structure rules used by the manifestless path;
2. parses all operands and rejects malformed or conflicting requirements before
   replacing durable project state;
3. resolves an omitted requirement to an immutable registry-derived
   requirement;
4. infers the target and ecosystem adapter when possible;
5. writes `.zpkg.toml` with a same-directory atomic no-clobber operation;
6. runs the existing resolver, integrity checks, lockfile writer, store,
   materializer, adapters, build-hook policy, and project transaction; and
7. removes the byte-identical generated manifest if installation fails.

A successful invocation leaves both `.zpkg.toml` and `.zpkg.lock`.

### Missing manifest with the explicit ephemeral flag

```bash
zed install acme/http-kit@^1 --do-not-write-new-manifest
```

Zed uses the established in-memory synthetic consumer manifest. It may create
or update `.zpkg.lock` and materialize packages, but it does not create
`.zpkg.toml`.

The flag suppresses only creation of a **missing** manifest. It does not disable:

- requirement and graph validation;
- checksum, signature, or provenance policy;
- frozen-mode drift checks;
- store locking or project transactions;
- package materialization;
- adapter output; or
- explicitly permitted build hooks.

### Existing manifest

When `.zpkg.toml` already exists, `--do-not-write-new-manifest` is an
informational no-op. The command remains a normal manifest-backed install and
must never turn an established managed project into an ephemeral one.

Package operands do not silently edit a human-authored existing manifest:

```bash
zed add acme/http-kit@^1
```

is the explicit mutation command. A manifest carrying the recognized generated
consumer identity remains inside the managed first-install workflow and may
accept additional package operands before its inferred identity is replaced.
That narrow rule supports both later convenience installs and true concurrent
first installs: under the project lock, distinct dependencies merge into one
deterministic generated manifest. A conflicting requirement leaves the file
unchanged and directs the caller to `zed add`.

### Frozen lock-only restoration

A lockfile without a manifest does not contain enough information to reconstruct
a truthful direct-dependency set. Lock-only restoration must therefore remain
explicit:

```bash
zed install --frozen --do-not-write-new-manifest
```

Without the flag, Zed fails with an actionable explanation instead of inventing
a manifest from all locked transitive packages.

## Canonical flag and compatibility aliases

The canonical spelling is:

```text
--do-not-write-new-manifest
```

The canonical environment variable is:

```text
ZED_PKG_DO_NOT_WRITE_NEW_MANIFEST=1
```

During the compatibility window, these continue to work and emit deprecation
guidance:

```text
--allow-no-manifest
--skip-manifest
ZED_PKG_ALLOW_NO_MANIFEST=1
```

Runtime parsing, terminal help, Bash completion, Zsh completion, and the
embedded flags-2-env contract expose the same canonical spelling and aliases.
Process startup bridges the canonical environment variable into the legacy
embedded environment key during the migration window; an explicit CLI option
retains precedence over inherited environment configuration.

## Generated manifest shape

Exact serialization follows the current manifest schema and standard writer. A
representative first-install manifest is:

```toml
[package]
org = "zed-local"
name = "my-project"
version = "0.0.0"
description = "Local Zed dependency manifest; edit package metadata before publishing"
keywords = ["zed-generated-consumer"]

[package.repository]
vcs = "git"
url = "https://localhost/zed-local/my-project"

[dependencies]
"acme/http-kit" = "^1"

[install]
adapter = "node"
target = "node"
```

Generated content has these properties:

- the name is a deterministic lowercase slug derived from the selected project
  directory, with `project` as the safe fallback;
- version is the neutral local placeholder `0.0.0`;
- the repository URL is deliberately non-remote and non-authoritative;
- `zed-generated-consumer` marks inferred metadata;
- requested direct requirements are preserved;
- unversioned operands become a deterministic registry-derived requirement
  before the file is written;
- inferred target and adapter are recorded only when Zed has a supported value;
  and
- timestamps, random identifiers, absolute machine paths, usernames, and home
  directories are forbidden.

## Non-publishable by default

A generated consumer manifest is immediately useful for installation but is not
a valid package publication declaration. `zed publish` fails closed while the
generated marker and placeholder identity remain.

To turn the project into a publishable package, the maintainer deliberately
reviews and edits at least:

- `package.org` and `package.name`;
- the real package version and version scheme;
- repository URL and VCS metadata;
- description and license as appropriate;
- language/ecosystem metadata when applicable; and
- the generated marker keyword.

Removing the marker is an explicit acknowledgement that the inferred local
identity has been reviewed. `--skip-vcs-checks` does not bypass this guard.

## Atomicity, locking, and recovery

### First writer

Generated bytes are written to a temporary file in the project directory,
flushed, synchronized, and persisted with no-clobber semantics. If another
writer creates `.zpkg.toml` first, Zed does not overwrite it.

### Failure rollback

Resolution and installation use the ordinary installer. If that operation fails
after the generated file is written, Zed removes the manifest only when its
current bytes still match the exact generated bytes. If another process or
editor changed the file, rollback refuses to erase that work and reports the
compound failure.

Updates to a recognized generated manifest retain the prior bytes and restore
them on ordinary installation failure, again only if no external writer changed
the replacement.

### Project-scoped manifest serialization

First installs and generated-manifest extension acquire an exclusive lock under
the configured Zed home, keyed by a hash of the canonical project path. The lock
does not pollute the project. It serializes manifest creation and dependency
merge while the ordinary installer retains ownership of content-store and
project-tree transactions.

### Live transaction recovery safety

Current-main validation exposed a Linux race that the stale feature branch could
not reveal: a second process could inspect another process's live
`.zpkg-staging` rollback journal before taking the install lock and mistake that
journal for abandoned state.

The shipped implementation fixes that behavior rather than weakening the
concurrency canary. Top-level recovery now runs only when staging state exists
and acquires the same kernel-backed store install lock held by every live
`ProjectTransaction` before reading or restoring the journal. A concurrent
invocation therefore waits for the live transaction instead of rolling it back.

A hard process termination can still leave complete recoverable staging state.
The next invocation recovers it while holding the same install lock. A process
must never leave partially written TOML.

## Project-root inference

The generated manifest is written at the same root selected for installation,
not blindly in the current working directory. Selection order is:

1. nearest ancestor containing `.zpkg.toml`;
2. nearest ancestor containing `.zpkg.lock` or a recognized native manifest;
3. nearest ancestor with a recognized source/project structure;
4. one unambiguous nested project within the bounded scan; and
5. the requested directory when no stronger signal exists.

The bounded scan skips hidden directories and generated/vendor trees such as
`node_modules`, `zed_modules`, `target`, `vendor`, `dist`, and `build`.
Ambiguous monorepos do not receive a guessed child manifest.

## Certified behavior matrix

| Case | Certified result |
| --- | --- |
| Missing manifest + one package | deterministic manifest, lockfile, and install |
| Missing manifest + several packages | one manifest with every direct dependency |
| Nested invocation | manifest written at inferred project root |
| Canonical flag | install/lock allowed; no manifest written |
| Canonical environment variable | same explicit ephemeral behavior |
| Legacy flags/environment | same behavior plus deprecation diagnostic |
| Existing authored manifest | ordinary install; no hidden mode switch |
| Existing manifest + new flag | informational no-op |
| Missing manifest + failed resolution | no generated manifest, lockfile, or project install tree |
| Sequential generated-manifest extension | preserves old and new direct dependencies |
| Concurrent first installs | one valid manifest, no lost distinct dependencies |
| Concurrent live transaction recovery | waits on the install lock; does not roll back the other process |
| Conflicting generated requirement | fails with no silent winner or file replacement |
| Frozen lock-only restore | requires explicit no-new-manifest intent |
| Generated-manifest publish | rejected even with VCS checks skipped |
| Bash/Zsh completion and help | canonical flag plus compatibility aliases |
| Node app/library fixtures | Ubuntu 24.04 and macOS 15 |
| Go, Python, and Rust app/library fixtures | Ubuntu 24.04 and macOS 15 |
| Copy-mode package trees | no symlinks; real native applications execute |
| Full lifecycle/browser/recursive/mise suites | green on the immutable product candidate |

## Relationship to Nix interoperability

Zed-to-Nix and Nix-to-Zed adapters depend on a trustworthy source of direct
dependency intent. Durable first-install manifests make those exports reviewable
and reproducible. The boundary remains strict:

- this feature does not require Nix for ordinary Zed use;
- it does not translate arbitrary Nix expressions;
- a Nix-imported dependency recorded by Zed follows the same durable-manifest
  rule unless the caller explicitly selects ephemeral installation; and
- lockfile adapter provenance remains separate from inferred local package
  identity.

## Compatibility lifecycle

The canonical flag, environment variable, help, completions, and runtime
behavior are shipped. Legacy spellings remain available for the documented
compatibility window and emit migration guidance. Aggregate use measurement is
permitted only where policy allows and must never collect package names,
credentials, paths, or other project content.

Removing a legacy spelling requires a semver-significant CLI release and an
explicit migration note. The durable default is a project-state improvement,
not removal of manifestless installation: ephemeral operation remains available
whenever the caller names that intent explicitly.
