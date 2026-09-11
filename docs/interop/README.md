# Executable interoperability policy

The normative design is [RFC 28](../28-universal-environment-interop.md). This
The normative design is [RFC 24](../24-universal-environment-interop.md). This
directory turns its cross-ecosystem invariants into a small machine-checked
contract so documentation and implementation PRs cannot silently disagree.

## Compatibility matrix

`compatibility-matrix.json` records the required boundary for:

- Nix;
- Flox and Devbox;
- mise and asdf;
- Docker and Podman through one canonical OCI model; and
- npm and Cargo native-registry publication.

The matrix is not a registry credential file, manager lock, or generated user
configuration. It describes which component is authoritative, which commands are
planned, what frozen state must exist, where platform identity lives, and what
constitutes immutable output identity.

## Policy gate

Run locally with:

```sh
python3 -B scripts/check_interop_matrix.py
```

The validator uses only Python's standard library. It fails when:

- an adapter is added or removed without an explicit schema review;
- a manager stops requiring frozen lock state;
- Flox or Devbox loses its declared Nix backing;
- mise or asdf allows moving channels in frozen mode;
- npm or Cargo stops requiring strict SemVer or immutable same-version bytes;
- any adapter moves platform identity into SemVer build metadata;
- Docker and Podman diverge from the same OCI image-layout model;
- scratch images stop being restricted to verified static outputs; or
- RFC 28 loses one of the normative invariants referenced by the matrix.
- RFC 24 loses one of the normative invariants referenced by the matrix.

The GitHub Actions workflow runs read-only, pins third-party Actions to immutable
commits, disables Python bytecode output, and retains the matrix plus its SHA-256
as review evidence.

## Change discipline

A matrix change should name the affected Linear issue and implementation PRs.
Changing a command or authority does not itself ship that command; the relevant
shared interface, CLI adapter, and independent E2E canary must still land. The
matrix provides the common review target those layers are expected to satisfy.
