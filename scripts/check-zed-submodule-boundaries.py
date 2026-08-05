#!/usr/bin/env python3
"""Validate Zed dependencies against classified git submodules."""

from __future__ import annotations

import configparser
import pathlib
import sys
import tomllib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED = {
    "reusable",
    "application",
    "test",
    "documentation",
    "website",
    "tooling",
    "operations",
}


def load_toml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def gitmodules() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read(ROOT / ".gitmodules", encoding="utf-8")
    result: dict[str, str] = {}
    for section in parser.sections():
        if not section.startswith("submodule "):
            continue
        path = parser.get(section, "path", fallback="").strip()
        url = parser.get(section, "url", fallback="").strip()
        if not path:
            raise ValueError(f"{section} has no path")
        if path in result:
            raise ValueError(f"duplicate submodule path: {path}")
        result[path] = url
    return result


def main() -> int:
    manifest = load_toml(ROOT / ".zpkg.toml")
    policy = load_toml(ROOT / "submodules.toml")
    dependencies = manifest.get("dependencies", {})
    records = policy.get("submodules", {})

    if not isinstance(dependencies, dict):
        raise ValueError(".zpkg.toml [dependencies] must be a table")
    if not isinstance(records, dict):
        raise ValueError("submodules.toml [submodules] must be a table")

    errors: list[str] = []
    paths = gitmodules()

    missing = sorted(set(paths) - set(records))
    extra = sorted(set(records) - set(paths))
    errors.extend(f"unclassified .gitmodules path: {path}" for path in missing)
    errors.extend(f"policy path is not a git submodule: {path}" for path in extra)

    for dependency in dependencies:
        package = dependency.lower().split("/", 1)[-1]
        if package.endswith("-infra") or package.endswith("-cli"):
            errors.append(f"forbidden monorepo Zed dependency: {dependency}")

    for path, record in records.items():
        if not isinstance(record, dict):
            errors.append(f"{path}: classification must be a table")
            continue
        role = record.get("role")
        package = record.get("package")
        if role not in ALLOWED:
            errors.append(f"{path}: invalid role {role!r}")
            continue
        if role == "reusable":
            if not isinstance(package, str) or not package:
                errors.append(f"{path}: reusable submodule has no package")
            elif package not in dependencies:
                errors.append(
                    f"{path}: reusable package {package} is absent from dependencies"
                )
        elif role in {"tooling", "operations"}:
            if isinstance(package, str) and package in dependencies:
                errors.append(
                    f"{path}: {role} package {package} must not be a dependency"
                )

    reusable_packages = {
        record.get("package")
        for record in records.values()
        if isinstance(record, dict) and record.get("role") == "reusable"
    }
    for dependency in dependencies:
        if dependency not in reusable_packages:
            errors.append(
                f"dependency {dependency} has no reusable submodule classification"
            )

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        f"validated {len(paths)} submodules and "
        f"{len(dependencies)} reusable Zed dependencies"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
