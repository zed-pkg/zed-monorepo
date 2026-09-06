# 3. Polyglot version strings

**Issue:** a truly polyglot ecosystem (Node, Python, Go, Rust, Erlang, …)
labels releases inconsistently, and mixing git tags, hg tags, and commit
hashes makes "what version is this?" ambiguous.

## Design

zed-pkg standardizes on **semver** as the resolution algebra and treats the
VCS tag as provenance, normalizing at the edges:

- **Manifest version** (`.zpkg.toml` `package.version`) is validated against
  the package's declared `package.version_scheme` — `semver` by default,
  `calver` for calendar versions, or `opaque` for arbitrary tags. This is the
  single normalized identity used for resolution and the store. See
  [`VersionScheme`/`PackageSection.version_scheme`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/version.rs)
  (validated in [`Manifest::validate`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/manifest.rs)).
- **Tag mapping** is configurable per package via `publish.tag_format`
  (default `v{version}`), so `v1.2.0`, `1.2.0`, or `rel-1.2.0` on the backing
  repo all map to the semver `1.2.0`. See
  [`Manifest::vcs_tag`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/manifest.rs).
- **Requirements** are semver/calver ranges (`^1.2`, `=0.2.0`, `>=2026.0.0`)
  or, for opaque packages, exact strings, resolved to the max satisfying
  stable version
  ([`Requirement`/`resolve`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/version.rs)).
  `parse_version` tolerates foreign tag spellings at the edges — a bare `v`,
  calendar versions, Go `+incompatible`, and a subset of PEP 440
  (`1.2.3rc1` → `1.2.3-rc.1`) — mapping them onto one semver total order.
- **Commit hashes** are recorded for provenance (`vcs_commit` in the
  lockfile), not used as version identifiers — see
  [4](04-lockfile-and-tag-immutability.md).

## Why not accept arbitrary version strings?

Letting every ecosystem's scheme flow through unchanged pushes the ambiguity
onto every consumer and the resolver. Normalizing to semver at publish time
(and validating it there — the API server rejects non-semver) keeps
resolution total and deterministic across languages.

## Status: implemented

- Semver validation, configurable `tag_format`, max-satisfying resolution, and
  commit recording — done.
- An optional `package.version_scheme` (`semver` | `calver` | `opaque`) now
  validates `package.version` the right way and drives resolution: calendar
  versions normalize to a semver total order (`2026.07.24` → `2026.7.24`);
  opaque tags resolve only by exact match. See
  [`zed-interfaces/src/version.rs`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/version.rs).
- Per-ecosystem tag normalization is applied during resolution: a bare leading
  `v`, Go's `+incompatible`, and a subset of PEP 440 (`1.2.3rc1` → `1.2.3-rc.1`)
  are all understood, so foreign tag spellings sort into one order.
- The scheme is carried through `PackageMetadata` and persisted server-side
  (api-server `package.version_scheme` column). Unit tests cover calendar
  ordering, opaque exact-match, and the normalization cases.
- Planned: broadening the PEP 440 coverage and exposing scheme presets as a
  publish-time lint.
