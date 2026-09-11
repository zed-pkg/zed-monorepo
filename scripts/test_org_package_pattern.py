#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("audit_org_package_pattern.py")
SPEC = importlib.util.spec_from_file_location("audit_org_package_pattern", MODULE_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class DetectionTests(unittest.TestCase):
    def test_role_suffixes(self) -> None:
        self.assertEqual(
            AUDIT.repo_role("zed-interfaces"),
            ("zed", "interfaces"),
        )
        self.assertEqual(AUDIT.repo_role("apme-libs"), ("apme", "lib"))
        self.assertIsNone(AUDIT.repo_role("plain-library"))

    def test_detects_applicable_prefix(self) -> None:
        projects = AUDIT.discover(
            "example",
            [
                {"name": "demo-interfaces"},
                {"name": "demo-monorepo"},
                {"name": "demo-api-server.rs"},
            ],
        )
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].prefix, "demo")
        self.assertEqual(projects[0].repos["interfaces"], "demo-interfaces")

    def test_target_alias(self) -> None:
        key, table = AUDIT.target(
            {"golang": {"dir": "clients/go"}},
            ("go", "golang"),
        )
        self.assertEqual(key, "golang")
        self.assertEqual(table["dir"], "clients/go")


class ParsingTests(unittest.TestCase):
    def test_gitmodule_paths(self) -> None:
        raw = b'''\n[submodule "apps/a"]\n  path = apps/a\n  url = x\n[submodule "apps/b"]\n  path = apps/b\n  url = y\n'''
        self.assertEqual(AUDIT.gitmodule_paths(raw), ["apps/a", "apps/b"])

    def test_runtime_claim_shape(self) -> None:
        matrix = {
            "runtimes": {
                name: {"supported": True, "ci": f"test:{name}"}
                for name in ("node", "deno", "bun", "edge")
            }
        }
        self.assertEqual(set(json.loads(json.dumps(matrix))["runtimes"]), {
            "node", "deno", "bun", "edge"
        })


if __name__ == "__main__":
    unittest.main()
