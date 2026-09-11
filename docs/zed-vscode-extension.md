# zed-vscode package-insights extension

Updated: 2026-08-05

## Ownership and system mapping

| System | Record |
| --- | --- |
| GitHub organization | `zed-pkg` |
| Target repository | `zed-pkg/zed-vscode` |
| Linear project | `github.com/zed-pkg` |
| Linear issue | `DEN-2278` |
| Related IDE protocol issue | `DEN-2175` |
| GitHub Project | `zed-pkg-project` |

`zed-pkg` is an independent multi-language package manager and is unrelated to the Zed editor. This repository is a Visual Studio Code extension for the `zed-pkg` package manager.

## Initial candidate

- Verified implementation commit: `376372168e12ddd0d2f3cf873a120671d64ca422`
- Tracking and contract-alignment commit: `7fe04d03d5c16c45381aff23eec4e8c6c441ec31`
- Intended long-lived branches: `main` and `dev`
- Delivery branch: `agent/den-2278-cross-system-tracking`

The implementation includes multi-root package discovery, `.zpkg.toml` and `.zpkg.lock` analysis, package-state and issue trees, diagnostics, quick fixes, visible Zed tasks, CI, VSIX release automation, and an offline static-analysis fallback.

## Canonical IDE boundary

The authoritative read-only protocol is:

```sh
zed inspect --workspace /absolute/package/root --json
```

The shared schema must live in `zed-interfaces` and be implemented by `zed-cli`. IDE integrations must not implement their own dependency resolver. Static parsing in the extension is a bootstrap and offline fallback, not an alternate source of truth.

## Safety contract

- Diagnostics and inspection are read-only.
- Every mutating recommendation displays the exact executable, argument vector, and working directory.
- Every mutating command requires explicit user confirmation.
- The extension never edits package state silently.
- Unknown schema versions fail closed and remain visible to the user.

## Promotion gates

1. Create public repository `zed-pkg/zed-vscode` without rewriting the verified initial commit.
2. Push `main`, `dev`, and the review branch.
3. Open and review the tracking/contract alignment pull request.
4. Require terminal TypeScript, unit-test, extension-build, workflow, and VSIX packaging checks.
5. Merge with an expected-head guard.
6. Publish the VSIX and retain its digest, workflow run, and provenance metadata.
7. Add the issue or pull request to `zed-pkg-project` with repository, Linear issue, candidate SHA, merge SHA, status, gate, and immutable evidence.
8. Update Linear and this document with the final merge and artifact identities before marking Done.

## Current environment boundary

The connected GitHub app can update existing repositories and pull requests, but it does not expose organization repository creation or GitHub Projects-v2 item mutation. Those two operations require an authenticated `gh` runtime with organization repository and project scopes. The implementation bundle and Git history remain ready for publication while this boundary is resolved.
