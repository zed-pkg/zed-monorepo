# 25. Complete one-version constraint solving

**Linear:** [DEN-1553](https://linear.app/denman/issue/DEN-1553/zed-cli-solve-overlapping-compatible-transitive-constraints-before)  
**Product:** [`zed-pkg/zed-cli#89`](https://github.com/zed-pkg/zed-cli/pull/89), merged as
`4cb2018b42c0f80086920185d92d6460be675804`  
**Validated product head:** `ddf0487f560c19000e2844b62797f1cd6299c26e`  
**Independent certification:** [`zed-pkg-test/zed-pkg-e2e#36`](https://github.com/zed-pkg-test/zed-pkg-e2e/pull/36), merged as
`ed257d21abf257561bf8e7ada83debb09c80b8b0`  
**Validated certification head:** `56327079db97eeb51a425c15266ace9268f81f1c`

The recursive installer selects one version per `org/name`. A first-match walk
cannot implement that policy correctly: a broad requirement may encounter a
newer version before a later, narrower but compatible path is discovered. Zed
now solves the complete active graph before publishing a project lockfile,
adapter state, staging directory, or materialized dependency.

## The false-conflict case

```text
consumer
├── left@1.0.0  -> shared ^1
└── right@1.0.0 -> shared <=1.5.0

published shared versions: 1.5.0, 1.9.0
```

`shared@1.9.0` satisfies the left path but not the right path.
`shared@1.5.0` satisfies both. Root declaration order, package-coordinate
lexical order, artifact response timing, and worker completion timing must not
change whether the graph is solvable or which stable solution is selected.

The independently certified cold result for this graph is:

```text
resolved=3 workers=5 downloaded=3
```

The three acquired artifacts are the two roots and selected `shared@1.5.0`.
The rejected `shared@1.9.0` archive is not speculatively downloaded before the
unresolved sibling root contributes `shared <=1.5.0`. Reversing the two root
dependencies produces the same lockfile and the same summary.

## Why range intersection alone is insufficient

Requirements contributed by a package are version-dependent and live in that
exact immutable artifact's `.zpkg.toml`. Replacing one candidate can:

- remove dependencies contributed only by the rejected version;
- add different dependencies from the replacement version;
- tighten or loosen requirements on other coordinates;
- create or remove a cycle; and
- force a decision on another coordinate to be reconsidered.

A monotonic algorithm that retains every observed constraint is incorrect
because rejected candidates leave stale requirements behind. Repeatedly picking
the current maximum is also incomplete: a valid solution may require
backtracking across more than one coordinate.

## Shipped deterministic model

For every coordinate, the solver retains each active requirement together with
its root-to-package provenance path. Candidate versions are considered in
canonical descending order for the package's declared version scheme.

For each branch of the search:

1. select the next unresolved coordinate deterministically;
2. obtain the exact candidate metadata and manifest through the established
   resolver and immutable artifact path;
3. clone the branch state before adding the candidate's dependencies;
4. propagate new requirements, including newly discovered paths through
   packages that were already selected;
5. reject the branch when any selected version no longer satisfies every active
   requirement; and
6. discard the complete rejected branch state before trying the next candidate.

Constraints and dependencies contributed only by a rejected version therefore
cannot leak into the final graph. Backtracking may cross several coordinates.
A cycle-closing edge remains an active requirement but its provenance path is
terminal, preventing infinite growth of equivalent paths.

A successful solve produces one exact selected graph. Normal installation and
prefetch consume that graph rather than running separate greedy traversals.

## Version-scheme semantics

Requirement matching follows the package's declared scheme:

- semver packages use normalized semver ranges;
- calver packages use normalized calendar-version ranges;
- opaque versions are exact identifiers; and
- workspace members use the same scheme-aware matcher as registry candidates.

An opaque identifier such as `legacy-api` cannot match `^1` merely because the
requirement resembles semver syntax. This compatibility boundary is a permanent
product regression test.

## Yanked-version policy

Fresh solving reads immutable version metadata before submitting an artifact to
the acquisition pool. A yanked candidate may be cached as unavailable for a
deterministic diagnostic, but its archive must not enter a fresh cache or store.
When all otherwise matching candidates are yanked, the error points to
lock-authoritative replay:

```bash
zed install --frozen
```

An existing exact lock remains authoritative after a selected version is later
yanked. Frozen replay may acquire and install that exact locked artifact; fresh
resolution may not select it.

## Shallowest provenance waves and bounded acquisition

Completeness must not destroy the existing five-worker acquisition contract.
The solver therefore batches one highest currently viable candidate for every
coordinate in the **shallowest active provenance wave** before waiting.

This ordering has two purposes:

- unresolved parents at the same depth can use the bounded worker pool in
  parallel; and
- deeper transitive coordinates wait until every still-unresolved shallower
  parent has had a chance to contribute its requirements.

In the overlap reproducer, both root packages are selected before the shared
coordinate is acquired. The right path's `<=1.5.0` requirement is therefore
active when the shared candidate is chosen, and `1.9.0` never enters either cold
home. In a wide independent frontier, equal-depth candidates still reach the
five-worker bound. A warm replay downloads zero artifacts.

Backtracking may acquire a non-yanked candidate required by an active search
branch and later reject that branch. The immutable artifact may remain reusable
in the global store, but it must never appear in the final `.zpkg.lock` or the
consumer project. Yanked candidates have the stricter pre-acquisition rule
above.

## Artifact and project-transaction boundaries

The complete solver does not introduce another downloader or lock protocol.
The established artifact layer continues to own:

- the bounded `FetchPool`;
- deterministic result consumption;
- per-SHA descriptor-backed operating-system locks;
- verified temporary downloads;
- atomic cache publication;
- temporary extraction; and
- atomic content-addressed-store publication.

The project transaction continues to own:

- `.zpkg.lock` publication;
- adapters and language wiring;
- staging and rollback;
- hooks and references; and
- symlink/copy materialization.

Exact solver selections are exposed only to the root consumer install through a
scoped, panic-safe context. Immutable package manifests loaded from the store
remain unchanged.

## Frozen installation

Frozen installation deliberately skips solving. The committed lock graph is the
authority:

1. parse and validate the existing lockfile;
2. verify package identity and immutable hashes;
3. acquire the exact locked artifacts;
4. preserve lockfile bytes; and
5. materialize the exact graph.

A newly published version, a changed registry `latest` value, or a later yank
must not silently rewrite or re-solve a frozen graph.

## Deterministic diagnostics

When no solution exists, the diagnostic identifies the conflicting coordinate
and every active incompatible requirement with its complete provenance path.
The order follows stable coordinate and provenance ordering, never worker
completion order.

The independent canary runs an unsatisfiable graph twice with reversed root
declaration order and requires byte-identical normalized output. Failure occurs
before `.zpkg.lock`, `zed_modules`, adapter state, or transaction staging is
published.

## Certified regression matrix

The permanent product and black-box suites cover:

1. `^1` plus `<=1.5.0` selecting `1.5.0` under either declaration order;
2. exactly three selected downloads for the canonical overlap cold solve;
3. equal-depth cold breadth reaching five workers;
4. warm replay downloading zero artifacts;
5. multi-coordinate deterministic backtracking;
6. removal of dependencies contributed only by a rejected candidate;
7. deterministic complete provenance for an unsatisfiable graph;
8. diamond and cycle termination with one selected version per coordinate;
9. opaque exact-only matching;
10. fresh yank rejection before archive acquisition;
11. exact frozen replay after the locked version is yanked;
12. identical selected graph ownership between preparation and transactional
    install;
13. per-SHA interprocess acquisition locking, including Windows regressions;
14. manifestless, durable-manifest, OCI, Nix, and development-shell
    compatibility; and
15. browser-visible fixture behavior through the pinned registry stack.

## Merge evidence

The exact product head passed all 14 `zed-cli` workflows before merge. Coverage
included ordinary CI and Clippy, recursive Linux and Windows locking,
frozen-lock integrity, durable and manifestless installation, polyglot and OCI
contracts, Nix interoperability, development-shell behavior, formal
methods/review, repository hardening, and agents policy.

The exact certification head passed all eight `zed-pkg-e2e` workflows before it
merged first: complete solver, full fixture lifecycle, fixture boundaries,
recursive graph, recursive stress, browser E2E, mise runtime, and lifecycle
source-map validation. The product merged only after that independent
certification, and both merges used exact expected-head SHA guards.

## Status

Implemented and independently certified. The former overlapping-compatible-range
limitation described by docs 24 and 25 is closed by DEN-1553. Future changes to
candidate ordering, version matching, yank handling, graph preparation, or
artifact prefetch must preserve the regression matrix above rather than merely
passing a focused unit test.
