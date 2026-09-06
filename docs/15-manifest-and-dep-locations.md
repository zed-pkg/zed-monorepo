# 15. The manifest, where deps go, and complementing npm/maven

**Issue:** zed is not trying to replace npm, Maven, pub, cargo, mix, or rebar.
The goal is narrower and friendlier: for a **few select dependencies** — an
internal library, a package that only lives on your VCS host, a pinned fork —
you source them **via zed** while the language's own package manager keeps
owning everything else. For that to work two things must be crystal clear: what
the manifest is, and *where zed puts the deps* so the native toolchain can see
them next to its own. This doc pins both down.

## The manifest: `.zpkg.toml`, at the repo root

Every zed package — in any language — has one `.zpkg.toml` at its root (TOML
only). Minimal shape:

```toml
[package]
org = "zedtest"            # lowercase slug; the registry namespace
name = "node-lib"          # lowercase slug; unique within the org
version = "1.0.0"          # semver by default (calver / opaque also supported)
description = "a zed-sourced library"
license = "MIT"

[package.repository]        # the VCS source of truth (any git/hg host)
vcs = "git"
url = "https://github.com/zed-pkg-test/node-lib"

[dependencies]              # the FEW deps you source via zed, as org/name = range
"zedtest/logkit" = "^0.3"

[install]                   # NEW: where zed materializes those deps (§ below)
dir = ".vendor/.zed"
```

Other sections (all optional): `[build]` / `[build-dependencies]` (a
post-extract compile step + its toolchain), `[bin]` (executables hoisted to
`<dir>/.bin` and runnable via `zed run`), `[publish]` (extra excludes, smoke
test), `[workspace]` (monorepo members), `[overrides.build]` (patch a dep's
build). The manifest is language-agnostic: a Node package also keeps its
`package.json`, a Java package its `pom.xml` — zed publishes those files too, so
the native toolchain still recognizes the package when zed drops it in place.

## Where deps go: `[install].dir` (configurable)

`zed install` resolves the `[dependencies]`, fetches each once into the global
content-addressed store (`~/.zed-pkg`), and links it into the project at:

```
<install.dir>/<org>/<name>/…
```

`[install].dir` defaults to **`zed_modules`** and is freely relocatable — e.g.
`.vendor/.zed` or `.deps/.zed`. It must be a safe relative path (no leading `/`,
no `..`). A `.zpkg.lock` pins exact versions + sha256 next to the manifest, and
the store is shared across projects (pnpm-style symlinks; `--install-mode copy`
for self-contained container layers).

## Complementing the native toolchain: adapters

Dropping files in a directory isn't enough — the language's resolver has to find
them. The **ecosystem adapter** (`--adapter`, `ZED_PKG_ADAPTER`, or
`[install].adapter`; `auto` detects from the project) wires the zed tree into
the toolchain *without touching* how the native manager resolves everything
else:

| Ecosystem | Adapter does | How you consume it (alongside npm/maven/…) |
| --- | --- | --- |
| **Node / TS / Next** (`node`) | symlinks `node_modules/@<org>/<name>` **and** writes `.zed/node_path` = the install dir | `require("@org/name")` resolves natively; or `NODE_PATH="$(cat .zed/node_path)" node …` for `require("org/name")`. npm still owns the rest of `node_modules`. |
| **JVM / Java / Kotlin** (`java`) | writes `.zed/classpath` = `:`-joined paths of every `.jar` under the install dir | `javac -cp "$(cat .zed/classpath):$MAVEN_CP" …` — append it to Maven's classpath. |
| **everything else** (`none`) | just the `<dir>/<org>/<name>` tree | point the toolchain's own path knob at it: cargo `[patch]`/path dep, Go `replace ⇒ ./<dir>/…`, pub `path:` dependency, mix `path:`/`ERL_LIBS`, CMake `add_subdirectory`. |

The principle ("structural translation"): the same stored artifact lands where
each toolchain looks, so a zed-sourced dep is indistinguishable from a native
one at build time — that's what makes zed a *complement*.

## Recipe per language (the extension pattern)

`none`-adapter ecosystems consume the tree through their own path mechanism; the
per-language one-liners:

- **Rust** — `Cargo.toml`: `logkit = { path = ".vendor/.zed/zedtest/logkit" }`.
- **Go** — `go.mod`: `replace zedtest/logkit => ./.vendor/.zed/zedtest/logkit`.
- **Dart / Flutter** — `pubspec.yaml`: `dependencies: { logkit: { path: .vendor/.zed/zedtest/logkit } }`.
- **Elixir** — `mix.exs`: `{:logkit, path: ".vendor/.zed/zedtest/logkit"}`.
- **Erlang (rebar3)** — `{deps,[{logkit,{path,".vendor/.zed/zedtest/logkit"}}]}` (or add the dir to `ERL_LIBS`).
- **Gleam** — a path dependency in `gleam.toml` pointing at the install dir.
- **C/C++** — `add_subdirectory(.vendor/.zed/zedtest/logkit)` / `-I` + link.

Each is "one line in the native manifest" — the native manager owns resolution;
zed only guarantees the source is present at `<install.dir>/<org>/<name>` with a
verified sha256.

## Status: implemented (CLI) + example repos

`[install].dir` and the Node NODE_PATH emission ship in `zed-cli` /
`zed-interfaces`. Worked, GitHub-Actions-tested examples live in the
[`zed-pkg-test`](https://github.com/zed-pkg-test) org as interdependent
lib/app pairs (a dependency published to a hermetic `file://` registry in CI,
then installed into the consumer's `[install].dir` and used by the native
toolchain). See doc 16 for the CI harness.
