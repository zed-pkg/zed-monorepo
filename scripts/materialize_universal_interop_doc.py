#!/usr/bin/env python3
"""Renumber the reviewed universal interop RFC onto current docs main.

The helper asserts the original heading/status and current README anchor. Any
concurrent content change fails closed rather than producing an approximate
renumbering.
"""

from pathlib import Path

rfc = Path("docs/28-universal-environment-interop.md")
text = rfc.read_text(encoding="utf-8")

old_heading = "# 24. Universal environment-manager interoperability\n"
new_heading = "# 28. Universal environment-manager interoperability\n"
if text.count(old_heading) != 1:
    raise SystemExit("expected exactly one reviewed RFC 24 heading")
text = text.replace(old_heading, new_heading, 1)

old_status = """**Status:** RFC and staged implementation plan for `DEN-1420`.  
**Related:** `DEN-1411`, `DEN-1413`, `DEN-588`, `DEN-591`, `DEN-100`.  
**First implementation slice:** `zed-interfaces` PR #10 introduces the shared
`EnvironmentPlan` contract and validation model; it is not considered shipped
until that PR and its generated-schema/lock follow-ups are reviewed and merged.
"""
new_status = """**Status:** architecture contract with foundation schemas implemented and
manager/native-registry/OCI adapter work continuing under `DEN-1420`.  
**Related:** `DEN-1411`, `DEN-1413`, `DEN-588`, `DEN-591`, `DEN-100`.  
**Current implementation foundation:** `zed-interfaces` main ships
`EnvironmentPlan` v1/v2, hardened `EnvironmentLock`, Nix export-plan, and OCI
contracts. Native-registry publication, source-aware ranges, lockfile
provenance, manager adapters, and final cross-platform certification remain
independently gated follow-up slices.
"""
if text.count(old_status) != 1:
    raise SystemExit("reviewed RFC status block no longer matches")
text = text.replace(old_status, new_status, 1)

for obsolete in (
    "docs/24-universal-environment-interop.md",
    "24-universal-environment-interop.md",
    "RFC 24",
    "doc 24",
):
    if obsolete in text:
        raise SystemExit(f"obsolete RFC number remains in materialized document: {obsolete}")

rfc.write_text(text, encoding="utf-8")

readme = Path("README.md")
index = readme.read_text(encoding="utf-8")
anchor = "| [27](docs/27-durable-first-install-manifests.md) | Durable `.zpkg.toml` creation on first dependency install | implemented; Node + Go/Python/Rust certified on Linux/macOS |\n"
row = "| [28](docs/28-universal-environment-interop.md) | Universal environment managers, native registries, and OCI interoperability | foundation implemented; adapter certification in progress |\n"
if index.count(anchor) != 1:
    raise SystemExit("current README doc-27 anchor is missing or duplicated")
if row in index:
    raise SystemExit("README already contains doc 28 row")
index = index.replace(anchor, anchor + row, 1)
readme.write_text(index, encoding="utf-8")

print("materialized current-main universal interoperability RFC as doc 28")
