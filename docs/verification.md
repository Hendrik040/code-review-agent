# Verification Gates

This project uses verification gates so comparison claims are backed by
fresh evidence, not vibes.

## Principle

Do not claim a phase, runner, reviewer, or fixture works unless a fresh
command has verified that exact claim.

## Current Gates

Run these before saying the current foundation is healthy:

```bash
uv run python -m compileall shared client_sdk agent_sdk compare.py pricing.py smoke.py
```

```bash
uv run python -c $'from shared.fixtures import CONTRACT_MISMATCH, materialize\nfrom shared.odis import build_context\nfrom shared.findings import to_json, from_json\nwith materialize(CONTRACT_MISMATCH) as f:\n    ctx = build_context(f.repo_path, f.base_ref, f.head_ref)\n    assert from_json(to_json(f.expected)) == f.expected\n    assert "<diff>" in ctx and "</diff>" in ctx\n    assert "<file name=\\"calc.py\\"" in ctx\n    assert "<callers>" in ctx and "main.py" in ctx and "call to add" in ctx\n    print("fixture and ODIS smoke: ok")'
```

## Future Gates

Once reviewer modules exist, `compare.py --task review` must report:

- valid `Finding` schema output
- expected fixture finding matched
- trace and result paths written
- token/cost accounting present

Once unit tests exist, pytest becomes a required gate:

```bash
uv run python -m pytest
```
