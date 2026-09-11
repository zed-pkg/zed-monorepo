#!/usr/bin/env python3
"""Validate the executable interoperability policy in docs/interop.

This intentionally uses only Python's standard library so documentation CI has
no package-manager bootstrap dependency.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "interop" / "compatibility-matrix.json"
EXPECTED_ADAPTERS = {
    "nix",
    "flox",
    "devbox",
    "mise",
    "asdf",
    "oci-docker",
    "oci-podman",
    "npm",
    "cargo",
}
REQUIRED_FIELDS = {
    "id",
    "class",
    "authority",
    "import_command",
    "export_command",
    "frozen_restore_command",
    "native_lock_required",
    "exact_runtime_required",
    "semver_publication_boundary",
    "platform_identity",
    "platform_in_semver_build_metadata",
    "immutable_output_identity",
    "notes",
}


class PolicyError(AssertionError):
    """Raised when the checked-in interoperability policy drifts."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def require_string(value: Any, field: str) -> str:
    require(isinstance(value, str), f"{field} must be a string")
    require(value == value.strip(), f"{field} must not have surrounding whitespace")
    require(bool(value), f"{field} must not be empty")
    require("\x00" not in value, f"{field} must not contain NUL")
    return value


def load_matrix() -> dict[str, Any]:
    try:
        raw = MATRIX_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PolicyError(f"missing matrix: {MATRIX_PATH}") from error
    require(raw.endswith("\n"), "matrix must end with one newline")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PolicyError(f"invalid JSON: {error}") from error
    require(isinstance(value, dict), "matrix root must be an object")
    canonical = json.dumps(value, indent=2, sort_keys=False) + "\n"
    require(raw == canonical, "matrix JSON must use deterministic two-space formatting")
    return value


def validate_core(matrix: dict[str, Any]) -> None:
    require(matrix.get("schema") == "zed.interop-matrix/v1", "unsupported matrix schema")
    rfc = require_string(matrix.get("rfc"), "rfc")
    rfc_path = (ROOT / rfc).resolve()
    require(rfc_path.is_relative_to(ROOT), "rfc path escapes repository root")
    require(rfc_path.is_file(), f"referenced RFC does not exist: {rfc}")

    invariants = matrix.get("core_invariants")
    require(isinstance(invariants, dict), "core_invariants must be an object")
    expected = {
        "zed_is_package_graph_resolver": True,
        "exact_versions_in_frozen_state": True,
        "build_metadata_is_platform_identity": False,
        "published_version_bytes_are_mutable": False,
        "generated_activation_command": "zed install --frozen",
        "plan_is_credential_free": True,
        "apply_revalidates_plan": True,
    }
    require(invariants == expected, "core interoperability invariants drifted")

    rfc_text = rfc_path.read_text(encoding="utf-8")
    for phrase in (
        "Zed resolves packages",
        "Build metadata is not a platform key",
        "A published `{org, name, version, target}` is immutable",
        "zed install --frozen",
        "FROM scratch",
    ):
        require(phrase in rfc_text, f"RFC lost normative phrase: {phrase!r}")


def validate_adapter(adapter: dict[str, Any], index: int) -> None:
    missing = REQUIRED_FIELDS - adapter.keys()
    require(not missing, f"adapter[{index}] is missing fields: {sorted(missing)}")
    adapter_id = require_string(adapter["id"], f"adapter[{index}].id")
    require(adapter_id in EXPECTED_ADAPTERS, f"unexpected adapter id: {adapter_id}")

    for field in (
        "class",
        "authority",
        "import_command",
        "export_command",
        "frozen_restore_command",
        "platform_identity",
        "immutable_output_identity",
        "notes",
    ):
        require_string(adapter[field], f"{adapter_id}.{field}")

    require(adapter["native_lock_required"] is True, f"{adapter_id} must require native lock state")
    require(
        adapter["platform_in_semver_build_metadata"] is False,
        f"{adapter_id} must keep platform identity outside SemVer build metadata",
    )
    require("latest" not in adapter["export_command"].lower(), f"{adapter_id} export may not emit latest")

    restore = adapter["frozen_restore_command"]
    explicit_restore = (
        "--frozen" in restore
        or adapter_id.startswith("oci-")
        or (adapter_id == "nix" and "--offline" in restore)
    )
    require(explicit_restore, f"{adapter_id} frozen restore must be explicit")

    if adapter_id in {"flox", "devbox"}:
        require(adapter.get("uses_nix") is True, f"{adapter_id} must declare its Nix backing")
        require(adapter["class"] == "nix-wrapper-environment", f"{adapter_id} class drifted")
        require("zed install --frozen" in adapter["frozen_restore_command"],
                f"{adapter_id} must activate the fixed frozen install")

    if adapter_id in {"mise", "asdf"}:
        require(adapter["class"] == "shim-runtime-manager", f"{adapter_id} class drifted")
        require(adapter["exact_runtime_required"] is True, f"{adapter_id} must resolve exact runtimes")
        require(adapter.get("moving_channels_allowed_in_frozen_mode") is False,
                f"{adapter_id} must reject moving channels in frozen mode")

    if adapter_id in {"npm", "cargo"}:
        require(adapter["class"] == "native-registry-publication", f"{adapter_id} class drifted")
        require(adapter["semver_publication_boundary"] is True,
                f"{adapter_id} must declare a SemVer publication boundary")
        require(adapter.get("strict_semver") is True, f"{adapter_id} must require strict SemVer")
        require(adapter.get("same_version_changed_bytes_allowed") is False,
                f"{adapter_id} must reject changed bytes for an existing version")
        require("SHA-256" in adapter["immutable_output_identity"],
                f"{adapter_id} immutable identity must include artifact SHA-256")
        require(adapter["export_command"].endswith(" --plan"),
                f"{adapter_id} publication must expose a credential-free plan")

    if adapter_id.startswith("oci-"):
        require(adapter["class"] == "deployment-transport", f"{adapter_id} class drifted")
        require(adapter.get("scratch_policy") == "verified-static-only",
                f"{adapter_id} scratch policy must fail closed")
        require(adapter.get("canonical_model") == "oci-image-layout/v1",
                f"{adapter_id} must use the canonical OCI image-layout model")
        require("OCI" in adapter["immutable_output_identity"],
                f"{adapter_id} immutable identity must be an OCI digest")


def validate_cross_adapter(adapters: list[dict[str, Any]]) -> None:
    ids = [adapter["id"] for adapter in adapters]
    require(len(ids) == len(set(ids)), "adapter ids must be unique")
    require(set(ids) == EXPECTED_ADAPTERS,
            f"adapter set drifted: missing={sorted(EXPECTED_ADAPTERS - set(ids))}, "
            f"extra={sorted(set(ids) - EXPECTED_ADAPTERS)}")

    commands: dict[str, str] = {}
    for adapter in adapters:
        for field in ("import_command", "export_command"):
            command = adapter[field]
            previous = commands.setdefault(command, adapter["id"])
            require(previous == adapter["id"],
                    f"command {command!r} is shared by {previous} and {adapter['id']}")

    docker = next(item for item in adapters if item["id"] == "oci-docker")
    podman = next(item for item in adapters if item["id"] == "oci-podman")
    require(docker["canonical_model"] == podman["canonical_model"],
            "Docker and Podman must emit the same canonical OCI model")
    require(docker["scratch_policy"] == podman["scratch_policy"],
            "Docker and Podman scratch eligibility must be identical")

    npm = next(item for item in adapters if item["id"] == "npm")
    cargo = next(item for item in adapters if item["id"] == "cargo")
    for field in (
        "semver_publication_boundary",
        "strict_semver",
        "platform_in_semver_build_metadata",
        "same_version_changed_bytes_allowed",
    ):
        require(npm[field] == cargo[field], f"npm/Cargo policy diverged for {field}")


def main() -> int:
    try:
        matrix = load_matrix()
        validate_core(matrix)
        adapters = matrix.get("adapters")
        require(isinstance(adapters, list), "adapters must be an array")
        require(all(isinstance(item, dict) for item in adapters), "every adapter must be an object")
        for index, adapter in enumerate(adapters):
            validate_adapter(adapter, index)
        validate_cross_adapter(adapters)
    except PolicyError as error:
        print(f"interop policy error: {error}", file=sys.stderr)
        return 1

    print(f"validated {len(adapters)} interoperability adapters from {MATRIX_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
