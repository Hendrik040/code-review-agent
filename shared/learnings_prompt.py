"""Shared helper used by BOTH reviewers to build the per-PR user prompt
with an optional ``<past_learnings>`` block + diff-derived AST chunks.

The helper is strictly additive: ANY failure (no env, missing diff,
broken Qdrant, no slug, etc.) returns the plain unmodified prompt so
the reviewer keeps running. Spec §8.2.

The Repo abstraction (sandbox.repo.Repo) exposes:
  - ``exec(cmd, timeout=...)`` returning an ExecResult with .stdout
  - ``path`` (LocalRepo only) — Path on the host; not available on Daytona
"""
from __future__ import annotations

import logging
from typing import Any

from shared.prompts import USER_PROMPT_TEMPLATE

log = logging.getLogger("learnings.prompt")


def infer_repo_slug(repo: Any) -> str | None:
    """Best-effort owner/name from `git remote get-url origin`. Returns
    None for non-GitHub remotes or any failure.

    Boundary-aware match on `github.com` so hosts like `notgithub.com`
    don't accidentally route into a GitHub-canonical collection
    (cross-tenant risk in the shared Qdrant cluster — spec §6).
    """
    try:
        url = repo.exec("git remote get-url origin", timeout=5).stdout.strip()
    except Exception:
        return None
    url = url.removesuffix(".git")
    # Two recognized forms:
    #   https://github.com/owner/repo  -> "://github.com/" boundary
    #   git@github.com:owner/repo      -> "@github.com:" boundary
    # GitHub Enterprise (github.foo.com) is intentionally rejected for v1.
    if "://github.com/" in url:
        path = url.split("://github.com/", 1)[1]
    elif "@github.com:" in url:
        path = url.split("@github.com:", 1)[1]
    else:
        return None
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return None


def parse_changed_lines(diff_text: str) -> dict[str, list[int]]:
    """Unified-diff → {file_path: [right-side line numbers added]}.

    Handles standard git diff output: '+++ b/path' file headers,
    '@@ -a,b +c,d @@' hunk headers, '+' added lines (excluding the
    '+++' header). Lines that aren't '+' (context lines) advance the
    counter without being recorded; '-' deleted lines don't.
    """
    out: dict[str, list[int]] = {}
    cur: str | None = None
    line_no: int = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ b/"):
            cur = raw[6:].strip()
            out.setdefault(cur, [])
        elif raw.startswith("@@"):
            try:
                rhs = raw.split("+")[1].split(" ")[0]
                line_no = int(rhs.split(",")[0])
            except Exception:
                line_no = 0
        elif cur and raw.startswith("+") and not raw.startswith("+++"):
            out[cur].append(line_no)
            line_no += 1
        elif cur and not raw.startswith("-"):
            line_no += 1
    return {k: v for k, v in out.items() if v}


def build_user_prompt_with_learnings(
    repo: Any, base_ref: str, head_ref: str, repo_slug: str | None
) -> str:
    """Build the reviewer's user prompt, with `<past_learnings>` block
    appended after the standard ODIS context if (and only if) the
    learnings layer produces non-empty filtered hits.

    Strictly additive — any failure in the learnings layer returns
    the plain unmodified prompt (spec §8.2)."""
    base = USER_PROMPT_TEMPLATE.format(
        repo_path="<sandbox repo root>", base_ref=base_ref, head_ref=head_ref,
    )
    if not repo_slug:
        return base
    repo_path = getattr(repo, "path", None)
    if repo_path is None:
        # Daytona / non-LocalRepo backends don't expose .path. The
        # query-side chunker needs a real Path; fall back gracefully.
        return base
    try:
        from learnings.config import load as load_cfg
        from learnings.ast_chunker import chunks_for_diff
        from learnings.voyage_client import VoyageClient
        from learnings.qdrant_store import QdrantStore
        from shared.learnings import (
            applicability_filter, format_for_prompt, retrieve_for_diff,
        )
        import anthropic

        cfg = load_cfg()
        diff_text = repo.exec(
            f"git diff {base_ref}..{head_ref}", timeout=30
        ).stdout
        changed = parse_changed_lines(diff_text)
        chunks = chunks_for_diff(repo_path, changed)
        if not chunks:
            return base
        store = QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
        embedder = VoyageClient(api_key=cfg.voyage_api_key)
        hits = retrieve_for_diff(
            repo=repo_slug, chunks=chunks, store=store, embedder=embedder,
            per_query_k=cfg.per_query_k, threshold=cfg.threshold,
        )
        if cfg.filter_enabled and hits:
            ant = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
            hits = applicability_filter(
                hits, anthropic_client=ant, diff_summary=diff_text,
                keep_max=cfg.top_k,
            )
        block = format_for_prompt(hits[: cfg.top_k])
        if not block:
            return base
        # Insert <past_learnings> AFTER the standard prompt body.
        return f"{base}\n\n{block}"
    except Exception as e:
        log.warning("learnings: prompt-build skipped (%s): %s", type(e).__name__, e)
        return base
