"""router_inputs: a rerun only pays for bugs that have no summary yet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from router_inputs import needs_summary  # noqa: E402


def test_existing_summary_is_skipped(tmp_path):
    e = {"project": "thefuck", "bug_id": 7}
    assert needs_summary(e, tmp_path) is True
    (tmp_path / "thefuck_7.summary.json").write_text("{}")
    assert needs_summary(e, tmp_path) is False
