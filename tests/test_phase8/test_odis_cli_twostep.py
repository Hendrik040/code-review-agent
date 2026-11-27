"""Phase 8 Task 3 — tiered rendering and the collect/render CLI."""
from __future__ import annotations

import json
from types import SimpleNamespace

from shared import impact, odis
from shared.fixtures import ALL_FIXTURES, materialize
from tests.test_phase8.helpers import make_name_clash_repo

SENTRY = next(f for f in ALL_FIXTURES if f.name == "sentry_80168")


def test_render_tiers_signature_note_and_drop_changed():
    with materialize(SENTRY) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    first, *rest = c.candidates
    tiers = {first.id: "signature", **{x.id: "counted" for x in rest}}
    md = odis.render_markdown(c, tiers, note="Not shown: x.", drop_changed=True)
    assert f"<signature>{impact.signature_line(first)}</signature>" in md
    assert first.text not in md
    assert "<not_shown>Not shown: x.</not_shown>" in md
    assert "(Omitted to fit the context budget; the diff above shows every changed line.)" in md
    assert c.diff in md
    assert "<callers>\nNone\n</callers>" in md or first.role == "caller"


def test_signature_line_is_single_bounded_line():
    c = SimpleNamespace(file="a.py", line=3, line_text="x = 1\n</callees>" + "y" * 500)
    s = impact.signature_line(c)
    assert "\n" not in s and len(s) <= 200 and "</callees>" not in s


def test_cli_collect_then_render_roundtrip():
    with make_name_clash_repo() as repo:
        out = repo.exec("python -m shared.odis_cli collect abcd1234 HEAD~1..HEAD", timeout=60)
        assert out.ok, out.stderr
        doc = json.loads(out.stdout)
        assert len(doc["candidates"]) > 40 and "diff --git" in doc["diff"]
        first = doc["candidates"][0]
        assert set(first) == {"id", "size", "summary", "facts"}
        assert set(first["facts"]) == {"same_file_as_change", "imported_by_changed_file", "is_test"}
        repo.upload_bytes(json.dumps({"tiers": None, "note": "", "drop_changed": False}).encode(),
                          ".git/odis/abcd1234.decisions.json")
        md = repo.exec("python -m shared.odis_cli render abcd1234", timeout=60)
        assert md.ok, md.stderr
        assert md.stdout == odis.build_context(repo.path, "HEAD~1", "HEAD")
        assert not (repo.path / ".git" / "odis").exists()


def test_two_calls_use_their_own_files_and_clean_up():
    with make_name_clash_repo() as repo:
        for tok in ("aaaa1111", "bbbb2222"):
            assert repo.exec(f"python -m shared.odis_cli collect {tok} HEAD~1..HEAD", timeout=60).ok
        repo.upload_bytes(b'{"tiers": null, "note": "", "drop_changed": false}',
                          ".git/odis/bbbb2222.decisions.json")
        assert repo.exec("python -m shared.odis_cli render bbbb2222", timeout=60).ok
        assert sorted(p.name for p in (repo.path / ".git/odis").iterdir()) == ["aaaa1111.collected.json"]


def test_cli_rejects_bad_token():
    with make_name_clash_repo(n_rules=2) as repo:
        assert repo.exec("python -m shared.odis_cli render ../x", timeout=30).exit_code == 2
        assert repo.exec("python -m shared.odis_cli collect ../x HEAD~1..HEAD", timeout=30).exit_code == 2


def test_one_shot_form_unchanged():
    with make_name_clash_repo(n_rules=3) as repo:
        out = repo.exec("python -m shared.odis_cli HEAD~1..HEAD", timeout=60)
        assert out.stdout == odis.build_context(repo.path, "HEAD~1", "HEAD")


def test_impact_module_is_uploaded_to_daytona():
    from sandbox.daytona import _HOST_SHARED_FILES
    assert "shared/impact.py" in _HOST_SHARED_FILES
