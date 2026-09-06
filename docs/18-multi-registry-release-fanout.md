# 18. Multi-registry release fan-out and target-only forge mirrors

Polyglot repositories have two related but distinct release surfaces:

1. **Zed Package artifacts**: one complete repository artifact plus one isolated artifact per declared language target.
2. **Native ecosystem packages**: npm, crates.io, Maven Central, RubyGems, PyPI, pub.dev, NuGet, Hex, Packagist, and similar registries.

The canonical source remains one Git repository and one lockstep version. Native registries are distribution mirrors of the same reviewed source commit, not alternate sources of truth.

## Release invariants

A valid release set has all of these properties:

- the feature/release branch descends directly from `main`;
- every target is rooted at the directory declared by `[targets.<language>].dir`;
- the complete-repository Zed artifact contains every declared target;
- each language Zed artifact is re-rooted and contains no sibling language tree;
- each language root contains its native package-manager manifest;
- native package dry-runs succeed from the same commit before credentials are exposed;
- all outputs use the root package version and record the same Git commit/tag;
- rerunning a partial release is idempotent: identical outputs are skipped and same-version/different-content outputs are rejected.

## Manifest convention

`[targets]` is authoritative for source isolation and Zed package names:

```toml
[targets.repository]
dir = "."
name = "fiducia-clients-repository"

[targets.nodejs]
dir = "clients/typescript"
name = "fiducia-client"
adapter = "node"

[targets.rust]
dir = "clients/rust"
name = "fiducia-client-rust"
```

Native registry identity remains authoritative in the native manifest inside the target root (`package.json`, `Cargo.toml`, `pom.xml`, `.gemspec`, and so on). CI must compare the target and native manifests rather than duplicate every ecosystem field in `.zpkg.toml`.

The Zed manifest declares where that already-defined package should go:

```toml
[targets.nodejs.native]
registry = "npm"
package = "@fiducia/client"
forge = ["github-packages", "gitlab-packages", "bitbucket-packages"]

[targets.golang.native]
registry = "go-modules"
package = "github.com/fiducia-cloud/fiducia-clients/clients/go"
tag_format = "clients/go/v{version}"
forge = ["gitlab-packages"]
```

The native manifest still owns the package name and version; the duplicated
identity is checked before a plan is emitted. The route exists so release
automation does not have to guess a destination from a target name.
`tag_format` is optional except where the ecosystem requires a distinct tag.
A single-language package with its native manifest at the repository root uses
the same fields under `[publish.native]`.

`zed release plan --json` emits the Zed artifacts, canonical native packages,
forge mirrors, and exact VCS tags without reading credentials or uploading.
`zed release preflight` then runs fixed package-manager checks with registry
credential environment variables removed. Arbitrary manifest shell commands
are not part of this model.

### Package-registry compatibility

The forge entry means “publish the same native package format to this forge's
package registry.” It does not mean “put every language into every forge”:

| Native format | Canonical destination | GitHub Packages | GitLab | Bitbucket Packages |
| --- | --- | --- | --- | --- |
| npm | npmjs.com | yes | yes | yes |
| Maven | Maven Central | yes | yes | yes |
| RubyGems | rubygems.org | yes | yes | no |
| NuGet | nuget.org | yes | yes | no |
| PyPI | pypi.org | no | yes | no |
| Composer | Packagist | no | yes | no |
| Go modules | VCS/module proxy | no | yes | no |
| Cargo | crates.io | no | no | no |
| Dart/Flutter | pub.dev | no | no | no |

The interface validates this matrix and rejects duplicate or impossible
provider/format pairs during manifest parsing. Support here means the route can
be represented and planned; authenticated upload adapters are a later,
separately reviewed boundary.

## GitHub, GitLab, and Bitbucket source mirrors

The normal whole-repository mirror is the ordinary repository remote. A language-only forge mirror is optional and should not become a submodule of the canonical repository.

Submodules invert the dependency relationship and add commit-pointer maintenance to the source tree. For generated mirrors, use a synthetic subtree commit instead:

```sh
split=$(git subtree split --prefix=clients/rust "$RELEASE_COMMIT")
git push rust-mirror "$split:refs/heads/main"
git tag -f "zed/rust/v$VERSION" "$split"
git push rust-mirror "refs/tags/zed/rust/v$VERSION"
```

A Git tag cannot point at a directory; it points at a commit. `git subtree split` creates the target-only commit that the target-specific branch and tag can reference. The same commit can be pushed to GitHub, GitLab, or Bitbucket.

Recommended naming:

- branch: `mirror/<target>` in the canonical repository, or `main` in a dedicated mirror repository;
- tag: `zed/<target>/v<version>` for target-only commits;
- ordinary root tag: `v<version>` for the canonical repository release.

Mirror commits are derived outputs. Changes must flow from the canonical monorepo and never be merged back from a mirror.

## Shared interfaces and release ordering

A client target with a path dependency outside its target directory is not independently publishable. This is common when clients consume generated wire interfaces from a sibling repository.

The correct release order is:

1. publish the interface packages for every native ecosystem and to Zed;
2. change client manifests to use hosted versions, retaining local path overrides only for development where the ecosystem supports a publish-time version fallback;
3. verify native packages from clean target-only staging directories;
4. publish client packages;
5. publish optional target-only forge mirrors.

CI must not hide a private sibling checkout behind a personal token. Prefer a GitHub App installation token or independently published interface packages. Pull-request workflows should remain credential-free and use package/build dry-runs only.

## GitHub Actions release shape

Pull-request CI performs no uploads:

```text
native tests -> native package dry-runs -> zed pack -> inspect artifacts -> zed publish --dry-run
```

A protected release workflow starts only from an immutable version tag, repeats all checks, obtains short-lived registry credentials through OIDC or a GitHub App where available, and publishes in dependency order. Each registry job reports its content digest into a final release-set attestation.

The initial client-repository rollout pins the reviewed `zed-cli` and `zed-interfaces` commits so package behavior cannot change underneath an open pull request.

## Current implementation boundary

Implemented now:

- complete-repository and isolated per-language Zed targets;
- deterministic target re-rooting and derived manifests;
- retry-safe Zed publish fan-out;
- CI checks for target isolation and native package manifests;
- typed canonical-native and forge-package routes;
- provider/format compatibility and package identity/version validation;
- separate native VCS tag formats for tag-resolved subdirectory packages;
- deterministic `zed release plan` output;
- credential-free native package-manager preflight where packages are already self-contained.

Still follow-up work:

- authenticated native registry adapters;
- release-set attestations and provenance aggregation;
- generic target-only forge mirror automation;
- publishable interface packages for repositories whose clients still depend on private sibling paths.
