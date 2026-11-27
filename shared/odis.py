"""Outside-Diff Impact Slicing (ODIS).

Build a curated review context that includes the diff plus the
unchanged callers and callees that touch it. The intuition: bugs at
the boundary between changed and unchanged code (e.g. a signature
change with un-updated callers) are invisible if you only show the
model the diff. ODIS pulls the one-hop neighbors in.

Ported from `code-review-baseline/ai-code-reviewer/review_demo.py`
(commit a48bca3). Functional behavior is preserved verbatim. The
only changes vs the baseline:

- `build_context(repo_path, base_ref, head_ref)` is the single public
  entry — the baseline hardcoded `HEAD~1` and used cwd.
- Type hints, no-op cosmetic cleanups.
- No OpenAI / model code (that lives in the reviewer modules).
- Returned snippet markup uses ```python``` fences and the same XML
  tags the baseline's prompt expects (<diff>, <file type="changed">,
  <callees>, <callers>) so we can reuse the baseline's prompt v0.

Limits (inherited from baseline, documented in docs/architecture.md):
- Python AST only.
- Local symbol resolution only — no module/qualified-name handling.
- One hop — caller-of-caller is not pulled in.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

# Directories never worth scanning for the call graph.
_EXCLUDE_DIR_PARTS: frozenset[str] = frozenset({
    ".venv", "venv", "env", ".tox", "site-packages", "node_modules",
    "__pycache__", ".git",
})


@dataclass(frozen=True)
class _ChangedSymbol:
    file: str   # relative to repo root
    name: str
    start: int  # line number (1-indexed)
    end: int


# --------------------------------------------------------------------------- #
# Diff parsing
# --------------------------------------------------------------------------- #

def changed_lines(repo: pathlib.Path, base_ref: str, head_ref: str) -> dict[str, set[int]]:
    """Return {file_path: {line_numbers_added_or_modified}} from a git diff.

    Uses `--unified=0` so the line ranges are minimal and exact.
    """
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--unified=0", "--no-color",
         f"{base_ref}..{head_ref}"]
    ).decode()
    current: str | None = None
    changes: dict[str, set[int]] = {}
    for line in diff.splitlines():
        # Reset on each new file in the diff so a deletion or rename
        # doesn't bleed hunks into the previous file's set.
        if line.startswith("diff --git "):
            current = None
        elif line.startswith("+++ "):
            # `+++ b/<path>` for a present file; `+++ /dev/null` for a
            # deletion. Only the former is reportable.
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and current:
            # Hunk header looks like: @@ -old +new,count @@ context.
            # `count == 0` (pure deletion) still anchors at line `start`
            # so callers/callees of removed code stay visible to ODIS.
            plus = next((p for p in line.split() if p.startswith("+")), None)
            if not plus:
                continue
            head = plus[1:]  # drop the leading +
            start_str, _, count_str = head.partition(",")
            start = int(start_str)
            count = int(count_str) if count_str else 1
            if count == 0:
                count = 1
            changes.setdefault(current, set()).update(range(start, start + count))
    return changes


# --------------------------------------------------------------------------- #
# AST scanning
# --------------------------------------------------------------------------- #

def _parse(path: pathlib.Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return None


def symbols_containing_lines(
    path: pathlib.Path, lines: set[int]
) -> list[tuple[str, int, int]]:
    """Functions/classes whose body spans any of the given lines."""
    tree = _parse(path)
    if tree is None:
        return []
    out: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            if any(start <= ln <= end for ln in lines):
                out.append((node.name, start, end))
    return out


def symbols_with_signature_changes(
    path: pathlib.Path, lines: set[int]
) -> set[str]:
    """Symbols whose `def` line itself was touched.

    These are the highest-risk changes: callers may now be passing the
    wrong argument shape. Callers of these are explicitly pulled into
    the impact section by `build_context`.
    """
    tree = _parse(path)
    if tree is None:
        return set()
    changed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno in lines:
                changed.add(node.name)
            # Class signature is also "changed" if __init__ changed.
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "__init__"
                        and item.lineno in lines
                    ):
                        changed.add(node.name)
    return changed


def calls_in_lines(path: pathlib.Path, lines: set[int]) -> set[str]:
    """Names of bare-name calls (`foo(...)`) within the given lines."""
    tree = _parse(path)
    if tree is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and getattr(node, "lineno", None) in lines
        ):
            out.add(node.func.id)
    return out


def callgraph_for_files(files: Iterable[pathlib.Path]) -> dict[str, dict[str, list[str]]]:
    """Cheap call graph: {defs: {file: [names]}, calls: {file: [names]}}.

    Bare-name only — `module.func` and import resolution are out of scope.
    """
    graph: dict[str, dict[str, list[str]]] = {"defs": {}, "calls": {}}
    for f in files:
        tree = _parse(f)
        if tree is None:
            continue
        defs = {
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        calls = {
            n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        key = str(f)
        graph["defs"][key] = sorted(defs)
        graph["calls"][key] = sorted(calls)
    return graph


def one_hop_slice(
    changed_symbols: list[_ChangedSymbol],
    cg: dict[str, dict[str, list[str]]],
) -> list[str]:
    """Files within one hop of the changed symbols (callers + callees)."""
    target_names = {s.name for s in changed_symbols}
    changed_files = {s.file for s in changed_symbols}
    slice_files: set[str] = set()

    # Callers: files (other than changed) that reference a changed symbol.
    for f, calls in cg["calls"].items():
        if f not in changed_files and any(t in calls for t in target_names):
            slice_files.add(f)

    # Callees: files defining what changed code calls.
    calls_from_changed: set[str] = set()
    for f in changed_files:
        calls_from_changed.update(cg["calls"].get(f, []))
    for f, defs in cg["defs"].items():
        if any(call in defs for call in calls_from_changed):
            slice_files.add(f)

    return sorted(slice_files)


# --------------------------------------------------------------------------- #
# Snippet extraction + formatting
# --------------------------------------------------------------------------- #

def snippet(path: pathlib.Path, line: int, pad: int = 5) -> str:
    """Lines around `line` with 1-indexed line-number prefixes.

    Uses errors='replace' so a non-UTF-8 file (rare but possible in
    real repos) doesn't abort the whole review with UnicodeDecodeError.
    """
    try:
        rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    i = max(0, line - pad - 1)
    j = min(len(rows), line + pad)
    return "\n".join(f"{k+1:>4}  {rows[k]}" for k in range(i, j))


def group_consecutive_lines(lines: list[int], gap: int = 5) -> list[list[int]]:
    """Cluster sorted line numbers into runs separated by > gap."""
    if not lines:
        return []
    sorted_lines = sorted(lines)
    chunks: list[list[int]] = [[sorted_lines[0]]]
    for ln in sorted_lines[1:]:
        if ln - chunks[-1][-1] <= gap:
            chunks[-1].append(ln)
        else:
            chunks.append([ln])
    return chunks


@dataclass
class ImpactCandidate:
    """One caller or callee ODIS found by name matching.

    `text` is the snippet exactly as today's context shows it; the other
    fields are what a selector (shared/impact.py) needs to rank it
    without reading the snippet.
    """
    id: str
    role: str                 # "callee" | "caller"
    file: str                 # repo-relative
    line: int                 # def/class line (callee) or call line (caller)
    symbol: str               # name, or "call to <name>" for callers (as today)
    line_text: str            # that source line, stripped
    doc: str                  # first docstring line (callees), else ""
    inside_function: str      # enclosing function (callers), else ""
    same_file_as_change: bool
    imported_by_changed_file: bool
    is_test: bool
    text: str


@dataclass
class Collected:
    diff: str
    changed: list[dict[str, str]]
    candidates: list[ImpactCandidate] = field(default_factory=list)


_CHANGED_OMITTED = (
    "(Omitted to fit the context budget; the diff above shows every changed line.)"
)


def _render_block(out: list[str], items: list[ImpactCandidate],
                  signatures: list[str]) -> None:
    for item in items:
        out.append(f'<file name="{item.file}" symbol="{item.symbol}">')
        out.append("```python")
        out.append(item.text)
        out.append("```")
        out.append("</file>")
    for line in signatures:
        out.append(f"<signature>{line}</signature>")
    if not items and not signatures:
        out.append("None")


def render_markdown(
    c: Collected,
    tiers: dict[str, str] | None = None,
    note: str = "",
    drop_changed: bool = False,
) -> str:
    """Print the context. `tiers=None` means every candidate in full,
    which reproduces the pre-Phase-8 output byte for byte.

    With `tiers`, a candidate absent from the dict is omitted (only
    duplicates are), "full" prints its snippet, "signature" prints one
    line, "counted" prints nothing; `note` follows the callers block.
    """
    def pick(role: str, tier: str) -> list[ImpactCandidate]:
        return [
            x for x in c.candidates
            if x.role == role and (tiers is None if tier == "all" else
                                   tiers is not None and tiers.get(x.id) == tier)
        ]

    out: list[str] = ["# Code Review Context\n"]
    out.append("## 1. Git Diff (What Changed)\n")
    out.append("<diff>")
    out.append(c.diff)
    out.append("</diff>\n")
    out.append("## 2. Changed Code (Modified Files with Context)\n")
    if drop_changed:
        out.append(_CHANGED_OMITTED + "\n")
    else:
        for item in c.changed:
            out.append(f'<file name="{item["file"]}" lines="{item["lines"]}" type="changed">')
            out.append("```python")
            out.append(item["text"])
            out.append("```")
            out.append("</file>\n")
    out.append("## 3. Impact Code (Contracts & Call Sites)\n")
    out.append(
        "### CALLEES: Definitions that the changed code CALLS "
        "(check if changed code respects these contracts)"
    )
    for role, tag in (("callee", "callees"), ("caller", "callers")):
        if role == "caller":
            out.append(
                "### CALLERS: Call sites that invoke the changed functions/classes "
                "(check if callers pass correct arguments)"
            )
        out.append(f"<{tag}>")
        if tiers is None:
            _render_block(out, pick(role, "all"), [])
        else:
            from shared import impact  # sandbox-safe, stdlib only
            _render_block(
                out, pick(role, impact.FULL),
                [impact.signature_line(x) for x in pick(role, impact.SIGNATURE)],
            )
        out.append(f"</{tag}>\n")
    if note:
        out.append(f"<not_shown>{note}</not_shown>\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #

def _walk_repo_python_files(repo: pathlib.Path) -> list[pathlib.Path]:
    return [
        p for p in repo.rglob("*.py")
        if not (set(p.parts) & _EXCLUDE_DIR_PARTS)
    ]


def _is_test_path(rel: str) -> bool:
    parts = pathlib.PurePosixPath(rel).parts
    base = parts[-1] if parts else ""
    return (
        any(p in ("tests", "test") for p in parts[:-1])
        or (base.startswith("test_") and base.endswith(".py"))
        or base.endswith("_test.py")
    )


def _imported_names(paths: Iterable[pathlib.Path]) -> set[str]:
    """Module last-components and names the given files import."""
    names: set[str] = set()
    for p in paths:
        tree = _parse(p)
        if tree is None:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                if n.module:
                    names.add(n.module.split(".")[-1])
                names.update(a.name for a in n.names)
            elif isinstance(n, ast.Import):
                names.update(a.name.split(".")[-1] for a in n.names)
    return names


def _innermost_function(tree: ast.AST, line: int) -> str:
    best: tuple[int, str] | None = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(n, "end_lineno", n.lineno)
            if n.lineno <= line <= end and (best is None or end - n.lineno < best[0]):
                best = (end - n.lineno, n.name)
    return best[1] if best else ""


def _source_line(rows: list[str], line: int) -> str:
    return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def collect(repo: pathlib.Path, base_ref: str, head_ref: str) -> Collected:
    """Everything `build_context` prints, as data. Candidates keep the
    pre-Phase-8 order and duplicates; ids are "c0", "c1", ..."""
    repo = repo.resolve()
    changes = changed_lines(repo, base_ref, head_ref)

    # Identify the symbols whose bodies span the diff lines.
    changed_symbols: list[_ChangedSymbol] = []
    for rel_path, lines in changes.items():
        if not rel_path.endswith(".py"):
            continue
        abs_path = repo / rel_path
        if not abs_path.exists():
            continue
        for name, start, end in symbols_containing_lines(abs_path, lines):
            changed_symbols.append(_ChangedSymbol(
                file=str(abs_path), name=name, start=start, end=end,
            ))

    repo_files = _walk_repo_python_files(repo)
    cg = callgraph_for_files(repo_files)
    impact_files = set(one_hop_slice(changed_symbols, cg))

    # Full unified-3 diff for the prompt.
    diff_text = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--unified=3", "--no-color",
         f"{base_ref}..{head_ref}"]
    ).decode()

    # Snippets of CHANGED code.
    changed_snippets: list[dict[str, str]] = []
    for rel_path, lines in changes.items():
        if not lines:
            continue
        abs_path = repo / rel_path
        for chunk in group_consecutive_lines(list(lines)):
            center = chunk[len(chunk) // 2]
            changed_snippets.append({
                "file": rel_path,
                "lines": f"{chunk[0]}-{chunk[-1]}",
                "text": snippet(abs_path, center, pad=8),
            })

    # Track which lines are already shown in the changed section so we
    # don't repeat them in the impact section.
    shown_lines: dict[str, set[int]] = {}
    for item in changed_snippets:
        f = item["file"]
        if "-" in item["lines"]:
            start_s, end_s = item["lines"].split("-")
            shown_lines.setdefault(f, set()).update(range(int(start_s), int(end_s) + 1))

    # Names that the changed lines actually call (for CALLEES), and names
    # whose signatures changed (for CALLERS).
    calls_from_changed: set[str] = set()
    changed_signature_names: set[str] = set()
    changed_py: list[pathlib.Path] = []
    for rel_path, lines in changes.items():
        if not rel_path.endswith(".py"):
            continue
        abs_path = repo / rel_path
        if abs_path.exists():
            changed_py.append(abs_path)
            calls_from_changed.update(calls_in_lines(abs_path, lines))
            changed_signature_names.update(symbols_with_signature_changes(abs_path, lines))
    imported = _imported_names(changed_py)

    candidates: list[ImpactCandidate] = []

    def add(rel: str, abs_path: pathlib.Path, rows: list[str], role: str,
            line: int, symbol: str, text: str, doc: str = "", inside: str = "") -> None:
        candidates.append(ImpactCandidate(
            id=f"c{len(candidates)}", role=role, file=rel, line=line,
            symbol=symbol, line_text=_source_line(rows, line), doc=doc,
            inside_function=inside, same_file_as_change=rel in changes,
            imported_by_changed_file=abs_path.stem in imported,
            is_test=_is_test_path(rel), text=text,
        ))

    def first_doc_line(node: ast.AST) -> str:
        doc = ast.get_docstring(node) or ""
        return doc.strip().splitlines()[0] if doc.strip() else ""

    for f_str in sorted(impact_files):
        abs_path = pathlib.Path(f_str)
        rel = str(abs_path.relative_to(repo)) if abs_path.is_absolute() else f_str
        tree = _parse(abs_path)
        if tree is None:
            continue
        try:
            rows = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            rows = []

        # CALLEES: definitions referenced by changed lines.
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in calls_from_changed:
                init_line = node.lineno
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "__init__"
                    ):
                        init_line = item.lineno
                        break
                rng = range(max(1, init_line - 12), init_line + 13)
                if rel in shown_lines and any(ln in shown_lines[rel] for ln in rng):
                    continue
                add(rel, abs_path, rows, "callee", node.lineno, node.name,
                    snippet(abs_path, init_line, pad=12), doc=first_doc_line(node))
            elif (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in calls_from_changed
            ):
                rng = range(max(1, node.lineno - 10), node.lineno + 11)
                if rel in shown_lines and any(ln in shown_lines[rel] for ln in rng):
                    continue
                add(rel, abs_path, rows, "callee", node.lineno, node.name,
                    snippet(abs_path, node.lineno, pad=10), doc=first_doc_line(node))

        # CALLERS: call sites of signature-changed names.
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in changed_signature_names
                and getattr(node, "lineno", None) is not None
            ):
                rng = range(max(1, node.lineno - 8), node.lineno + 9)
                if rel in shown_lines and any(ln in shown_lines[rel] for ln in rng):
                    continue
                add(rel, abs_path, rows, "caller", node.lineno,
                    f"call to {node.func.id}", snippet(abs_path, node.lineno, pad=8),
                    inside=_innermost_function(tree, node.lineno))

    return Collected(diff=diff_text, changed=changed_snippets, candidates=candidates)


def build_context(
    repo: pathlib.Path,
    base_ref: str,
    head_ref: str,
) -> str:
    """Build the ODIS markdown context for the diff base_ref..head_ref.

    Both reviewers (Client SDK and Agent SDK) call this and inject the
    result into their first user prompt. They may then dig further with
    Read/Bash tools, but ODIS is what they start with.
    """
    return render_markdown(collect(repo, base_ref, head_ref))
