"""One-off survey: BugsInPy patch sizes by project.

Reads every projects/<name>/bugs/<n>/bug_patch.txt under
dataset/bugsinpy/ and prints:

  1. Per-project bug count + patch-size distribution
  2. Global histogram of (files_touched, lines_changed)
  3. Yield estimate at the ≤3-files / ≤30-lines filter we plan to use
     in prepare_dataset.py

Usage:
    uv run python bugsinpy_bench/scripts/survey.py

Run from repo root.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

DATASET = Path("bugsinpy_bench/dataset/bugsinpy/projects")

# Filter we plan to apply in prepare_dataset.py.
MAX_FILES = 3
MAX_LINES_CHANGED = 30  # added + removed combined

_FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch_text: str) -> tuple[int, int, int]:
    """Return (files_touched, lines_added, lines_removed)."""
    files: set[str] = set()
    added = 0
    removed = 0
    for line in patch_text.splitlines():
        m = _FILE_HEADER.match(line)
        if m:
            files.add(m.group(2))
            continue
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return len(files), added, removed


def main() -> None:
    if not DATASET.is_dir():
        raise SystemExit(f"BugsInPy not found at {DATASET}; clone first.")

    per_project: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    file_count_hist: Counter[int] = Counter()
    line_count_hist: Counter[int] = Counter()
    parse_errors: list[Path] = []

    for project_dir in sorted(DATASET.iterdir()):
        if not project_dir.is_dir():
            continue
        bugs_dir = project_dir / "bugs"
        if not bugs_dir.is_dir():
            continue
        for bug_dir in sorted(bugs_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
            patch = bug_dir / "bug_patch.txt"
            if not patch.is_file():
                parse_errors.append(patch)
                continue
            try:
                files, added, removed = parse_patch(patch.read_text(errors="replace"))
            except Exception:
                parse_errors.append(patch)
                continue
            per_project[project_dir.name].append((files, added, removed))
            file_count_hist[files] += 1
            line_count_hist[added + removed] += 1

    # Per-project breakdown.
    total = 0
    pass_filter = 0
    rows = []
    for project, entries in sorted(per_project.items(), key=lambda kv: -len(kv[1])):
        n = len(entries)
        total += n
        passing = sum(1 for f, a, r in entries if f <= MAX_FILES and (a + r) <= MAX_LINES_CHANGED)
        pass_filter += passing
        median_files = sorted(e[0] for e in entries)[n // 2]
        median_lines = sorted(e[1] + e[2] for e in entries)[n // 2]
        rows.append((project, n, passing, median_files, median_lines))

    print("Per-project (sorted by total bug count):")
    print(f"  {'project':<14} {'bugs':>5} {'pass_filter':>12}  {'med_files':>9} {'med_lines':>9}")
    for project, n, passing, median_files, median_lines in rows:
        pct = 100.0 * passing / n if n else 0.0
        print(f"  {project:<14} {n:>5} {passing:>6} ({pct:>4.0f}%)  {median_files:>9} {median_lines:>9}")
    print(f"\nTotal bugs: {total}")
    print(f"Pass filter (≤{MAX_FILES} files / ≤{MAX_LINES_CHANGED} lines): {pass_filter} ({100*pass_filter/total:.0f}%)")

    print("\nFiles-touched histogram:")
    for k in sorted(file_count_hist):
        bar = "#" * min(60, file_count_hist[k] // 2)
        print(f"  {k:>3} files  {file_count_hist[k]:>4}  {bar}")

    print("\nLines-changed histogram (binned):")
    bins = [0, 5, 10, 20, 30, 50, 100, 250, 1000, 10**9]
    bin_counts: list[int] = [0] * (len(bins) - 1)
    for lines, count in line_count_hist.items():
        for i in range(len(bins) - 1):
            if bins[i] <= lines < bins[i + 1]:
                bin_counts[i] += count
                break
    for i, c in enumerate(bin_counts):
        label = f"[{bins[i]:>3},{bins[i+1] if bins[i+1] < 10**9 else '∞':>4})"
        bar = "#" * min(60, c // 5)
        print(f"  {label}  {c:>4}  {bar}")

    if parse_errors:
        print(f"\nParse errors: {len(parse_errors)} (skipped):")
        for p in parse_errors[:5]:
            print(f"  {p}")


if __name__ == "__main__":
    main()
