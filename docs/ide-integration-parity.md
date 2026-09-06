# IDE integration parity and sandbox certification

Updated: 2026-08-05

## Purpose

This record compares the Zed Package Manager integrations for Sublime Text,
JetBrains IDEs, Visual Studio Code, Qt Creator, Xcode, Eclipse, and Visual
Studio against one shared capability, safety, testing, and distribution bar.

`zed-pkg` is an independent package manager and is unrelated to the Zed editor.

## Parity levels

1. **Core conformance** — multi-root discovery, package-state diagnostics,
   versioned inspection adapter, deterministic fallback, argv execution,
   bounded runtime, credential redaction, unsafe-action rejection, and native
   unit tests.
2. **Native shell** — editor-native diagnostics, package tree/tool window,
   file watchers, settings, exact command and working-directory preview, and
   explicit confirmation before mutation.
3. **Distribution** — dedicated repository, reproducible package, retained
   artifacts, clean editor-instance tests, signing, and marketplace or update-
   channel publication.

An integration is described as fully user-facing parity only after all three
levels pass. Buildable cores are not represented as completed editor plugins.

## Current comparison

| Integration | Repository/source | Core | Native shell | Distribution | Current position |
| --- | --- | --- | --- | --- | --- |
| Sublime Text | `zed-pkg/zed-sublimetext` | Pass | Pass | Partial | Live integration; multi-root parity, staging recovery, confirmation gates, deterministic `.sublime-package`, and independent Python 3.8/3.14 sandbox certification pass. Clean-profile platform verification and Package Control publication remain. |
| JetBrains / IntelliJ | `zed-pkg/zed-intellij` | Pass | Pass | Partial | Live integration; plugin verifier, package-state tool window/diagnostics, multi-package discovery, output redaction, wrong-launcher detection, staging recovery, and independent sandbox certification pass. Marketplace/clean-instance publication evidence remains. |
| VS Code | `zed-pkg/.github/blueprints/zed-vscode` | Pass | Candidate pass | Partial | Source-visible extension candidate with multi-root tree, Problems diagnostics, commands, settings, watchers, safe CLI boundary, tests, and valid VSIX. Dedicated repository, extension-host GUI tests, signing, and Marketplace publication remain. |
| Qt Creator | `zed-pkg/.github/blueprints/zed-qtcreator` | Pass | Missing | Missing | C++20 process/safety core and CTest pass. `ExtensionSystem::IPlugin`, ProjectExplorer/Issues integration, clean-instance tests, and plugin packaging remain. |
| Xcode | `zed-pkg/.github/blueprints/zed-xcode` | Pass | Missing | Missing | Swift process/safety core and macOS tests pass. Companion app, Xcode Source Editor Extension, entitlements, signing, and app/appex tests remain. |
| Eclipse | `zed-pkg/.github/blueprints/zed-eclipse` | Pass | Missing | Missing | Java 21 process/safety core and Maven/JUnit tests pass. PDE/OSGi shell, view, markers, quick fixes, plug-in application tests, and p2 publication remain. |
| Visual Studio | `zed-pkg/.github/blueprints/zed-visual-studio` | Pass | Missing | Missing | .NET 8 process/safety core and Windows tests pass. AsyncPackage, tool window, Error List integration, experimental-instance tests, signing, and VSIX publication remain. |

## Shared conformance bar

All certified live integrations and candidates are evaluated for:

- multi-root package discovery;
- manifest, lockfile, materialization, stale-lock, and interrupted-transaction
  diagnostics;
- CLI availability and wrong-executable detection;
- executable-plus-argument-vector process execution without a shell;
- explicit working directory and bounded timeout/cancellation;
- token, authorization, password, secret, API-key, and GitHub-token redaction;
- versioned `zed inspect --workspace <absolute-root> --json` adaptation;
- deterministic read-only fallback when the inspection endpoint is unavailable;
- rejection of command actions that do not require explicit confirmation;
- native unit/toolchain tests and retained artifacts where packageable.

The final shared JSON inspection endpoint remains tracked in
`zed-pkg/zed-cli#191`; integrations must not become independent dependency
resolvers.

## Merged delivery evidence

| Change | Pull request | Merge commit |
| --- | --- | --- |
| Sublime multi-root and conformance parity | `zed-pkg/zed-sublimetext#3` | `c3153867dff0b560946c9b7e287ed50366b87e6c` |
| JetBrains safety and staging parity | `zed-pkg/zed-intellij#2` | `7282fdbc7046bb2ba58369b59ef627211033e145` |
| Shared parity contract and five candidate implementations | `zed-pkg/.github#25` | `051c897578657f8993924f4ecd2a176f4448d404` |
| Independent seven-editor sandbox matrix | `zed-pkg-test/zed-pkg-e2e#105` | `ee7d220807008e9222bbe80e2efbf3c39b21dfc7` |

## Native candidate certification

Candidate workflow run `31048652586` passed:

- parity policy validation;
- VS Code Node tests and VSIX packaging;
- Qt Creator CMake build and CTest on Ubuntu;
- Xcode Swift tests on macOS;
- Eclipse Java 21/Maven tests;
- Visual Studio .NET tests on Windows.

VS Code retained candidate artifact:

- artifact ID: `8947482937`;
- outer artifact digest:
  `sha256:d1d9ab59cca070b6b9a4ba36f14809c3131a9a755bfd5d6b03b6b6392ae3db85`;
- inner VSIX SHA-256:
  `5cf6bec8304cc0de2f96c71533d4c27978c6a053bc759bb67a86a42cd0f51b63`.

The previous opaque VS Code Git bundle was removed from certification after its
compressed pack failed clone verification. The certified VS Code candidate is
fully source-visible.

## Independent sandbox certification

Test-organization workflow run `31048735205` passed all jobs against immutable
candidate heads:

- Sublime Text under Python 3.8 and 3.14, including package build and an isolated
  fixture matrix;
- JetBrains `check buildPlugin verifyPlugin` and plugin artifact upload;
- VS Code tests, VSIX packaging, and artifact upload;
- Qt Creator CMake/CTest;
- Xcode Swift/macOS tests;
- Eclipse Java/Maven tests;
- Visual Studio .NET/Windows tests;
- machine-readable parity-policy validation.

The Sublime fixture matrix uses a temporary HOME and temporary workspaces. It
covers unmanaged, lock-only, missing-lock, stale-lock, missing-materialization,
interrupted-transaction, invalid-TOML, wrong-CLI, and multi-root cases and
asserts that analysis does not mutate fixtures or HOME.

Retained test-org artifacts:

| Artifact | ID | Digest |
| --- | ---: | --- |
| `sandbox-jetbrains` | `8947719871` | `sha256:dddae7f19f18088dadd6d47dd8192786e20a11be6c6dee8fc725491b82fa46b9` |
| `sandbox-vscode` | `8947511633` | `sha256:1e814606946f3a7a4fef1e56341d5e7d200d1f011b24bd3dbaaef8a9adc5e678` |
| `sandbox-sublime-3.8` | `8947510120` | `sha256:6c801d6cee4a163f2a16734ac013655581794314ef865853b5381570e9baba21` |
| `sandbox-sublime-3.14` | `8947509853` | `sha256:6c801d6cee4a163f2a16734ac013655581794314ef865853b5381570e9baba21` |

## Remaining promotion work

The durable promotion backlog is `zed-pkg/.github#28`:

1. create dedicated repositories for VS Code, Qt Creator, Xcode, Eclipse, and
   Visual Studio;
2. complete each missing editor-native shell;
3. run clean editor-instance GUI tests using the editor vendor's supported test
   harness or experimental instance;
4. sign and publish VSIX, p2, app/appex, Qt Creator plugin, and Marketplace
   artifacts;
5. adopt the final `zed inspect` contract from `zed-cli#191`;
6. add repositories, PRs, and distribution work to `zed-pkg-project` when
   Projects v2 mutation access is available.

Linear issue `DEN-2508` remains In Progress until those distribution gates are
complete.
