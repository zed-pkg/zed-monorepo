# 19. Polyglot publishing: what is actually verified

Doc 18 sets the release model for multi-registry fan-out. This doc is its
empirical counterpart: what CI now *proves* and what it *found* when run
against real repositories.

Everything below was run against the nine `*-clients` repositories and a
five-language fixture, not reasoned about.

## Goal 2 works: `[targets.repository]` is supported

An earlier draft of this doc claimed `dir = "."` was rejected by `zed pack`.
That was wrong, and it is worth recording why: `pack_all` does guard against a
target carrying its own `.zpkg.toml`, but the guard **exempts the repository
root explicitly**:

```rust
// `dir = "."` is the explicit whole-repository target used alongside
// language slices. Its manifest is the source manifest by definition
// and is replaced with the derived single-target manifest below.
// Nested targets must still never carry a second manifest.
if section.dir != "." && source.join(MANIFEST_FILE).exists() {
```

with a test asserting the repository artifact contains every language slice.
So doc 18's convention is correct as written, and the whole-repository artifact
(goal 2) ships alongside the isolated slices (goal 3) from one manifest.

The parity gate therefore permits `dir = "."` and enforces isolation only
*between language targets*: a language target nested inside another language
target would put the inner language's bytes in the outer artifact, which is the
thing doc 17 exists to prevent.

## What CI proves now

`zed-cli/.github/workflows/polyglot.yml` packs `tests/fixtures/polyglot` — one
repo, five languages — and asserts:

- exactly five artifacts, one per declared target;
- each slice contains its own language and **no** file extension belonging to
  the other four;
- each slice carries its ecosystem's native manifest at its *root*, so the
  native toolchain recognizes it without configuration;
- no slice carries a `[targets]` block (fan-out cannot recurse);
- dev/test files are stripped and `LICENSE` is hoisted into every slice;
- all five publish to a `file://` registry, and republishing skips
  byte-identical targets rather than erroring.

Then — the part nothing checked before — each slice is handed to the **real**
native tool: `npm pack --dry-run`, `python -m build` + `twine check`,
`cargo package`, `gem build`, `go build`. If npm would reject the tarball, CI
fails.

That is the load-bearing evidence for doc 18's claim that native registries can
mirror the same commit: the slice `zed pack` emits *is already* a publishable
native package.

## What it found

| Finding | Where |
| --- | --- |
| `test_*.py` shipped in every published Python slice — `DEFAULT_EXCLUDES` had `*_test.py` but not unittest's default `test*.py` pattern | `zed-interfaces/src/excludes.rs`, fixed |
| Version drift: `pubspec.yaml` at `1.0.0` against a repo version of `0.1.0` | `daedalus-clients`, fixed |
| Go subdirectory modules need a target-specific tag, not the repository-wide tag | fiducia, quaestor, athleto, daedalus — **represented by native `tag_format`; authenticated release execution remains open** |
| The gate ran the ecosystem's tooling against the *source subtree* while claiming to check "exactly what the registry would receive". Packing strips dev files, hoists `LICENSE` into every slice, and substitutes the derived manifest — so it both missed real problems and invented ones: scintilla's dart slice was rejected for a missing LICENSE the artifact contains | all `zed-polyglot.yml`, fixed (`--json` now emits the artifact name; jobs unpack it) |
| `dir = "."` was assigned a native registry by inference. A repo keeping its own workspace `package.json` at the root had that mistaken for the whole-repository target's identity, and the dry-run tried to publish the entire repo to npm — contradicting `Manifest::validate`, which rejects a native route on `dir = "."` | `check-native-parity.py`, fixed |
| Default excludes stripped `CHANGELOG*` while `publish.exclude` can only *add* patterns, so no repository could ship one — and `dart pub publish` fails a package outright without it | `zed-interfaces/src/excludes.rs`, fixed (`include_readme` covers both) |
| Published slices did not declare which language they were for, so nothing could stop a `-java` client installing into a Node project | `zed-interfaces` `package.language`/`ecosystem` + the install guard, fixed |

## A retracted finding: "slices depend on things outside themselves"

An earlier revision of this doc listed three slices as unpublishable because
their manifests reach outside the slice — `athleto-clients` dart
(`path: ../../../athleto-sync`), `scintilla-clients` flutter (`path: ../dart`),
`fiducia-clients` rust (a `git =` dependency crates.io forbids). That finding was
wrong, and the reason is worth keeping.

The retraction holds for the two Dart cases and **overreached on the third**.

**Correct.** `scintilla-clients` flutter and `athleto-clients` dart both declare
`publish_to: none`, the parity gate honors it and reports `ok; publish_to: none`,
and athleto's manifest already uses the idiomatic shape — hosted versions under
`dependencies`, paths only under `dependency_overrides`, with a comment noting
release automation swaps them. There was nothing to fix in either.

**Overreached.** Grouping `fiducia-clients` rust into the same retraction was
wrong, and DEN-709 had it right. `publish = false` explains why the *parity
script* skips that slice; it does not explain why the crates.io dry-run stopped
failing, and it says nothing at all about the Go and Java slices in the same
repo — both of which had real defects (a `replace` pointing at
`../../../fiducia-interfaces/generated/go`, and Java source that would not
compile) that this doc never examined before dismissing the class.

Those are now genuinely fixed rather than reclassified: the Go `replace` is gone
and the target declares `tag_format = "clients/go/v{version}"`; the packed Java
slice compiles clean (`javac` on JDK 24, and `java -> Maven Central` passes CI);
Rust is classified out via `publish = false` with no native route, which is one
of the two resolutions DEN-709 itself proposed. The full matrix is 30/30 green.

Two lessons, not one. The `dir = "."` correction above: check what a manifest
declares about its own publishing before calling a dependency shape a defect.
And this one: a retraction is a claim like any other — verifying two of three
cases and generalizing is the same error as the finding it was retracting.

## The Go tag gap is now represented explicitly

A Go module in a subdirectory is fetched by the tag `<subdir>/vX.Y.Z`. That is
the module proxy's rule, not a convention. `clients/go` at `0.1.0` therefore
requires the tag `clients/go/v0.1.0`.

`[publish].tag_format` remains the repository-wide Zed release tag. A native
Go route now adds its own tag template:

```toml
[targets.golang.native]
registry = "go-modules"
package = "github.com/fiducia-cloud/fiducia-clients/clients/go"
tag_format = "clients/go/v{version}"
```

Manifest validation requires the directory prefix, and the release plan emits
`clients/go/v0.1.0` alongside the repository tag `v0.1.0`. Creating and
attesting that native tag belongs to the future authenticated release runner.
Target-only *source* mirrors remain a separate `git subtree split` concern.

The same mechanism generalizes beyond Go: Swift, and any ecosystem that
resolves a subdirectory by tag, are served by the same per-target
`tag_format` rather than a repo-wide template.

## Identity cannot be derived, only declared

Doc 18 is right that native manifests stay authoritative. The audit shows *how
far* the names diverge, which is why no naming rule could ever recover them:

```
target      zed package                            native registry  native package
----------  -------------------------------------  ---------------  ----------------------------------
golang      fiducia/fiducia-clients-golang@0.1.0   Go module proxy  github.com/…/clients/go
java        fiducia/fiducia-clients-java@0.1.0     Maven Central    cloud.fiducia:fiducia-client@0.1.0
nodejs      fiducia/fiducia-clients-nodejs@0.1.0   npm              @fiducia/client@0.1.0
python      fiducia/fiducia-clients-python@0.1.0   PyPI             fiducia-client@0.1.0
…
31 target(s): 29 publishable to a native registry, 2 to zpkg.tech only
```

Two further constraints the implemented `[targets.<name>.native]` schema
accommodates:

- **Not every target has a registry.** `shell` and `matlab` are legitimately
  zpkg.tech-only. `registry` must be optional, not defaulted.
- **Not every ecosystem declares a version.** Go, Swift, Packagist, opam,
  Clojars and sbt take the version from the VCS tag alone, so "keep versions in
  sync" cannot be a uniform check. LuaRocks is the inverse: `0.1.0-1` is
  version `0.1.0` plus a rockspec revision, and naive comparison reports drift
  that is not there.

## The registry does not know what language a package is

Every check described so far runs against artifacts on disk or a `file://`
registry. Driving the *live* registry in a browser
(`zed-e2e/suites/{playwright,puppeteer}/web-polyglot.*`) surfaces the gap none
of them could: one publish of a four-language repository leaves five navigable
packages, and **nothing in the API or the UI says which language any of them
is**.

`package.language` and `package.ecosystem` are declared in the manifest and
enforced by the install guard, but they stop at the artifact. They are absent
from the registry DTOs (`PackageMetadata`, `PackageSummary`) and from the
package page. Two consequences:

- Browsing the registry, `acme-clients-java` is indistinguishable from any
  unrelated package. The `-java` suffix is a naming convention the registry
  does not understand, and a target that overrode `name` has no suffix at all.
- The language guard can only refuse a mismatched install *after* the artifact
  is downloaded and its manifest read. The registry could have refused it up
  front.

The browser suite asserts what the UI does expose — separate pages per
language, distinct `sha256` per slice, lockstep versions, and that the polyglot
source name deliberately does not resolve. Language identity is the piece it
cannot assert, because there is nothing to assert against.

Promoting `language`/`ecosystem` into the registry contract is the natural next
step after typed native routes: the same declaration that decides where a slice
publishes should also be what the registry advertises.

## Status

Verified in CI across nine client repositories and one fixture. Typed native
routes, forge compatibility validation, deterministic release planning, and
per-route tag formats are implemented. Authenticated registry uploads,
release-set attestations, and generic target-only source-mirror automation
remain open.
