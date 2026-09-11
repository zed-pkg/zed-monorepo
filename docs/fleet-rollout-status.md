# Fleet package-pattern rollout status

Status date: 2026-08-05

This ledger separates direct repository remediation from audit coverage. A
repository is not considered compliant merely because a language directory or
Zed target exists: the client contract requires native package/build metadata,
implementation source, and runtime or structural validation.

## Directly remediated organizations

The following organizations have coordinated draft branches and pull requests
for the applicable interfaces, library, clients, CLI, and monorepo roles.
Nothing in this table is represented as merged until GitHub Actions and review
complete.

| Organization | Direct changes | Important notes |
| --- | --- | --- |
| `zed-pkg` | canonical clients, CLI package edges, monorepo/submodule boundary, fleet policy | no `zed-lib` repository exists, so no dangling dependency was added |
| `fiducia-cloud` | clients and monorepo | `fiducia-lib` and `fiducia-cli` do not exist; expiring topology exceptions record the missing work |
| `athlet-o` | interfaces, lib, clients, CLI, monorepo | complete dependency chain; Kotlin and Swift are required |
| `apostille-me` | interfaces, plural `apme-libs`, clients, CLI, monorepo | all consumers use the existing plural library coordinate |
| `anticaptrad` | interfaces, canonical singular `act-lib`, clients, CLI, monorepo | `act-libs` also exists and remains excluded pending role/name reconciliation |
| `voxletra` | interfaces, lib, clients, CLI, monorepo | mobile-facing; Kotlin and Swift are mandatory |
| `shared-auth` | interfaces, lib, clients, CLI, monorepo | shared mobile/server SDK; Kotlin and Swift are mandatory |

The product repositories use branch `agent/zed-package-contract-20260805`,
except the canonical Zed branches and Fiducia monorepo branch documented in
their pull requests.

## Validation completed outside GitHub Actions

The following checks were executed against the actual draft branches:

- The canonical `zed-clients` structural validator passed.
- Product client validators passed for Fiducia, Athlet-O, Apostille Me,
  Anticaptrad, Voxletra, and Shared Auth. They require all 16 client slices:
  C, C++, Zig, Gleam, Erlang, Elixir, Dart, Rust, Java, Go, Python, Ruby, PHP,
  TypeScript, Kotlin, and Swift.
- TypeScript runtime contracts declare Node.js, Deno, Bun, and edge execution;
  edge probes invoke the pinned `wrangler@4` runtime.
- CLI manifests passed exact dependency checks where a complete package chain
  exists: interfaces, library, and clients are required; infrastructure is
  forbidden.
- Recursive monorepo initialization and boundary checks passed locally on
  Linux for Zed, Fiducia, Athlet-O, Apostille Me, Anticaptrad, Voxletra, and
  Shared Auth.
- GitHub workflows repeat recursive submodule checks on Linux, macOS, and
  Windows. Those remote checks remain merge gates and are not claimed green in
  this ledger.

## Connected organizations under executable audit

These connected production organizations are covered by the central auditor
but have not yet received the same coordinated direct repository changes:

- `agent-pontifex`
- `akrion-sim`
- `benefactor-cc`
- `canonical-cloud`
- `channelsiege`
- `declarative-migrations`
- `embedded-alerts`
- `evento-globolo`
- `file-tunnel`
- `hypesiege`
- `memebank`
- `messaging-intel`
- `meta-agents-demo`
- `networking-components`
- `ORESoftware`
- `opto-sync`
- `quaestor-ledger`
- `scintilla-run`
- `streamkore`
- `StreemPilot`
- `usa-acc`

The scheduled auditor reports missing role repositories, malformed manifests or
locks, dependency-boundary violations, incomplete client slices, missing
TypeScript runtime coverage, mobile SDK omissions, and monorepo/submodule
violations. Audit coverage is not equivalent to remediation.

## Access and topology blockers

- Organizations without a current GitHub App installation cannot be read or
  changed by this rollout. The auditor records them as unavailable rather than
  compliant.
- The available GitHub connector can update repositories but does not expose a
  repository-creation operation. Missing `*-clients`, `*-interfaces`, `*-lib`,
  `*-cli`, or `*-monorepo` repositories therefore remain explicit creation
  findings.
- `zed-pkg/zed-lib`, `fiducia-cloud/fiducia-lib`, and
  `fiducia-cloud/fiducia-cli` are known missing repositories.
- `anticaptrad/act-lib` and `anticaptrad/act-libs` overlap. The current package
  graph selects `act-lib` and forbids importing both until ownership and API
  responsibilities are reconciled.
- Private sibling submodules require a repository or organization secret named
  `SUBMODULE_TOKEN`. Workflows fall back to `github.token`, which is sufficient
  only when that token can read every referenced repository.
- Draft pull requests remain unmerged until their branch protection, native
  build, runtime, and three-operating-system submodule checks finish.

## Required completion criteria

An applicable organization is complete only when:

1. interfaces and library repositories are published as valid Zed packages;
2. clients import interfaces and library, contain real implementations for the
   required language matrix, and pass native/runtime checks;
3. CLI imports interfaces, library, and clients without importing infra;
4. monorepo imports reusable source packages but not CLI or infra, and recursive
   submodules work on Linux, macOS, and Windows;
5. `.zpkg.toml` and `.zpkg.lock` pass the central format and dependency checks;
6. all required GitHub Actions and reviews pass, followed by dependency-order
   merges.
