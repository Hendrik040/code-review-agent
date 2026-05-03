# tool-offload-compare

Empirical comparison of how the **Claude Agent SDK** (which wraps the Claude
Code harness) and the bare **Anthropic Python client SDK** each handle a large
tool-call output. Same `fetch_url` tool on both sides, same URL, same model —
the script prints a small table showing how many characters of the tool result
each path actually puts into the model's context.

## Setup

```bash
pip install -e .
cp .env.example .env  # then fill in ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY=...
```

The Agent SDK requires the `claude` CLI on `PATH` (Claude Code must be
installed locally — the SDK shells out to it).

## Run

```bash
python compare.py                          # default: long Wikipedia article
python compare.py https://example.com      # small page sanity check
```
