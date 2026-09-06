# GitHub organization delivery operations

This runbook defines how the Zed package-management organizations move work
from Linear intent to reviewed GitHub code, exact-head certification, artifacts,
and releases. It complements the canonical organization registry in
[`33-github-linear-project-registry.md`](33-github-linear-project-registry.md)
and its machine-readable TOML source.

## Organization map

| GitHub organization | Linear project | Intended GitHub Project | Primary responsibility |
| --- | --- | --- | --- |
| `zed-pkg` | `github.com/zed-pkg` | `zed-pkg-project` | Product code, interfaces, CLI/runtime, servers, clients, documentation, packaging, release artifacts, and infrastructure |
| `zed-pkg-test` | `github.com/zed-pkg-test` | `zed-pkg-test-project` | Independent lifecycle, manager, offline, security, OCI, Nix, browser, concurrency, and polyglot certification |

The organization Project titles are reservations, not proof of creation. Until
the connected GitHub identity can list organization Projects and read back each
board's exact number, node ID, owner, and URL, their registry state remains
`permission-blocked`.

## Canonical repositories

### `zed-pkg`

The product organization currently uses these repository classes:

- **Runtime and commands:** `zed-cli`, `zed-lock`.
- **Contracts:** `zed-interfaces` and generated schemas.
- **Services and synchronization:** `zed-api-server.rs`, `zed-web-server.rs`,
  `zed-sync`.
- **SDKs and editor integrations:** `zed-clients`, `zed-vscode`,
  `zed-sublimetext`.
- **Composition and operations:** `zed-monorepo`, `zed-infra`, `zed-e2e`.
- **Architecture and governance:** `zed-docs` and the organization `.github`
  repository when present.

A new repository is created only when it has an independent release,
permissions, ownership, deployment, or certification boundary. A temporary
branch, experiment, one-off migration, or alternate spelling is not by itself a
repository boundary.

### `zed-pkg-test`

`zed-pkg-test/zed-pkg-e2e` owns broad independent candidate certification.
Specialized repositories own durable black-box boundaries, including
`nix-export-interop`, `manager-interop-e2e`, `security-adversarial-e2e`,
`offline-cache-e2e`, `oci-multiplatform-e2e`, `concurrent-install-locking`,
`constraint-solver-blackbox`, and language/application fixture repositories.

Fixture repositories are test inputs, not production packages merely because a
workflow archives them. Their project status belongs to `zed-pkg-test-project`
and their product requirement remains linked to the relevant `zed-pkg` Linear
issue or pull request.

## Authentication and credential policy

GitHub writes may use either:

1. the installed GitHub App/API connection; or
2. an operator-controlled `gh` CLI session whose scopes were reviewed for the
   requested operation.

The delivery result is the same: commits are pushed to named branches, changes
are reviewed through pull requests, and protected-branch policy remains in
force. A personal access token must never be pasted into source, workflow YAML,
command history committed to a repository, an issue, a Project field, a Linear
document, or generated evidence. An exposed token is revoked and replaced; it
is not reused merely because the owner authorized a particular operation.

Repository-scoped `GITHUB_TOKEN` credentials are preferred for branch-local
workflow writes. Stable publication uses an explicitly reviewed release
identity and immutable tag rather than a general-purpose personal token.

## Branch, pull-request, and merge procedure

1. Read the current default branch and the relevant Linear issue before
   changing code.
2. Create a descriptive branch from the exact current base.
3. Commit ordinary product, test, or documentation files. Temporary
   materializers must remove themselves before promotion.
4. Open a pull request that states the contract, safety boundary, validation,
   Linear issue, and any predecessor or successor relationship.
5. Run focused tests first, then the repository's exact-head workflows.
6. Repair failures at their real boundary. Do not suppress a platform, relax a
   frozen check, or mark a flaky failure green without evidence.
7. Confirm the pull request is mergeable, review discussions are resolved, and
   every required exact-head check is terminal-successful.
8. Merge using the repository's configured strategy. Record the merge commit in
   Linear and close only predecessors whose substantive work is traced into the
   successor.
9. Re-run or observe default-branch certification when the change affects
   release, lock, package, manager, Nix, OCI, or cross-platform behavior.

A workflow-created commit is acceptable only when the final branch contains the
same ordinary auditable files a human commit would contain. Carrier workflows,
one-shot scripts, trigger files, and write credentials are not product output.

## Exact-head checks and independent certification

Repository checks prove the candidate compiles and satisfies its local
contracts. Independent `zed-pkg-test` checks prove the compiled CLI or artifact
through a disposable external environment. High-risk changes should cover both.

Typical exact-head gates include:

- formatting and strict Clippy;
- unit, integration, and compiled CLI tests;
- Ubuntu, macOS, and Windows matrices;
- frozen and registry-free replay;
- concurrent-process and interruption behavior;
- archive traversal and tamper canaries;
- Nix fixed-output reproducibility and reference checks;
- OCI/copy-mode boundaries;
- help, completion, README, and flags-to-environment parity; and
- checkout cleanliness after the test.

The candidate SHA used by an independent workflow is recorded in its evidence.
A later commit invalidates that evidence until the workflow is repinned or
rerun.

## Artifact policy

### Pull requests and release candidates

Pull-request and `release/**` workflows may publish commit-addressed archives,
checksums, reports, browser output, schemas, and bounded failure diagnostics as
GitHub Actions artifacts. These artifacts are review evidence and expire under
the workflow retention policy. Their names include enough candidate identity to
avoid confusing output from different commits.

### Stable releases

Stable releases originate from reviewed immutable tags. Before publication:

- the tag resolves to the reviewed commit;
- the required platform matrix is green;
- archive and checksum generation is deterministic;
- release files are produced by the repository workflow rather than a local
  unrecorded build;
- provenance and source identities are retained; and
- no credential or secret appears in the artifact, checksum, log, SBOM,
  receipt, or release notes.

Schemas, SDKs, native ecosystem packages, OCI artifacts, and Nix outputs follow
their own reviewed fan-out policy. One successful upload does not permit a
workflow to claim publication to every configured registry.

### Certification artifacts

`zed-pkg-test` publishes JSON evidence, checksums, bounded diagnostics, and
replay inputs. Evidence identifies the product repository and exact candidate
SHA. Certification artifacts do not become product releases.

## GitHub Project procedure

The standard titles are:

```text
zed-pkg-project
zed-pkg-test-project
```

Do not create a second board while Projects inventory is unavailable. After the
GitHub identity receives organization Projects read/write permission:

1. list all organization Projects;
2. compare titles case-insensitively and inspect archived boards;
3. create a board only when no canonical equivalent exists;
4. add Status, Priority, Linear, Repository, Release, Risk, and Dependency
   fields;
5. create Delivery, Repositories, Releases, Risks, and Linear-sync views;
6. read back the exact number, node ID, owner, visibility, and URL; and
7. update the TOML registry, this documentation, and both Linear projects in one
   reviewed change.

Repository Projects or guessed `/projects/1` URLs are not substitutes for a
verified organization Project.

## Linear update procedure

For each delivery slice:

- the Linear issue describes product intent, acceptance criteria, dependencies,
  and durable design decisions;
- the pull request links the Linear issue;
- a Linear comment records the PR, important test findings, exact candidate or
  merge SHA, and remaining limitations;
- milestones reflect actual dependency order; and
- the issue moves to Done only after the shipped or merged state satisfies its
  acceptance criteria.

The Linear project description or a linked document contains the organization
map and GitHub Project status. Transient workflow IDs and temporary branches
belong in issue comments, not the permanent project description.

## Operational checklist

Before declaring a delivery complete, verify:

- [ ] The repository and organization are the canonical owners.
- [ ] The branch was based on the intended default-branch commit.
- [ ] A pull request exists and links its Linear issue.
- [ ] Required exact-head checks are terminal-successful.
- [ ] Independent certification is present when the boundary warrants it.
- [ ] The merged commit is recorded in Linear.
- [ ] Artifacts are commit-addressed or tag-addressed as appropriate.
- [ ] No PAT, password, token, signed URL, or secret value entered durable
      project state.
- [ ] Superseded branches and PRs are closed only after traceability is recorded.
- [ ] GitHub Project URLs and numbers were read back, not inferred.
