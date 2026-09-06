# 28. zed-lock: evented cross-platform process locking

**Status:** architecture approved; `zed-cli` prototype and conformance coverage landed in
[`zed-pkg/zed-cli#178`](https://github.com/zed-pkg/zed-cli/pull/178); standalone
`zed-pkg/zed-lock` extraction is tracked by
[DEN-2076](https://linear.app/denman/issue/DEN-2076/zed-lock-create-event-driven-cross-platform-process-lock-library-and).

## Purpose

`zed-pkg` needs one reusable local-locking boundary for recursive installation,
uninstallation, immutable-store publication, build-cache publication, project
mutation, refs updates, and recovery. The library must coordinate independent
processes on Linux, macOS, and Windows without introducing a timer-driven
`try_lock` loop or treating lock-file state as ownership.

The proposed repository and Rust crate are both named `zed-lock`:

```text
github.com/zed-pkg/zed-lock
crate: zed-lock
```

`zed-lock` owns local operating-system lock mechanics. It does not own package
graph solving, downloads, package transactions, rollback, project
materialization, distributed leases, or consensus.

## Core decision

A normal contended acquisition makes exactly one blocking or overlapped native
lock request:

- Linux: a blocking whole-file advisory lock, normally `flock(LOCK_EX)`;
- macOS: the certified native whole-file advisory-lock backend;
- Windows: `LockFileEx`, preferably with overlapped/event or IOCP completion.

The operating system remains authoritative for both ownership and wake-up.
Production acquisition must not use:

- repeated `try_lock` calls;
- sleep, backoff, jitter, or retry timers;
- filesystem watchers;
- lock-file existence or mtime checks;
- PID-file reclamation;
- ordinary Fiducia or other network calls.

A lock file is a stable rendezvous object. Its continued presence is harmless;
ownership belongs to the open descriptor or handle.

## Threads coordinate processes efficiently

The lock protects state shared by **processes**, but the efficient asynchronous
adapter inside each process is a **thread**.

```text
async or responsive caller
        |
        | enqueue one acquisition
        v
bounded helper-thread service
        |
        | blocking flock / native wait
        v
kernel wait queue
        |
        | owner releases or exits
        v
helper thread wakes
        |
        | channel / oneshot / waker
        v
caller receives LockGuard
```

On Linux, userspace threads are individually scheduled kernel tasks. A blocked
helper thread consumes no CPU while the kernel parks it. Other threads in the
same process continue resolving packages, downloading unrelated artifacts, or
driving an async runtime.

A separate waiter process would not provide a fundamentally different kernel
wake-up mechanism. It would add another address space, process startup and
teardown, duplicated runtime state, descriptor-transfer or IPC logic, and
supervision. Therefore:

- use a helper thread or bounded blocking-thread service by default;
- do not spawn one subprocess per async acquisition;
- retain child-process tests because the library must prove cross-process
  exclusion and release after process death;
- consider a subprocess backend only for a measured exceptional need such as
  hard cancellation or fault isolation.

Process-based conformance tests describe what is being coordinated, not how an
individual async waiter must be implemented.

## Platform contract

### Linux

Use one blocking native request against a dedicated, stable lock file. The
request runs outside the async executor on a helper thread. An
open-file-description `fcntl` variant may be considered only when its
interoperability and ownership semantics are explicitly justified and covered
by the shared suite.

### macOS

macOS is a first-class backend, not an assumed Unix alias. Certify native
blocking behavior, process termination, case-insensitive path aliases, symlink
aliases, handle inheritance, cancellation cleanup, and stable lock-file
identity on macOS runners.

### Windows

Use `LockFileEx` over a stable byte range. Prefer overlapped operation with an
event or IOCP-compatible completion adapter. A dedicated blocking waiter thread
is an acceptable fallback. Where supported, use `CancelIoEx` for cancellation.
Ordinary contention must not set `LOCKFILE_FAIL_IMMEDIATELY` and retry on a
timer.

## Lock identity and lifecycle

- Lock paths live in a private Zed lock directory and are normally keyed by a
  canonical lock class plus artifact/build/project identity.
- Do not lock a target that will be atomically replaced. Lock a separate stable
  rendezvous file.
- Do not unlink or recreate the lock file during ordinary release. Reopening the
  same path after replacement can refer to a different inode or file object and
  split one logical lock domain.
- Open descriptors and handles are close-on-exec or non-inheritable by default.
- The returned guard owns the descriptor or handle and releases through
  explicit release, guard drop, handle close, panic unwinding, or process exit.
- PID, process-start identity, hostname, command, operation name, and timestamps
  are optional diagnostics only; they never prove ownership.
- Path canonicalization and alias handling must prevent two spellings of one
  logical lock from becoming independent lock domains.

## API shape

The standalone crate should expose reviewed equivalents of:

```rust
let guard = LockFile::open(path)?.acquire_exclusive().await?;
let guard = LockFile::open(path)?.acquire_exclusive_blocking()?;
let maybe_guard = LockFile::open(path)?.try_acquire_exclusive()?;
```

Required behavior:

- async, blocking, and explicit immediate acquisition;
- exclusive locking in v1;
- runtime-neutral core with optional runtime adapters;
- monotonic deadlines and timeouts;
- deterministic same-process reentrancy handling;
- no upgrade or downgrade in v1;
- no FIFO promise unless fairness is implemented above the operating system;
- structured timeout, cancellation, permission, unsupported-filesystem, and
  native-error classification;
- optional tracing without coupling the crate to `zed-cli`.

## Cancellation and bounded resources

Dropping or timing out an acquisition must never leak ownership.

A blocked Unix advisory-lock syscall may not be portably interruptible. If the
helper later acquires after its receiver has disappeared, it immediately
releases and closes the descriptor instead of publishing a guard. Detached and
cancelled waiters must be resource-bounded so a heavily contended caller cannot
create unbounded threads.

Windows should use native overlapped cancellation when available while
preserving the same no-leak rule.

Timeout is a caller policy, not a reason to restart native acquisition in a
polling loop. A timeout API may keep the original native request alive or cancel
it according to the platform contract, but it must not create repeated
nonblocking probes.

## zed-cli integration

Move the following mechanics behind `zed-lock`:

- one checkout-local operation lock for each mutating lifecycle command;
- per-artifact locks for immutable source publication;
- per-build locks for platform-specific build-cache publication;
- refs and shared-metadata coordination;
- deterministic lock ordering and optional debug-time inversion detection.

Keep these responsibilities in `zed-cli`:

- graph solving and deterministic planning;
- `.zpkg.lock` generation or frozen verification;
- downloads, digest verification, staging, and atomic publication;
- hooks, adapters, rollback, reference tracking, and project materialization;
- the bounded five-worker recursive installer;
- post-wake revalidation of the immutable store and mutable project plan.

After a contended artifact lock wakes, the caller must re-check the store. The
previous owner probably completed the artifact while this process slept.

## Local versus distributed coordination

`zed-lock` is local operating-system coordination. It is not a distributed
lease, quorum, fencing, or consensus library.

Fiducia remains an optional outer layer for genuinely shared mutable state that
spans hosts or process namespaces. Ordinary same-host installs and store work
make no Fiducia call. An SSE or WebSocket notification from a distributed
service is only a wake-up hint; ownership still requires a fresh authoritative
lease acquisition and fencing token.

## Conformance suite

The shared suite runs on Linux, macOS, and Windows and proves:

1. A holder blocks a waiter without production polling, and release wakes it.
2. Multiple independent processes contend for one identity with one owner.
3. Holder crash or forced termination releases ownership.
4. Timeout and cancellation never expose or retain a late-acquired guard.
5. Lock files remain stable across releases and replacement attempts cannot
   create concurrent owners.
6. Handles are not unintentionally inherited across spawn or exec.
7. Same identities serialize while unrelated identities retain concurrency.
8. Several CLI processes and five recursive workers publish one absent artifact
   exactly once.
9. Warm-store replay performs no protected download work after wake and
   re-check.
10. Instrumentation observes one native blocking or overlapped request and zero
    timer-driven retries per contended acquisition.
11. Unix async instrumentation proves helper-thread waiting rather than waiter
    subprocess creation.
12. Stress, panic, forced-exit, aliasing, path-normalization, and waiter-budget
    tests do not deadlock or weaken exclusion.

Tests use processes because process boundaries, crash release, and descriptor
inheritance are part of the contract. Test orchestration may use markers,
pipes, events, and bounded waits; those are not production lock-notification
mechanisms.

## Current implementation evidence

[`zed-pkg/zed-cli#178`](https://github.com/zed-pkg/zed-cli/pull/178)
landed a runtime-neutral `LockWaiter` prototype that:

- executes one blocking native acquisition on a dedicated thread;
- transfers the guard through an in-process channel;
- retains one pending native request across repeated caller timeouts;
- drops a late-acquired guard when delivery is no longer possible;
- adds Linux, macOS, and Windows process-lock conformance coverage;
- documents that strict FIFO fairness is not promised.

The prototype validates the architecture but remains in `zed-cli` until the
standalone `zed-lock` repository is created, published, and integrated without
weakening the transaction or immutable-store contracts.

## Related documentation

- [6 — process-level locking](06-process-locking.md)
- [24 — recursive installs and artifact locking](24-recursive-installs-and-artifact-locking.md)
- [`zed-cli/docs/locking.md`](https://github.com/zed-pkg/zed-cli/blob/main/docs/locking.md)
- [Linear canonical architecture document](https://linear.app/denman/document/zed-lock-event-driven-cross-platform-locking-architecture-and-b19dc7a81fe5)

## Non-goals

- Polling a nonblocking lock until it succeeds.
- Treating file existence, PID metadata, or timestamps as ownership.
- Deleting lock files as an unlock or stale-owner mechanism.
- Spawning one helper process per local async acquisition.
- Providing cross-host correctness on arbitrary NFS or SMB deployments without
  a separately certified outer coordination layer.
- Moving package resolution, transaction semantics, downloads, rollback, or
  materialization into `zed-lock`.
