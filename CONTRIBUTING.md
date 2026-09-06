# Contributing to zed-pkg

## Superseded pull-request salvage

Do not close a pull request as superseded, outmoded, obsolete, replaced, or duplicated by a successor until the successor incorporates at least one concrete item from it.

Apply this rule to every superseded pull request. A successor that replaces several earlier pull requests must carry forward at least one item from each predecessor.

A qualifying item may be implementation code, a corrected design element, a test, fixture, schema example, migration or rollback step, compatibility case, API name, invariant, acceptance criterion, edge case, review finding, performance insight, architectural rationale, or documented rejected alternative. When the earlier implementation should not survive, preserve a negative test, failure case, invariant, or review lesson.

A link or closing comment alone does not count. The item must materially affect the successor and have a durable location.

### Required traceability

The successor pull-request body must contain a `Superseded PR salvage` section. For every predecessor, record:

1. the exact pull-request URL or repository-local number;
2. the item carried forward; and
3. where it was incorporated, such as a file path, test name, commit, issue, decision record, or documentation section.

The predecessor closing comment must link the successor and repeat the salvaged item and location.

### Closure sequence

1. Inspect the predecessor code, tests, discussion, review threads, and CI findings.
2. Select at least one useful item.
3. Incorporate it into the successor.
4. Add the traceability block to the successor body.
5. Verify the cited artifact exists on the successor branch.
6. Close the predecessor only after those steps are complete.

When the successor is not ready, leave the predecessor open or convert it to draft.

### Example

```markdown
## Superseded PR salvage

Supersedes: yes

- Predecessor: https://github.com/zed-pkg/zed-cli/pull/123
  Salvaged: The interrupted-download cleanup case and atomic-cache invariant.
  Incorporated at: `src/install_graph/tests.rs`, test `failed_downloads_remove_staging_files`.
```

The organization pull-request template requires an explicit `Supersedes: none` or a complete salvage block. The reusable salvage workflow validates the structure, while reviewers confirm the cited item is substantive and present.
