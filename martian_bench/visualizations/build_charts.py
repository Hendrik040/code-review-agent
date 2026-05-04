"""Build the pitch-deck visualizations for both benches.

Reads:
  - bugsinpy_bench/results/sweep_*/scores.json   (our 6-cell BugsInPy matrix)
  - martian_bench/results/sweep_*/judged.json    (our 6-cell Martian cells)
  - martian_bench/dataset/martian/offline/results/anthropic_claude-sonnet-4-5-20250929/evaluations.json
        (Martian's published per-PR per-tool results — filtered to Sentry slice)

Writes one HTML file per chart into visualizations/output/. Each HTML is
self-contained (Plotly is bundled inline) so they open in any browser.

Charts produced:

  bugsinpy_recall_vs_cost.html      — recall-vs-cost Pareto, our matrix
  bugsinpy_recall_by_effort.html    — line plot, recall as effort scales
  bugsinpy_project_heatmap.html     — projects × cells, target recall
  martian_precision_recall.html     — P-R scatter, ours + commercials
  martian_f1_bars.html              — F1 ranking bar chart, ours + commercials
  matrix_summary_table.html         — full metric table for both benches

Usage:
    uv run python visualizations/build_charts.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]

SDK_COLORS = {
    "agent":  "#1f77b4",
    "client": "#d62728",
}
COMMERCIAL_COLOR = "#7f7f7f"
OUR_COLOR_AGENT = "#1f77b4"
OUR_COLOR_CLIENT = "#d62728"

# ---------------------------------------------------------- loaders --


def _load_bugsinpy_cells() -> list[dict]:
    """Each cell is one (sdk, effort) sweep with scores.json."""
    cells = []
    rd = PROJECT_ROOT / "bugsinpy_bench" / "results"
    if not rd.is_dir():
        return cells
    for sd in sorted(rd.iterdir()):
        if not sd.is_dir() or not sd.name.startswith("sweep_2026"):
            continue
        if sd.name.endswith("_001") or "tail" in sd.name:
            continue
        scores = sd / "scores.json"
        if not scores.is_file():
            continue
        cells.append(json.loads(scores.read_text()))
    cells.sort(key=lambda c: (c["sdk"], EFFORT_ORDER.index(c["effort"]) if c["effort"] in EFFORT_ORDER else 99))
    return cells


def _load_martian_cells() -> list[dict]:
    """Each cell = one martian judged.json."""
    cells = []
    rd = PROJECT_ROOT / "martian_bench" / "results"
    if not rd.is_dir():
        return cells
    for sd in sorted(rd.iterdir()):
        if not sd.is_dir() or not sd.name.startswith("sweep_2026"):
            continue
        if "smoke" in sd.name:
            continue
        judged = sd / "judged.json"
        if not judged.is_file():
            continue
        meta = json.loads((sd / "meta.json").read_text())
        j = json.loads(judged.read_text())
        j["meta"] = meta
        cells.append(j)
    cells.sort(key=lambda c: (c["sdk"], EFFORT_ORDER.index(c["effort"]) if c["effort"] in EFFORT_ORDER else 99))
    return cells


def _load_martian_commercials() -> dict[str, dict[str, float]]:
    """Read Martian's published per-tool eval, filter to Sentry-only,
    compute micro-averaged P/R/F1 per tool. Returns:
        {tool_name: {tp, fp, fn, precision, recall, f1, n_prs}}
    """
    p = (PROJECT_ROOT / "martian_bench" / "dataset" / "martian"
         / "offline" / "results"
         / "anthropic_claude-sonnet-4-5-20250929" / "evaluations.json")
    if not p.is_file():
        return {}
    data = json.loads(p.read_text())
    # Filter to Sentry PRs only.
    is_sentry = lambda url: ("sentry-greptile" in url) or ("getsentry/sentry" in url)
    by_tool: dict[str, dict[str, float]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0, "n_prs": 0,
                 "total_candidates": 0, "total_golden": 0}
    )
    for url, tool_results in data.items():
        if not is_sentry(url):
            continue
        for tool, m in tool_results.items():
            if m.get("skipped"):
                continue
            entry = by_tool[tool]
            entry["tp"] += m.get("tp", 0)
            entry["fp"] += m.get("fp", 0)
            entry["fn"] += m.get("fn", 0)
            entry["total_candidates"] += m.get("total_candidates", 0)
            entry["total_golden"] += m.get("total_golden", 0)
            entry["n_prs"] += 1
    out: dict[str, dict[str, float]] = {}
    for tool, m in by_tool.items():
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        p_val = tp / (tp + fp) if (tp + fp) else 0.0
        r_val = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p_val * r_val / (p_val + r_val) if (p_val + r_val) else 0.0
        out[tool] = {**m, "precision": p_val, "recall": r_val, "f1": f1}
    return out


def _our_martian_label(c: dict) -> str:
    return f"ours ({c['sdk']}/{c['effort']})"


def _save(fig: go.Figure, name: str, title: str) -> None:
    out = OUT_DIR / name
    fig.write_html(str(out), include_plotlyjs="inline", full_html=True)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------- charts --


def chart_bugsinpy_recall_vs_cost(cells: list[dict]) -> None:
    fig = go.Figure()
    by_sdk: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        by_sdk[c["sdk"]].append(c)
    for sdk, ss in by_sdk.items():
        ss.sort(key=lambda c: EFFORT_ORDER.index(c["effort"]) if c["effort"] in EFFORT_ORDER else 99)
        fig.add_trace(go.Scatter(
            x=[c["global"]["avg_cost_usd"] for c in ss],
            y=[c["global"]["target_recall"] for c in ss],
            mode="lines+markers+text",
            text=[c["effort"] for c in ss],
            textposition="top center",
            marker=dict(size=14, color=SDK_COLORS.get(sdk, "#888"),
                        line=dict(width=2, color="white")),
            line=dict(color=SDK_COLORS.get(sdk, "#888"), width=2),
            name=f"{sdk} SDK",
            hovertemplate=(
                "<b>%{text} effort</b><br>"
                "Cost: $%{x:.2f}/bug<br>"
                "Target recall: %{y:.0%}<br>"
                "<extra></extra>"
            ),
        ))
    fig.update_layout(
        title="BugsInPy — Recall vs Cost (target = matches maintainer fix)",
        xaxis_title="Avg cost per bug (USD)",
        yaxis_title="Target recall",
        yaxis_tickformat=".0%",
        template="plotly_white",
        height=500,
    )
    _save(fig, "bugsinpy_recall_vs_cost.html", "BugsInPy Pareto")


def chart_bugsinpy_recall_by_effort(cells: list[dict]) -> None:
    fig = go.Figure()
    by_sdk: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        by_sdk[c["sdk"]].append(c)
    for sdk, ss in by_sdk.items():
        ss.sort(key=lambda c: EFFORT_ORDER.index(c["effort"]) if c["effort"] in EFFORT_ORDER else 99)
        fig.add_trace(go.Scatter(
            x=[c["effort"] for c in ss],
            y=[c["global"]["target_recall"] for c in ss],
            mode="lines+markers", name=f"{sdk} · target",
            line=dict(color=SDK_COLORS.get(sdk, "#888"), width=2.5),
            marker=dict(size=12),
        ))
        fig.add_trace(go.Scatter(
            x=[c["effort"] for c in ss],
            y=[c["global"]["broad_recall"] for c in ss],
            mode="lines+markers", name=f"{sdk} · broad (any real bug)",
            line=dict(color=SDK_COLORS.get(sdk, "#888"), width=2, dash="dash"),
            marker=dict(size=12, symbol="circle-open"),
            opacity=0.7,
        ))
    fig.update_layout(
        title="BugsInPy — Recall by Reasoning Effort",
        xaxis_title="Reasoning effort",
        yaxis_title="Recall",
        yaxis_tickformat=".0%",
        yaxis_range=[0, 0.7],
        template="plotly_white",
        height=500,
    )
    _save(fig, "bugsinpy_recall_by_effort.html", "Recall by effort")


def chart_bugsinpy_project_heatmap(cells: list[dict]) -> None:
    cell_labels = [f"{c['sdk']}/{c['effort']}" for c in cells]
    projects = sorted({p for c in cells for p in c["by_project"]})
    z = []
    for p in projects:
        row = []
        for c in cells:
            agg = c["by_project"].get(p, {})
            row.append(agg.get("target_recall") if agg.get("n", 0) > 0 else None)
        z.append(row)
    text = [[f"{(v or 0):.0%}" if v is not None else "" for v in row] for row in z]
    fig = go.Figure(data=go.Heatmap(
        z=z, x=cell_labels, y=projects,
        colorscale="RdYlGn", zmin=0, zmax=1,
        text=text, texttemplate="%{text}", textfont=dict(size=11),
        hovertemplate="Project: %{y}<br>Cell: %{x}<br>Recall: %{text}<extra></extra>",
        colorbar=dict(title="Target<br>recall", tickformat=".0%"),
    ))
    fig.update_layout(
        title="BugsInPy — Target Recall by Project × (SDK, effort)",
        template="plotly_white",
        height=max(500, 30 * len(projects) + 200),
    )
    _save(fig, "bugsinpy_project_heatmap.html", "BugsInPy heatmap")


def chart_martian_precision_recall(our_cells: list[dict], commercials: dict) -> None:
    fig = go.Figure()
    # Commercials
    if commercials:
        fig.add_trace(go.Scatter(
            x=[m["precision"] for m in commercials.values()],
            y=[m["recall"] for m in commercials.values()],
            mode="markers+text",
            text=list(commercials.keys()),
            textposition="top right",
            marker=dict(size=14, color=COMMERCIAL_COLOR, symbol="circle-open",
                        line=dict(width=2)),
            name="Commercial (Martian published)",
            hovertemplate=(
                "<b>%{text}</b><br>Precision: %{x:.0%}<br>"
                "Recall: %{y:.0%}<extra></extra>"
            ),
        ))
    # Ours
    for c in our_cells:
        if c["micro_precision"] is None:
            continue
        color = SDK_COLORS.get(c["sdk"], "#888")
        fig.add_trace(go.Scatter(
            x=[c["micro_precision"]],
            y=[c["micro_recall"]],
            mode="markers+text",
            text=[_our_martian_label(c)],
            textposition="top right",
            marker=dict(size=18, color=color, symbol="diamond",
                        line=dict(width=2, color="white")),
            name=_our_martian_label(c),
            showlegend=True,
            hovertemplate=(
                "<b>%{text}</b><br>Precision: %{x:.0%}<br>"
                "Recall: %{y:.0%}<extra></extra>"
            ),
        ))
    fig.update_layout(
        title="Martian Sentry — Precision vs Recall (our cells vs commercial tools)",
        xaxis_title="Precision (matches / candidates, micro-avg)",
        yaxis_title="Recall (golden bugs caught, micro-avg)",
        xaxis_tickformat=".0%", yaxis_tickformat=".0%",
        xaxis_range=[0, 1.05], yaxis_range=[0, 1.05],
        template="plotly_white",
        height=600,
    )
    _save(fig, "martian_precision_recall.html", "Martian P-R scatter")


def chart_martian_f1_bars(our_cells: list[dict], commercials: dict) -> None:
    bars = []
    for tool, m in commercials.items():
        bars.append({"name": tool, "f1": m["f1"], "kind": "commercial",
                     "color": COMMERCIAL_COLOR})
    for c in our_cells:
        bars.append({"name": _our_martian_label(c),
                     "f1": c["micro_f1"], "kind": "ours",
                     "color": SDK_COLORS.get(c["sdk"], "#888")})
    bars.sort(key=lambda b: -b["f1"])

    fig = go.Figure(data=go.Bar(
        x=[b["name"] for b in bars],
        y=[b["f1"] for b in bars],
        marker_color=[b["color"] for b in bars],
        text=[f"{b['f1']:.0%}" for b in bars],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>F1: %{y:.0%}<extra></extra>",
    ))
    fig.update_layout(
        title="Martian Sentry — F1 Score Ranking (our cells vs commercial tools)",
        xaxis_title="Tool",
        yaxis_title="F1 (micro)",
        yaxis_tickformat=".0%",
        yaxis_range=[0, max((b["f1"] for b in bars), default=1) * 1.2],
        template="plotly_white",
        height=550,
        xaxis_tickangle=-30,
    )
    _save(fig, "martian_f1_bars.html", "Martian F1 ranking")


def chart_matrix_summary_table(bugsinpy: list[dict], martian: list[dict]) -> None:
    rows: list[tuple[str, ...]] = []
    rows.append(("Bench", "SDK", "Effort", "N", "Target R", "Broad R",
                 "Precision", "F1", "$/bug", "$/target"))
    for c in bugsinpy:
        g = c["global"]
        rows.append((
            "BugsInPy", c["sdk"], c["effort"], str(g["n"]),
            f"{g['target_recall']:.0%}",
            f"{g['broad_recall']:.0%}",
            f"{(g.get('precision_strict') or 0):.0%}",
            f"{g['f1_strict']:.0%}",
            f"${g['avg_cost_usd']:.2f}",
            f"${g['cost_per_target_bug']:.2f}" if g.get('cost_per_target_bug') else "—",
        ))
    for c in martian:
        rows.append((
            "Martian", c["sdk"], c["effort"], str(c["n_prs"]),
            f"{c['micro_recall']:.0%}",
            "—",  # broad recall not defined for martian
            f"{(c.get('micro_precision') or 0):.0%}" if c.get('micro_precision') is not None else "—",
            f"{c['micro_f1']:.0%}",
            "—",  # martian doesn't track per-bug cost in scoring (in meta though)
            "—",
        ))
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(rows[0]),
                    fill_color="#1f77b4", font=dict(color="white"), align="center"),
        cells=dict(values=list(zip(*rows[1:])),
                   fill_color=[["#f5f5f5" if i % 2 else "white" for i in range(len(rows) - 1)]],
                   align="center", height=28),
    )])
    fig.update_layout(
        title="Full Bench Matrix — both BugsInPy + Martian cells",
        template="plotly_white",
        height=max(400, 50 + 30 * len(rows)),
    )
    _save(fig, "matrix_summary_table.html", "Summary table")


# ----------------------------------------------------------- main --


def main() -> None:
    print(f"Building visualizations into {OUT_DIR}…")
    bugsinpy = _load_bugsinpy_cells()
    martian = _load_martian_cells()
    commercials = _load_martian_commercials()

    print(f"  BugsInPy cells:         {len(bugsinpy)}")
    print(f"  Martian (ours) cells:   {len(martian)}")
    print(f"  Martian commercials:    {len(commercials)} tools")

    if bugsinpy:
        chart_bugsinpy_recall_vs_cost(bugsinpy)
        chart_bugsinpy_recall_by_effort(bugsinpy)
        chart_bugsinpy_project_heatmap(bugsinpy)
    if martian or commercials:
        chart_martian_precision_recall(martian, commercials)
        chart_martian_f1_bars(martian, commercials)
    chart_matrix_summary_table(bugsinpy, martian)

    print(f"\nAll charts → {OUT_DIR}")
    if (OUT_DIR / "matrix_summary_table.html").exists():
        print(f"Open: file://{(OUT_DIR / 'matrix_summary_table.html').resolve()}")


if __name__ == "__main__":
    main()
