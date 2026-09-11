# 14. Client-side sync: patterns and the opto-sync package adoption

**Issue:** zed's offline-first story—optimistic writes in the browser, a durable
local store, and synchronization with Postgres/Supabase—is the same class of
problem solved by established sync engines. Rather than maintain two competing
implementations, the direction is to consume
[`github.com/opto-sync/opto-sync-clients`](https://github.com/opto-sync/opto-sync-clients),
which wraps the shared C reconciliation core
[`syncer.c`](https://github.com/opto-sync/syncer.c).

This document records the required correctness patterns, the current state of
the opto-sync implementation, and the package boundary zed uses to adopt it.

## What the field does (distilled)

Surveying Linear, Replicache/Zero, ElectricSQL, PowerSync, RxDB, WatermelonDB,
and CRDT engines such as Automerge and Yjs, the patterns that consistently
matter for a JSONB-merge client are:

1. **Two-tier optimistic write**—update the in-memory/reactive view immediately
   and persist to a durable local queue before network I/O.
2. **Restart-safe queue** with a `pending/synced/failed` lifecycle; flush from
   durable rows, not an in-memory request list.
3. **Exactly-once echo deduplication**—stable `clientId` plus monotonic
   `mutationId`; the server keeps a high-water mark and ignores replays.
4. **Rebase on pull**—authoritative server state becomes the base and every
   unconfirmed local mutation replays oldest-first.
5. **Do not timestamp-gate your own pending overlay.** Otherwise an older local
   edit disappears until its push lands.
6. **Field/element merge instead of whole-document replacement**, so disjoint
   concurrent edits survive.
7. **Logical clocks instead of client wall clocks** for conflict ordering.
8. **Explicit tombstones or delete operations**; an additive merge cannot infer
   removal safely.
9. **Idempotent replay**—re-sending a mutation is a semantic no-op.
10. **Server authority and durable rejection**—surface transformations or
    rejection instead of silently reverting optimistic state.
11. **Appropriate local storage**—IndexedDB for browser document/KV workloads;
    SQLite for relational or larger on-device data sets.

## Current opto-sync correctness contract

`syncer.c` is a pure merge function. Queueing, identity, HLC state, transport,
checkpointing, and rebase live in `opto-sync-clients`.

The current clients use the canonical merge policy:

- `arrayStrategy: MERGE_BY_KEY`;
- `arrayMatchKeys: "id"`;
- `resolveByTimestamp: true`;
- LWW keys `updatedAt,syncedAt`; and
- **no FWW key by default**.

The previous recommendation to set `createdAt` as an FWW key was wrong for this
engine. FWW is a node-level veto: a newer FWW value rejects the whole incoming
node, even when that node carries the newest `updatedAt`. Two devices creating
the same identity offline could therefore make one replica permanently unable
to update the record. `createdAt` is retained as ordinary data, not as a default
veto.

The implementation now includes:

- TypeScript: Dexie/IndexedDB, native Node and real browser WASM reconciliation,
  persisted HLC, `(clientId, mutationId)` deduplication, atomic queue helpers,
  rebase/local view, and a checkpointed protocol loop;
- Dart: Drift/SQLite plus browser IndexedDB/WASM coverage, HLC and mutation
  identity, atomic queue helpers, rebase, and the protocol loop;
- Rust: first-party SQLite protocol store, runtime-neutral storage seams, HLC,
  mutation identity, atomic application/queue transactions, rebase, and a
  protocol driver; and
- Gleam: the protocol queue and typed BEAM/NIF reconciliation surface.

The non-negotiable rendering rule remains:

> **Render `localView`, not `reconcileIncoming`.**

`reconcileIncoming` does not know about mutations that are still queued.
`localView` rebases those mutations over server state so a user's edit does not
flicker away between pull and acknowledgement.

## Zed package identities

The repositories now declare Zed manifests and deterministic pack/dry-run CI:

| Package | Version | Unit |
|---|---:|---|
| `opto-sync/syncer` | `0.2.1` | whole engine repository and native bindings |
| `opto-sync/syncer-c` | `0.2.1` | self-contained C core |
| `opto-sync/syncer-wasm` | `0.2.1` | self-contained browser/worker WASM binding |
| `opto-sync/opto-sync-clients` | `0.2.0` | whole client repository |
| `opto-sync/opto-sync-e2e` | `0.1.0` | coordinated cross-runtime conformance harness |

The clients are intentionally one repository package for the first release.
Their native manifests still reference `../../../syncer.c`; publishing
`clients/ts`, `clients/dart`, `clients/rust`, or `clients/gleam` as isolated
language targets would omit files required by those manifests. A deterministic
archive that cannot build is not a valid package.

Language fan-out follows only after each target can build in a clean consumer
without a sibling Git checkout. The accepted designs are an independently
published native binding, a hash-checked vendored core, or a native manifest
that resolves the separately installed Zed dependency without absolute paths.

## What zed-sync still owns during migration

Adopting opto-sync does not remove product-specific responsibilities:

- map zed's public change envelopes and write-policy enums to the opto protocol;
- implement authentication, tenant/table authorization, and token refresh;
- define the tombstone/deletion and retention policy for registry data;
- connect Postgres/Supabase catch-up cursors and realtime hints to the protocol
  driver (realtime is a hint, never the durable cursor);
- preserve zed's telemetry and error-policy surface; and
- prove behavior with shared conformance fixtures before removing the bespoke
  zed-sync implementation.

The migration should be adapter-first: keep zed's external API stable, route one
runtime through `opto-sync-clients`, run both implementations against the same
fixtures, then delete duplicated reconciliation code only after parity is
measured.

## Release and consumption order

```sh
# in each opto-sync repository
zed pack
zed publish --dry-run

# publish dependency order after matching reviewed tags exist
# 1. opto-sync/syncer@0.2.1 (+ c/wasm targets)
# 2. opto-sync/opto-sync-clients@0.2.0
# 3. opto-sync/opto-sync-e2e@0.1.0
```

Consumer lockfiles must pin the resulting artifact SHA-256, byte size, VCS tag,
and commit. Until the registry entries exist, the source repositories keep only
the lockfile format header rather than fabricating hashes.

## Status: package-ready adoption staged

The merge semantics, durable optimistic-write behavior, and cross-runtime test
matrix are implemented. The three opto-sync repositories are Zed-package ready,
with pinned-tooling package CI. Remaining work is release/tag publication,
native language-slice self-containment, and the measured zed-sync adapter
migration—not another sync engine rewrite.
