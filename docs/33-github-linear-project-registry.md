# GitHub organization, Linear project, and GitHub Project registry

Every GitHub organization in the Zed package-management portfolio needs one
canonical planning identity. The durable mapping is:

```text
GitHub organization <org>
        ↕
Linear project github.com/<org>
        ↕
GitHub Project <org>-project
```

The machine-readable source is
[`config/github-linear-project-registry.toml`](../config/github-linear-project-registry.toml).
The authenticated branch, pull-request, exact-head test, artifact, release, and
Linear update procedure is maintained in
[`github-org-delivery-operations.md`](github-org-delivery-operations.md).
This document explains the policy, current records, and the permission boundary
for creating organization Projects.

## Canonical ownership rules

For each organization:

1. The Linear project name is exactly `github.com/<org>` unless a documented
   legacy product project is the canonical replacement.
2. The GitHub Project title is exactly `<org>-project`.
3. The organization Project owns portfolio state, cross-repository sequencing,
   release readiness, risks, and dependencies. Repository issues remain the
   detailed engineering work items.
4. Linear owns product intent, architecture decisions, milestones, and durable
   project status. GitHub owns code, reviews, checks, releases, and executable
   delivery evidence.
5. A Linear issue and GitHub issue may refer to the same work, but neither is
   silently duplicated. One record is canonical and the other links to it.
6. Every pull request body names its Linear issue when one exists. Linear
   comments and status updates link the resulting PR and merge commit.
7. GitHub Project fields should include Status, Priority, Linear, Repository,
   Release, Risk, and Dependency. Automation may update fields but must never
   erase human-authored context.

## Current Zed organization records

| GitHub organization | Canonical Linear project | Intended GitHub Project | Current Project state | Canonical delivery scope |
| --- | --- | --- | --- | --- |
| [`zed-pkg`](https://github.com/zed-pkg) | [`github.com/zed-pkg`](https://linear.app/denman/project/githubcomzed-pkg-5a53230ae6cc) | `zed-pkg-project` | permission blocked; not claimed as created | CLI, interfaces, lock runtime, clients, servers, sync, infra, E2E, docs, monorepo |
| [`zed-pkg-test`](https://github.com/zed-pkg-test) | [`github.com/zed-pkg-test`](https://linear.app/denman/project/githubcomzed-pkg-test-e0b5db761974) | `zed-pkg-test-project` | permission blocked; not claimed as created | fixture packages, lifecycle matrix, security, offline, OCI, manager, registry, concurrency, and Nix certification |

The connected GitHub App installations can administer the repositories in both
organizations. Their current installation IDs are retained in the registry only
as operational inventory; workflows and application code must not depend on
those IDs as permanent public identifiers.

## Why the Projects are not marked as created

Repository, issue, pull-request, check, workflow, and release access does not
imply organization-Project access. The current integration receives a Projects
permission error when querying the organization Project API. Until the operator
or GitHub App has organization Projects read/write permission, this registry
uses:

```toml
github_project_status = "permission-blocked"
github_project_number = 0
github_project_url = ""
```

Do not guess that a board is `/projects/1`. Do not write a fabricated URL into
Linear. A board becomes `created` only after its node/number and owner are read
back from GitHub. Permission grant, deduplication, field creation, and registry
read-back are tracked in [zed-docs issue #47](https://github.com/zed-pkg/zed-docs/issues/47).

## Operator commands after Projects permission is granted

The GitHub CLI session needs the `project` scope:

```bash
gh auth status
gh auth refresh -s project
```

Inventory before creation:

```bash
gh project list --owner zed-pkg --format json
gh project list --owner zed-pkg-test --format json
```

Create only when no title-equivalent board exists:

```bash
gh project create --owner zed-pkg --title zed-pkg-project
gh project create --owner zed-pkg-test --title zed-pkg-test-project
```

Then read the exact number and URL back from GitHub and update both this registry
and the corresponding Linear project. Creation is not complete until the board
has at least the standard fields and links to its canonical Linear project.

## Standard GitHub Project fields

| Field | Type | Purpose |
| --- | --- | --- |
| Status | single select | Backlog, Ready, In progress, In review, Blocked, Done |
| Priority | single select | Urgent, High, Medium, Low |
| Linear | text | Canonical Linear issue or project URL |
| Repository | repository | Delivery repository |
| Release | text | Version, tag, or delivery wave |
| Risk | single select | None, Low, Medium, High |
| Dependency | text | Blocking issue, PR, project, or package |

Recommended views:

- **Delivery:** grouped by Status and sorted by Priority.
- **Repositories:** grouped by Repository.
- **Releases:** grouped by Release.
- **Risks:** filtered to blocked or nonempty Risk.
- **Linear sync:** items with a Linear URL, grouped by Status.

## Artifact and release policy

`zed-pkg` publishes code-derived artifacts only after the exact commit passes its
required checks. Pull-request artifacts are commit-addressed and ephemeral.
Stable package, CLI, schema, SDK, and Nix interoperability releases originate
from reviewed immutable tags and retain checksums and provenance.

`zed-pkg-test` publishes certification evidence, bounded diagnostics, checksums,
and replay inputs as workflow artifacts. Test fixtures do not become production
packages merely because a workflow archived them.

Artifact publication must not require a personal token embedded in a workflow,
repository variable, generated file, issue, Project field, or Linear document.
Use repository-scoped workflow credentials or an explicitly reviewed publishing
identity.

## Update procedure

When an organization, Linear project, Project board, or canonical repository
changes:

1. Update the TOML registry in one pull request.
2. Update this document when policy or human-readable status changes.
3. Run `scripts/check-github-linear-project-registry.py`.
4. Update the canonical Linear project description or a linked Linear document.
5. Link the pull request and merge commit in Linear.
6. For a created board, confirm its exact owner, title, number, and URL by API or
   `gh project list`; never infer them from convention.

The registry begins with the two organizations that directly own Zed product
and certification delivery. Other GitHub organizations should add one validated
record per pull request rather than copying unverified Project URLs in bulk.
