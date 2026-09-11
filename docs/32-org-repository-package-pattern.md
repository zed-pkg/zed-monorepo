# Organization repository and Zed-package pattern

Status: operational policy

This policy applies per product prefix to organizations that expose an API,
protocol, SDK, reusable client, or cross-repository integration surface. It is
conditional: documentation-only, archived, mirror, and `*-test` organizations
do not need the whole topology merely to satisfy a naming checklist.

The mature reference is `fiducia-cloud/fiducia-clients`: support means a real
package/build marker, implementation, and CI command, not an empty directory.

## Repository roles

For a product prefix `acme`, prefer:

| Repository | Role | Rule |
| --- | --- | --- |
| `acme-interfaces` | wire contracts, schemas, shared types | root `.zpkg.toml` and `.zpkg.lock` |
| `acme-lib` | shared implementation primitives | root Zed package when this role exists |
| `acme-clients` | polyglot SDKs under `clients/` | depends on interfaces and lib when present |
| `acme-cli` | command-line consumer | depends on interfaces, lib, and its client target |
| `acme-monorepo` | pinned integration workspace | Zed package plus classified submodules |
| `acme-infra` | deployment and operations | never a monorepo Zed dependency |

Legacy abbreviations and `*-libs` remain valid during migration only when they
are recorded as fleet-audit overrides. New repositories use singular `*-lib`.

## Dependency edges

A clients manifest declares reusable contracts and implementation primitives:

```toml
[dependencies]
"example-org/acme-interfaces" = "^0.1.0"
"example-org/acme-lib" = "^0.1.0" # omit only when no lib repository exists
```

A CLI declares the same layers plus the client target for its implementation
language:

```toml
[dependencies]
"example-org/acme-interfaces" = "^0.1.0"
"example-org/acme-lib" = "^0.1.0"
"example-org/acme-clients-rust" = "^0.1.0"
```

Native manifests such as `Cargo.toml`, `go.mod`, and `package.json` must express
the same graph. A Zed-only dependency that native builds cannot resolve is not
compliant.

A monorepo normally imports interfaces, lib, clients, and other reusable
application packages. It must not declare `*-infra` or `*-cli` as Zed
dependencies. Those repositories may remain submodules for portfolio inventory,
operator workflows, or integration tests, but are classified as `operations`
and `tooling`, not reusable packages.

## Required client surfaces

A conforming `acme-clients/clients` tree declares these targets:

| Zed target | Default directory | Minimum marker |
| --- | --- | --- |
| `c` | `clients/c` | `CMakeLists.txt` or public header |
| `cpp` | `clients/cpp` | `CMakeLists.txt` or public header |
| `zig` | `clients/zig` | `build.zig` |
| `gleam` (`gleamlang`) | `clients/gleam` | `gleam.toml` |
| `erlang` | `clients/erlang` | `rebar.config` |
| `elixir` | `clients/elixir` | `mix.exs` |
| `dart` | `clients/dart` | `pubspec.yaml` |
| `rust` | `clients/rust` | `Cargo.toml` |
| `java` | `clients/java` | Maven or Gradle build |
| `golang` (`go`) | `clients/go` | `go.mod` |
| `python` (`python3`) | `clients/python` | `pyproject.toml` |
| `ruby` | `clients/ruby` | gemspec |
| `php` | `clients/php` | `composer.json` |
| `nodejs` (`typescript`) | `clients/typescript` or `clients/ts` | `package.json` and `tsconfig.json` |
| `kotlin` | `clients/kotlin` | Gradle build; required for Android/mobile products |
| `swift` | `clients/swift` | `Package.swift`; required for Apple/mobile products |

Example target declarations:

```toml
[targets.c]
dir = "clients/c"

[targets.cpp]
dir = "clients/cpp"

[targets.zig]
dir = "clients/zig"

[targets.gleam]
dir = "clients/gleam"

[targets.erlang]
dir = "clients/erlang"

[targets.elixir]
dir = "clients/elixir"

[targets.dart]
dir = "clients/dart"
adapter = "dart"

[targets.rust]
dir = "clients/rust"
adapter = "rust"

[targets.java]
dir = "clients/java"
adapter = "java"

[targets.golang]
dir = "clients/go"
adapter = "go"

[targets.python]
dir = "clients/python"
adapter = "python"

[targets.ruby]
dir = "clients/ruby"

[targets.php]
dir = "clients/php"

[targets.nodejs]
dir = "clients/typescript"
adapter = "node"

[targets.kotlin]
dir = "clients/kotlin"
adapter = "java"

[targets.swift]
dir = "clients/swift"
```

A target containing only a README, `.gitkeep`, or a future-work promise is not
support. It needs native package metadata, implementation source, and a
build/smoke/test command in CI.

## TypeScript runtimes

TypeScript support covers Node.js, Deno, Bun, and standards-based edge
runtimes. Either use a Web-API-only universal ESM core tested under all four, or
use a shared core plus `runtimes/node`, `runtimes/deno`, `runtimes/bun`, and
`runtimes/edge` adapters.

Record the claim at the TypeScript target root in `runtime-matrix.json`:

```json
{
  "schema": 1,
  "model": "universal-core",
  "runtimes": {
    "node": {"supported": true, "ci": "npm test"},
    "deno": {"supported": true, "ci": "deno test -A"},
    "bun": {"supported": true, "ci": "bun test"},
    "edge": {"supported": true, "ci": "npm run test:edge"}
  }
}
```

## Git submodule interoperability

A submodule monorepo maintains three independent records:

1. `.gitmodules` pins editable source repositories.
2. `.zpkg.toml` declares reusable, versioned dependencies.
3. `submodules.toml` classifies every gitlink.

```toml
version = 1

[submodules."apps/acme-interfaces"]
role = "reusable"
package = "example-org/acme-interfaces"

[submodules."apps/acme-clients"]
role = "reusable"
package = "example-org/acme-clients-repository"

[submodules."apps/acme-cli"]
role = "tooling"

[submodules."apps/acme-infra"]
role = "operations"
```

Allowed roles are `reusable`, `application`, `test`, `documentation`,
`website`, `tooling`, and `operations`. Every `.gitmodules` path is classified.
A reusable entry names a package in `[dependencies]`; tooling and operations
entries must not appear there. Clone/update workflows use recursive submodule
initialization and preserve exact gitlink SHAs.

## Fleet audit

`scripts/audit_org_package_pattern.py` performs read-only discovery through the
GitHub API. It detects product prefixes, applies legacy-name overrides, parses
Zed manifests, checks dependency edges and targets, applies Kotlin/Swift only
to mobile products, rejects monorepo imports of infra/CLI, and verifies
`.gitmodules`/`submodules.toml` coverage.

```sh
GH_TOKEN=... python3 scripts/audit_org_package_pattern.py \
  --org fiducia-cloud --format markdown

GH_TOKEN=... python3 scripts/audit_org_package_pattern.py \
  --config config/org-package-pattern.toml --format markdown
```

The audit is intentionally read-only. Missing repository creation and semantic
client implementations remain explicit, reviewable changes in each owning
organization.
