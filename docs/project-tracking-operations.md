# Project tracking operating procedure

1. Create or update the Linear issue before implementation begins.
2. Link the owning repository and pull request to the Linear issue.
3. Add the issue or pull request to the organization GitHub Project.
4. Record the exact candidate SHA before final review.
5. Require terminal exact-head checks and no unresolved review threads.
6. Merge with an expected-head guard when supported.
7. Record the merge SHA in Linear and the GitHub Project item.
8. Mark both systems Done only after the merge or explicit non-code acceptance artifact exists.

For diverged feature stacks, prefer reconstruction from current `main` with a deliberate semantic union over force updates or conflict-side selection.
