# Git submodules, Zed packages, workspaces, and release composition

Status: operational policy; the primary package publication boundary shipped in `zed-cli` PR 171; nested-repository and reviewed generated-input hardening shipped in `zed-cli` PR 172; remote editable-workspace sources are a proposal, not an implemented feature.
Status: operational policy; package publication-boundary hardening is under review in `zed-cli` PR 171; remote editable-workspace sources are a proposal, not an implemented feature.

Git submodules and Zed packages solve different problems. Treating them as interchangeable makes a repository graph difficult to build, release, secure, and deploy. This document defines the supported boundary between source composition, installable dependencies, release inventory, and deployment composition.

## One mechanism per layer

Use these mechanisms for these layers:

| Layer | Canonical mechanism | Purpose |
| --- | --- | --- |
| Versioned library, schema, SDK, CLI, or build-tool dependency | Zed package | Resolve a declared version, verify an artifact, and materialize it reproducibly |
| Local members already in one checkout | Zed workspace | Develop several local packages without publishing every edit |
| Editable checkout spanning independent repositories | Git submodule today; remote Zed workspace source proposed | Preserve independent Git histories while presenting one development tree |
| Coordinated release inventory | Explicit release manifest | Pin component commits, package versions, contract versions, and OCI digests |
| Runtime deployment | OCI digest plus GitOps source | Promote immutable artifacts without rendering from source-composition directories |
| Infrequently changed source that must be embedded in a published artifact | Zed dependency or Git subtree; embedded submodule only by explicit exception | Ensure a plain source checkout contains or can deterministically acquire the required bytes |

The governing rule is:

> Do not use Git submodules as a package manager, do not use Zed as a deployment orchestrator, and do not use either mechanism as an implicit architecture catalog.

## Normative dependency policy

A reusable package dependency belongs in `.zpkg.toml` and `.zpkg.lock`. This includes shared interfaces, generated and hand-written SDK layers, reusable libraries, CLIs, code generators, and build tooling.

A Git submodule is acceptable only when the consumer needs an independently editable source checkout, a deliberate source snapshot, or inventory metadata. A submodule must not silently stand in for a package dependency merely because both repositories are developed together.

Production build and deployment automation must work from a clean checkout with documented initialization steps. Argo CD and equivalent GitOps controllers must not render a deployment path inside a submodule. Production manifests should reference immutable image digests and should be sourced directly from the repository that owns the deployable workload.

## Gitlink classifications

Every retained gitlink must be classified as exactly one of:

- `workspace`: editable source used for cross-repository development;
- `inventory`: a commit pin showing which repository revision participates in a composition;
- `embedded-source`: source required inside the package or build context;
- `experiment-reference`: a reference implementation or test fixture with no production dependency;
- `legacy`: read-only compatibility pending removal.

The classifications imply these rules:

| Classification | May be packed | May be deployed from its path | Required checks |
| --- | --- | --- | --- |
| `workspace` | no | no | initialized only for the development workflow that requested it |
| `inventory` | no | no | exact commit recorded; release manifest remains authoritative |
| `embedded-source` | only when explicitly declared | no | initialized, exact commit, clean tree, recursive state settled, nested VCS metadata stripped |
| `experiment-reference` | no | no | production dependency scanner must reject imports from it |
| `legacy` | no | no | ownership and removal plan recorded |

A `branch = main` entry in `.gitmodules` does not replace the superproject's exact gitlink commit. Update automation should raise a pull request that advances the gitlink, runs compatibility checks, and records the reason for the change.

## Implemented `zed-cli` submodule safety

Current Zed submodule support is opt-in. When the Git-submodule mode is selected, the CLI verifies adopted submodule metadata before mutation and records exact submodule state in the lock extension.

The pack guard distinguishes excluded submodules from source intentionally included in an artifact. An included submodule must be initialized, point at the recorded gitlink commit, have a clean worktree, and have its recursive state settled. Packaging strips nested `.git` directories and pointer files so VCS internals cannot leak into the artifact.

An excluded optional submodule does not have to be initialized merely to pack unrelated source. An included submodule does. This prevents a valid-looking artifact from being produced from a fresh checkout in which required submodule content was never materialized.

## Publication boundaries and ignored files

`.gitignore` is a local working-tree rule, not a publication rule. A file ignored by Git can still be eligible for a package unless it is separately excluded by the package contract.

The package guard shipped in `zed-cli` PR 171 fails closed when an untracked Git-ignored regular file remains eligible for a whole-tree or target artifact. Supported remedies are explicit `[publish].exclude` entries and, for a whole-tree package, `.zedignore` rules.

When Git is available, Zed uses Git's own ignore engine and preserves the exception for tracked files that also match an ignore rule. The read-only query scopes `safe.directory` to the exact canonical owning worktree, without changing user or repository configuration and without trusting a wildcard.

When Git is absent from a slim runtime image, Zed conservatively evaluates global excludes, ordinary and linked-worktree `.git/info/exclude` files, ancestor `.gitignore` files, and nested `.gitignore` files. Every ignore-matched regular file is treated as potentially untracked. This may require an explicit package exclusion for a tracked ignore-matched file, but it does not convert the absence of Git into permission to publish a secret.

For polyglot packages, source targets are copied into staging trees before final packing. A `.zedignore` located only inside a source target is not an active final-pack rule in that staging lifecycle. Use a root manifest `[publish].exclude` rule for ordinary target content that must be omitted.

Repository-level files beginning with `LICENSE`, `LICENCE`, `COPYING`, or `NOTICE` are different: the packer copies them into every target that does not provide its own file of the same name, and these legal files are always included. The hardening shipped in PR 172 models that copy path before packing, so an ignored root legal file cannot bypass target-root scanning or be hidden with `[publish].exclude`.

PR 172 also extends the Git-backed scan into initialized nested repositories and submodules. Ignored local files inside an embedded source tree are therefore evaluated against the final package artifacts even though the superproject's `git ls-files` query cannot see them.

### Reviewed generated inputs

Some release workflows intentionally generate ignored artifacts, such as compiled WebAssembly or generated client bundles. PR 172 adds a narrow root-level `.zedinclude` control file for those cases.

The contract is fail closed:

- `.zedinclude` must be a regular file in the package root;
- it must be tracked, committed, and clean in both the index and worktree;
- patterns are project-relative globs using `/` separators;
- absolute paths, traversal, negation, Windows drive prefixes, empty segments, backslashes, and project-wide patterns such as `*`, `**`, and `**/*` are rejected;
- the control file itself is excluded from every package artifact;
- Git must be available to verify the control file; the Git-less fallback does not honor it;
- allowing an ignored file does not weaken included-submodule initialization, revision, cleanliness, recursion, or nested-VCS-metadata checks.

Example:

```gitignore
# .gitignore
dist/generated.wasm
```

```text
# .zedinclude — reviewed and committed
dist/generated.wasm
```

Prefer force-tracking a stable source artifact or declaring an ordinary package dependency when that accurately represents the release. Use `.zedinclude` only for generated bytes that must enter the package while remaining ignored during normal development.
The package guard under review in `zed-cli` PR 171 fails closed when an untracked Git-ignored regular file remains eligible for a whole-tree or target artifact. Supported remedies are explicit `[publish].exclude` entries and, for a whole-tree package, `.zedignore` rules.

When Git is available, Zed uses Git's own ignore engine and preserves the exception for tracked files that also match an ignore rule. The read-only query scopes `safe.directory` to the exact canonical worktree, without changing user or repository configuration and without trusting a wildcard.

When Git is absent from a slim runtime image, Zed conservatively evaluates global excludes, `.git/info/exclude`, and nested `.gitignore` files. Every ignore-matched regular file is treated as potentially untracked. This may require an explicit package exclusion for a tracked ignore-matched file, but it does not convert the absence of Git into permission to publish a secret.

For polyglot packages, source targets are copied into staging trees before final packing. A `.zedignore` located only inside a source target is not an active final-pack rule in that staging lifecycle. Use a root manifest `[publish].exclude` rule for target content that must be omitted.

## Release composition

A composition repository may pin source commits for developer convenience, but a release must be described explicitly. A release manifest should record at least:

```toml
[release]
name = "example-product"
version = "2026.08.0"

[components.api]
repository = "github:example/example-api"
commit = "<immutable commit>"
image = "registry.example/api@sha256:<digest>"
contract = "example-interfaces@2.4.1"

[components.web]
repository = "github:example/example-web"
commit = "<immutable commit>"
image = "registry.example/web@sha256:<digest>"
```

The manifest, not the checked-out submodule directory, is the promotion input. It separates source inventory from package resolution and from deployed artifacts.

## Proposed remote editable workspaces

Zed workspaces currently describe local member globs. They do not yet materialize independent remote repositories. Replacing workspace-oriented submodules requires a separate remote-source feature rather than pretending every editable repository is an ordinary package dependency.

A proposed source declaration is:

```toml
[workspace.sources.api]
url = "github:example/example-api"
rev = "<immutable commit>"
path = "apps/api"
editable = true
```

Proposed commands are:

```text
zed workspace sync
zed workspace status
zed workspace update api
zed workspace lock
```

A remote-workspace lock should record the canonical repository URL, immutable commit, tree digest, checkout path, package or interface version where applicable, access classification, and whether the source is editable, embedded, or inventory-only.

The implementation should materialize each repository independently and link it into the workspace. It must preserve independent Git histories and must not turn the workspace lock into a package or deployment lock. This section is a proposal and must not be treated as current CLI behavior.

## Migration procedure

For each composition repository:

1. Inventory every gitlink and assign one classification.
2. Replace reusable dependency gitlinks with Zed package declarations and lock entries.
3. Replace release-only gitlinks with an explicit release manifest.
4. Keep editable cross-repository gitlinks temporarily as `workspace` until remote workspace sources exist.
5. Convert source that must be embedded in a published artifact to a Zed dependency or subtree where practical.
6. Add CI that rejects unclassified gitlinks, uninitialized included submodules, dirty or revision-mismatched embedded source, and deployment paths beneath submodules.
7. Verify a clean clone can build, pack, test, and deploy using only declared initialization steps.

## CI enforcement

Repository policy should reject:

- an unclassified gitlink;
- a package dependency represented only by a submodule;
- an included submodule that is uninitialized, dirty, or at the wrong commit;
- nested VCS metadata in a package artifact;
- an ignored file in the primary or an initialized nested Git worktree that remains eligible for publication;
- an ignored root legal file that would be copied into a polyglot target;
- an untracked, dirty, symlinked, malformed, or project-wide `.zedinclude` policy;
- an ignored file that remains eligible for publication;
- an Argo CD or equivalent render path inside a submodule;
- a release that records only mutable branches or tags;
- disagreement between the release manifest, package lock, contract version, and deployed OCI digest.

These checks make Git submodules an explicit source-composition tool and Zed an explicit package tool, while preserving a clean promotion boundary for release and deployment systems.
