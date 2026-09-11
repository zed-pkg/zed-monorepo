# 10. End-to-end testing across servers, CLI, and browsers

**Issue:** zed-pkg is a polyglot system whose pieces only matter together — a
Rust API server, a Rust web UI reading the same Postgres, and a Rust CLI that
publishes and installs against them. Per-repo unit tests prove the parts; they
cannot prove that a `zed publish` lands bytes the web UI then renders and that
another machine's `zed install` can pin. That cross-service guarantee needs a
single harness that boots the whole stack and drives it the way real clients
do.

[`zed-e2e`](https://github.com/zed-pkg/zed-e2e) is that harness: one
orchestrator boots the system once, and **three independent browser
frameworks** plus the `zed` CLI exercise it.

## The harness (one stack)

[`harness/stack.ts`](https://github.com/zed-pkg/zed-e2e/blob/main/harness/stack.ts)
boots the pipeline that every suite shares:

```
postgres (Docker) -> migrations -> zed-api-server -> zed-web-server
```

- **Postgres 16** runs in a throwaway container (`zed-e2e-postgres`). The
  **API server** applies the schema on boot (`auto_migrate` →
  `Migrator::up`) and owns it; the **web server** reads that same database.
- Both servers are `cargo build`-ed in debug and spawned as child processes
  with logs under `.stack/`; the harness polls each `/healthz` before handing
  off to the suites.
- The CLI runs against an **isolated `ZED_PKG_HOME`** under `.stack/` with
  `ZED_PKG_REGISTRY` pointed at the local API server, so a run never touches
  the developer's real `~/.zed-pkg` store (`runZed`).
- Publish tokens are minted through the API server's `create-token`
  subcommand, and
  [`harness/fixtures.ts`](https://github.com/zed-pkg/zed-e2e/blob/main/harness/fixtures.ts)
  publishes a stable seed dataset (`acme/http-kit`, `acme/logkit`,
  `acme/cryptobox`) through real `zed publish` calls so the browser suites
  have something to browse. `ZED_E2E_API_URL`/`ZED_E2E_WEB_URL` point the
  suites at an already-running stack instead of booting one.

Ports: API `48080`, web `48081`, Postgres `55432`.

## What each suite covers

- **Playwright** ([`suites/playwright`](https://github.com/zed-pkg/zed-e2e/tree/main/suites/playwright))
  — three specs across the whole stack:
  - *`cli-lifecycle`* drives the real `zed` binary against the live registry:
    `org claim`, publish → install with a transitive dependency (asserting the
    pnpm-style `zed_modules/` symlink layout and the `.zpkg.lock` sha256 pin),
    `--frozen` reinstall, container-safe `--install-mode copy` (asserts a
    symlink-free tree), registry immutability (re-publishing a version is
    refused), and `zed yank` hiding a version from fresh resolution.
  - *`api-contract`* exercises the API server's REST surface directly (no
    browser): `healthz`, package/version metadata, clean 404 error codes,
    search (including that a literal `%` is not treated as a LIKE wildcard),
    unauthenticated-publish rejection, the unpkg-style file route, and the
    `nosniff` header.
  - *`web-ui`* drives the MASH web UI (Maud + Axum + SeaORM + HTMX) in a real
    browser: the home listing, HTMX live search, package pages with the
    version-provenance column (VCS tag + sha256), and the CSP / frame-options
    / nosniff security headers.
- **Puppeteer** ([`suites/puppeteer`](https://github.com/zed-pkg/zed-e2e/tree/main/suites/puppeteer))
  — the same web UI in raw Chromium via `node:test`: a second, independent
  browser engine check of the HTMX flows and security headers.
- **Selenium** ([`suites/selenium`](https://github.com/zed-pkg/zed-e2e/tree/main/suites/selenium))
  — a third engine (chromedriver) driving the UI through the W3C WebDriver
  protocol rather than CDP, so a browser-automation regression can't slip past
  all three frameworks.

Because the stack is shared mutable state, suites run serially; individual
specs isolate themselves by unique org/package names.

## Running

Prerequisites: Docker (Postgres 16), a Rust toolchain (the two servers and the
CLI build in debug on first run), and Node 20+. Sibling checkouts of
`zed-api-server.rs`, `zed-web-server.rs`, and `zed-cli` are expected next to
`zed-e2e`.

- Playwright is wired through
  [`playwright.config.ts`](https://github.com/zed-pkg/zed-e2e/blob/main/playwright.config.ts):
  `globalSetup`/`globalTeardown` boot and tear down the stack, so
  `npx playwright test` runs the whole Playwright suite.
- The Puppeteer and Selenium suites are `node:test` files that call
  `startStack()`/`stopStack()` themselves and run under `tsx`.

Set `ZED_E2E_API_URL`/`ZED_E2E_WEB_URL` to reuse one already-running stack
across suites, and `ZED_E2E_KEEP=1` to leave the stack up after a run.

## Status: implemented

The orchestrator, seed fixtures, and all three browser suites — plus the CLI
lifecycle and API-contract suites — exist and run the two Rust servers and the
`zed` CLI together against a real Postgres. This is the top-level check that
the API server ([2](02-store-project-bridge-oci.md),
[4](04-lockfile-and-tag-immutability.md)), the web UI, and the CLI agree on
one contract end to end.
