"""Suite-wide guard: no test talks to the live Jev API by accident.

learnings.config loads .env at import, so a developer's real
TYPESAFE_API_KEY would otherwise switch the Learnings judges and the
router to Jev mid-test. Tests that want Jev set the key themselves and
stub `shared.jev.ask` or pass a fake client.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_live_jev(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("LEARNINGS_JUDGE", raising=False)
