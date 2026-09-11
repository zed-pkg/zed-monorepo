#!/usr/bin/env python3
"""Read-only audit of the clients/interfaces/lib/CLI/monorepo Zed pattern."""

from __future__ import annotations

import argparse
import base64
import dataclasses
import fnmatch
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

ROLE_SUFFIXES = (
    ("-interfaces", "interfaces"),
    ("-monorepo", "monorepo"),
    ("-clients", "clients"),
    ("-infra", "infra"),
    ("-libs", "lib"),
    ("-lib", "lib"),
    ("-cli", "cli"),
)
REQUIRED = {
    "c": ("c",),
    "cpp": ("cpp", "c++"),
    "zig": ("zig",),
    "gleam": ("gleam", "gleamlang"),
    "erlang": ("erlang",),
    "elixir": ("elixir",),
    "dart": ("dart",),
    "rust": ("rust",),
    "java": ("java",),
    "golang": ("golang", "go"),
    "python": ("python", "python3"),
    "ruby": ("ruby",),
    "php": ("php",),
    "nodejs": ("nodejs", "typescript", "node", "ts"),
}
MOBILE = {"kotlin": ("kotlin",), "swift": ("swift",)}
MARKERS = {
    "c": ("CMakeLists.txt", "meson.build", "Makefile", "*.h"),
    "cpp": ("CMakeLists.txt", "meson.build", "Makefile", "*.hpp", "*.hh"),
    "zig": ("build.zig",),
    "gleam": ("gleam.toml",),
    "erlang": ("rebar.config",),
    "elixir": ("mix.exs",),
    "dart": ("pubspec.yaml",),
    "rust": ("Cargo.toml",),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "golang": ("go.mod",),
    "python": ("pyproject.toml", "setup.py", "setup.cfg"),
    "ruby": ("*.gemspec",),
    "php": ("composer.json",),
    "nodejs": ("package.json", "tsconfig.json"),
    "kotlin": ("build.gradle", "build.gradle.kts"),
    "swift": ("Package.swift",),
}
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".h", ".hpp", ".zig", ".gleam", ".erl", ".ex",
    ".dart", ".rs", ".java", ".go", ".py", ".rb", ".php", ".ts", ".kt",
    ".swift",
}
SUBMODULE_ROLES = {
    "reusable", "application", "test", "documentation", "website", "tooling",
    "operations",
}
MOBILE_RE = re.compile(
    r"(?:^|[-_.])(android|ios|mobile|flutter|swift|kotlin)(?:$|[-_.])",
    re.I,
)


@dataclasses.dataclass
class Project:
    org: str
    prefix: str
    repos: dict[str, str]
    mobile: bool = False


@dataclasses.dataclass(frozen=True)
class Finding:
    severity: str
    org: str
    project: str
    code: str
    message: str
    repo: str | None = None


class GitHub:
    def __init__(self, token: str, api_url: str) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.cache: dict[str, Any] = {}

    def get(self, path: str) -> Any:
        url = path if path.startswith("http") else self.api_url + path
        if url in self.cache:
            return self.cache[url]
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "zed-org-pattern-audit/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                value = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"GitHub API {exc.code}: {url}: {detail}") from exc
        self.cache[url] = value
        return value

    def repos(self, org: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            encoded = urllib.parse.quote(org, safe="")
            chunk = self.get(
                f"/orgs/{encoded}/repos?type=all&per_page=100&page={page}"
            )
            if not isinstance(chunk, list):
                raise RuntimeError(f"unexpected repository response for {org}")
            result.extend(repo for repo in chunk if not repo.get("archived"))
            if len(chunk) < 100:
                return result
            page += 1

    def file(self, org: str, repo: str, path: str) -> bytes | None:
        path = "/".join(
            urllib.parse.quote(part, safe="") for part in PurePosixPath(path).parts
        )
        endpoint = (
            f"/repos/{urllib.parse.quote(org, safe='')}/"
            f"{urllib.parse.quote(repo, safe='')}/contents/{path}"
        )
        try:
            value = self.get(endpoint)
        except FileNotFoundError:
            return None
        if not isinstance(value, dict) or value.get("type") != "file":
            return None
        return base64.b64decode(value["content"])

    def directory(self, org: str, repo: str, path: str) -> list[dict[str, Any]] | None:
        path = "/".join(
            urllib.parse.quote(part, safe="") for part in PurePosixPath(path).parts
        )
        endpoint = (
            f"/repos/{urllib.parse.quote(org, safe='')}/"
            f"{urllib.parse.quote(repo, safe='')}/contents/{path}"
        )
        try:
            value = self.get(endpoint)
        except FileNotFoundError:
            return None
        return value if isinstance(value, list) else None


def repo_role(name: str) -> tuple[str, str] | None:
    for suffix, role in ROLE_SUFFIXES:
        if name.lower().endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)], role
    return None


def discover(org: str, repos: Sequence[Mapping[str, Any]]) -> list[Project]:
    groups: dict[str, Project] = {}
    names = [str(repo["name"]) for repo in repos if repo.get("name")]
    for name in names:
        item = repo_role(name)
        if not item:
            continue
        prefix, role = item
        key = prefix.lower()
        groups.setdefault(key, Project(org, prefix, {})).repos[role] = name
    mobile = any(MOBILE_RE.search(name) for name in names)
    return [
        dataclasses.replace(project, mobile=mobile)
        for project in groups.values()
        if {"interfaces", "clients", "monorepo"} & project.repos.keys()
    ]


def apply_overrides(
    projects: list[Project], org: str, entries: Iterable[Mapping[str, Any]]
) -> None:
    for entry in entries:
        if entry.get("org") != org:
            continue
        prefix = str(entry["prefix"])
        project = next(
            (item for item in projects if item.prefix.lower() == prefix.lower()),
            None,
        )
        if project is None:
            project = Project(org, prefix, {})
            projects.append(project)
        for role in ("interfaces", "lib", "clients", "cli", "monorepo", "infra"):
            value = entry.get(role)
            if isinstance(value, str) and value:
                project.repos[role] = value
        if "mobile" in entry:
            project.mobile = bool(entry["mobile"])


def parse_toml(raw: bytes | None, label: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return tomllib.loads(raw.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{label}: {exc}") from exc


def deps(manifest: Mapping[str, Any]) -> set[str]:
    value = manifest.get("dependencies", {})
    return set(value) if isinstance(value, dict) else set()


def target(
    targets: Mapping[str, Any], aliases: Iterable[str]
) -> tuple[str, Mapping[str, Any]] | None:
    keys = {str(key).lower(): key for key in targets}
    for alias in aliases:
        if alias.lower() in keys:
            key = keys[alias.lower()]
            value = targets[key]
            return str(key), value if isinstance(value, dict) else {}
    return None


def covers(org: str, keys: set[str], repo: str, package_prefix: str | None = None) -> bool:
    candidates = [
        key.lower() for key in keys if key.lower().startswith(f"{org}/".lower())
    ]
    exact = f"{org}/{repo}".lower()
    if exact in candidates:
        return True
    if package_prefix and any(
        key.startswith(f"{org}/{package_prefix}".lower()) for key in candidates
    ):
        return True
    return any(key.split("/", 1)[-1].startswith(repo.lower()) for key in candidates)


def gitmodule_paths(raw: bytes | None) -> list[str]:
    if raw is None:
        return []
    return [
        match.group(1)
        for line in raw.decode(errors="replace").splitlines()
        if (match := re.match(r"\s*path\s*=\s*(.+?)\s*$", line))
    ]


class Audit:
    def __init__(self, api: GitHub) -> None:
        self.api = api
        self.findings: list[Finding] = []
        self.manifests: dict[tuple[str, str], dict[str, Any] | None] = {}

    def add(
        self, severity: str, project: Project, code: str, message: str,
        repo: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(severity, project.org, project.prefix, code, message, repo)
        )

    def manifest(self, project: Project, repo: str) -> dict[str, Any] | None:
        key = (project.org, repo)
        if key in self.manifests:
            return self.manifests[key]
        try:
            value = parse_toml(
                self.api.file(project.org, repo, ".zpkg.toml"),
                f"{project.org}/{repo}/.zpkg.toml",
            )
        except ValueError as exc:
            self.add("error", project, "INVALID_ZPKG_TOML", str(exc), repo)
            value = None
        self.manifests[key] = value
        if value is None:
            self.add(
                "error", project, "MISSING_ZPKG_MANIFEST",
                "repository has no valid root .zpkg.toml", repo,
            )
        elif self.api.file(project.org, repo, ".zpkg.lock") is None:
            self.add(
                "warning", project, "MISSING_ZPKG_LOCK",
                "checked-in .zpkg.lock is missing", repo,
            )
        return value

    def run_project(self, project: Project) -> None:
        if "interfaces" not in project.repos:
            self.add("error", project, "MISSING_INTERFACES_REPO", "no *-interfaces repo")
        if "clients" not in project.repos:
            self.add("error", project, "MISSING_CLIENTS_REPO", "no *-clients repo")
        if "lib" not in project.repos:
            self.add(
                "warning", project, "MISSING_LIB_REPO",
                "no *-lib repo; create it or record a deliberate exception",
            )

        manifests = {
            role: self.manifest(project, repo)
            for role, repo in project.repos.items()
            if role in {"interfaces", "lib", "clients", "cli", "monorepo"}
        }
        if manifests.get("clients"):
            self.clients(project, manifests["clients"])
        if manifests.get("cli"):
            self.cli(project, manifests["cli"], manifests.get("clients"))
        if manifests.get("monorepo"):
            self.monorepo(project, manifests["monorepo"])

    def clients(self, project: Project, manifest: Mapping[str, Any]) -> None:
        repo = project.repos["clients"]
        keys = deps(manifest)
        for role in ("interfaces", "lib"):
            expected = project.repos.get(role)
            if expected and not covers(project.org, keys, expected):
                self.add(
                    "error", project, f"CLIENTS_MISSING_{role.upper()}_DEPENDENCY",
                    f"clients does not depend on {project.org}/{expected}", repo,
                )
        targets = manifest.get("targets", {})
        if not isinstance(targets, dict):
            self.add("error", project, "CLIENTS_MISSING_TARGETS", "no targets", repo)
            return
        required = dict(REQUIRED)
        if project.mobile:
            required.update(MOBILE)
        for canonical, aliases in required.items():
            found = target(targets, aliases)
            if found is None:
                self.add(
                    "error", project, "CLIENT_TARGET_MISSING",
                    f"required target {canonical} is not declared", repo,
                )
                continue
            name, table = found
            directory = table.get("dir")
            if not isinstance(directory, str) or not directory:
                self.add(
                    "error", project, "CLIENT_TARGET_DIR_MISSING",
                    f"target {name} has no dir", repo,
                )
                continue
            entries = self.api.directory(project.org, repo, directory)
            if entries is None:
                self.add(
                    "error", project, "CLIENT_TARGET_DIR_NOT_FOUND",
                    f"{name} points at missing {directory}", repo,
                )
                continue
            names = [str(item.get("name", "")) for item in entries]
            if not any(
                fnmatch.fnmatch(filename, pattern)
                for filename in names
                for pattern in MARKERS[canonical]
            ):
                self.add(
                    "error", project, "CLIENT_MARKER_MISSING",
                    f"{directory} lacks a native package/build marker", repo,
                )
            source_here = any(
                item.get("type") == "file"
                and PurePosixPath(str(item.get("name", ""))).suffix.lower()
                in SOURCE_SUFFIXES
                for item in entries
            )
            source_dir = any(
                item.get("type") == "dir"
                and str(item.get("name", "")).lower()
                in {"src", "lib", "sources", "include"}
                for item in entries
            )
            if not (source_here or source_dir):
                self.add(
                    "error", project, "CLIENT_IMPLEMENTATION_MISSING",
                    f"{directory} has no visible implementation source", repo,
                )
            if canonical == "nodejs":
                self.typescript_matrix(project, repo, directory)

    def typescript_matrix(self, project: Project, repo: str, directory: str) -> None:
        raw = self.api.file(
            project.org, repo, f"{directory.rstrip('/')}/runtime-matrix.json"
        )
        if raw is None:
            self.add(
                "error", project, "TYPESCRIPT_RUNTIME_MATRIX",
                "runtime-matrix.json is missing", repo,
            )
            return
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.add(
                "error", project, "TYPESCRIPT_RUNTIME_MATRIX",
                f"invalid runtime matrix: {exc}", repo,
            )
            return
        runtimes = value.get("runtimes", {}) if isinstance(value, dict) else {}
        for runtime in ("node", "deno", "bun", "edge"):
            record = runtimes.get(runtime) if isinstance(runtimes, dict) else None
            if (
                not isinstance(record, dict)
                or record.get("supported") is not True
                or not str(record.get("ci", "")).strip()
            ):
                self.add(
                    "error", project, "TYPESCRIPT_RUNTIME_MISSING",
                    f"{runtime} is not supported with a CI command", repo,
                )

    def cli(
        self, project: Project, manifest: Mapping[str, Any],
        clients_manifest: Mapping[str, Any] | None,
    ) -> None:
        repo = project.repos["cli"]
        keys = deps(manifest)
        for role in ("interfaces", "lib"):
            expected = project.repos.get(role)
            if expected and not covers(project.org, keys, expected):
                self.add(
                    "error", project, f"CLI_MISSING_{role.upper()}_DEPENDENCY",
                    f"CLI does not depend on {project.org}/{expected}", repo,
                )
        clients_repo = project.repos.get("clients")
        package = None
        if clients_manifest:
            table = clients_manifest.get("package", {})
            package = table.get("name") if isinstance(table, dict) else None
        if clients_repo and not covers(project.org, keys, clients_repo, package):
            self.add(
                "error", project, "CLI_MISSING_CLIENTS_DEPENDENCY",
                "CLI does not depend on the clients package/target", repo,
            )

    def monorepo(self, project: Project, manifest: Mapping[str, Any]) -> None:
        repo = project.repos["monorepo"]
        keys = deps(manifest)
        forbidden = {
            project.repos[role].lower()
            for role in ("infra", "cli")
            if role in project.repos
        }
        for key in keys:
            package = key.lower().split("/", 1)[-1]
            if package.endswith("-infra") or package.endswith("-cli") or package in forbidden:
                self.add(
                    "error", project, "MONOREPO_FORBIDDEN_DEPENDENCY",
                    f"monorepo imports forbidden package {key}", repo,
                )
        for role in ("interfaces", "lib", "clients"):
            expected = project.repos.get(role)
            if expected and not covers(project.org, keys, expected):
                self.add(
                    "error", project, "MONOREPO_MISSING_REUSABLE_DEPENDENCY",
                    f"monorepo does not import reusable package from {expected}", repo,
                )

        paths = gitmodule_paths(self.api.file(project.org, repo, ".gitmodules"))
        if not paths:
            self.add(
                "warning", project, "MONOREPO_NO_SUBMODULES",
                "no .gitmodules paths found", repo,
            )
            return
        try:
            policy = parse_toml(
                self.api.file(project.org, repo, "submodules.toml"),
                f"{project.org}/{repo}/submodules.toml",
            )
        except ValueError as exc:
            self.add("error", project, "INVALID_SUBMODULE_POLICY", str(exc), repo)
            return
        if policy is None:
            self.add(
                "error", project, "MISSING_SUBMODULE_POLICY",
                "submodules.toml is required", repo,
            )
            return
        records = policy.get("submodules", {})
        if not isinstance(records, dict):
            self.add(
                "error", project, "INVALID_SUBMODULE_POLICY",
                "no [submodules.*] tables", repo,
            )
            return
        for path in paths:
            record = records.get(path)
            if not isinstance(record, dict):
                self.add(
                    "error", project, "UNCLASSIFIED_SUBMODULE",
                    f"{path} is not classified", repo,
                )
                continue
            role = record.get("role")
            package = record.get("package")
            if role not in SUBMODULE_ROLES:
                self.add(
                    "error", project, "INVALID_SUBMODULE_ROLE",
                    f"{path} has invalid role {role!r}", repo,
                )
            elif role == "reusable" and package not in keys:
                self.add(
                    "error", project, "REUSABLE_SUBMODULE_NOT_DEPENDENCY",
                    f"{path} package is absent from dependencies", repo,
                )
            elif role in {"tooling", "operations"} and package in keys:
                self.add(
                    "error", project, "NONREUSABLE_SUBMODULE_IMPORTED",
                    f"{path} is {role} but is imported", repo,
                )


def markdown(findings: Sequence[Finding], count: int) -> str:
    totals = defaultdict(int)
    for item in findings:
        totals[item.severity] += 1
    lines = [
        "# Organization package-pattern audit", "",
        f"Projects: **{count}**  ",
        f"Errors: **{totals['error']}** · Warnings: **{totals['warning']}**", "",
    ]
    if not findings:
        return "\n".join(lines + ["No findings.", ""])
    lines += [
        "| Severity | Organization/project | Repository | Code | Finding |",
        "| --- | --- | --- | --- | --- |",
    ]
    order = {"error": 0, "warning": 1}
    for item in sorted(
        findings,
        key=lambda value: (
            order.get(value.severity, 9), value.org.lower(),
            value.project.lower(), value.code,
        ),
    ):
        message = item.message.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item.severity.upper()} | `{item.org}/{item.project}` | "
            f"`{item.repo or '—'}` | `{item.code}` | {message} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", action="append", default=[])
    parser.add_argument("--config")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output")
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument(
        "--api-url", default=os.getenv("GITHUB_API_URL", "https://api.github.com")
    )
    parser.add_argument(
        "--fail-on", choices=("error", "warning", "never"), default="error"
    )
    args = parser.parse_args(argv)

    config: dict[str, Any] = {}
    if args.config:
        with open(args.config, "rb") as handle:
            config = tomllib.load(handle)
    orgs = list(dict.fromkeys([*config.get("orgs", []), *args.org]))
    if not orgs:
        parser.error("provide --org or --config with orgs")
    token = os.getenv(args.token_env)
    if not token:
        parser.error(f"{args.token_env} is not set")

    patterns = [
        re.compile(str(value), re.I)
        for value in config.get("exclude_org_regex", [r"-test$"])
    ]
    overrides = config.get("overrides", [])
    api = GitHub(token, args.api_url)
    audit = Audit(api)
    count = 0

    for org in orgs:
        if any(pattern.search(org) for pattern in patterns):
            continue
        try:
            projects = discover(org, api.repos(org))
            apply_overrides(projects, org, overrides)
            for project in sorted(projects, key=lambda item: item.prefix.lower()):
                count += 1
                audit.run_project(project)
        except RuntimeError as exc:
            audit.findings.append(
                Finding("error", org, "—", "ORG_READ_FAILED", str(exc))
            )

    if args.format == "json":
        output = json.dumps(
            {
                "projects": count,
                "findings": [dataclasses.asdict(item) for item in audit.findings],
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
    else:
        output = markdown(audit.findings, count)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        sys.stdout.write(output)

    severities = {item.severity for item in audit.findings}
    if args.fail_on == "error" and "error" in severities:
        return 1
    if args.fail_on == "warning" and severities & {"error", "warning"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
