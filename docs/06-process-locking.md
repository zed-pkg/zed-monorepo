# 6. Process-level locking

**Issue:** CLI commands are highly concurrent. A user can run `zed install` in
two terminals, or CI can launch several installers against one shared
`ZED_PKG_HOME`. Without process coordination, callers can duplicate downloads,
publish partial cache entries, race extraction, or corrupt mutable project and
reference metadata.

The current implementation is in `zed-cli`. The reusable cross-platform lock
boundary is being extracted into `zed-pkg/zed-lock` under
[DEN-2076](https://linear.app/denman/issue/DEN-2076/zed-lock-create-event-driven-cross-platform-process-lock-library-and).
The canonical extraction design is [doc 31](31-zed-lock-evented-cross-platform-locking.md).
The canonical extraction design is [doc 28](28-zed-lock-evented-cross-platform-locking.md).

## Design

zed-pkg uses descriptor- or handle-backed advisory lock files under
`~/.zed-pkg/locks/`:

- **Per-artifact locks** serialize acquisition of one SHA-256 while allowing
  unrelated hashes to download concurrently. Recursive prefetch and the
  transactional installer use the same acquisition function and therefore the
  same lock.
- **Per-build locks** serialize publication of one target-specific build-cache
  identity while unrelated build keys remain concurrent.
- **Project-operation locks** protect a checkout's mutating lifecycle command,
  including lockfile, references, submodule-adjacent metadata, and
  materialization changes.
- **Refs and shared-metadata locks** protect narrow mutable global-store indexes
  without serializing unrelated immutable artifact work.

The lock file is only a stable rendezvous path. Ownership belongs to the open
file descriptor or operating-system handle. The operating system releases the
lock when the owning guard closes its descriptor/handle or the owner process
terminates, so a crashed or killed `zed` process does not leave a stale logical
owner behind.

Lock files are not deleted during ordinary release. Deleting and recreating the
same pathname can produce a second inode or file object while an older descriptor
still refers to the original, splitting one logical lock domain into concurrent
owners.

## Blocking, non-polling acquisition

A normal contended acquisition issues one native blocking or overlapped request:

- Linux uses a blocking whole-file advisory lock, normally `flock(LOCK_EX)`;
- macOS uses and independently certifies its native blocking whole-file locking
  behavior;
- Windows uses `LockFileEx` over a stable byte range, preferably with an
  overlapped event or IOCP-compatible completion path.

A contended waiter sleeps in the operating system and wakes when the owner
releases the descriptor/handle or terminates. Production acquisition has no
`try_lock_exclusive` retry loop, spin interval, exponential backoff, jitter,
stale-PID reclamation, lockfile-deletion protocol, filesystem watcher, or
periodic filesystem polling.

An explicit `try_acquire` API may perform one immediate nonblocking attempt.
That API is not the implementation of ordinary waiting or timeout handling.
Repeated caller timeouts must not start repeated native probes.

## Responsive callers: helper thread, not helper process

A synchronous command with no useful independent work may invoke the blocking
native lock directly on its calling thread. A caller that must keep its main
thread, worker pool, or async runtime responsive uses the same native request on
a helper thread or bounded blocking-thread service:

```text
responsive caller
       |
       | submit one acquisition
       v
helper thread / bounded blocking worker
       |
       | blocking native lock request
       v
operating-system wait queue
       |
       | owner releases or exits
       v
helper thread wakes
       |
       | channel / oneshot / waker / event
       v
caller receives the guard
```

Only the helper thread sleeps; other threads in the Zed process remain runnable.
On Linux, userspace threads are individually scheduled kernel tasks. The
scheduler ultimately wakes a task in both the thread and process cases, so the
important savings come from avoiding another address space, process startup and
teardown, duplicated runtime state, descriptor-transfer logic, supervision, and
cross-process IPC.

Therefore, one waiter subprocess per acquisition is not the normal architecture.
A subprocess backend is acceptable only for a measured exceptional requirement,
such as hard cancellation or fault isolation, whose benefit outweighs that
additional cost.

Child-process tests are still mandatory. They prove that independent CLI
processes exclude one another, that owner death releases a lock, and that
handles are not accidentally inherited. Those tests describe what is being
coordinated; they do not prescribe a process-based async adapter.

## Cancellation and timeout behavior

Dropping or timing out a pending wait must never leak ownership.

On Unix, a helper thread already blocked in a native advisory-lock syscall may
not be portably interruptible. If it later acquires after its receiver has been
canceled or dropped, it immediately releases and closes the descriptor rather
than exposing a guard. Outstanding detached or canceled waiters must be bounded
so pathological contention cannot create unbounded threads.

On Windows, the preferred overlapped implementation uses the native I/O
cancellation path where available while preserving the same no-leak rule.

A monotonic deadline is caller policy. It must not be implemented as a loop of
nonblocking attempts separated by timers.

## Lock identity, aliases, and inheritance

- Lock paths are canonicalized by lock class and logical identity.
- A dedicated lock file is used instead of a target that will be atomically
  replaced.
- The lock directory is user-private and resists symlink/reparse-point
  substitution.
- Descriptors and handles are close-on-exec or non-inheritable by default.
- The resulting guard has exclusive logical ownership of its descriptor/handle.
- PID, process start identity, hostname, command, timestamp, and operation name
  may be recorded for diagnostics, but they never establish ownership.
- Symlink aliases, case-insensitive aliases, and Windows path aliases must not
  create independent lock domains for one logical resource.

## Per-artifact acquisition protocol

For an artifact with hash `<sha256>`:

1. Check the immutable content-addressed store.
2. Acquire `locks/artifact-<sha256>.lock`.
3. Re-check the store after waking; another process may have completed the
   artifact while this process slept.
4. Download to a temporary file in the cache directory.
5. Verify SHA-256 and declared artifact metadata.
6. Atomically rename the verified file into its final cache path.
7. Extract to a temporary directory and atomically rename the complete store
   entry into place.
8. Drop the lock guard.

A failed or interrupted download never becomes the final cache entry. A corrupt
cache entry is removed and replaced while the per-hash lock is held. Waiters
therefore observe either a complete immutable artifact or no artifact, never a
half-published one.

The lock is deliberately per content hash rather than global. Two processes can
make progress on different dependencies at the same time while still downloading
any one artifact at most once in aggregate.

## Project mutation boundary

Concurrent workers resolve metadata and acquire immutable artifacts. The
existing install transaction remains responsible for lockfile writes, adapter
wiring, project references, rollback, and `zed_modules/` materialization.

The project-operation lock surrounds the mutating command, and the caller
revalidates its project plan after acquisition. `zed-lock` owns acquisition and
guard mechanics; it does not absorb package-manager transaction semantics.

On Unix, project packages remain symlinks into the global store by default. Copy
mode remains explicit for Docker/OCI and is the non-Unix fallback. Process
locking is not a reason to copy package trees into every project.

## Local versus distributed coordination

`zed-lock` is local operating-system coordination. It is not a distributed
lease, quorum, fencing, or consensus service.

Fiducia remains an optional outer layer for mutable state genuinely shared
across hosts or process namespaces. Ordinary same-host installs, uninstalls,
store publication, build-cache publication, and refs updates make no Fiducia or
other network call. A distributed SSE or WebSocket notification is only a
wake-up hint; it never grants ownership and must be followed by a fresh
authoritative lease acquisition and fencing token.

## Implementation provenance

- Core recursive graph resolution, five-worker queue, unified artifact
  acquisition, and tests originated in
  [`zed-pkg/zed-cli#53`](https://github.com/zed-pkg/zed-cli/pull/53).
- True parent/child artifact-lock tests and the permanent Windows workflow were
  reviewed in [`zed-pkg/zed-cli#65`](https://github.com/zed-pkg/zed-cli/pull/65).
- Kernel-blocking lower-level store/install/build locks plus orderly-release and
  forced-owner-exit regressions were reviewed in
  [`zed-pkg/zed-cli#67`](https://github.com/zed-pkg/zed-cli/pull/67).
- Runtime-neutral helper-thread waiting, one-request timeout behavior, and the
  expanded Linux/macOS/Windows process conformance suite landed in
  [`zed-pkg/zed-cli#178`](https://github.com/zed-pkg/zed-cli/pull/178).
- The composed recursive, recovery, workspace, uninstall, Linux, and Windows
  certification merged through
  [`zed-pkg-test/zed-pkg-e2e#14`](https://github.com/zed-pkg-test/zed-pkg-e2e/pull/14).

The earlier stacked branch heads were verified as ancestors of current
`zed-cli/main`; the implementation and regression behavior described here are
landed, not merely proposed by historical pull-request pages.

See also [24 — recursive installs and artifact locking](24-recursive-installs-and-artifact-locking.md)
and [31 — zed-lock evented cross-platform locking](31-zed-lock-evented-cross-platform-locking.md).
and [28 — zed-lock evented cross-platform locking](28-zed-lock-evented-cross-platform-locking.md).

## Required regressions

The permanent suites prove that:

- a separate process reaches acquisition and remains blocked while the owner
  holds the descriptor;
- the waiter wakes after orderly guard drop and forced owner termination;
- a responsive caller remains runnable while a helper thread sleeps in the
  kernel;
- repeated caller timeouts retain one pending native request rather than
  creating retries;
- a dropped receiver causes any late-acquired guard to be released immediately;
- multiple waiters receive exclusive successive handoffs without assuming FIFO;
- unrelated lock classes, homes, artifact hashes, and build keys remain
  concurrent;
- concurrent recursive prefetches sharing one home download one absent hash once
  in aggregate;
- recursive and transactional paths share one artifact lock;
- failed downloads leave no final cache/store publication or staging leak;
- lock-file aliases and replacement attempts cannot split the lock domain;
- descriptors and handles are not unintentionally inherited;
- Linux, macOS, and Windows execute the shared process-lock contracts;
- multiple projects materialize symlinks to identical immutable store targets;
- instrumentation observes one native blocking/overlapped request and zero
  timer-driven retries for ordinary contention.

## Status

Kernel-backed local locking and the helper-thread evented prototype are
implemented and cross-platform certified in `zed-cli`. Extraction into the
standalone `zed-pkg/zed-lock` crate and migration of all agreed lock classes are
tracked by DEN-2076. This document replaces older polling, stale-lock,
lockfile-deletion, and waiter-subprocess designs.
