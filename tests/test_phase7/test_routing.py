"""Phase 7 — Jev model routing (shared/routing.py).

No network: Jev is replaced by a fake client that returns the same
shape typesafe-sdk's SystemOneResponse exposes (`.scores[name]
.probabilities` keyed by integer level, `.nouls[name].noul`). One test
builds the real SDK request offline to prove QUESTIONS is a payload the
SDK accepts.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox.repo import ExecResult
from shared import routing

DEEP = routing.Tier("deep", "claude-opus-4-7", "max")


class FakeRepo:
    def __init__(self, diff: str = "diff --git a/x.py b/x.py\n+print(1)\n"):
        self.diff = diff
        self.cmds: list[str] = []

    def exec(self, cmd: str, cwd: str = ".", timeout: int = 15) -> ExecResult:
        self.cmds.append(cmd)
        out = "1\t0\tx.py\n" if "--numstat" in cmd else self.diff
        return ExecResult(stdout=out, stderr="", exit_code=0)


class FakeJev:
    def __init__(self, probs, high_stakes=0.02, error: Exception | None = None):
        self.probs, self.high_stakes, self.error = probs, high_stakes, error
        self.calls: list[dict] = []

    def system_one(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        if self.error:
            raise self.error
        return SimpleNamespace(
            scores={"depth": SimpleNamespace(probabilities=dict(enumerate(self.probs)))},
            nouls={"high_stakes": SimpleNamespace(noul=self.high_stakes)},
        )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # route() loads .env; a developer's real key must not leak into tests.
    monkeypatch.setattr(routing, "load_dotenv", lambda **_: None)
    for name in ("TYPESAFE_API_KEY", "ROUTER_RISK", "ROUTER_MAX_DIFF_CHARS",
                 "ROUTER_TIMEOUT", "ROUTER_TIER_LIGHT", "ROUTER_TIER_STANDARD",
                 "ROUTER_TIER_DEEP"):
        monkeypatch.delenv(name, raising=False)


def _route(probs, **kw):
    jev = FakeJev(probs, **{k: kw.pop(k) for k in ("high_stakes", "error") if k in kw})
    return routing.route(FakeRepo(), "base", "head", default=DEEP, client=jev, **kw), jev


@pytest.mark.parametrize("probs, expected", [
    ((0.90, 0.08, 0.02), "light"),      # P(deeper)=0.10 <= 0.15
    ((0.80, 0.15, 0.05), "standard"),   # 0.20 > 0.15, then 0.05 <= 0.15
    ((0.10, 0.80, 0.10), "standard"),
    ((0.10, 0.60, 0.30), "deep"),       # 0.30 chance it needs deep
    ((0.34, 0.33, 0.33), "deep"),       # unsure never downgrades
])
def test_picks_cheapest_tier_within_risk(probs, expected):
    decision, _ = _route(probs)
    assert decision.tier.name == expected
    assert decision.source == "jev"


def test_boundary_is_inclusive():
    assert routing.pick_level((0.85, 0.10, 0.05), 0.0, 0.15)[0] == 0
    assert routing.pick_level((0.84, 0.11, 0.05), 0.0, 0.15)[0] == 1


def test_high_stakes_forces_deep_even_when_diff_looks_trivial():
    decision, _ = _route((0.97, 0.02, 0.01), high_stakes=0.8)
    assert decision.tier == DEEP
    assert "high-stakes" in decision.reason


def test_deep_tier_is_the_callers_default():
    decision, _ = _route((0.0, 0.1, 0.9))
    assert (decision.tier.model, decision.tier.effort) == ("claude-opus-4-7", "max")


def test_no_key_means_no_call_and_default_tier():
    repo = FakeRepo()
    decision = routing.route(repo, "base", "head", default=DEEP)
    assert decision.tier == DEEP and decision.source == "default"
    assert repo.cmds == []  # didn't even read the diff


@pytest.mark.parametrize("error", [TimeoutError("slow"), RuntimeError("401 key=sk-secret")])
def test_jev_failure_falls_back_without_leaking_the_error(error):
    decision, _ = _route((1.0, 0.0, 0.0), error=error)
    assert decision.tier == DEEP and decision.source == "default"
    assert "sk-secret" not in decision.reason


def test_malformed_distribution_is_not_routed_on():
    decision, _ = _route((0.2, 0.1, 0.1))  # sums to 0.4
    assert decision.tier == DEEP and decision.source == "default"


def test_empty_diff_falls_back():
    jev = FakeJev((1.0, 0.0, 0.0))
    decision = routing.route(FakeRepo(diff=""), "a", "b", default=DEEP, client=jev)
    assert decision.source == "default" and jev.calls == []


def test_env_overrides_tiers_and_risk(monkeypatch):
    monkeypatch.setenv("ROUTER_TIER_LIGHT", "claude-opus-4-7:medium")
    monkeypatch.setenv("ROUTER_RISK", "0.5")
    decision, _ = _route((0.6, 0.3, 0.1))  # P(deeper)=0.4 <= 0.5
    assert decision.tier == routing.Tier("light", "claude-opus-4-7", "medium")


def test_bad_tier_spec_falls_back(monkeypatch):
    monkeypatch.setenv("ROUTER_TIER_LIGHT", "claude-haiku-5-5:turbo")
    decision, _ = _route((1.0, 0.0, 0.0))
    assert decision.tier == DEEP and decision.source == "default"


def test_state_carries_title_stats_and_marks_truncation(monkeypatch):
    monkeypatch.setenv("ROUTER_MAX_DIFF_CHARS", "10")
    jev = FakeJev((1.0, 0.0, 0.0))
    repo = FakeRepo(diff="x" * 50)
    routing.route(repo, "a b", "head", default=DEEP, title="Fix typo", client=jev)
    state = jev.calls[0]["state"]
    assert "Pull request title: Fix typo" in state
    assert "1\t0\tx.py" in state
    assert "first 10 of 50 characters" in state and "x" * 11 not in state
    assert "'a b'..head" in repo.cmds[0]  # refs are shell-quoted


def test_questions_are_a_request_the_real_sdk_accepts():
    """Build (don't send) the request with the installed typesafe-sdk."""
    pytest.importorskip("typesafe_sdk")
    import json

    from typesafe_sdk._core.config import Config
    from typesafe_sdk._core.endpoints import prepare_system_one
    from typesafe_sdk._core.response_types import SystemOneResponse

    cfg = Config.resolve("test-key", None, None, None, None, False)
    request, pending = prepare_system_one(
        cfg, "some diff", routing.QUESTIONS, None, None, None, None, SystemOneResponse
    )
    body = json.loads(request.content)
    assert pending is None
    assert body["model"] == "jev-latest"
    assert body["questions"]["depth"]["type"] == "score"
    assert len(body["questions"]["depth"]["criteria"]) == len(routing.TIER_NAMES)
    assert body["questions"]["high_stakes"]["type"] == "noul"


def test_routes_through_the_real_sdk_client_and_response_parser():
    """Real TypeSafeClient + real response model over a mock transport,
    using the wire shape from the SDK's own schema (string level keys)."""
    pytest.importorskip("typesafe_sdk")
    import json

    import httpx2
    from typesafe_sdk import TypeSafeClient

    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "model": "jev-1",
            "usage": {"input_tokens": 120, "output_tokens": 12},
            "answers": {
                "depth": {
                    "type": "score", "score": 0.1, "confidence": 0.9,
                    "legend": {"0": "None", "1": "Local", "2": "Deep"},
                    "probabilities": {"0": 0.92, "1": 0.06, "2": 0.02},
                },
                "high_stakes": {"type": "noul", "noul": 0.03},
            },
        })

    with TypeSafeClient(api_key="test-key", compression=False,
                        transport=httpx2.MockTransport(handler)) as client:
        decision = routing.route(FakeRepo(), "base", "head", default=DEEP, client=client)

    assert seen["path"] == "/v1/systemone" and seen["auth"] == "Bearer test-key"
    assert "x.py" in seen["body"]["state"]
    assert decision.source == "jev" and decision.tier.name == "light"
    assert decision.depth_probs == (0.92, 0.06, 0.02) and decision.high_stakes == 0.03


def test_pricing_at_the_routed_model_matches_the_harness():
    """run_044 (Opus 4.7): the harness reported $0.918825 for this usage."""
    import pricing

    usage = {
        "input_tokens": 8, "output_tokens": 13835,
        "cache_read_input_tokens": 179482, "cache_creation_input_tokens": 77307,
        "cache_creation": {"ephemeral_5m_input_tokens": 77307, "ephemeral_1h_input_tokens": 0},
    }
    assert pricing.cost_usd(usage, "claude-opus-4-7") == pytest.approx(0.918825, abs=1e-6)
    assert pricing.cost_usd(usage, "some-unlisted-model") is None
    # No model: the module-level constants, which are the Opus 4.7 rates too.
    assert pricing.cost_usd(usage) == pytest.approx(0.918825, abs=1e-6)


def test_review_header_names_the_model_only_when_known():
    from github.post_review import RunMeta
    from github.review_summary import _render_run_header

    base = dict(run_id=7, sdk="agent", effort="high",
                timestamp_utc="2026-05-03T14:32:00Z", num_turns=5, cost_usd=0.4)
    assert "Agent SDK · effort=high" in _render_run_header(RunMeta(**base))
    routed = _render_run_header(RunMeta(**base, model="claude-sonnet-5-5"))
    assert "Agent SDK · claude-sonnet-5-5 · effort=high" in routed


def test_fallback_uses_the_configured_deep_tier(monkeypatch):
    """A benchmark arm with deep=Opus 5.5 must not fall back to Opus 4.7."""
    monkeypatch.setenv("ROUTER_TIER_DEEP", "claude-opus-5-5:high")
    no_key = routing.route(FakeRepo(), "b", "h", default=DEEP)
    assert (no_key.tier.model, no_key.tier.effort) == ("claude-opus-5-5", "high")
    assert no_key.source == "default"
    failed, _ = _route((1.0, 0.0, 0.0), error=TimeoutError())
    assert failed.tier.model == "claude-opus-5-5"


def test_a_bad_deep_override_falls_back_to_the_callers_default(monkeypatch):
    monkeypatch.setenv("ROUTER_TIER_DEEP", "claude-opus-5-5:turbo")
    assert routing.route(FakeRepo(), "b", "h", default=DEEP).tier == DEEP
