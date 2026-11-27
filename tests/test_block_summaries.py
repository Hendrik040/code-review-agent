import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from block_summaries import get_blocks, numstat  # noqa: E402

TWO_FILE_DIFF = (
    "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    "diff --git a/pkg/b.py b/pkg/b.py\n--- a/pkg/b.py\n+++ b/pkg/b.py\n@@ -1 +1 @@\n-y = 1\n+y = 2\n"
)
YAML_AND_PY_DIFF = (
    "diff --git a/conf/app.yaml b/conf/app.yaml\n--- a/conf/app.yaml\n+++ b/conf/app.yaml\n@@ -1 +1 @@\n-a: 1\n+a: 2\n"
    "diff --git a/pkg/mod.py b/pkg/mod.py\n--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-z = 1\n+z = 2\n"
)


class FakeClient:
    def __init__(self, blocks_per_call):
        self.n = blocks_per_call
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        blocks = [{"kind": "function", "symbol": f"f{i}", "lines_added": i, "lines_removed": 0,
                   "before": "b", "after": "a", "callers_or_users_touched": [], "constructs": [],
                   "complexity_1_10": 3} for i in range(self.n)]
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({"blocks": blocks}))],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50))


def test_numstat_counts_per_file():
    d = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-x\n+y\n+z\n"
    assert numstat(d) == [{"path": "a.py", "added": 2, "removed": 1}]


def test_get_blocks_caches_by_diff_hash(tmp_path):
    client = FakeClient(blocks_per_call=2)
    r1 = get_blocks(client, "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    r2 = get_blocks(client, "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert client.calls == 2 and r1["cached"] is False and r2["cached"] is True
    assert len(r2["blocks"]) == 4


def test_non_python_files_are_described(tmp_path):
    r = get_blocks(FakeClient(blocks_per_call=1), "t", YAML_AND_PY_DIFF, cache_dir=tmp_path)
    assert {b["file"] for b in r["blocks"]} == {"conf/app.yaml", "pkg/mod.py"}


def test_zero_blocks_is_valid(tmp_path):
    r = get_blocks(FakeClient(blocks_per_call=0), "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert r["blocks"] == [] and r["blocks_dropped"] == 0


def test_cap_keeps_40_largest(tmp_path):
    r = get_blocks(FakeClient(blocks_per_call=25), "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert len(r["blocks"]) == 40 and r["blocks_dropped"] == 10
    assert min(b["lines_added"] for b in r["blocks"]) == 5
