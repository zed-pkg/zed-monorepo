# Repository synchronization and semantic branch merging

This runbook defines the repeatable synchronization procedure for repositories in the `zed-pkg` organization. It applies to ordinary feature branches, automated-agent branches, validation branches, pull requests, and temporary `sync-divergent` refs.

The goal is not merely to make Git report a clean merge. The goal is to preserve the complete intended behavior, contracts, tests, documentation, operational safeguards, and history of every valid line of work in a coherent default branch.

## Invariants

1. GitHub is the shared source of truth. Work is complete only when commits and refs are present in the real remote repository.
2. Begin from the current remote default branch and refresh remote metadata before comparing work.
3. Never use force-push, destructive reset, history rewriting, or blanket “ours/theirs” conflict selection.
4. Merge contract and interface changes before dependent implementations when work spans repositories.
5. Treat tests, schemas, generated artifacts, lockfiles, deployment manifests, and documentation as part of the feature—not disposable merge noise.
6. Keep credentials, tokens, private URLs, kubeconfigs, and production data out of commands, diffs, logs, and merge messages.
7. Use immutable commit identifiers for cross-repository pins and validation evidence.

## 1. Inventory the live remote state

For every maintained repository:

- identify the default branch and its current commit;
- list all remote branches, including agent, CI, WIP, and `sync-divergent` refs;
- list every open pull request, draft or ready;
- identify linked Linear issues and existing supersession or dependency relationships;
- record branch-protection requirements and required checks.

Do not infer repository state from local ZIP files, chat attachments, stale clones, or branch names alone.

## 2. Classify each line of work

For each branch or pull request, compare it with the current default branch and classify it as one of:

- **Already incorporated:** its tip is an ancestor of the default branch.
- **Fast-forwardable:** it is behind the default branch and can be advanced without discarding commits.
- **Additive:** it contributes disjoint behavior that should be merged.
- **Overlapping but compatible:** both lines modify the same concept and require a designed union.
- **Superseded:** a newer implementation contains the valid intent and stronger guarantees.
- **Invalid or abandoned:** it is intentionally rejected for a documented technical reason.

A branch is not superseded merely because its files conflict or its implementation is older. Identify the actual user-visible and contract-level intent before deciding.

## 3. Perform a conceptual merge

When two lines overlap, write down the invariants from both sides before editing. Resolve conflicts by constructing one implementation that satisfies the compatible invariants.

Typical examples:

- preserve a newer schema version while retaining an older branch's unique endpoint or field;
- preserve stricter security boundaries while retaining development-only loopback behavior;
- keep transactional locking and recovery while adapting test actors to realistic ownership;
- keep canonical generated output while incorporating generator changes rather than hand-editing generated files;
- retain current release metadata while adding missing language or platform support;
- preserve both independent test assertions when they cover distinct failure modes.

If requirements truly conflict, choose based on the current source-of-truth contract, security model, compatibility policy, and linked issue—not based on which side Git labels as current.

The merge commit or pull-request description must explain:

- what each side intended;
- which invariants were preserved;
- which obsolete mechanism was replaced;
- why no valid behavior was silently dropped;
- the exact commits and checks used as evidence.

## 4. Validate the merged result

Run the repository's focused checks and the relevant cross-repository gates. At minimum:

- formatting, compilation, unit tests, doctests, linting, and static analysis;
- contract, schema, lockfile, generator-drift, and serialization checks;
- platform and language matrices touched by the change;
- container, installation, recovery, and deployment checks when applicable;
- security and secret-redaction tests;
- cross-repository interoperability against immutable dependency commits.

Search the resulting default-branch tree for unresolved merge-marker patterns. Search generated files and workflow files as well as source code.

Do not weaken a failing assertion merely to make the union pass. Determine whether the assertion, implementation, fixture, or source-of-truth contract is wrong, then repair the correct layer.

## 5. Publish through GitHub

For changes requiring new commits:

1. push a named feature branch to the real GitHub repository;
2. open a pull request linked to the Linear issue;
3. wait for or run the required checks on the exact head commit;
4. resolve review threads and merge conflicts semantically;
5. merge through GitHub so the relationship between the reviewed head and default branch is durable;
6. verify the merge commit is reachable from the remote default branch.

For a historical branch already incorporated into the default branch, a non-force fast-forward of that ref to the current default-branch commit is a safe synchronization proof: it succeeds only when no branch-only commit is being discarded.

## 6. Final remote verification

Repeat the inventory after all merges:

- there are no relevant open pull requests;
- every retained remote branch is equal to or descended from the current default branch;
- no branch-only commit remains unreviewed;
- no unresolved merge-marker pattern exists in the default branch;
- required checks succeeded on each exact reviewed head;
- cross-repository pins identify immutable merged commits;
- the repositories and commits are visible at their GitHub URLs.

Branch deletion is a separate cleanup operation. Do not conflate deletion with synchronization, and do not delete a ref until its commits are proven reachable from the default branch and repository policy permits deletion.

## 7. Update Linear

For each issue involved:

- attach the pull request and final merge commit;
- record exact tested head and merge commit identifiers;
- summarize semantic conflict decisions and validation evidence;
- relate superseded or follow-up issues instead of creating duplicates;
- move completed implementation issues to Done;
- keep genuinely recurring operations or blocked cleanup work open with their current boundary stated explicitly.

A synchronization run is complete only when GitHub and Linear describe the same final state.
