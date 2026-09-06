# Deterministic offline release-plan review

Status: **implemented** in `zed-pkg/zed-cli` through
[`#31`](https://github.com/zed-pkg/zed-cli/pull/31) and hardened through
[`#33`](https://github.com/zed-pkg/zed-cli/pull/33), tracked by Linear DEN-1301
and DEN-1343.

## Why this exists

`zed release plan` computes the credential-free release model used to explain
what a publish would do. Terminal prose is useful interactively and `--json` is
the stable machine boundary, but neither is an efficient review artifact for a
multi-target release with native registries and forge mirrors. A reviewer needs
one portable document that can be retained by CI, printed, and opened without a
server, registry credential, or network connection.

The browser report is not a second planner. The JSON emitted by the Rust CLI
remains authoritative; rendering is a pure, fail-closed projection of that
model.

## Review flow

A repository can generate and inspect the same plan in three forms:

```sh
zed release plan
zed release plan --json > build/release-plan.json
node scripts/render-release-plan-html.mjs \
  --input build/release-plan.json \
  --output build/release-plan.html
```

The renderer also accepts JSON on standard input. The resulting HTML opens
through `file://` and contains source provenance, exact Zed/native/forge counts,
explicit empty states, captioned artifact tables, and progressive client-side
filtering. Escape clears the filter and restores the complete plan.

JavaScript is an enhancement rather than a prerequisite. Without JavaScript,
the filter stays hidden and every artifact remains readable. A visible-on-focus
skip link, stable heading order, descriptive table captions, and associated
filter instructions/status make the report usable with keyboards and assistive
technology.

## Security and integrity contract

The renderer and report are intentionally narrow:

- validate the expected release-plan shape before rendering and reject missing
  or malformed fields;
- HTML-escape every plan-derived value before placing it in text or an
  attribute;
- authorize the static inline stylesheet and filter code with exact SHA-256
  Content Security Policy hashes rather than broad `unsafe-inline` rules;
- include no remote scripts, styles, fonts, analytics, images, or network
  calls;
- write through a private same-directory temporary file and atomically rename
  it into place;
- refuse an existing symbolic-link output instead of following or replacing
  its target;
- reject unknown renderer options and missing option values;
- never load registry tokens or invoke a publish endpoint.

The same-directory rename is important. A temporary file on another filesystem
cannot be atomically renamed, and a predictable world-readable temporary file
would expose a partially written plan. Symlink refusal prevents a chosen output
path from redirecting the writer to an unrelated file.

## Print contract

Printing is a complete release review, not a snapshot of the current screen
filter. Print media:

- hides filtering and skip-navigation controls;
- restores every artifact row even when the screen view is filtered;
- repeats table headers;
- avoids splitting table rows, provenance cards, and metrics where practical;
- retains provenance and destination counts;
- removes screen-only backgrounds while retaining visible boundaries.

This also makes browser-generated PDF review deterministic and self-contained.

## Browser automation contract

The GitHub Actions workflow builds the locked Rust CLI, generates a realistic
npm plus crates.io plan with forge mirrors, renders the HTML, and opens the same
file in Chromium, Firefox, and WebKit. Each engine verifies:

- semantic landmarks, heading order, source provenance, and captions;
- exact counts and table rows;
- filtering and Escape reset;
- keyboard order and visible skip navigation;
- JavaScript-disabled readability;
- print restoration of filtered rows and repeated headers;
- forced-colors boundary behavior;
- narrow/mobile containment;
- no console or page errors;
- no HTTP or HTTPS requests;
- retention of the reviewed HTML as a CI artifact.

This is browser automation over the actual Rust-generated release model, not a
fixture-only screenshot test.

## Relationship to publishing

The report is advisory and read-only. It does not weaken any existing publish
preflight, clean-tree, tag, validation, authentication, or registry policy. A
protected release workflow can retain both the exact JSON plan and the HTML
review artifact, then run the ordinary publish command only after the normal
review and environment gates succeed.

## Drift rule

Any future renderer, UI, or automation must consume the authoritative JSON
model or another versioned contract emitted by the planner. Reimplementing
release routing in JavaScript, a web server, or CI configuration would create
an unreviewable second source of truth and is out of scope.
