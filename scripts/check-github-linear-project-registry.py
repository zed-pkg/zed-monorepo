#!/usr/bin/env python3
"""Validate the GitHub organization ↔ Linear ↔ GitHub Project registry."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "github-linear-project-registry.toml"
DOC = ROOT / "docs" / "33-github-linear-project-registry.md"

ALLOWED_PROJECT_STATES = {
    "created",
    "permission-blocked",
    "planned",
    "retired",
}
REQUIRED_ORGS = {"zed-pkg", "zed-pkg-test"}


def fail(message: str) -> None:
    raise SystemExit(f"github-linear-project-registry: {message}")


def safe_https_url(value: str, *, label: str, host: str | None = None) -> None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        fail(f"{label} is not a valid URL")
    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"{label} must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        fail(f"{label} may not contain credentials, query strings, or fragments")
    if host is not None and parsed.hostname != host:
        fail(f"{label} must use host {host}")


def main() -> int:
    data = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("schema") != "zed.github-linear-project-registry/v1":
        fail("unexpected registry schema")

    organizations = data.get("organizations")
    if not isinstance(organizations, dict):
        fail("organizations must be a table")
    if not REQUIRED_ORGS.issubset(organizations):
        fail("required zed-pkg and zed-pkg-test records are missing")

    doc = DOC.read_text(encoding="utf-8")
    project_urls: set[str] = set()
    linear_ids: set[str] = set()

    for org, record in sorted(organizations.items()):
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?", org):
            fail(f"invalid GitHub organization key {org!r}")
        if not isinstance(record, dict):
            fail(f"organization {org} must be a table")

        github_org_url = record.get("github_org_url")
        linear_project_id = record.get("linear_project_id")
        linear_project_name = record.get("linear_project_name")
        linear_project_url = record.get("linear_project_url")
        project_title = record.get("github_project_title")
        project_status = record.get("github_project_status")
        project_number = record.get("github_project_number")
        project_url = record.get("github_project_url")
        installation_id = record.get("github_app_installation_id")
        repositories = record.get("canonical_delivery_repos")

        if github_org_url != f"https://github.com/{org}":
            fail(f"organization {org} has a noncanonical GitHub URL")
        safe_https_url(github_org_url, label=f"{org}.github_org_url", host="github.com")

        if not isinstance(installation_id, int) or installation_id <= 0:
            fail(f"organization {org} needs a positive installation ID")
        if not isinstance(linear_project_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            linear_project_id,
        ):
            fail(f"organization {org} has an invalid Linear project ID")
        if linear_project_id in linear_ids:
            fail(f"Linear project ID is reused by organization {org}")
        linear_ids.add(linear_project_id)

        if linear_project_name != f"github.com/{org}":
            fail(f"organization {org} has a noncanonical Linear project name")
        if not isinstance(linear_project_url, str):
            fail(f"organization {org} is missing its Linear project URL")
        safe_https_url(
            linear_project_url,
            label=f"{org}.linear_project_url",
            host="linear.app",
        )

        if project_title != f"{org}-project":
            fail(f"organization {org} has a noncanonical GitHub Project title")
        if project_status not in ALLOWED_PROJECT_STATES:
            fail(f"organization {org} has an unsupported Project state")
        if not isinstance(project_number, int) or project_number < 0:
            fail(f"organization {org} has an invalid Project number")
        if not isinstance(project_url, str):
            fail(f"organization {org} has a non-string Project URL")

        if project_status == "created":
            if project_number <= 0:
                fail(f"created Project for {org} needs a positive number")
            expected = f"https://github.com/orgs/{org}/projects/{project_number}"
            if project_url != expected:
                fail(f"created Project for {org} has a noncanonical URL")
            safe_https_url(project_url, label=f"{org}.github_project_url", host="github.com")
            if project_url in project_urls:
                fail(f"Project URL is reused by organization {org}")
            project_urls.add(project_url)
        elif project_number != 0 or project_url != "":
            fail(f"uncreated Project for {org} must not claim a number or URL")

        if not isinstance(repositories, list) or not repositories:
            fail(f"organization {org} has no canonical delivery repositories")
        for repository in repositories:
            if not isinstance(repository, str) or "/" not in repository:
                fail(f"organization {org} has an invalid repository entry")
            owner, name = repository.split("/", 1)
            if owner != org and repository != "zed-pkg/zed-docs":
                fail(f"repository {repository} is outside organization {org}")
            if not name or any(character.isspace() for character in name):
                fail(f"organization {org} has an invalid repository name")

        for required_text in (
            github_org_url,
            linear_project_url,
            project_title,
        ):
            if required_text not in doc:
                fail(f"human-readable document omits {required_text}")

    forbidden = ("ghp_", "github_pat_", "token=", "password=", "@github.com:")
    combined = REGISTRY.read_text(encoding="utf-8") + "\n" + doc
    for marker in forbidden:
        if marker in combined:
            fail(f"registry documentation contains forbidden credential marker {marker!r}")

    print(
        f"validated {len(organizations)} GitHub organization project records "
        f"from {REGISTRY.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
