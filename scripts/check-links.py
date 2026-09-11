#!/usr/bin/env python3
"""Verify every cross-repo deep-link in the docs still resolves.

These docs cite exact source files in sibling repos
(`https://github.com/zed-pkg/<repo>/blob/main/<path>`). Code moves — a
function gets absorbed into another module, a script is renamed — and the
citation silently becomes a 404 that only a reader discovers. This resolves
each link against a local checkout instead of the network, so it is fast,
offline, and works the same in CI and on a laptop.

Usage:
    python3 scripts/check-links.py [siblings-root]

`siblings-root` defaults to the parent directory (the standard layout where
every zed-pkg repo is a sibling). Exits non-zero listing any dead links.
"""

import pathlib
import re
import sys

LINK = re.compile(
    r"https://github\.com/zed-pkg/([A-Za-z0-9._-]+)/blob/main/([A-Za-z0-9._/-]+)"
)


def main() -> int:
    docs_root = pathlib.Path(__file__).resolve().parent.parent
    siblings = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else docs_root.parent

    sources = sorted(docs_root.glob("docs/**/*.md")) + [docs_root / "README.md"]
    links: dict[tuple[str, str], set[str]] = {}
    for md in sources:
        if not md.exists():
            continue
        for match in LINK.finditer(md.read_text()):
            key = (match.group(1), match.group(2))
            links.setdefault(key, set()).add(str(md.relative_to(docs_root)))

    # A repo that was not checked out cannot be judged; say so rather than
    # reporting its links as broken.
    skipped = sorted({repo for repo, _ in links if not (siblings / repo).is_dir()})
    broken = [
        (repo, path, sorted(cited))
        for (repo, path), cited in sorted(links.items())
        if (siblings / repo).is_dir() and not (siblings / repo / path).exists()
    ]

    checked = len(links) - sum(1 for repo, _ in links if repo in skipped)
    print(f"checked {checked} cross-repo deep-link(s) against {siblings}")
    for repo in skipped:
        print(f"  note: {repo} not checked out; its links were skipped")
    for repo, path, cited in broken:
        print(f"  BROKEN zed-pkg/{repo}/blob/main/{path}")
        print(f"         cited in: {', '.join(cited)}")

    if broken:
        print(f"\n{len(broken)} dead link(s) — update the citation or the path.")
        return 1
    print("all resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
