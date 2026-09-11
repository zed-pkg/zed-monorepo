# Windows clean-room acceptance for `zed develop`

**Status:** certified and merged.  
**Linear implementation corrections:** [DEN-1616](https://linear.app/denman/issue/DEN-1616/zed-cli-suppress-powershell-profiles-in-zed-develop-command-mode) and [DEN-1634](https://linear.app/denman/issue/DEN-1634/zed-cli-normalize-windows-child-process-cwd-for-verbatim-project-paths).  
**Linear external certification:** [DEN-1614](https://linear.app/denman/issue/DEN-1614/zed-e2e-add-windows-clean-room-certification-for-zed-develop).  
**Linear contract:** [zed develop Windows clean-room acceptance contract](https://linear.app/denman/document/zed-develop-windows-clean-room-acceptance-contract-316cfafd9902).  
**Merged CLI PR:** [`zed-pkg/zed-cli#100`](https://github.com/zed-pkg/zed-cli/pull/100).  
**Merged E2E PR:** [`zed-pkg/zed-e2e#16`](https://github.com/zed-pkg/zed-e2e/pull/16).  
**Merged release canary:** [`zed-pkg-test/zed-pkg-e2e#43`](https://github.com/zed-pkg-test/zed-pkg-e2e/pull/43).

The completed [Unix clean-room contract](zed-develop-clean-room-acceptance.md)
certifies `zed develop` on Ubuntu and macOS. This document adds the Windows
boundary that the original contract intentionally did not claim.

The external Windows suite checks out exact commits, builds the real `zed.exe`
on Windows Server 2022, and imports no implementation test helpers. It consumes
no repository secret and makes no registry, cloud, AI-provider, or user-account
request.

## Immutable reviewed stack

The certification used these immutable commits:

```text
zed-cli merge   fd3b3e487b2bdd129dd67403ad51f7299cfe6828
zed-e2e source  144d17e28afa9586bc71ec43f340a0e0328a54b4
zed-e2e merge   6807fce462b46c421def6b06c5b4050ae9ddf436
zed-interfaces  c2e049006453c26ca8ca291783f681fce75cb01f
flags-2-env     2f62e40932a0fcb8b9bf1b4c84473e34fa3c51c7
release canary  72228839933efc933b91d28f3b44bf473458dfac
```

The CLI merge commit preserves the failure-atomic Git-submodule takeover work
that landed independently on `main` while adding the disjoint Windows shell and
child-process corrections. The release canary retains the reviewed E2E source
SHA as provenance: PR #16 merged that exact source without code conflicts, and
the merge commit records its incorporation into `main`.

A later source change requires a new explicit pin and complete replay; a moving
branch name is not evidence.

## PowerShell command mode

For non-interactive command execution, Zed invokes any explicitly selected
`pwsh`, `pwsh.exe`, `powershell`, or `powershell.exe` as:

```text
<shell> -NoLogo -NoProfile -NonInteractive -Command <command>
```

The switches establish a deterministic automation boundary:

- `-NoLogo` removes banner output;
- `-NoProfile` prevents current-user, all-users, current-host, and all-host
  profiles from executing implicitly;
- `-NonInteractive` prevents prompts and interactive host behavior;
- `-Command` evaluates the caller-supplied command through PowerShell.

The switches apply only when `-c` / `--command` is present. If a user explicitly
requests an interactive PowerShell session, Zed does not inject command-mode
switches and preserves PowerShell's native interactive startup semantics.

### Why this is a security boundary

PowerShell profiles are arbitrary code. They can mutate the environment, load
credentials, contact networks, change aliases, or execute unrelated startup
logic. Before DEN-1616, Zed used `-NoLogo -Command` and therefore did not uphold
the established no-implicit-shell-profile contract on Windows.

The regression test does not merely inspect an argument vector. It:

1. redirects `HOME` and `USERPROFILE` to a temporary directory;
2. asks PowerShell for its actual current-user profile locations;
3. refuses to write if any returned path escapes that temporary home;
4. writes unmistakable fake canaries to the profile files;
5. proves those canaries load during ordinary PowerShell startup; and
6. proves the real `zed.exe` command path neither executes nor emits them.

The same assertion verifies `ZED_DEV`, child project-root cwd, and exit-code
propagation.

## Canonical identity and Windows child cwd

Project discovery and the managed environment retain the canonical filesystem
identity. Windows canonicalization may produce verbatim paths:

```text
\\?\C:\path
\\?\UNC\server\share\path
```

Those paths are valid identities but are not accepted consistently as a child
process current directory. Before launch, Zed converts only the prefix:

```text
\\?\C:\path                    -> C:\path
\\?\UNC\server\share\path     -> \\server\share\path
```

Ordinary drive paths, ordinary UNC paths, and device paths remain unchanged.
The conversion uses UTF-16 code units, so Unicode project paths are not passed
through lossy UTF-8 conversion. `ZED_DEV_PROJECT_ROOT` remains canonical while
the native child starts from the equivalent process-compatible path.

The external fixture begins in `project/src/nested`, which owns no manifest.
PowerShell and cmd.exe must find `package.json` and `src/nested` from their own
current directory. This proves they start at the owning project root without
making one textual Windows path spelling part of the public contract.

## cmd.exe command mode

Zed retains the product boundary:

```text
cmd.exe /D /S /C <command>
```

`/D` disables AutoRun commands, `/S` applies cmd.exe command-string parsing, and
`/C` executes the command and exits.

The independent harness discovers the nearest manifest-owning project root and
creates two fixed-name batch files there:

1. `zed-develop-cmd-contract.cmd` performs one native statement per managed-env,
   cwd, and exit-code assertion;
2. `zed-develop-cmd-launcher.cmd` calls the assertion, captures `ERRORLEVEL` on
   the next statement, and returns it unchanged.

Zed executes `call zed-develop-cmd-launcher.cmd`. Relative fixed names avoid an
incidental inner absolute-path quoting layer under `/S /C`; the test still
exercises Zed's real shell arguments, selected cwd, environment delivery, and
child status propagation. The static policy rejects nested-caller placement,
standalone quoted batch invocation, quoted absolute `CALL`, and loss of explicit
`ERRORLEVEL` propagation.

## Managed environment contract

The Windows clean-room suite verifies:

- byte-identical `zed develop --print-env` and `zed dev --print-env` output;
- global options before the alias;
- nested invocation selecting the owning project root;
- environment-only flags-2-env configuration;
- explicit CLI precedence over inherited Nix and mise modes;
- no implicit `.env`, `.envrc`, production dotenv, or PowerShell-profile
  values;
- no inherited token or credential canaries in stdout, stderr, JSON, or retained
  evidence;
- bounded `--no-install` writes under documented `.zed/dev` state; and
- no `.zpkg.toml` or `.zpkg.lock` creation.

## Python virtual environments

With an explicit interpreter, `--python-venv required`, and a project-local
custom path, the suite proves:

- `VIRTUAL_ENV` identifies the selected directory;
- the executed Python process uses it as `sys.prefix`;
- the executable is resolved from the Windows `Scripts` directory; and
- all created virtual-environment state remains inside the selected project.

## Isolated Windows user state

`--isolated-home` must set both:

```text
HOME=<project>/.zed/dev/home
USERPROFILE=<project>/.zed/dev/home
```

The managed home starts empty. The suite creates fake source-home credentials at
representative Codex, AWS, GCloud, GitHub CLI, npm, and registry locations, then
proves none is copied or emitted.

## Failure contract

The external test covers:

- child exit status through PowerShell and cmd.exe;
- a missing shell executable;
- an invalid enum value;
- conflicting `--print-env` and `--command` modes; and
- interactive invocation with redirected standard streams.

All diagnostics must remain actionable and free of every fake credential canary.

## Workflow policy

The independent workflow must remain:

- on the explicit `windows-2022` runner rather than a moving latest label;
- read-only with `contents: read`;
- free of secret inheritance, OIDC writes, and persisted checkout credentials;
- pinned to immutable Action, CLI, interface, and flags-2-env commits;
- bounded by a 40-minute timeout and concurrency cancellation;
- source-clean without reset or cleanup-based masking;
- limited to runner-temporary evidence retained for no more than seven days; and
- followed by a direct scan of retained evidence for every fake canary.

The static policy suite contains 11 checks and ratchets the PowerShell/cmd/profile/
venv assertions, project-root relative cmd launcher, explicit `ERRORLEVEL`
capture, immutable source pins, and locked source build.

## Certified evidence

Cross-organization run
[30903855437](https://github.com/zed-pkg-test/zed-pkg-e2e/actions/runs/30903855437)
checked out reviewed E2E source `144d17e28afa9586bc71ec43f340a0e0328a54b4`
and merged CLI `fd3b3e487b2bdd129dd67403ad51f7299cfe6828` on
Windows Server 2022. It:

- passed all 11 imported workflow-policy tests;
- built the real CLI with the committed Cargo lock;
- passed 19 native Windows assertions;
- scanned every retained file for all 11 fake credential canaries;
- proved the canary, E2E, CLI, and interface checkouts remained clean; and
- uploaded exactly two bounded evidence files.

The retained report records:

```text
assertion_count=19
managed_environment_sha256=24903e36d446a5dbe15018a7ced801fbbb164ab7ca26149930b58fecfc4d9525
credential_canaries_retained=false
external_registry_required=false
temporary_home_retained=false
```

Artifact `windows-develop-cross-org-30903855437-1` has ID `8890260522`, size
`1563` bytes, and ZIP digest:

```text
sha256:f253e73fe7a3a6c2062b818ce6d45db6b8de9ee5b29fe7c996ddc9631bbaa2dd
```

The archive was downloaded and independently scanned again; no fake credential
canary was present.

The implementation, primary consumer contract, and durable release canary merged
as:

```text
zed-cli PR #100      fd3b3e487b2bdd129dd67403ad51f7299cfe6828
zed-e2e PR #16       6807fce462b46c421def6b06c5b4050ae9ddf436
zed-pkg-e2e PR #43   72228839933efc933b91d28f3b44bf473458dfac
```

## Change control

Any future change to Windows shell arguments, profile behavior, default shell
selection, canonical identity versus child cwd, HOME/USERPROFILE handling,
virtual-environment activation, or failure propagation requires:

1. a Linear implementation or contract issue;
2. focused repository-local tests;
3. a new immutable E2E candidate pin;
4. successful native Windows clean-room evidence; and
5. updated documentation explaining the intentional semantic change.

Future trusted activation or explicit profile-loading functionality must obtain
a separate, visible trust decision. It must not weaken command mode's default
no-implicit-profile behavior.
