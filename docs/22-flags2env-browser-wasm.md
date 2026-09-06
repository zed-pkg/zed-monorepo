# flags2env in browser WebAssembly

Status: **implemented** in `ORESoftware/flags-2-env` through
[`#15`](https://github.com/ORESoftware/flags-2-env/pull/15) and extended with
isolated workers and three-engine automation through
[`#17`](https://github.com/ORESoftware/flags-2-env/pull/17), tracked by Linear
DEN-1300 and DEN-1342.

## Why this belongs in the Zed architecture

`zed-cli` uses flags2env as its declarative CLI boundary, including nested
subcommands and the package-aware `zed dev` / `zed develop` shell. Related Zed
and SDK tooling needs to inspect the same command contracts in browser-based
documentation, review tools, and workers. A JavaScript rewrite would create
different alias, validation, help, and coercion semantics.

The browser client therefore compiles the existing C parser with Emscripten and
calls the same explicit-path ABI used by native language clients. JavaScript is
only an ownership, browser-filesystem, and worker-lifecycle adapter.

## Main-thread runtime model

Each main-thread client instance:

1. creates an isolated Emscripten module;
2. writes one `.cli-flags.toml` to the module's in-memory filesystem;
3. converts validated JavaScript strings to owned C strings;
4. invokes the existing parse, structured-parse, command-resolution, audit,
   coercion, or help entrypoint;
5. copies the returned C string into JavaScript;
6. calls `f2e_free` in a `finally` path before returning.

The exported browser surface covers:

- normal parsing;
- structured parsing with provided flags, commands, extras, unknown options,
  and errors separated;
- canonical nested-command resolution;
- configuration audit;
- typed environment coercion;
- subcommand-aware help.

It does not expose raw pointers or duplicate TOML/argv parsing logic.

## Worker isolation model

For production UI use, `createFlags2EnvWorker` runs the same module inside a
module Web Worker. The main thread communicates through bounded request-ID RPC:

- initialization creates one WebAssembly instance and one MEMFS config;
- parse, structured parse, command resolution, audit, coercion, help, and
  config replacement use the same native-backed operations;
- each request has a deterministic timeout and pending requests reject on
  worker failure or termination;
- `terminate()` closes the client and later requests fail explicitly;
- only bounded error names and messages cross the worker boundary; stacks and
  internal filesystem paths do not;
- separate workers have separate WebAssembly memory and MEMFS state, so two
  configurations cannot leak into one another.

The worker path requires no SharedArrayBuffer or cross-origin-isolation headers.
It remains useful on ordinary static hosting and through `file://`-adjacent
local development servers.

## Input and ownership hardening

The browser boundary rejects work before allocating into WebAssembly memory
when any of these conditions are met:

- configuration text exceeds 1 MiB;
- argv contains more than 4,096 entries;
- one argument exceeds 64 KiB;
- a serialized payload or worker envelope exceeds 4 MiB;
- any C-bound string contains a NUL byte;
- another main-thread call is already active on the same instance;
- terminal width is invalid or outside the supported bound;
- a worker request is malformed, non-serializable, timed out, or targets an
  unsupported method.

These are browser/FFI safety limits, not changes to native parser semantics.
Every JavaScript-owned allocation and every C-owned result has one explicit
cleanup path.

## Emscripten portability boundary

The native parser uses POSIX stream locking around help output. Single-threaded
Emscripten libc does not declare the same `flockfile` / `funlockfile` surface.
The browser build includes a narrowly scoped compatibility header that makes
those locks evaluated no-ops only for the non-pthread Emscripten target. Native
builds keep their normal locking behavior.

Dynamic code execution is disabled in the Emscripten build. The demo uses a
restrictive Content Security Policy, local assets only, and text rendering for
parser output.

## Browser automation contract

The GitHub Actions workflow builds the real C core and launches Chromium,
Firefox, and WebKit with Playwright. Every engine exercises the existing
main-thread contract and the worker contract, including:

- normal and structured argv parsing;
- nested commands and inherited/global flags;
- canonical command resolution;
- invalid typed values;
- subcommand-aware help;
- configuration audit and environment coercion;
- owned-result lifetime behavior;
- NUL rejection and every size/count limit;
- two-worker configuration isolation and runtime config replacement;
- a burst of concurrent caller requests through one worker;
- sanitized unsupported-request failures;
- deterministic worker startup timeout;
- termination and closed-state rejection;
- keyboard focus and narrow-screen containment;
- absence of external requests, console errors, and page errors.

Native sanitizers, Nix checks, generated-code clients, and the isolated Docker
client matrix run on the same reviewed head so browser additions cannot silently
weaken the native package surface.

## Adoption rule

Browser consumers should import the generated main-thread or worker client and
treat all returned help and diagnostics as text. They must not reach into
Emscripten internals, retain raw pointers, bypass configured limits, or
introduce a JavaScript fallback parser. New operations should first exist in
the versioned C ABI and native tests, then be exposed through the browser
wrapper and worker protocol.
