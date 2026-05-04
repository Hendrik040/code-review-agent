"""Capture pipeline — single-iteration body.

`capture_once` runs ONE poll cycle: list PRs → list comments since
cursor → for each mention, chunk + embed + upsert. `capture_watch`
loops it. Spec §8.1: anchor errors advance cursor; transient infra
(Voyage/Qdrant) bails the iteration so the daemon retries.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from github.pr_fetch import Comment, PullRequest

from learnings.ast_chunker import chunk_for_anchor
from learnings.config import load as load_config
from learnings.extractor import Extractor, Mention
from learnings.github_adapter import GitHubAdapter
from learnings.qdrant_store import LearningPayload, QdrantStore, collection_for, point_id_for
from learnings.state import State
from learnings.voyage_client import VoyageClient, VoyageError

try:
    from qdrant_client.http.exceptions import UnexpectedResponse as _QdrantHttpError
except ImportError:
    _QdrantHttpError = Exception  # noqa — fallback if qdrant-client moves the path

log = logging.getLogger("learnings.capture")

DEFAULT_STATE_PATH = Path("shared/memory/learnings_state.json")
DEFAULT_CLONE_ROOT = Path("/tmp/learnings_clones")


def _is_transient_infra(exc: BaseException) -> bool:
    """Voyage retry-exhaustion or Qdrant HTTP error → transient.
    Anchor problems (FileNotFoundError, etc.) → permanent (advance cursor)."""
    return isinstance(exc, (VoyageError, _QdrantHttpError))


def _ensure_clone(repo: str, head_sha: str, root: Path) -> Path:
    """Ensure a local checkout of `repo` at `head_sha`. Returns the
    checkout path. Reuses an existing clone if present."""
    target = root / repo.replace("/", "__")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["gh", "repo", "clone", repo, str(target)],
            check=True, capture_output=True, timeout=120,
        )
    subprocess.run(
        ["git", "-C", str(target), "fetch", "origin", head_sha],
        check=True, capture_output=True, timeout=60,
    )
    # Self-heal a dirty tree from a prior daemon crash mid-checkout. We
    # never edit the clone, so reset+clean is always safe; without this,
    # a botched run leaves the worktree in a state `git checkout` refuses.
    subprocess.run(
        ["git", "-C", str(target), "reset", "--hard"],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        ["git", "-C", str(target), "clean", "-fd"],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", head_sha],
        check=True, capture_output=True, timeout=30,
    )
    return target


def _process_comment(
    *, repo: str, pr: PullRequest, comment: Comment, mention: Mention,
    embedder: VoyageClient, store: QdrantStore, repo_clone_root: Path,
) -> None:
    clone = _ensure_clone(repo, pr.head_sha, repo_clone_root)
    src = clone / comment.file_path
    chunk = chunk_for_anchor(
        src, line_start=comment.line_start, line_end=comment.line_end
    )
    vec = embedder.embed_one(chunk.text, input_type="document")
    payload = LearningPayload(
        code_chunk_text=chunk.text,
        learning_text=mention.text,
        repo=repo,
        pr_number=pr.number,
        file_path=comment.file_path,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
        chunk_kind=chunk.kind,
        language="python",
        author=comment.author,
        captured_at=datetime.now(timezone.utc).isoformat(),
        commit_sha=pr.head_sha,
    )
    store.upsert(
        collection_for(repo),
        point_id=point_id_for(repo, comment.comment_id),
        vector=vec, payload=payload,
    )


def capture_once(
    *, repo: str, adapter: GitHubAdapter, embedder: VoyageClient,
    store: QdrantStore, state_path: Path, repo_clone_root: Path,
    handle: str, call_words: tuple[str, ...],
) -> None:
    """One iteration of the capture loop."""
    state = State(state_path)
    extractor = Extractor(handle=handle, call_words=call_words)
    cursor = state.cursor(repo)

    try:
        prs = adapter.list_open_prs(repo)
    except Exception as e:
        log.warning("list_open_prs failed for %s: %s", repo, e)
        return

    for pr in prs:
        try:
            comments = adapter.list_pr_review_comments(pr, since_id=cursor)
        except Exception as e:
            log.warning("list_pr_review_comments failed for #%d: %s", pr.number, e)
            continue
        for c in comments:
            mention = extractor.parse(c.body)
            try:
                if mention is not None:
                    _process_comment(
                        repo=repo, pr=pr, comment=c, mention=mention,
                        embedder=embedder, store=store,
                        repo_clone_root=repo_clone_root,
                    )
                state.advance(repo, c.comment_id)
            except Exception as e:
                if _is_transient_infra(e):
                    # Spec §8.1: Voyage 5xx / Qdrant errors → backoff +
                    # requeue. Do NOT advance the cursor; bail this
                    # iteration so we don't hammer the broken service.
                    log.warning(
                        "comment %d (#%d) infra failure (%s); requeueing for next iteration",
                        c.comment_id, pr.number, type(e).__name__,
                    )
                    return
                log.warning(
                    "comment %d (#%d) processing failed (%s: %s) — advancing past it",
                    c.comment_id, pr.number, type(e).__name__, e,
                )
                state.advance(repo, c.comment_id)


def capture_watch(*, interval_s: int, **kwargs) -> None:
    log.info("capture daemon starting; interval=%ds", interval_s)
    while True:
        try:
            capture_once(**kwargs)
        except Exception as e:
            log.exception("capture iteration crashed: %s", e)
        time.sleep(interval_s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="learnings.capture")
    p.add_argument("--repo", required=True, help="owner/name")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None,
                   help="seconds between polls in --watch mode (overrides env)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    embedder = VoyageClient(api_key=cfg.voyage_api_key)
    store = QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
    adapter = GitHubAdapter()

    common = dict(
        repo=args.repo, adapter=adapter, embedder=embedder, store=store,
        state_path=DEFAULT_STATE_PATH, repo_clone_root=DEFAULT_CLONE_ROOT,
        handle=cfg.handle, call_words=cfg.call_words,
    )

    if args.once:
        capture_once(**common)
    else:
        capture_watch(interval_s=args.interval or cfg.interval_s, **common)
    return 0


if __name__ == "__main__":
    sys.exit(main())
