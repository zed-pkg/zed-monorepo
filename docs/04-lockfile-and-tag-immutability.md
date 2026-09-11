# 4. Lockfile vs mutable tags and branches

**Issue:** because zed-pkg is anchored to VCS, it inherits VCS's mutability
threat — a repo owner can force-push `main` or delete and recreate `v1.2.0`
pointing at different (possibly malicious) code. A lockfile is the only thing
between a deterministic build and chaos, and switching branches must not
silently change what's installed.

## Design: artifacts are immutable, the lockfile pins bytes

The key move is that **installs never pull from a tag or branch at install
time.** They pull an immutable, content-addressed artifact:

- Publishing uploads a specific tarball; the registry stores it by sha256 and
  **refuses to overwrite an existing `org/name@version`** (`version_exists`).
  A deleted-and-recreated tag cannot change already-published bytes.
- `.zpkg.lock` pins, per package: `sha256`, `size`, `vcs_tag`, **`vcs_commit`**,
  and the source registry. Install verifies the downloaded artifact's sha256
  against the lock.
  ([`Lockfile`/`LockedPackage`](https://github.com/zed-pkg/zed-interfaces/blob/main/src/lockfile.rs).)
- `zed install --frozen` installs **exactly** the locked sha256s and fails on
  any drift between manifest and lock — the mode CI and containers use.
- **Yanking** is the one sanctioned version-level control, and it is
  non-destructive: `zed yank org/name@version` marks a published version
  hidden from *fresh* resolution — cargo-style, the resolver falls through to
  the next-best match and errors only when every version satisfying the
  requirement is yanked — while the bytes stay downloadable so existing
  `.zpkg.lock` pins keep installing. It never rewrites or deletes an artifact,
  so it can't break a locked build. See the registry
  [`yank` route](https://github.com/zed-pkg/zed-api-server.rs/blob/main/src/routes/yank.rs),
  the `zed yank` CLI, and the resolver's yanked-version skip
  ([`install`](https://github.com/zed-pkg/zed-cli/blob/main/src/ops.rs)).

So switching git branches in your *own* repo changes `.zpkg.toml` /
`.zpkg.lock`, and `--frozen` makes the resulting install fully determined by
the lock. A dependency author mutating their tag cannot affect you unless you
re-resolve, and even then a changed artifact for an existing version is
rejected by the registry.

## Provenance at publish time

Authors **must** create a matching tag on the backing repo before publishing;
the CLI verifies the tag exists and points at `HEAD`
([`zed-cli/src/vcs.rs`](https://github.com/zed-pkg/zed-cli/blob/main/src/vcs.rs)),
and the server re-verifies against the forge
([`zed-api-server` verify](https://github.com/zed-pkg/zed-api-server.rs/blob/main/src/verify.rs),
`ZED_VERIFY_TAGS=github`). The tag and commit are then frozen into the lock.

## Status: implemented

Lockfile with sha256 + commit pinning, `--frozen`, registry immutability,
non-destructive yanking, and two-sided tag verification all exist today.
Planned: Sigstore/cosign signatures over the manifest + tarball, and a `zed
audit` that re-checks every locked artifact's sha256 and tag→commit binding.
