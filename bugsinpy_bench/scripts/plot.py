"""Plot the BugsInPy bench matrix.

Reads multiple sweep_<id>/scores.json files (one per cell of
SDK × effort) and emits the pitch-deck charts:

  recall_vs_cost.png      Recall-vs-cost Pareto. Each (sdk, effort) is
                          a point. The headline chart.
  recall_by_effort.png    Lines per SDK, X = effort, Y = recall.
                          Shows the diminishing-returns curve.
  per_project_heatmap.png Projects × cells, color = target recall.
  precision_recall.png    P-R scatter, one point per cell.
  cost_distribution.png   Boxplot of $/bug per cell.
  metric_summary.png      Wide table: recall · precision · F1 · cost
                          · latency for every cell.

Each plot is self-titled with sweep IDs + git rev so you can trace any
chart back to the runs that produced it.

Usage:
    uv run python bugsinpy_bench/scripts/plot.py \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_low \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_high \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_max \\
        bugsinpy_bench/results/sweep_2026-05-04_client_low \\
        bugsinpy_bench/results/sweep_2026-05-04_client_high \\
        bugsinpy_bench/results/sweep_2026-05-04_client_max
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FIGURES_DIR = PROJECT_ROOT / "bugsinpy_bench" / "figures"

EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]

SDK_COLORS = {
    "agent":  "#1f77b4",  # blue
    "client": "#d62728",  # red
}


def _load_sweeps(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        scores = p / "scores.json"
        if not scores.is_file():
            print(f"  warning: {scores} not found, skipping", file=sys.stderr)
            continue
        out.append(json.loads(scores.read_text()))
    out.sort(key=lambda s: (s["sdk"], EFFORT_ORDER.index(s["effort"]) if s["effort"] in EFFORT_ORDER else 99))
    return out


def _cell_label(s: dict) -> str:
    return f"{s['sdk']}/{s['effort']}"


def _sweep_id_str(sweeps: list[dict]) -> str:
    rev = sweeps[0].get("harness_git_rev", "?")[:7] if sweeps else "?"
    return f"{len(sweeps)} sweeps · harness {rev}"


# ----------------------------- charts -------------------------------------- #


def plot_recall_vs_cost(sweeps: list[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for s in sweeps:
        g = s["global"]
        color = SDK_COLORS.get(s["sdk"], "#888")
        ax.scatter(g["avg_cost_usd"], g["target_recall"], s=120, color=color,
                   edgecolor="white", zorder=3)
        ax.annotate(_cell_label(s),
                    xy=(g["avg_cost_usd"], g["target_recall"]),
                    xytext=(8, 4), textcoords="offset points",
                    fontsize=9)

    # Connect same-SDK points by effort to show curve.
    by_sdk: dict[str, list[dict]] = {}
    for s in sweeps:
        by_sdk.setdefault(s["sdk"], []).append(s)
    for sdk, ss in by_sdk.items():
        ss = sorted(ss, key=lambda x: EFFORT_ORDER.index(x["effort"]) if x["effort"] in EFFORT_ORDER else 99)
        xs = [s["global"]["avg_cost_usd"] for s in ss]
        ys = [s["global"]["target_recall"] for s in ss]
        ax.plot(xs, ys, color=SDK_COLORS.get(sdk, "#888"), alpha=0.4, zorder=2)

    ax.set_xlabel("Avg cost per bug (USD)")
    ax.set_ylabel("Target recall (LLM-judge match w/ maintainer)")
    ax.set_title(f"Recall vs Cost — {_sweep_id_str(sweeps)}",
                 loc="left", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


def plot_recall_by_effort(sweeps: list[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    by_sdk: dict[str, list[dict]] = {}
    for s in sweeps:
        by_sdk.setdefault(s["sdk"], []).append(s)
    for sdk, ss in by_sdk.items():
        ss = sorted(ss, key=lambda x: EFFORT_ORDER.index(x["effort"]) if x["effort"] in EFFORT_ORDER else 99)
        xs = [s["effort"] for s in ss]
        ys_target = [s["global"]["target_recall"] for s in ss]
        ys_broad = [s["global"]["broad_recall"] for s in ss]
        color = SDK_COLORS.get(sdk, "#888")
        ax.plot(xs, ys_target, "o-", color=color, label=f"{sdk} · target")
        ax.plot(xs, ys_broad, "o--", color=color, alpha=0.6, label=f"{sdk} · broad")
    ax.set_xlabel("Reasoning effort")
    ax.set_ylabel("Recall")
    ax.set_title(f"Recall by effort — {_sweep_id_str(sweeps)}",
                 loc="left", fontsize=11)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


def plot_per_project_heatmap(sweeps: list[dict], out: Path) -> None:
    if not sweeps:
        return
    cells = [_cell_label(s) for s in sweeps]
    projects = sorted({p for s in sweeps for p in s["by_project"]})
    matrix = [
        [s["by_project"].get(p, {}).get("target_recall", 0.0) for s in sweeps]
        for p in projects
    ]
    fig, ax = plt.subplots(figsize=(max(7, 0.7 * len(cells) + 4),
                                    max(4, 0.35 * len(projects) + 1.5)))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(len(cells)))
    ax.set_xticklabels(cells, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(projects)))
    ax.set_yticklabels(projects, fontsize=9)
    ax.set_title(f"Target recall by project · {_sweep_id_str(sweeps)}",
                 loc="left", fontsize=11)
    fig.colorbar(im, ax=ax, label="target recall")
    # Annotate cells
    for i, p in enumerate(projects):
        for j, _ in enumerate(cells):
            v = matrix[i][j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center",
                    fontsize=8, color="black" if 0.3 < v < 0.7 else "white")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


def plot_precision_recall(sweeps: list[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    for s in sweeps:
        g = s["global"]
        if g.get("precision_strict") is None:
            continue
        color = SDK_COLORS.get(s["sdk"], "#888")
        ax.scatter(g["precision_strict"], g["target_recall"],
                   s=140, color=color, edgecolor="white", zorder=3)
        ax.annotate(_cell_label(s),
                    xy=(g["precision_strict"], g["target_recall"]),
                    xytext=(6, 4), textcoords="offset points", fontsize=9)
    ax.set_xlabel("Precision (strict — matches maintainer / findings)")
    ax.set_ylabel("Recall (target)")
    ax.set_title(f"Precision vs Recall — {_sweep_id_str(sweeps)}",
                 loc="left", fontsize=11)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


def plot_metric_summary_table(sweeps: list[dict], out: Path) -> None:
    cells = [_cell_label(s) for s in sweeps]
    rows = [
        ["target recall"]    + [f"{s['global']['target_recall']:.0%}" for s in sweeps],
        ["broad recall"]     + [f"{s['global']['broad_recall']:.0%}" for s in sweeps],
        ["precision strict"] + [
            f"{s['global']['precision_strict']:.0%}" if s['global'].get('precision_strict') is not None else "-"
            for s in sweeps
        ],
        ["F1 (strict)"]      + [f"{s['global']['f1_strict']:.0%}" for s in sweeps],
        ["avg cost / bug"]   + [f"${s['global']['avg_cost_usd']:.2f}" for s in sweeps],
        ["cost / target"]    + [
            f"${s['global']['cost_per_target_bug']:.2f}" if s['global'].get('cost_per_target_bug') else "-"
            for s in sweeps
        ],
        ["avg latency (s)"]  + [f"{s['global']['avg_latency_s']:.0f}" for s in sweeps],
        ["avg findings"]     + [f"{s['global']['avg_findings']}" for s in sweeps],
    ]
    fig, ax = plt.subplots(figsize=(max(7, 1.3 * len(cells) + 3),
                                    1 + 0.4 * len(rows)))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=[""] + cells,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.4)
    ax.set_title(f"Bench summary — {_sweep_id_str(sweeps)}",
                 loc="left", fontsize=11, pad=14)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweeps", nargs="+",
                    help="One or more sweep_<id>/ directories.")
    ap.add_argument("--figures-dir", default=str(DEFAULT_FIGURES_DIR))
    args = ap.parse_args()
    paths = [Path(p) for p in args.sweeps]
    sweeps = _load_sweeps(paths)
    if not sweeps:
        sys.exit("no sweeps with scores.json found")

    figs = Path(args.figures_dir)
    figs.mkdir(parents=True, exist_ok=True)

    plot_recall_vs_cost(sweeps, figs / "recall_vs_cost.png")
    plot_recall_by_effort(sweeps, figs / "recall_by_effort.png")
    plot_per_project_heatmap(sweeps, figs / "per_project_heatmap.png")
    plot_precision_recall(sweeps, figs / "precision_recall.png")
    plot_metric_summary_table(sweeps, figs / "metric_summary.png")


if __name__ == "__main__":
    main()
