# Clean-room acceptance for `zed develop`

**Status:** independent cross-repository certification in review.  
**Linear:** [DEN-1518](https://linear.app/denman/issue/DEN-1518/zed-e2e-independently-certify-zed-develop-clean-room-shell-and-secret).  
**Acceptance PR:** [`zed-pkg/zed-e2e#13`](https://github.com/zed-pkg/zed-e2e/pull/13).  
**Historical implementation:** [`zed-pkg/zed-cli#18`](https://github.com/zed-pkg/zed-cli/pull/18).  
**Historical deep regression suite:** [`zed-pkg/zed-cli#20`](https://github.com/zed-pkg/zed-cli/pull/20).  
**Canonical alias integration:** [`zed-pkg/zed-cli#21`](https://github.com/zed-pkg/zed-cli/pull/21).

`zed develop` enters a project-aware, cross-language development environment.
`zed dev` is its canonical alias. The implementation repository has extensive
unit, integration, shell, and platform tests; this document defines the
independent consumer contract that must also pass from a clean checkout in
`zed-pkg/zed-e2e`.

The independent suite protects against a class of false confidence that
repository-local tests cannot completely eliminate: test helpers, inherited
working-tree state, developer credentials, cached dependencies, or assumptions
about the implementation checkout can make a command appear correct without
proving its public executable boundary.

## Command boundary

The two public spellings are alternate input forms for one typed command:

```text
zed develop [OPTIONS]
zed dev [OPTIONS]
```

For identical inputs they must produce the same:

- canonical command selection;
- flags-2-env mapping;
- project-root selection;
- managed environment;
- shell invocation;
- child exit status;
- help and completion surface; and
- security boundary.

The automation form is:

```sh
zed dev -c '<command>'
```

Interactive invocation requires a real terminal. Redirected input or output
must fail with an actionable diagnostic rather than silently starting a shell
with different semantics.

## Clean-room test architecture

The acceptance workflow is deliberately separate from `zed-cli`:

1. check out one exact `zed-cli` commit;
2. check out the exact `zed-interfaces` contract pinned by that candidate;
3. verify the candidate's exact flags-2-env revision;
4. build the real `zed` executable with the committed Cargo lock;
5. create all project, home, credential, and shell fixtures under temporary
   runner-owned directories;
6. execute the candidate as an external process without importing `zed-cli`
   test modules;
7. retain a non-secret JSON report containing immutable inputs and completed
   assertions.

The initial certification pins:

```text
zed-cli        7e5ac1897a872223f8316ef1c3342a2fa1982504
zed-interfaces dc0e0a0620b9462817950b552d3d334a184b1cb1
flags-2-env    2f62e40932a0fcb8b9bf1b4c84473e34fa3c51c7
```

Those values are evidence inputs, not floating branch names. A future candidate
must update the pin explicitly and rerun the complete contract.

## Managed environment invariants

For a project selected by the ordinary manifest or native-project discovery
rules:

- `ZED_DEV=1` is present;
- `ZED_DEV_PROJECT_ROOT` is the canonical owning project root;
- invoking from a nested child does not turn that child into a separate project;
- language tool homes and caches are project-local under `.zed/dev` unless an
  explicit supported path is selected;
- managed PATH entries have deterministic precedence and are not duplicated;
- `zed dev --print-env` and `zed develop --print-env` are byte-identical for
  identical inputs;
- `--print-env` emits the managed overlay only, not the inherited process
  environment;
- explicit command-line options override inherited flags-2-env values;
- `--no-install` performs no registry resolution and does not create or modify
  `.zpkg.toml` or `.zpkg.lock`; and
- already-inside-Nix execution does not recursively invoke Nix.

The acceptance suite invokes the command from a nested directory and verifies
these properties against the real executable.

## Secret and trust boundary

The currently shipped command does not implicitly load:

- `.env`;
- `.envrc`;
- production dotenv files;
- parent-project environment files;
- shell startup profiles;
- Codex or other AI-provider credentials;
- AWS, GCloud, GitHub CLI, npm, or registry credentials.

Tests create unmistakably fake canary values for every category. Those values
must be absent from:

- stdout and stderr;
- `--print-env` JSON;
- the managed home;
- retained workflow evidence; and
- diagnostics from intentional failure cases.

This is a no-implicit-secret default, not a claim that environment activation
can never support trusted configuration. Intentional dotenv loading, activation
trust, templates, task graphs, and manager-native execution are separate,
explicitly reviewed capabilities tracked by DEN-1435, DEN-1441, DEN-1442, and
related issues. Those features must preserve a fail-closed default and make the
additional trust decision visible.

## Isolated home

`--isolated-home` redirects the relevant user configuration roots into the
project's managed state:

```text
<project>/.zed/dev/home
```

The directory is created empty. It must not copy configuration or credential
files from the caller's real home. The clean-room suite creates fake files at
paths representative of:

```text
~/.codex/auth.json
~/.aws/credentials
~/.config/gcloud/application_default_credentials.json
~/.config/gh/hosts.yml
~/.npmrc
```

It then proves that none appears in the isolated home and that none of their
canary values appears in output.

## Shell matrix

The independent Unix contract covers:

- Bash on Linux and macOS;
- Zsh on Linux and macOS;
- Fish on Linux;
- a generic POSIX executable used as a PTY canary;
- non-interactive command execution;
- real interactive PTY entry;
- child exit-code propagation;
- missing-shell diagnostics; and
- rejection of an interactive invocation with redirected standard streams.

The implementation repository retains the broader PowerShell and `cmd.exe`
dispatch matrix. The initial clean-room workflow does not claim Windows evidence
that it does not execute. A Windows external certification can be added as a
separate reviewed slice without weakening the Linux/macOS contract.

## Python virtual environment

With an exact interpreter, `--python-venv required`, and an explicit
project-local `--venv` path:

- Zed creates or reuses a usable virtual environment;
- `VIRTUAL_ENV` identifies the canonical selected path;
- the virtual environment's executable directory has the required PATH
  precedence;
- creation remains inside the selected project; and
- malformed or unavailable environments fail before shell execution.

The clean-room suite uses a custom `.custom/venv` path and verifies `sys.prefix`
through the activated shell rather than merely checking that a directory was
created.

## Bounded project writes

With `--no-install`, the command may create documented development state under
`.zed/dev`. It must not create package-management state, modify native project
manifests, or write outside the selected project and configured Zed home.

The suite snapshots the project top-level entries before activation and accepts
only the existing fixture files plus `.zed`. It separately asserts that neither
`.zpkg.toml` nor `.zpkg.lock` exists after the run.

## Failure behavior

The executable boundary must preserve failures accurately:

- a child shell exit status is returned to the caller;
- a missing shell names the selected executable and reports that shell startup
  failed;
- interactive mode without a terminal fails before launching a child;
- malformed options remain redacted where their values may contain secrets; and
- failure diagnostics do not print inherited credential canaries.

The first external contract explicitly checks exit code `37`, a missing shell,
and redirected-terminal rejection. Repository-local tests retain the broader
invalid-enum, conflicting-mode, redaction, Nix, and Windows matrix.

## GitHub Actions policy

The acceptance workflow must remain:

- read-only (`contents: read`);
- free of repository and organization secrets;
- pinned to immutable Action commits;
- explicitly timed out;
- concurrency-cancelled for superseded candidates;
- independent of registry, cloud, and AI-provider availability; and
- evidence-producing without retaining canary values or temporary homes.

Each operating-system job records:

- E2E candidate commit;
- CLI candidate commit;
- interface contract commit;
- flags-2-env commit;
- runner operating system and architecture;
- Rust, Cargo, Python, and shell identities;
- a SHA-256 of the managed environment output;
- managed environment key names; and
- completed assertion names.

Ten policy tests ratchet the workflow itself. They reject mutable Action refs,
write or OIDC permissions, secret inheritance, persisted checkout credentials,
floating dependency pins, weakened OS or timeout coverage, unsafe artifact
retention, missing canaries, removal of the source-cleanliness proof, and any
bytecode-producing validation followed by cleanup-based masking.

That final invariant caught a real review-time defect: Python's ordinary import
cache created `tests/cli/__pycache__/`. The accepted repair prevents the write
with `PYTHONDONTWRITEBYTECODE=1` and in-memory `compile(...)`; it does not delete,
ignore, or reset the evidence after the fact.

Evidence retention is short and diagnostic. It is not a credential or user-home
backup mechanism.

## Change control

A change to a public invariant in this document requires all of the following:

1. a Linear implementation or contract issue under `github.com/zed-pkg`;
2. focused `zed-cli` tests at the correct implementation layer;
3. an updated immutable candidate pin in the independent E2E suite;
4. updated documentation describing the intentional behavior;
5. successful exact-head workflow evidence attached to the owning issue; and
6. semantic review of interactions with flags-2-env, Nix composition,
   environment-manager adapters, and secret/trust policy.

A green repository-local suite is necessary but not sufficient for changing the
external contract. The independent test must continue to exercise the public
binary from a clean checkout.

## Initial reviewed evidence

The initial external contract was reviewed at E2E head
`24bc0b60910727f7ecb1da1cb53d1683a2de80c4`.

- [Clean-room run 30837794664](https://github.com/zed-pkg/zed-e2e/actions/runs/30837794664)
  passed on Ubuntu 24.04 and macOS 15. Both jobs passed the ten policy tests, the
  immutable CLI build, the functional suite, the source-cleanliness proof, and
  non-secret evidence upload.
- [Existing full-stack run 30837796445](https://github.com/zed-pkg/zed-e2e/actions/runs/30837796445)
  passed Playwright, Puppeteer, Selenium, the CLI/API/web stack, and the
  process-memory artifact boundary.
- [Agents-policy run 30837797718](https://github.com/zed-pkg/zed-e2e/actions/runs/30837797718)
  passed.

The Linux report records 18 assertions across Bash, Zsh, and Fish, with managed
environment digest
`35ac6394a7c0e8e441814ed47f2365b78e517cd502121daa974dd556fa954478`.
The macOS report records 17 assertions across Bash and Zsh, with managed
environment digest
`49b869cd80feb3bb574cc53c2e6f61e873d5f5dfac0b25ee0cf93b7c134b05e1`.
Both reports record `credential_canaries_retained = false` and
`external_registry_required = false`.

The downloaded artifact archives were scanned directly for every fake
credential-canary value; none was present. Their archive digests are:

```text
Linux sha256:871ce6e084acfb90c165d4d84ba4b6ea8f990ce28f0423fea0d811bd23bca0c6
macOS sha256:3848a15788f98391059151203b9dd8dbb60eef933f7ee5b58355474dff113d83
```

## Documentation indexing note

Several active architecture PRs currently add a document numbered `24` from
independent historical branch points. This file intentionally uses a stable
unnumbered name and does not modify the README index. The eventual documentation
stack must resolve those numbering conflicts conceptually, preserving every
valid architecture document rather than selecting one `24` wholesale.
