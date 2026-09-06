# 24. Recursive installs and artifact locking

**Issue:** a Zed package can depend on another Zed package, which can depend on
more packages. `zed install` must resolve and install that complete transitive
graph without downloading shared dependencies repeatedly, deadlocking on
cycles, producing nondeterministic lockfiles, or copying immutable package
trees into every project.

Primary implementation tracker:
[DEN-1505](https://linear.app/denman/issue/DEN-1505/zed-cli-recursively-install-package-dependency-graphs-with-a-five).
Reusable local-lock extraction:
[DEN-2076](https://linear.app/denman/issue/DEN-2076/zed-lock-create-event-driven-cross-platform-process-lock-library-and).

## Goals

The recursive installer must:

- expand dependencies declared by every selected package;
- choose one compatible version per `org/name`;
- terminate cycles and deduplicate diamond graphs;
- report conflicts in stable graph order;
- acquire independent artifacts concurrently, with five workers by default;
- coordinate threads and independent CLI processes without lock polling;
- download and extract each content hash once per shared Zed home;
- preserve immutable, content-addressed storage and symlink-first project
  materialization;
- keep lockfile writes, hooks, adapters, references, and rollback inside one
  deterministic project transaction;
- keep the local lock mechanism independently reusable through the planned
  `zed-pkg/zed-lock` crate.

## Two-phase architecture

Recursive installation separates immutable acquisition from mutable project
work.

### Phase 1: deterministic graph discovery and prefetch

Registry metadata resolution stays on the coordinator thread. Starting with the
consumer's direct requirements, the resolver repeatedly selects a package,
reads that package's manifest dependencies, and adds unseen requirements to the
pending graph.

The resolver maintains one selected version for each package coordinate. Active
requirements are solved together through the complete deterministic solver.
Packages already expanded are not needlessly repeated, cycles terminate, and
diamond dependencies converge on one selected node.

Only independent artifact work is submitted to workers. That work includes
cache lookup, download, digest verification, atomic cache publication, and
content-addressed-store extraction.

### Phase 2: transactional project materialization

After the complete graph is selected and its immutable artifacts are available,
the existing install transaction performs:

- frozen-lock verification or deterministic lockfile generation;
- pre/post hooks and native adapter wiring;
- project reference updates;
- rollback bookkeeping;
- `zed_modules/` materialization.

Workers do not independently rewrite `.zpkg.lock`, mutate project directories,
or run project hooks. Completion order therefore cannot leak into lockfile or
error order.

## Bounded worker queue

The registry and store interfaces are synchronous. The implementation therefore
uses a small blocking worker pool rather than adding a Tokio runtime around
blocking I/O.

The default is five concurrent artifact tasks:

```text
ZED_PKG_INSTALL_CONCURRENCY=5 zed install
```

The supported range is 1 through 32. Zero and invalid values use the default;
oversized values are bounded according to the CLI configuration contract.

Idle workers block on a condition variable. They do not wake periodically to
check the queue. Each task carries a stable sequence number so a faster later
download cannot reorder user-facing failures ahead of an earlier graph task.

A panic at the worker boundary is caught and returned as a sequenced task
failure. The coordinator receives one terminal result for every dispatched
task and cannot wait forever because a worker unwound after popping work.

Conceptually:

```text
solve direct and transitive requirements in stable order
assign immutable artifact work a stable sequence number
run at most five artifact tasks at once
collect every result by sequence number
if any task failed: abort before project commit
materialize the exact solved graph through the existing transaction
```

## Per-artifact cross-process lock

Every artifact SHA-256 has one stable rendezvous file:

```text
$ZED_PKG_HOME/locks/artifact-<sha256>.lock
```

The lock is descriptor- or handle-backed and acquired through the operating
system's blocking/overlapped exclusive-lock primitive. A waiter sleeps in the
kernel or native I/O subsystem until the owner releases the descriptor/handle
or exits. There is no retry timer, exponential backoff, jitter, stale PID file,
lockfile deletion protocol, filesystem watcher, or production polling loop.

The critical section is deliberately keyed by content hash rather than package
name or whole install. Two processes may download different dependencies at the
same time, while requests for the same bytes converge on one owner.

The lock file persists across releases. Its presence is not ownership. Deleting
or replacing it during unlock could let new openers refer to a second inode or
file object while an old descriptor remains locked, splitting the lock domain.

## Evented adapter: a thread waits; processes are coordinated

The lock exists to coordinate independent CLI **processes**, but a responsive
caller inside one process should adapt the blocking request with a **thread**,
not a helper process.

`zed-cli` now contains a runtime-neutral `LockWaiter` prototype. It invokes one
blocking acquisition closure on a dedicated thread, then transfers the acquired
RAII guard through an in-process channel. The caller can continue unrelated
work while the helper thread sleeps in the kernel.

```text
caller -> helper thread -> one native lock request -> kernel wait
                                              owner releases
caller <- channel/waker <- acquired guard <- helper thread wakes
```

On Linux, userspace threads are individually scheduled tasks. Waking a blocked
thread and waking a task in another process use the same broad scheduler
machinery; the helper-thread design avoids another address space, process
startup/teardown, duplicated runtime state, descriptor-transfer logic, and
cross-process IPC.

Accordingly:

- synchronous callers may block their own calling thread directly;
- responsive/async callers use a helper thread or bounded blocking-thread
  service plus a channel, oneshot, waker, event, or equivalent completion path;
- one subprocess per acquisition is not the normal architecture;
- child-process tests remain required because they certify cross-process
  exclusion, process-death release, and descriptor/handle inheritance;
- process-based tests do not prescribe a process-based waiter implementation.

The canonical standalone extraction contract is
[31 — zed-lock evented cross-platform locking](31-zed-lock-evented-cross-platform-locking.md).
[28 — zed-lock evented cross-platform locking](28-zed-lock-evented-cross-platform-locking.md).
The helper-thread prototype and expanded conformance coverage landed in
[`zed-pkg/zed-cli#178`](https://github.com/zed-pkg/zed-cli/pull/178).

## Platform behavior

- **Linux:** one blocking whole-file advisory-lock request, normally
  `flock(LOCK_EX)`, outside any async executor.
- **macOS:** the same high-level blocking-helper-thread model, with independent
  tests for native semantics, case-insensitive aliases, process termination,
  and handle inheritance.
- **Windows:** `LockFileEx` over a stable byte range, preferably through
  overlapped/event or IOCP-compatible completion; a blocking helper thread is
  an acceptable fallback.

Ordinary contention never repeatedly sets a nonblocking flag and sleeps. An
explicit `try_acquire` operation may make one immediate attempt, but it is a
separate API.

## Unified artifact acquisition

Recursive prefetch, the transactional installer, frozen installs, build
preparation, `zed add`, and `zed remove` use one acquisition function. No older
direct-download path may bypass the per-hash lock.

For a missing artifact:

1. Check the immutable store.
2. Acquire `artifact-<sha256>.lock`.
3. Re-check the store after waking.
4. Download into a temporary file inside the cache directory.
5. Verify SHA-256 and declared artifact metadata.
6. Atomically rename the verified file to the final cache path.
7. Extract into a temporary directory.
8. Atomically rename the complete content-addressed store entry into place.
9. Release the descriptor- or handle-backed guard.

The post-lock store re-check is essential. A waiting process usually wakes
because another process just completed the artifact; it should reuse that entry
instead of downloading again.

Temporary files live on the same filesystem as their final paths so publication
can use atomic rename. A failed or interrupted download never becomes the final
cache entry. A corrupt cached artifact is removed and replaced while the hash
lock is held.

## Cancellation and timeouts

Timeout behavior must not turn acquisition into polling.

On Unix, a helper thread already blocked in the native syscall may not be
portably cancelable. If its receiver times out or is dropped and the helper later
acquires, it immediately drops the guard and closes the descriptor rather than
exposing or retaining ownership. Detached/canceled waiters must be bounded.

On Windows, the preferred overlapped implementation uses the native I/O
cancellation path where available. In every backend, cancellation and timeout
must never leak a late-acquired lock.

Repeated calls that observe a pending timeout retain one native acquisition
request; they do not start new `try_lock` attempts.

## Symlink-first materialization

The global store contains the one extracted immutable package tree:

```text
~/.zed-pkg/store/v1/<shard>/<sha256>/pkg/
```

A consumer project points at it:

```text
project/zed_modules/<org>/<name>
    -> ~/.zed-pkg/store/v1/<shard>/<sha256>/pkg/
```

A diamond graph therefore stores its shared leaf once. Every consumer and every
path that requires the leaf resolves to the same immutable target.

Copy mode remains explicit for Docker/OCI images and is the non-Unix fallback.
Concurrency and process safety are not reasons to silently copy package trees.

## Project-operation boundary and lock ordering

Immutable artifact acquisition stays fine-grained. Mutable project work is
protected by one checkout-local operation lock for the command.

After acquiring that lock, `zed-cli` revalidates its plan before writing
`.zpkg.lock`, references, adapters, submodule-adjacent metadata, or
materialization state. Narrow refs/build/store locks follow the documented lock
ordering so a coarse project operation never creates an inversion with a
lower-level publication lock.

The planned `zed-lock` crate owns canonical lock identity, native acquisition,
guard lifetime, cancellation cleanup, and platform error classification.
`zed-cli` continues to own graph solving, revalidation, transactions, downloads,
staging, atomic publication, hooks, rollback, and materialization.

## Determinism and conflict behavior

Graph traversal order, requirement provenance, task sequence, and final package
ordering remain stable across runs. The result must not depend on which network
request finishes first.

When active requirements have no common version, the installer reports the
canonical unsatisfied coordinate and every relevant provenance path. It does not
silently select whichever worker completed first.

Frozen installation resolves from the exact lock graph and never rewrites the
input lockfile. A manifestless frozen replay may materialize the complete graph
from `.zpkg.lock` without synthesizing `.zpkg.toml` when the user selected the
supported no-manifest path.

The complete overlapping-constraint solver is documented in
[25 — complete constraint solving](25-complete-constraint-solving.md).

## Failure and recovery rules

- A failed artifact task aborts project commit.
- Worker panics become ordinary sequenced errors.
- Cache publication occurs only after full digest verification.
- Store publication occurs only after complete extraction.
- Temporary downloads and extraction directories are cleaned on failure.
- Waiters re-check the store after acquiring the hash lock.
- Forced process termination releases descriptor/handle ownership automatically.
- A timed-out or canceled waiter never later exposes or retains a guard.
- Project rollback remains the responsibility of the existing transaction.
- Lock files remain stable and are not deleted to recover from a crash.
- Unsupported network-filesystem semantics fail clearly or require an explicit
  outer coordination policy rather than silently weakening safety.

## Required regression matrix

### Graph semantics

- diamond dependency resolves and acquires every package once;
- cycle terminates after every required package is expanded;
- overlapping compatible constraints select the common candidate regardless of
  declaration or completion order;
- unsatisfiable requirements fail in deterministic graph order with provenance;
- frozen lock-only install restores the complete graph without a manifest;
- warm replay downloads zero artifact bytes.

### Concurrency

- default worker count is five;
- supported overrides remain within configured bounds;
- a gated HTTP fixture with twelve cold artifacts observes a peak of exactly
  five live transfers and never exceeds five;
- a worker panic returns a sequenced error and does not deadlock completion;
- distinct artifact and build identities retain useful concurrency.

### Threads and processes

- a helper thread sleeps in one native acquisition while the caller remains
  responsive;
- repeated caller timeouts retain one native acquisition request;
- a dropped receiver causes immediate cleanup of any late-acquired guard;
- concurrent prefetches sharing one home download one absent hash once;
- recursive and transactional acquisition paths racing one hash share one lock
  and one download;
- a child process reaches lock acquisition, remains blocked while the parent
  owns the descriptor, and wakes after orderly release;
- a blocked waiter wakes after the owning process is forcibly terminated;
- multiple waiters make exclusive successive progress without assuming FIFO;
- descriptors/handles are not unintentionally inherited;
- the shared contracts pass on Linux, macOS, and Windows.

### Publication and layout

- corrupt partial cache is replaced under the hash lock;
- failed downloads leave no final cache/store entry or staging leak;
- lock-file deletion/replacement and path aliases cannot split ownership;
- cache and per-hash lock cardinality match the selected graph;
- every default materialization is a symlink into the shared store;
- separate consumers resolve each package to identical store targets;
- copy-mode OCI contracts remain green.

### No-polling evidence

- instrumented acquisition records one native blocking/overlapped request per
  waiter;
- ordinary contention records zero timer-driven nonblocking retries;
- a blocked waiter consumes negligible CPU relative to an intentionally polling
  comparison implementation;
- process tests use markers, pipes, events, and bounded failure timeouts only for
  orchestration, never as production ownership authority.

## Certified multi-process scenario

The companion E2E suite publishes a 13-package graph: one root plus twelve
leaves. It launches four separate `zed install` processes against one shared
home.

Every process resolves all 13 packages, but aggregate cold downloads equal 13
rather than 52. Download ownership can be split across processes because locks
are per hash rather than global. All four consumers materialize symlinks to
identical store targets. A fresh frozen replay downloads 13 artifacts into a new
home, and a warm frozen replay downloads zero.

## Implementation and review history

1. [`zed-pkg/zed-cli#53`](https://github.com/zed-pkg/zed-cli/pull/53) —
   recursive resolver, five-worker condition-variable queue, unified
   acquisition, symlink-first materialization, and core tests.
2. [`zed-pkg/zed-cli#65`](https://github.com/zed-pkg/zed-cli/pull/65) —
   true interprocess artifact-lock regression and Windows shared-home tests.
3. [`zed-pkg/zed-cli#67`](https://github.com/zed-pkg/zed-cli/pull/67) —
   kernel-blocking install/build/store locks and owner-exit recovery coverage.
4. [`zed-pkg/zed-cli#68`](https://github.com/zed-pkg/zed-cli/pull/68) —
   fail-closed manifest, identity, coordinate, and deterministic-error hardening.
5. [`zed-pkg-test/zed-pkg-e2e#14`](https://github.com/zed-pkg-test/zed-pkg-e2e/pull/14) —
   immutable graph, five-worker, four-process, frozen-replay, lifecycle, browser,
   and cleanup-safety certification.
6. [`zed-pkg/zed-docs#23`](https://github.com/zed-pkg/zed-docs/pull/23) —
   recursive-install architecture and the original blocking-lock contract.
7. [`zed-pkg/zed-cli#178`](https://github.com/zed-pkg/zed-cli/pull/178) —
   helper-thread evented adapter, one-request timeout semantics, and expanded
   Linux/macOS/Windows lock conformance.
8. [DEN-2076](https://linear.app/denman/issue/DEN-2076/zed-lock-create-event-driven-cross-platform-process-lock-library-and)
   — standalone `zed-pkg/zed-lock` extraction, shared API, and conformance suite.

## Local versus distributed coordination

The locks described here are local operating-system locks. Ordinary same-host
install, uninstall, store, build, and refs operations make no Fiducia call.

Fiducia may wrap genuinely multi-host mutable state with renewal and fencing.
A distributed event notification is only a hint to retry authoritative lease
acquisition; it never grants ownership. Distributed coordination does not
replace local descriptor/handle locks for same-host filesystem mutation.

## Non-goals

- zed-pkg does not reimplement native package-manager dependency graphs.
- It does not serialize all downloads behind one global artifact mutex.
- It does not add an async runtime solely to wrap synchronous registry APIs.
- It does not let worker completion order determine lockfile order.
- It does not copy package directories by default.
- It does not treat deleting lock files as releasing ownership.
- It does not poll nonblocking acquisition until success.
- It does not spawn one helper process per local async lock wait.
- It does not hide partial success by committing a reduced dependency graph.
- `zed-lock` does not absorb package resolution, transaction, rollback, or
  materialization responsibilities.

See also [1 — content-addressable storage + symlinks](01-cas-and-symlinks.md),
[2 — store/project bridge under OCI](02-store-project-bridge-oci.md),
[6 — process-level locking](06-process-locking.md), and
[31 — zed-lock evented cross-platform locking](31-zed-lock-evented-cross-platform-locking.md).
[28 — zed-lock evented cross-platform locking](28-zed-lock-evented-cross-platform-locking.md).
