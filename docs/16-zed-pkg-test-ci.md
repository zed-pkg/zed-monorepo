# 16. The zed-pkg-test CI harness (GitHub Actions only)

**Issue:** doc 15 defines the manifest and the "complement, don't replace"
model. This doc is the proof: a set of real repos in the
[`zed-pkg-test`](https://github.com/zed-pkg-test) org, in different languages,
some depending on each other **via zed**, each tested with nothing but GitHub
Actions — no registry server, no external services.

## Layout: interdependent lib/app pairs

Each ecosystem is a pair: a `*-lib` published to the zed registry and a `*-app`
that sources it via zed while its native package manager owns everything else.

| Pair | Native manager zed complements | How the app consumes the zed dep |
| --- | --- | --- |
| [`node-lib`](https://github.com/zed-pkg-test/node-lib) + [`node-app`](https://github.com/zed-pkg-test/node-app) | **npm** | `[install].dir = ".vendor/.zed"`, `adapter = "node"` → `node_modules/@zedtest/node-lib` link + `.zed/node_path`; app `require("@zedtest/node-lib")` |
| [`rust-lib`](https://github.com/zed-pkg-test/rust-lib) + [`rust-app`](https://github.com/zed-pkg-test/rust-app) | **cargo / crates.io** | `[install].dir = ".vendor/.zed"`; app `Cargo.toml` path dep `rust-lib = { path = ".vendor/.zed/zedtest/rust-lib" }` |

Both are verified green locally and in CI: the app builds and runs, using the
zed-sourced dependency, with the native toolchain none the wiser.

## The polyglot case: one lib repo, many language packages

The pairs above are each one language. Real client repos are not — a
`*-clients` repo generates the same API client for a dozen languages from one
spec. Shipping that as one package would make a Java consumer download the Node,
Python and Dart trees, and would let a Node project install the Java client and
silently get files its toolchain never reads.

So [`polyglot-lib`](https://github.com/zed-pkg-test/polyglot-lib) is **one repo
publishing four packages**, declared with one `[targets]` table:

```toml
[targets.nodejs]
dir = "node"
adapter = "node"

[targets.golang]
dir = "go"
adapter = "go"
# …python, rust
```

`zed publish` emits one artifact per target, named `<package.name>-<target>`,
re-rooted at that subtree:

```
zedtest/polyglot-lib-nodejs@0.1.0   <- node/    (npm)
zedtest/polyglot-lib-python@0.1.0   <- python/  (pypi)
zedtest/polyglot-lib-golang@0.1.0   <- go/      (gomod)
zedtest/polyglot-lib-rust@0.1.0     <- rust/    (cargo)
```

One version in the repo, N packages on the wire, each ~650 bytes instead of one
fat artifact. Two apps consume the *same* upstream repo through different
packages:

| App | Package it takes | Proves |
| --- | --- | --- |
| [`polyglot-node-app`](https://github.com/zed-pkg-test/polyglot-node-app) | `polyglot-lib-nodejs` | `npm install` + `zed install` coexist; `require("@zedtest/polyglot-lib-nodejs")` resolves; no `.go`/`.py`/`.rs` in the tree |
| [`polyglot-go-app`](https://github.com/zed-pkg-test/polyglot-go-app) | `polyglot-lib-golang` | `go.mod` `replace` → `.vendor/.zed/zedtest/polyglot-lib-golang`; generated `.zed/go.work` also builds |

### Each app's CI asserts the negative case too

The positive path is the easy half. Every polyglot app's `zed-e2e.yml` ends by
asking for a *different* language and requiring the install to **fail**:

```
error: `zedtest/polyglot-lib-golang` targets the `gomod` ecosystem, but this project looks like `npm`
  try instead: zedtest/polyglot-lib-nodejs
  if this is deliberate, re-run with --allow-ecosystem-mismatch
```

This works because each published artifact's derived `.zpkg.toml` declares what
it is for — `language = "golang"`, `ecosystem = "gomod"` — and `zed install`
compares that against the ecosystems it detects in the consumer's project root.
Two axes are needed, not one: Java, Kotlin, Scala and Clojure are four packages
by *language* but one *ecosystem*, so a Kotlin client is correctly installable in
a Gradle project while a Node one is not.

Deliberately permissive in two cases, because a false rejection is worse than a
missed catch: a package that claims no ecosystem (everything published before
language tagging) is never gated, and a project with no recognizable ecosystem at
all is treated as unverifiable rather than wrong.

### Getting the language suffix wrong is recoverable

Package names use the colloquial tokens people search for (`-nodejs`, `-golang`),
but project inference produces short ones (`node`, `go`), and users type either.
Both resolve: `zed add zedtest/polyglot-lib-node` finds `-nodejs`, and a bare
`zed add zedtest/polyglot-lib` in a Gradle project routes to `-java`. Nothing
server-side is involved — the CLI appends or swaps a language suffix and probes,
after trying the exact name first so a real package always wins.

## The workflow (no more than GHA)

Every `*-app` ships `.github/workflows/zed-e2e.yml` with the same shape:

1. **Build the zed CLI from source.** `git clone` `zed-cli` **and**
   `zed-interfaces` (they must be siblings — the CLI path-depends on the
   interfaces crate), then `cargo build --release --bin zed`. Both are public,
   so the clone needs no token.
2. **Publish the dependency to a hermetic `file://` registry.** `git clone` the
   `*-lib` repo and `zed publish --skip-vcs-checks` into
   `file://$RUNNER_TEMP/zed-reg`. No server — the file registry *is* the
   registry. `ZED_PKG_HOME` / `ZED_PKG_REGISTRY` are exported once via
   `$GITHUB_ENV`.
3. **Let the native manager run** (`npm install`, or cargo resolves crates.io) —
   this is the "complement" half.
4. **`zed install`** — materializes the select deps into `[install].dir` and
   runs the adapter (node_modules link + `.zed/node_path`, or just the tree for
   cargo's path dep).
5. **Build/run in the language** and assert the zed dep resolved.

Because the registry is `file://` and the only services are the language
toolchains' own `setup-*` actions, the whole thing runs on a stock
`ubuntu-latest` runner with no secrets.

## Extending to the rest of the matrix

New ecosystems follow the identical pattern; only step 4→5 changes, per the
per-language recipe in [doc 15](15-manifest-and-dep-locations.md):

- **typescript / nextjs** — same as node (add a `tsc`/`next build` step).
- **go** — `go.mod` `replace zedtest/x => ./.vendor/.zed/zedtest/x`; `go build`.
- **java / kotlin** — a `[build]` step in the `*-lib` compiles a jar; the app
  uses `javac -cp "$(cat .zed/classpath)" …` (adapter `java`); `setup-java`.
- **dart / flutter** — `pubspec.yaml` `path:` dependency; `dart`/`flutter test`.
- **elixir / erlang** — `mix.exs` / rebar `{path, …}` (or `ERL_LIBS`).
- **gleam** — path dependency in `gleam.toml`.
- **cpp** — `add_subdirectory(.vendor/.zed/zedtest/…)`; CMake.

The `*-lib` in each case carries both its `.zpkg.toml` (for zed) and its native
manifest (`package.json` / `Cargo.toml` / `pom.xml` / `pubspec.yaml` / …), so
the native toolchain recognizes it the moment zed drops it into `[install].dir`.

## Status

| Harness | State |
| --- | --- |
| `node-*`, `rust-*` single-language pairs | proven in CI |
| `polyglot-lib` + `polyglot-node-app` + `polyglot-go-app` | scaffolded and verified locally (publish → 4 packages, both apps build and run, wrong-language install refused); repos not yet created in the org |

The remaining single-language pairs (ts, nextjs, java, dart, flutter, elixir,
erlang, gleam, cpp) are stamped from the lib/app + `zed-e2e.yml` template with
the doc-15 recipe swapped in for the build/run step. Additional polyglot
consumers (a python app, a rust app) are stamped from `polyglot-go-app` — only
the toolchain setup and the build/run step change; `polyglot-lib` already
publishes all four packages.
