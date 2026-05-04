"""Derive bug-introducing commits for BugsInPy bugs.

For every projects/<name>/bugs/<n>/ folder under dataset/bugsinpy/, this
script:

  1. parses bug.info (buggy_commit_id, fixed_commit_id) and project.info
     (github_url);
  2. parses bug_patch.txt to get the (file, removed-line-numbers) ranges
     touched by the maintainer's fix — the "oracle" for our scorer;
  3. ensures the upstream repo is cloned locally (partial clone in
     dataset/upstream_clones/);
  4. runs `git blame fixed_commit^ -- <file>` against the buggy lines to
     identify the commit that wrote them: that's the bug-introducing
     commit;
  5. applies filters (≤30 lines / ≤3 files in the fix patch; introducer
     exists; introducer diff is reviewable) and tags each entry with
     source = "blame" | "synthetic_revert" | "skip" + a reason;
  6. writes prepared.json.

Usage:
    uv run python bugsinpy_bench/scripts/prepare_dataset.py
    uv run python bugsinpy_bench/scripts/prepare_dataset.py --sample 30
    uv run python bugsinpy_bench/scripts/prepare_dataset.py --projects pandas,flask

Run from repo root.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# Pinned BugsInPy SHA — bump deliberately when re-vendoring.
BUGSINPY_PIN = "11c5f1eea954a42132cfd06bf257766a7963e0fd"

DATASET = Path("bugsinpy_bench/dataset")
BUGSINPY_DIR = DATASET / "bugsinpy"
CLONES_DIR = DATASET / "upstream_clones"
OUTPUT = DATASET / "prepared.json"

# Filter thresholds: fix-patch shape (small focused fixes only).
MAX_PATCH_FILES = 3
MAX_PATCH_LINES = 30  # added + removed combined

# Filter thresholds: introducing-commit shape. We allow larger commits than
# the fix because real introducers are sometimes refactors of moderate
# size — but if blame lands on a 1000-line refactor, the bug is buried in
# noise and we drop the entry. Bumped from 200→400 lines after the
# 30-bug prototype showed several legitimate introducers landing in the
# 200-300 line range (luigi #1 at 199, scrapy 17/35 at ~253). Real PRs
# routinely run that size; the agent already handles them.
MAX_INTRODUCER_FILES = 8
MAX_INTRODUCER_LINES = 400

# How many distinct commits the blame step is allowed to surface across the
# buggy lines before we declare blame "diffuse" and skip the bug.
MAX_BLAME_FANOUT = 3

# Patch parsing.
_FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_KV = re.compile(r'^(\w+)="?(.*?)"?$')


@dataclass
class OracleRange:
    file: str
    line_start: int
    line_end: int


@dataclass
class PreparedEntry:
    project: str
    bug_id: int
    upstream_repo: str  # e.g. "pandas-dev/pandas"
    github_url: str
    buggy_commit: str
    fixed_commit: str
    oracle: list[OracleRange]
    fix_patch_files: int
    fix_patch_lines: int
    source: str  # "blame" | "synthetic_revert" | "skip"
    skip_reason: Optional[str] = None
    introducing_commit: Optional[str] = None
    introducer_files: Optional[int] = None
    introducer_lines: Optional[int] = None
    introducer_message: Optional[str] = None
    notes: list[str] = field(default_factory=list)


# ---------- Parsing ----------


def _parse_kv_file(path: Path) -> dict[str, str]:
    """Parse a shell-style key=value file (BugsInPy uses these)."""
    out: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KV.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def parse_bug_patch(patch_text: str) -> list[OracleRange]:
    """Return ranges of buggy lines (in the OLD version's line numbering).

    Each hunk has a header `@@ -A,B +C,D @@`; A is the starting line in
    the old (buggy) file. We walk the hunk body, tracking the current
    old-side line number, and emit a range covering the contiguous run
    of `-` lines.
    """
    ranges: list[OracleRange] = []
    cur_file: Optional[str] = None
    old_line = 0
    in_hunk = False
    run_file: Optional[str] = None
    run_start: Optional[int] = None
    run_end: Optional[int] = None

    def _flush():
        nonlocal run_file, run_start, run_end
        if run_file is not None and run_start is not None and run_end is not None:
            ranges.append(OracleRange(file=run_file, line_start=run_start, line_end=run_end))
        run_file = None
        run_start = None
        run_end = None

    for line in patch_text.splitlines():
        m = _FILE_HEADER.match(line)
        if m:
            _flush()
            cur_file = m.group(2)
            in_hunk = False
            continue
        m = _HUNK.match(line)
        if m:
            _flush()
            old_line = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk or cur_file is None:
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and not line.startswith("---"):
            # Remove from old.
            if run_file != cur_file or run_end is None or run_end + 1 != old_line:
                _flush()
                run_file = cur_file
                run_start = old_line
            run_end = old_line
            old_line += 1
        elif line.startswith("+") and not line.startswith("+++"):
            # Pure add — doesn't advance old_line; doesn't extend a removed run.
            _flush()
        else:
            # Context.
            _flush()
            old_line += 1
    _flush()
    return ranges


def patch_size(patch_text: str) -> tuple[int, int]:
    """(files_touched, lines_changed) — sum of additions + deletions."""
    files: set[str] = set()
    changed = 0
    for line in patch_text.splitlines():
        m = _FILE_HEADER.match(line)
        if m:
            files.add(m.group(2))
        elif line.startswith(("+++", "---", "@@")):
            continue
        elif line.startswith(("+", "-")):
            changed += 1
    return len(files), changed


# ---------- Git ----------


def _run(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def repo_slug_from_url(github_url: str) -> str:
    return github_url.rstrip("/").removesuffix(".git").removeprefix("https://github.com/")


def ensure_clone(github_url: str, dest: Path) -> None:
    """Partial-clone (blobless) the upstream repo if not already there."""
    if (dest / ".git").is_dir():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  cloning {github_url} → {dest} (blobless)…", flush=True)
    res = _run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-tags",
            github_url,
            str(dest),
        ],
        timeout=900,
    )
    if res.returncode != 0:
        raise RuntimeError(f"clone failed: {res.stderr.strip()[:300]}")


def commit_exists(repo: Path, sha: str) -> bool:
    res = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo)
    return res.returncode == 0


def resolve_full_sha(repo: Path, ref: str) -> Optional[str]:
    res = _run(["git", "rev-parse", ref], cwd=repo)
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def blame_line(repo: Path, commit: str, file: str, line: int) -> Optional[str]:
    """Return the SHA that wrote `file:line` as of `commit`. None if blame fails."""
    # Bumped from 30s→60s after prototype: pandas/luigi blame on
    # large hot-path files (indexing.py, scheduler.py) can take 30-50s.
    res = _run(
        [
            "git",
            "blame",
            "--porcelain",
            "-L",
            f"{line},{line}",
            commit,
            "--",
            file,
        ],
        cwd=repo,
        timeout=60,
    )
    if res.returncode != 0:
        return None
    first = res.stdout.split("\n", 1)[0].strip()
    if not first:
        return None
    sha = first.split(" ", 1)[0]
    return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else None


def commit_stats(repo: Path, sha: str) -> Optional[tuple[int, int, str]]:
    """Return (files_changed, lines_changed, subject) for the commit."""
    res = _run(
        ["git", "show", "--no-color", "--numstat", "--format=%s", sha],
        cwd=repo,
        timeout=30,
    )
    if res.returncode != 0:
        return None
    lines = res.stdout.splitlines()
    if not lines:
        return None
    subject = lines[0]
    files = 0
    changed = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            files += 1
            changed += int(parts[0]) + int(parts[1])
    return files, changed, subject


# ---------- Pipeline ----------


def process_bug(
    project: str,
    bug_id: int,
    bug_dir: Path,
    project_info: dict[str, str],
    repo_dir: Path,
) -> PreparedEntry:
    bug_info = _parse_bug_info_safe(bug_dir / "bug.info")
    github_url = project_info.get("github_url", "")
    upstream_repo = repo_slug_from_url(github_url)
    fixed_commit = bug_info.get("fixed_commit_id", "")
    buggy_commit = bug_info.get("buggy_commit_id", "")

    base = PreparedEntry(
        project=project,
        bug_id=bug_id,
        upstream_repo=upstream_repo,
        github_url=github_url,
        buggy_commit=buggy_commit,
        fixed_commit=fixed_commit,
        oracle=[],
        fix_patch_files=0,
        fix_patch_lines=0,
        source="skip",
    )

    patch_path = bug_dir / "bug_patch.txt"
    if not patch_path.is_file():
        base.skip_reason = "missing_bug_patch"
        return base
    patch_text = patch_path.read_text(errors="replace")
    base.oracle = parse_bug_patch(patch_text)
    base.fix_patch_files, base.fix_patch_lines = patch_size(patch_text)

    if base.fix_patch_files > MAX_PATCH_FILES or base.fix_patch_lines > MAX_PATCH_LINES:
        base.skip_reason = (
            f"fix_patch_too_large ({base.fix_patch_files}f/{base.fix_patch_lines}l "
            f"> {MAX_PATCH_FILES}f/{MAX_PATCH_LINES}l)"
        )
        return base
    if not base.oracle:
        base.skip_reason = "no_removed_lines (pure-addition fix)"
        return base
    if not fixed_commit:
        base.skip_reason = "missing_fixed_commit"
        return base
    if not commit_exists(repo_dir, fixed_commit):
        base.skip_reason = "fixed_commit_missing_upstream"
        return base

    # Blame each oracle line in the file's pre-fix state.
    introducer_candidates: Counter[str] = Counter()
    blame_failed = False
    for rng in base.oracle:
        for line in range(rng.line_start, rng.line_end + 1):
            sha = blame_line(repo_dir, f"{fixed_commit}^", rng.file, line)
            if not sha:
                blame_failed = True
                break
            introducer_candidates[sha] += 1
        if blame_failed:
            break

    if blame_failed:
        base.notes.append("blame_failed_on_one_or_more_lines")
        base.source = "synthetic_revert"
        base.skip_reason = None
        return base
    if not introducer_candidates:
        base.source = "synthetic_revert"
        base.skip_reason = None
        base.notes.append("no_blame_candidates")
        return base
    if len(introducer_candidates) > MAX_BLAME_FANOUT:
        base.source = "synthetic_revert"
        base.skip_reason = None
        base.notes.append(f"blame_diffuse ({len(introducer_candidates)} commits)")
        return base

    # Pick the most-common; tie-break by latest commit (we use a fast
    # commit-date proxy: the first one returned by `rev-list` order).
    introducer = introducer_candidates.most_common(1)[0][0]
    stats = commit_stats(repo_dir, introducer)
    if stats is None:
        base.source = "synthetic_revert"
        base.notes.append("introducer_stats_failed")
        return base
    files, changed, subject = stats
    base.introducing_commit = introducer
    base.introducer_files = files
    base.introducer_lines = changed
    base.introducer_message = subject

    if files > MAX_INTRODUCER_FILES or changed > MAX_INTRODUCER_LINES:
        base.source = "synthetic_revert"
        base.notes.append(
            f"introducer_too_large ({files}f/{changed}l > {MAX_INTRODUCER_FILES}f/{MAX_INTRODUCER_LINES}l)"
        )
        return base

    # The introducer's diff must include every oracle file. Without this
    # check, a multi-file oracle can pick an introducer that only touches
    # one of them — leaving the agent reviewing a diff that doesn't even
    # contain the buggy code (caught during pilot on pandas#134, where
    # blame settled on a CI commit that touched a tests file but not the
    # actually-buggy holiday.py). When this fails, fall back to
    # synthetic_revert: the buggy file IS in that diff by construction.
    files_in_introducer = _files_in_commit(repo_dir, introducer)
    oracle_files = {r.file for r in base.oracle}
    missing = oracle_files - files_in_introducer
    if missing:
        base.source = "synthetic_revert"
        base.notes.append(
            f"introducer_missing_oracle_files ({sorted(missing)[:3]})"
        )
        return base

    base.source = "blame"
    return base


def _files_in_commit(repo: Path, sha: str) -> set[str]:
    """Return the set of file paths the given commit touched."""
    res = _run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=repo,
        timeout=30,
    )
    if res.returncode != 0:
        return set()
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


def _parse_bug_info_safe(path: Path) -> dict[str, str]:
    try:
        return _parse_kv_file(path)
    except Exception:
        return {}


# ---------- CLI ----------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0,
                    help="If >0, randomly sample N bugs (deterministic via --seed).")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--projects", type=str, default="",
                    help="Comma-separated project filter (e.g., pandas,flask).")
    ap.add_argument("--output", type=str, default=str(OUTPUT))
    args = ap.parse_args()

    if not BUGSINPY_DIR.is_dir():
        sys.exit(f"BugsInPy not found at {BUGSINPY_DIR}; clone first.")

    # Discover bugs.
    project_filter = {p.strip() for p in args.projects.split(",") if p.strip()}
    bugs: list[tuple[str, int, Path]] = []
    project_infos: dict[str, dict[str, str]] = {}
    for project_dir in sorted((BUGSINPY_DIR / "projects").iterdir()):
        if not project_dir.is_dir():
            continue
        if project_filter and project_dir.name not in project_filter:
            continue
        info_path = project_dir / "project.info"
        if not info_path.is_file():
            continue
        project_infos[project_dir.name] = _parse_bug_info_safe(info_path)
        bugs_dir = project_dir / "bugs"
        if not bugs_dir.is_dir():
            continue
        for bd in sorted(bugs_dir.iterdir()):
            if bd.is_dir() and bd.name.isdigit():
                bugs.append((project_dir.name, int(bd.name), bd))

    if args.sample and args.sample < len(bugs):
        rng = random.Random(args.seed)
        bugs = rng.sample(bugs, args.sample)

    print(f"Processing {len(bugs)} bug(s) across {len(project_infos)} project(s)…")

    # Group bugs by project so we can clone once per project.
    by_project: dict[str, list[tuple[int, Path]]] = {}
    for project, bug_id, bug_dir in bugs:
        by_project.setdefault(project, []).append((bug_id, bug_dir))

    entries: list[PreparedEntry] = []
    t0 = time.time()
    for project, items in by_project.items():
        info = project_infos.get(project, {})
        github_url = info.get("github_url", "")
        if not github_url:
            print(f"  [{project}] no github_url, skipping {len(items)} bug(s)")
            for bug_id, _ in items:
                entries.append(PreparedEntry(
                    project=project, bug_id=bug_id, upstream_repo="",
                    github_url="", buggy_commit="", fixed_commit="",
                    oracle=[], fix_patch_files=0, fix_patch_lines=0,
                    source="skip", skip_reason="missing_github_url",
                ))
            continue

        repo_dir = CLONES_DIR / project
        try:
            ensure_clone(github_url, repo_dir)
        except Exception as exc:
            print(f"  [{project}] clone failed: {exc}", flush=True)
            for bug_id, _ in items:
                entries.append(PreparedEntry(
                    project=project, bug_id=bug_id, upstream_repo=repo_slug_from_url(github_url),
                    github_url=github_url, buggy_commit="", fixed_commit="",
                    oracle=[], fix_patch_files=0, fix_patch_lines=0,
                    source="skip", skip_reason=f"clone_failed: {exc!s}"[:200],
                ))
            continue

        for bug_id, bug_dir in items:
            try:
                entry = process_bug(project, bug_id, bug_dir, info, repo_dir)
            except Exception as exc:
                entry = PreparedEntry(
                    project=project, bug_id=bug_id,
                    upstream_repo=repo_slug_from_url(github_url),
                    github_url=github_url, buggy_commit="", fixed_commit="",
                    oracle=[], fix_patch_files=0, fix_patch_lines=0,
                    source="skip", skip_reason=f"exception: {exc!s}"[:200],
                )
            entries.append(entry)

    elapsed = time.time() - t0
    print(f"\nProcessed {len(entries)} bugs in {elapsed:.1f}s")

    # Stats.
    by_source: Counter[str] = Counter(e.source for e in entries)
    by_skip: Counter[str] = Counter(e.skip_reason or "" for e in entries if e.source == "skip")
    print(f"  by source: {dict(by_source)}")
    print(f"  blame yield: {by_source['blame']}/{len(entries)} ({100*by_source['blame']/max(1,len(entries)):.0f}%)")
    if by_skip:
        print("  skip reasons:")
        for reason, n in by_skip.most_common():
            print(f"    {n:>4}  {reason}")

    # Write JSON.
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        [{**asdict(e), "oracle": [asdict(o) for o in e.oracle]} for e in entries],
        indent=2,
    ))
    print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
