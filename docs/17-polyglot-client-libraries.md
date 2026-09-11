# 17. Polyglot client libraries: publish by language, install by language

**Issue:** a whole class of our repos is *one library, many languages* —
`fiducia-clients`, `sonus-auris-clients`, `daedalus-clients`, `zed-clients`,
`shared-auth-clients`, `scintilla-clients`, `athleto-clients`. Each ships the
same API surface as a TypeScript package, a Java artifact, a Go module, a
Python package, and more. They must be zed packages. But a Java service must
never download the Node sources to get the Java client, and a Node app must
never end up with a `pom.xml` in its dependency tree.

So the question is not "how do we publish a multi-language repo" — it is
**"what is the unit of installation?"**

## The decision: the language slice is the package

One repo, one version, **one published package per language**:

```
fiducia/fiducia-clients-nodejs@1.1.2     <- clients/ts only
fiducia/fiducia-clients-java@1.1.2       <- clients/java only
fiducia/fiducia-clients-golang@1.1.2     <- clients/go only
```

A consumer depends on exactly one of them and downloads exactly those bytes.

### Why not the alternatives

Three designs were on the table. The other two lose on the thing that matters:

| Design | A Java consumer downloads | Consumer complexity |
| --- | --- | --- |
| **One fat package**, whole tree installed | every language | must reach into `…/clients/java` itself |
| **One fat package**, sliced at install time | every language (then discards most) | none |
| **Package per language** ✅ | Java only | none — an ordinary dependency |

Slicing at install *looks* equivalent and is not: the artifact still crosses
the network and still lands in the shared store. For repos where the Node
client is 40 MB of transitive TypeScript and the Go client is 200 KB, that is
the whole ballgame. Publishing separate names is the only option where the
wire cost matches what the consumer actually uses.

It also means **consumers need no new zed features at all** — a per-language
package is a normal package. All of the machinery lives in `publish`, which is
run by us, not by every consumer.

## The manifest: one `[targets]` block, N packages

The repo keeps a single `.zpkg.toml` at its root — one source of truth, one
version number, no drift between languages:

```toml
[package]
org = "fiducia"
name = "fiducia-clients"
version = "1.1.2"
description = "Fiducia API clients"

[package.repository]
vcs = "git"
url = "https://github.com/fiducia-cloud/fiducia-clients"

# Each target becomes its own published package.
[targets.nodejs]
dir = "clients/ts"          # this ecosystem's package root
adapter = "node"            # how consumers wire it into their toolchain

[targets.java]
dir = "clients/java"
adapter = "java"

[targets.golang]
dir = "clients/go"          # adapter omitted -> `none` (go.mod replace)

[targets.python]
dir = "clients/python"
```

`zed publish` fans this out into four artifacts. Each carries a **derived,
standalone manifest** (`manifest_for_target`): same org, version, and repo URL;
the target's own package name and adapter; and **no `[targets]`** — a slice is
single-language by construction, so fan-out can never recurse.

Naming defaults to `<name>-<target>`, which is what produces
`fiducia-clients-java`. Override per target with `name = "…"` when an
ecosystem expects a different spelling (e.g. `fiducia-js-sdk`).

The declaration is also the isolation allowlist. `zed pack` refuses missing
target directories, duplicate source roots, duplicate/invalid published names,
unsafe paths, nested target manifests, and unknown adapters. Only files below
the declared target root enter that artifact (plus a repository-level
license/notice when needed). The target directory is re-rooted, so
`clients/ts/package.json` becomes `package.json` in the Node artifact.
Development caches such as `node_modules`, Cargo `target`, `.dart_tool`,
`.gradle`, generated `build` trees, Python bytecode/virtualenvs, and
Erlang/Elixir build dependencies are excluded.

### Versioning: lockstep by default

All targets publish at the repo's single `[package].version`. That is the
right default for client libraries generated from one API surface: `-java` and
`-nodejs` at `1.1.2` are the same contract, and a consumer reading one
changelog can reason about all of them. If one language ever needs to diverge,
it graduates to its own repo — that is a clearer signal than per-target
version fields that quietly drift.

## Installing: name the language, or let zed infer it

The explicit form is an ordinary dependency, and is what CI and lockfiles
should record:

```toml
[dependencies]
"fiducia/fiducia-clients-java" = "^1.1"
```

For convenience, `[install].target` (or `--target` / `ZED_PKG_TARGET`) states
which language a project speaks, and zed infers it from the project's own
native manifest when unset:

| Marker at the project root | Inferred target |
| --- | --- |
| `package.json` | `nodejs` |
| `Cargo.toml` | `rust` |
| `go.mod` | `golang` |
| `pyproject.toml` / `setup.py` / `requirements.txt` | `python` |
| `pom.xml` / `build.gradle[.kts]` | `java` |
| `pubspec.yaml`, `mix.exs`, `rebar.config`, `gleam.toml`, `Gemfile`, `composer.json`, `CMakeLists.txt` | `dart`, `elixir`, `erlang`, `gleam`, `ruby`, `php`, `cpp` |

This is what makes `zed install` do the right thing in each consumer with zero
configuration — the same command in a Node app and a Java service resolves to
different packages.

Requesting a target a package does not publish is an **error listing what it
does publish**, never a silent fallback: installing a tree the toolchain
cannot read is a worse outcome than a clear failure.

## Where each language's source lands

The per-language package is dropped at `<install.dir>/<org>/<name>` and the
adapter recorded in its manifest wires it into the native toolchain — the same
"structural translation" contract as doc 15, now with the guarantee that the
tree contains only that ecosystem's files:

- **nodejs** → `node_modules/@fiducia/fiducia-clients-nodejs` + `.zed/node_path`;
  `require("@fiducia/fiducia-clients-nodejs")` resolves natively.
- **java** → `.zed/classpath` gains the target's jars; append to the Maven
  classpath.
- **golang** → `go.mod`: `replace fiducia/clients => ./.vendor/.zed/fiducia/fiducia-clients-golang`.
- **python** → the package root goes on `PYTHONPATH` / is `pip install -e`-able.

Because the published slice is the ecosystem's package root, its own native
manifest (`package.json`, `pom.xml`, `go.mod`, `pyproject.toml`) sits at the
top of what zed installs — so the native toolchain recognizes it immediately.

## Applying this to a client repo

1. Add `.zpkg.toml` at the repo root with one `[targets.<lang>]` per client
   directory.
2. Keep each client directory's **native** manifest where it already is; zed
   publishes it as part of that target's artifact.
3. `zed publish` → N packages at one version.
4. Consumers depend on the language package they need.

The repository checks in one `.zpkg.lock` beside the root manifest. That lock
pins Zed dependencies used to build/test the source repository; it is not a
catalog of the packages produced by `[targets]`. Consumer repositories create
their own lock entries for the exact language package they selected, including
artifact sha256, byte size, VCS tag, commit, and registry.

### Release preflight

Run this sequence from the polyglot repository:

```sh
# Native contract/parity tests remain owned by the repository.
./scripts/check-all-clients

# Structural checks + deterministic language-only artifacts.
zed pack

# Validate native identities/versions and show Zed, native, forge, and tag fan-out.
zed release plan

# Ask native package managers to build/check without credentials or uploads.
zed release preflight

# Verify the common Zed tag/commit and show Zed fan-out without mutation.
zed publish --dry-run

# Upload all targets in deterministic target-name order.
zed publish
```

All targets share one verified VCS tag/commit. If a multi-target upload is
interrupted, rerunning `zed publish` skips byte-identical targets already in
the registry and continues; a same-version/different-sha target is rejected.
This gives release-set retry safety without weakening version immutability.

The seven repos this is for: `fiducia-clients`, `sonus-auris-clients`,
`daedalus-clients`, `zed-clients`, `shared-auth-clients`, `scintilla-clients`,
`athleto-clients`.

## Status

Implemented in `zed-interfaces` and `zed-cli`: `[targets]`, collision/path
validation, per-target derived manifests, deterministic re-rooted artifact
fan-out, publish fan-out with retry safety, target-aware install compatibility,
typed canonical/forge release routes, credential-free native preflight, and
generated JSON Schema. The audited client repositories carry root manifests,
whole-repository targets, and isolated per-language targets; native routes are
declared only for package manifests that are not explicitly opted out or
blocked by unpublished path dependencies.
