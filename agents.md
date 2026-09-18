# Agent instructions

## Scope and hierarchy

- These instructions apply to the whole `zed-pkg/zed-monorepo` repository unless a deeper lowercase `agents.md` adds narrower rules.
- Before editing, resolve the current working directory and load every readable ancestor `agents.md` from the filesystem root to the working directory. Do not search siblings. Resolve symlinks, deduplicate resolved files, and report unreadable or cyclic instruction files.
- `.claude/CLAUDE.md`, `.gemini/GEMINI.md`, and `.openai/AGENTS.md` are pointers only. Never duplicate instructions in tool-specific files.

## Repository role

This repository is the pinned integration and submodule umbrella for the `zed-pkg` organization. It records exact cross-repository combinations under `apps/` and verifies them together. A submodule update is a release-set change, not a source edit to the vendored repository.

## Working rules

- Start from the current default branch and keep each change tied to its Linear issue.
- Inspect `README.md`, `.gitmodules`, `Makefile`, and existing workflows before changing pins or integration behavior.
- Preserve gitlink mode `160000`; do not replace submodules with copied directories or edit vendored contents as ordinary files.
- Update contract/interface pins before dependent services when a change spans repositories.
- Keep CI deterministic: pin external revisions, avoid mutable `main` checkouts inside tests, and do not add hidden network or credential requirements.
- Never commit tokens, kubeconfigs, registry credentials, generated secrets, or production environment files.
- Keep documentation, tests, and integration expectations synchronized with every release-set change.

## Validation

Run the focused repository checks documented in `README.md`. For instruction-policy changes also run:

```sh
python3 tools/agents_policy.py validate --repo . --print-chains
python3 -m unittest discover -s tests -p 'test_agents_policy.py' -v
```

The `agents policy` workflow is the authoritative cross-repository enforcement gate.

<!-- BEGIN ores-agents-pointer: managed by ORESoftware/my-ai; edit there, not here -->

## Canonical agent instructions

Before doing anything else in this repository, also read:

    .ores/agents/AGENTS.md

That path is a symlink to `~/codes/oresoftware/my-ai/AGENTS.md`, whose canonical copy is
<https://github.com/ORESoftware/my-ai/blob/main/AGENTS.md>.

It exists at a fixed path *inside* the repository because some agents cannot walk up past
the repository root, so machine-wide instructions one or more directories above are
invisible to them. This pointer plus that path make the same file reachable from a working
directory anywhere in the tree.

The symlink is deliberately **not committed**: it names an absolute path that is only valid
on a machine with `~/codes/oresoftware/my-ai` checked out, so committing it would produce a
broken link for everyone else and for CI. `.ores/` is git-ignored for that reason. If
`.ores/agents/AGENTS.md` is missing on your machine, create it with:

    mkdir -p .ores/agents
    ln -sfn "$HOME/codes/oresoftware/my-ai/AGENTS.md" .ores/agents/AGENTS.md

or run `~/codes/oresoftware/my-ai/scripts/link-repo-agents.sh` once to do it for every git
repository under `~/codes`, and `--check` to verify them.

A missing `.ores/agents/AGENTS.md` is a setup gap on the reader's machine, never a reason to
skip the canonical instructions: fetch them from the URL above instead.

<!-- END ores-agents-pointer -->

## Repository-local Git worktrees

- Create or use a Git worktree only when the human operator explicitly authorizes it for the current task. Concurrency or a dirty checkout is not permission by itself.
- Put every authorized worktree at `<repository-root>/tmp/worktrees/<name>`; from the repository root, use `./tmp/worktrees/<name>`. Never place worktrees beside repositories or organization directories.
- Keep `tmp`, `temp`, `tmp/worktrees`, and `temp/worktrees` ignored in the repository-root `.gitignore`. Do not commit files from those directories.
- Relocate or remove a worktree only when the operator explicitly requests it. Before removal, preserve and publish intended changes, verify its commit is represented on the target branch, and confirm there are no tracked, untracked, ignored-sensitive, or in-use files that must survive. Remove it with `git worktree remove <path>` without `--force`; never delete a worktree directory with `rm`.
