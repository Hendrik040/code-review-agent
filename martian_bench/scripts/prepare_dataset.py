"""Prepare Martian's Sentry-only PR slice for our reviewer.

Reads martian/offline/golden_comments/sentry.json (10 PRs), looks up
each PR's base + head SHAs on the fork org via the gh CLI, and writes
prepared_martian.json — the input file that run_martian.py consumes.

Usage:
    uv run python martian_bench/scripts/prepare_dataset.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDENS_PATH = PROJECT_ROOT / "martian_bench" / "dataset" / "martian" / "offline" / "golden_comments" / "sentry.json"
OUT_PATH = PROJECT_ROOT / "martian_bench" / "dataset" / "prepared_martian.json"


_PR_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")


def main() -> None:
    if not GOLDENS_PATH.is_file():
        sys.exit(f"missing {GOLDENS_PATH}")
    raw = json.loads(GOLDENS_PATH.read_text())
    print(f"Loaded {len(raw)} PR(s) from sentry.json")

    out = []
    for pr in raw:
        url = pr["url"]
        m = _PR_URL_RE.search(url)
        if not m:
            print(f"  skip — bad url: {url}")
            continue
        repo_slug = m.group(1)
        pr_number = int(m.group(2))
        github_url = f"https://github.com/{repo_slug}"
        # Get base + head SHAs via gh
        res = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo_slug,
             "--json", "baseRefOid,headRefOid,title,baseRefName,headRefName"],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            print(f"  ERR  {url}  →  gh failed: {res.stderr.strip()[:100]}")
            continue
        info = json.loads(res.stdout)
        out.append({
            "pr_url": url,
            "pr_number": pr_number,
            "repo_slug": repo_slug,
            "github_url": github_url,
            "original_url": pr.get("original_url", ""),
            "title": pr.get("pr_title", ""),
            "base_sha": info["baseRefOid"],
            "head_sha": info["headRefOid"],
            "base_ref": info.get("baseRefName", ""),
            "head_ref": info.get("headRefName", ""),
            "goldens": pr.get("comments", []),  # [{comment, severity}, ...]
        })
        print(f"  ✓  {repo_slug}#{pr_number}  base={info['baseRefOid'][:8]}  head={info['headRefOid'][:8]}  goldens={len(pr.get('comments', []))}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT_PATH}  ({len(out)} entries)")


if __name__ == "__main__":
    main()
