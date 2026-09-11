# zed-sublimetext package-insights extension

Updated: 2026-08-05

## Ownership and system mapping

| System | Record |
| --- | --- |
| GitHub organization | `zed-pkg` |
| Repository | `zed-pkg/zed-sublimetext` |
| Linear project | `github.com/zed-pkg` |
| Linear issue | `DEN-2326` |
| Linear delivery document | `zed-sublimetext extension delivery and project tracking contract` |
| GitHub Project | `zed-pkg-project` |
| Shared CLI dependency | `zed-pkg/zed-cli#191` |

`zed-pkg` is an independent multi-language package manager and is unrelated to
the Zed editor. This repository is the Sublime Text integration for the
`zed-pkg` package manager.

## Delivered implementation

The repository provides a native Sublime Text Python plugin that:

- discovers the active Zed package root;
- inspects `.zpkg.toml`, `.zpkg.lock`, materialization state, and interrupted
  `.zpkg-staging` transactions;
- distinguishes the package-manager CLI from the unrelated Zed editor launcher;
- renders diagnostics and recommended actions in Sublime Text;
- requires explicit confirmation before every mutating action;
- executes commands as argument arrays rather than shell-interpolated strings;
- redacts credentials and token-shaped values before displaying process output;
- supports Sublime's Python 3.8 compatibility environment and the current
  Python 3.14 host mapping through a vendored MIT-licensed TOML parser.

The extension performs a deterministic local read-only subset until
`zed-pkg/zed-cli#191` delivers the shared non-mutating JSON inspection contract.
It must not become an independent package resolver.

## Immutable delivery evidence

| Evidence | Value |
| --- | --- |
| Initial implementation commit | `2776656d4c3e24218b1b758f0462190b4fc1f5c6` |
| Python 3.8 TOML compatibility commit | `08e8255128d0c138ae2506bc267036584bc5908f` |
| Packaging PR | `zed-pkg/zed-sublimetext#1` |
| Reviewed PR head | `1e278d7373c3e138a871b3f09104200addd18138` |
| Squash merge commit | `358c746552601d472f7878b43882d9d0bec0bf2b` |
| Successful post-merge workflow | run `31037791942` |
| Artifact ID | `8943657193` |
| Artifact name | `ZedPackageInsights-358c746552601d472f7878b43882d9d0bec0bf2b` |
| Retained artifact ZIP SHA-256 | `69c4adc7c69e00c67bbdf02789ff6959bcafb1546b80a9045bd4e1ce349f0bf4` |
| Installable package SHA-256 | `b82e2b6b48c6151cbcda6c885f2c847026778ec86e8e64068ec6b8c2d51ed740` |
| Artifact expiration | `2026-09-04T19:17:28Z` |
| Local preflight | 18 tests passed; deterministic package build verified |

The GitHub Actions artifact is the authoritative retained build from the merge
commit. Its outer digest exactly matches GitHub's reported digest. The inner
`ZedPackageInsights.sublime-package` passed ZIP integrity verification and
contains 27 sorted, unique entries with the fixed `1980-01-01 00:00:00`
timestamp. The vendored TOML parser and its MIT license are present; development
scripts, tests, and workflow metadata are absent.

## Packaging contract

`scripts/build-package.py` creates
`dist/ZedPackageInsights.sublime-package` with deterministic file ordering,
timestamps, permissions, and compression. Development-only paths, test sources,
GitHub metadata, and Zed package-publication metadata are excluded.

The completed CI contract is:

1. compile and test under Python 3.8;
2. compile and test under Python 3.14;
3. build the deterministic Sublime Text package;
4. verify archive contents and byte-for-byte reproducibility;
5. upload `ZedPackageInsights-<commit-sha>` with bounded retention.

All five gates passed for merge commit
`358c746552601d472f7878b43882d9d0bec0bf2b`.

## GitHub Project operating record

All implementation, release, Package Control, compatibility, and CLI-contract
work belongs in the organization project titled `zed-pkg-project`. The canonical
registry currently records the project as `permission-blocked` because the
available GitHub app cannot mutate Projects v2 and the current runtime does not
provide working authenticated `gh project` access.

Required board fields:

- **Status:** Backlog, Ready, In Progress, In Review, Done
- **Priority:** Urgent, High, Medium, Low
- **Area:** IDE Integration, CLI Contract, Packaging, Documentation, Testing
- **Repository:** `zed-sublimetext`

The release-distribution work is tracked in
`zed-pkg/zed-sublimetext#2` and Linear issue `DEN-2326`.

## Remaining promotion gates

1. install the retained artifact in clean Sublime Text profiles on macOS,
   Windows, and Linux;
2. verify healthy, stale-lock, lock-only, invalid-TOML, and interrupted-
   transaction fixtures;
3. submit or update the package in Package Control;
4. record the Package Control publication URL and version;
5. add the delivery issue, release issue, and merged PR to `zed-pkg-project`
   when Projects v2 mutation access is available;
6. update `DEN-2326` with installation and publication evidence before marking
   Done.
