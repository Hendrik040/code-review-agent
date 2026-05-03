"""Build a code-review fixture from a real GitHub PR.

Fetches the PR's base + head SHAs and the changed files at each SHA,
writes them under tests/fixtures/<name>/v1/ (base) and /v2/ (head)
preserving paths, plus a README.md with provenance.

Usage:
    uv run python scripts/build_pr_fixture.py getsentry/sentry 80168
    uv run python scripts/build_pr_fixture.py getsentry/sentry 80168 abc_subclass_pass

The auto-name is `<repo>_<pr>` (here: `sentry_80168`). Files newly
added in the PR are skipped at v1; files deleted are skipped at v2.

Once built, register the fixture by editing shared/fixtures.py to add
its `Fixture(name=..., expected=...)` entry.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = PROJECT_ROOT / "tests" / "fixtures"


def _gh_json(endpoint: str) -> Any:
    """Invoke `gh api <endpoint>` and parse stdout as JSON."""
    out = subprocess.check_output(["gh", "api", endpoint], text=True)
    return json.loads(out)


def _gh_json_paginated(endpoint: str) -> list[Any]:
    """Invoke `gh api --paginate --slurp <endpoint>` and flatten the
    list-of-pages into a single list. The plain `_gh_json` returns only
    the first page (~30 items by default); large PRs lose files silently.
    """
    out = subprocess.check_output(
        ["gh", "api", "--paginate", "--slurp", endpoint], text=True
    )
    pages = json.loads(out)
    flat: list[Any] = []
    for page in pages:
        flat.extend(page)
    return flat


def _fetch_file(owner: str, repo: str, path: str, ref: str) -> str | None:
    """Return the file's text at `ref`, or None if it doesn't exist there."""
    safe_path = path.replace("#", "%23").replace("?", "%3F")
    try:
        data = _gh_json(f"repos/{owner}/{repo}/contents/{safe_path}?ref={ref}")
    except subprocess.CalledProcessError:
        return None  # 404, etc. — file didn't exist at that ref
    if data.get("type") != "file":
        return None
    encoding = data.get("encoding")
    if encoding != "base64":
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def _write(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build(owner: str, repo: str, pr_number: int, fixture_name: str) -> Path:
    print(f"Fetching {owner}/{repo}#{pr_number} ...")
    pr = _gh_json(f"repos/{owner}/{repo}/pulls/{pr_number}")
    base_sha = pr["base"]["sha"]
    head_sha = pr["head"]["sha"]
    title = pr["title"]
    files = _gh_json_paginated(f"repos/{owner}/{repo}/pulls/{pr_number}/files")

    fixture_dir = FIXTURES_ROOT / fixture_name
    if fixture_dir.exists():
        sys.exit(f"refuse to overwrite: {fixture_dir} already exists")
    (fixture_dir / "v1").mkdir(parents=True)
    (fixture_dir / "v2").mkdir(parents=True)

    print(f"  base: {base_sha[:8]}  head: {head_sha[:8]}  files: {len(files)}")

    skipped_v1: list[str] = []
    skipped_v2: list[str] = []
    file_summary: list[str] = []

    for f in files:
        path = f["filename"]
        status = f.get("status", "modified")
        adds = f.get("additions", 0)
        dels = f.get("deletions", 0)
        file_summary.append(f"  {path}  +{adds} -{dels}  ({status})")

        if status != "added":
            base_text = _fetch_file(owner, repo, path, base_sha)
            if base_text is None:
                skipped_v1.append(path)
            else:
                _write(fixture_dir / "v1" / path, base_text)

        if status != "removed":
            head_text = _fetch_file(owner, repo, path, head_sha)
            if head_text is None:
                skipped_v2.append(path)
            else:
                _write(fixture_dir / "v2" / path, head_text)

    readme = f"""\
# Fixture: {fixture_name}

Built from {owner}/{repo}#{pr_number} via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/{owner}/{repo}/pull/{pr_number}
- **Title**: {title}
- **base sha**: `{base_sha}`
- **head sha**: `{head_sha}`
- **files** ({len(files)}):
{chr(10).join(file_summary)}

## Layout

- `v1/` — files at `base_sha` (the bug-free state for this PR's purposes;
  in reality the bug is INTRODUCED at head_sha for some PRs and FIXED at
  head_sha for others — read the headline bug from the fixture's expected
  Finding to know which).
- `v2/` — files at `head_sha`.

The loader (`shared/fixtures.py:_materialize`) recursively copies these
trees into a temp git repo, commits `v1` then `v2`, returns refs
`HEAD~1..HEAD`.

## License notice

Source code is from {owner}/{repo} and retains its upstream license.
This snapshot is included as a code-review evaluation fixture; not for
redistribution as a product.
"""
    _write(fixture_dir / "README.md", readme)

    print(f"\nWrote fixture to {fixture_dir}")
    if skipped_v1:
        print(f"  v1 skipped (file didn't exist at base): {len(skipped_v1)}")
    if skipped_v2:
        print(f"  v2 skipped (file removed in PR): {len(skipped_v2)}")
    print()
    print("Next steps:")
    print(f"  1. Read the diff: cd {fixture_dir} && diff -ru v1 v2 | less")
    print(f"  2. Add a Fixture(...) entry in shared/fixtures.py with expected findings.")

    return fixture_dir


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(
            "usage: build_pr_fixture.py <owner/repo> <pr_number> [fixture_name]"
        )
    spec = args[0]
    if "/" not in spec:
        sys.exit(f"expected <owner>/<repo>, got {spec!r}")
    owner, repo = spec.split("/", 1)
    try:
        pr_number = int(args[1])
    except ValueError:
        sys.exit(f"PR number must be an integer, got {args[1]!r}")
    fixture_name = args[2] if len(args) >= 3 else f"{repo}_{pr_number}"

    build(owner, repo, pr_number, fixture_name)


if __name__ == "__main__":
    main()
