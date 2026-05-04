"""Shared retrieval-side learnings module — used by BOTH reviewers.

Responsibilities (spec §3):
  - retrieve_for_diff(repo, chunks)        -> threshold-filtered hits
  - applicability_filter(hits, diff)        -> Haiku-judged subset
  - format_for_prompt(hits)                 -> <past_learnings> XML
  - search_tool_handler(query, repo, k)    -> <item ...> XML for the tool

Strictly additive: any failure returns an empty result so the reviewer
keeps running (spec §8).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from typing import Any, Protocol

from learnings.ast_chunker import Chunk
from learnings.qdrant_store import Hit, QdrantStore, collection_for

log = logging.getLogger("shared.learnings")


class Embedder(Protocol):
    def embed_one(self, text: str, *, input_type: str = "document") -> list[float]: ...


_INTRO = (
    "These are corrections previous maintainers have given for code with "
    "similar shape. Treat them as priors, not rules. If a learning clearly "
    "applies to a finding you're about to make, cite it; if it suggests a "
    "finding you'd otherwise miss, raise that finding. If it doesn't apply, "
    "ignore it silently."
)


def _cdata(text: str) -> str:
    """Wrap text in <![CDATA[...]]> safely. CDATA sections terminate on
    `]]>`; the standard escape splits the offending sequence across two
    sections so the parser sees the literal three characters."""
    return f"<![CDATA[{text.replace(']]>', ']]]]><![CDATA[>')}]]>"


def apply_threshold(hits: list[Hit], threshold: float) -> list[Hit]:
    return [h for h in hits if h.score >= threshold]


def retrieve_for_diff(
    *,
    repo: str,
    chunks: list[Chunk],
    store: QdrantStore,
    embedder: Embedder,
    collection_override: str | None = None,
    per_query_k: int = 5,
    threshold: float = 0.78,
) -> list[Hit]:
    """One embed + query per AST chunk; merge, dedupe, threshold."""
    collection = collection_override or collection_for(repo)
    by_id: dict[str, Hit] = {}
    for chunk in chunks:
        try:
            vec = embedder.embed_one(chunk.text, input_type="query")
            hits = store.search(collection, query_vector=vec, k=per_query_k)
        except Exception:
            continue  # fail-open per spec §8
        for h in hits:
            existing = by_id.get(h.point_id)
            if existing is None or h.score > existing.score:
                by_id[h.point_id] = h
    raw_hits = sorted(by_id.values(), key=lambda h: h.score, reverse=True)
    log.info(
        "learnings retrieve: repo=%s chunks=%d raw_hits=%d threshold=%.3f scores=%s",
        repo, len(chunks), len(raw_hits), threshold,
        [f"{h.score:.3f}" for h in raw_hits[:10]],
    )
    return apply_threshold(raw_hits, threshold)


def applicability_filter(
    hits: list[Hit],
    *,
    anthropic_client: Any,
    diff_summary: str,
    model: str = "claude-haiku-4-5-20251001",
    keep_max: int = 5,
) -> list[Hit]:
    """Haiku judges each hit. Drop "no"; keep "yes" + "maybe". Spec §5.2.

    Returns up to ``keep_max`` hits, preserving original score order.

    Fail-open semantics (spec §8.2 — "Applicability filter (Haiku)
    failure → Skip filter; pass through threshold-only results"): if
    the Haiku call raises ANY exception, the whole filter step bails
    and returns ``hits[:keep_max]`` unfiltered. Per-hit fail-open
    would mix "Haiku said yes/maybe" with "Haiku threw — we don't know"
    in the output and silently consume the keep_max budget with
    un-judged hits.
    """
    if not hits:
        return []
    try:
        verdicts = [
            _judge_applicability(anthropic_client, model, diff_summary, h)
            for h in hits
        ]
    except Exception:
        return hits[:keep_max]
    return [h for h, v in zip(hits, verdicts) if v in ("yes", "maybe")][:keep_max]


def _slice_diff_for_file(diff_text: str, file_path: str) -> str:
    """Extract just the hunks for ``file_path`` from a unified diff.

    Returns the substring from `diff --git a/<file>` (or `+++ b/<file>`)
    through the start of the next file's diff (or end of input). Empty
    string if the file isn't in the diff.

    Why: applicability_filter's Haiku call needs the diff context for
    the SPECIFIC file the past learning is anchored to. Passing the
    whole diff would either be wasteful (8+ KB per call × N hits) or
    dishonestly truncated (the previous diff_summary[:2000] cap dropped
    critical hunks past the cutoff and made Haiku say "no" on real
    matches).
    """
    marker = f"diff --git a/{file_path} "
    start = diff_text.find(marker)
    if start == -1:
        # Fall back to looking for the +++ b/ marker (some diffs lack
        # the diff --git header, e.g. plain `diff -u` output).
        marker = f"+++ b/{file_path}\n"
        start = diff_text.find(marker)
        if start == -1:
            return ""
    # Find the next file's diff --git block (or EOF).
    end = diff_text.find("\ndiff --git ", start + 1)
    return diff_text[start:end if end != -1 else len(diff_text)]


def _judge_applicability(client: Any, model: str, diff_summary: str, hit: Hit) -> str:
    p = hit.payload
    file_path = p.get("file_path", "")
    # Use only the hunks for THIS hit's file. Keeps the prompt small
    # and removes the "Haiku says no because the relevant lines were
    # past the truncation cap" failure mode.
    file_diff = _slice_diff_for_file(diff_summary, file_path) if file_path else ""
    if not file_diff:
        # No matching file in the diff → can't judge applicability;
        # default to "maybe" so the hit isn't dropped silently.
        return "maybe"
    prompt = (
        "Is the past learning below applicable to the diff hunk below?\n"
        "Answer EXACTLY one word: yes, no, or maybe.\n\n"
        f"PAST LEARNING:\n{p.get('learning_text','')}\n\n"
        f"PAST CODE ANCHOR ({p.get('file_path','')}:"
        f"{p.get('line_start','')}-{p.get('line_end','')}):\n"
        f"{p.get('code_chunk_text','')}\n\n"
        f"NEW DIFF FOR {file_path}:\n{file_diff}\n\n"
        "Answer:"
    )
    msg = client.messages.create(
        model=model, max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    word = (msg.content[0].text or "").strip().lower()
    if word.startswith("yes"):
        return "yes"
    if word.startswith("no"):
        return "no"
    return "maybe"


def format_for_prompt(hits: list[Hit]) -> str:
    if not hits:
        return ""
    items = "\n".join(_render_item(i + 1, h) for i, h in enumerate(hits))
    return f"<past_learnings>\n  <intro>\n    {_INTRO}\n  </intro>\n{items}\n</past_learnings>"


def _render_item(idx: int, h: Hit) -> str:
    p = h.payload
    # Phase 6.1: <bug_context> is OMITTED entirely when empty (vs. an empty
    # self-closing tag) to keep the prompt tight when no parent bot finding
    # was attached.
    bug_context_xml = ""
    bc = p.get("bug_context", "")
    if bc:
        bug_context_xml = f"\n    <bug_context>{escape(bc)}</bug_context>"
    return (
        f'  <item id="{idx}" score="{h.score:.2f}" '
        f'file="{escape(p.get("file_path",""), quote=True)}" '
        f'lines="{p.get("line_start","")}-{p.get("line_end","")}" '
        f'author="{escape(p.get("author",""), quote=True)}" '
        f'pr="{escape(p.get("repo",""), quote=True)}#{p.get("pr_number","")}" '
        f'captured="{escape(p.get("captured_at","")[:10], quote=True)}">\n'
        f"    <learning>{escape(p.get('learning_text',''))}</learning>"
        f"{bug_context_xml}\n"
        f'    <original_code language="{escape(p.get("language",""), quote=True)}">'
        f"{_cdata(p.get('code_chunk_text',''))}</original_code>\n"
        f"  </item>"
    )


def search_tool_handler(
    *, query: str, repo: str, store: QdrantStore, embedder: Embedder,
    collection_override: str | None = None, k: int = 5,
) -> str:
    """Body of the `search_learnings` tool. Returns an XML-fragment string."""
    collection = collection_override or collection_for(repo)
    try:
        vec = embedder.embed_one(query, input_type="query")
        hits = store.search(collection, query_vector=vec, k=k)
    except Exception:
        return "<results/>"
    if not hits:
        return "<results/>"
    items = "\n".join(_render_item(i + 1, h) for i, h in enumerate(hits))
    return f"<results>\n{items}\n</results>"
