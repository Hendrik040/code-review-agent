"""Figures for bugsinpy_bench/EXPERIMENT_LOG.md, drawn from committed results.

Reads bugsinpy_bench/routing/triage_scores.json (written by route_and_score.py)
and writes PNGs to bugsinpy_bench/experiment_figures/.

Usage:
    uv run python bugsinpy_bench/scripts/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
SCORES = ROOT / "bugsinpy_bench" / "routing" / "triage_scores.json"
OUT = ROOT / "bugsinpy_bench" / "experiment_figures"

# Categorical palette, fixed order (blue, orange, aqua, yellow, violet).
BLUE, ORANGE, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
INK, MUTED, GRID, SURFACE, EMPTY = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb", "#ecebe6"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def cost_vs_found(s: dict) -> None:
    S = s["setups"]
    n = 30.0
    pts = [  # (setup key, label, colour, marker, hollow, label side)
        ("all_haiku_local", "Haiku 5.5 medium", BLUE, "o", False, "r"),
        ("all_haiku_cloud", "", BLUE, "o", True, ""),
        ("all_sonnet_local", "Sonnet 5.5 high", ORANGE, "^", False, "r"),
        ("all_sonnet_cloud", "", ORANGE, "^", True, ""),
        ("all_opus_max", "Opus 4.7 max", AQUA, "s", False, "r"),
        ("all_opus_high", "Opus 4.7 high", AQUA, "s", False, "r"),
        ("triage_deep_opus_max_local", "Triage, deep 4.7 max", VIOLET, "D", False, "a"),
        ("triage_deep_opus_max_cloud", "", VIOLET, "D", True, ""),
        ("triage_deep_opus_high_local", "Triage, deep 4.7 high", VIOLET, "D", False, "b"),
        ("triage_deep_opus_high_cloud", "", VIOLET, "D", True, ""),
        ("triage_deep_opus_opus55_high_local", "Triage, deep 5.5 high", VIOLET, "D", False, "b"),
        ("triage_deep_opus_opus55_high_cloud", "", VIOLET, "D", True, ""),
        ("all_opus55_high", "Opus 5.5 high", YELLOW, "*", False, "r"),
    ]
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=160)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for key, label, colour, marker, hollow, side in pts:
        if key not in S:
            continue
        x, y = S[key]["cost_usd"] / n, S[key]["found"]
        size = 220 if marker == "*" else 70
        ax.scatter([x], [y], s=size, marker=marker, linewidths=1.6, zorder=3,
                   facecolors=SURFACE if hollow else colour, edgecolors=colour)
        if label:
            # side: l/r = left/right of the mark, a/b = centred above/below it
            dx, dy, ha = {"l": (-9, 0, "right"), "r": (9, 0, "left"),
                          "a": (0, 11, "center"), "b": (0, -12, "center")}[side]
            ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points",
                        ha=ha, va="center", fontsize=9, color=INK)
    ax.set_xscale("log")
    ax.set_xlim(0.003, 2)
    ax.set_ylim(8, 24)
    ticks = [0.005, 0.01, 0.05, 0.1, 0.5, 1]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
    ax.set_xlabel("Review cost per bug (USD, log scale)")
    ax.set_ylabel("Bugs found (of 30)")
    ax.set_title("Pilot, 30 BugsInPy bugs: bugs found against cost per bug", loc="left", fontsize=11, color=INK)
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=BLUE, label="Haiku 5.5 medium"),
        plt.Line2D([], [], marker="^", ls="", color=ORANGE, label="Sonnet 5.5 high"),
        plt.Line2D([], [], marker="s", ls="", color=AQUA, label="Opus 4.7, no triage (May)"),
        plt.Line2D([], [], marker="*", ls="", color=YELLOW, markersize=12, label="Opus 5.5 high, no triage"),
        plt.Line2D([], [], marker="D", ls="", color=VIOLET, label="Jev triage"),
        plt.Line2D([], [], marker="o", ls="", markerfacecolor=SURFACE, markeredgecolor=MUTED, label="hollow = cloud run"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8.5, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "pilot30_cost_vs_found.png")
    plt.close(fig)


def overlap_grid(s: dict) -> None:
    arms = [("haiku_local", "Haiku 5.5"), ("haiku_cloud", "Haiku 5.5\ncloud"),
            ("sonnet_local", "Sonnet 5.5"), ("sonnet_cloud", "Sonnet 5.5\ncloud"),
            ("opus_max", "Opus 4.7\nmax"), ("opus_high", "Opus 4.7\nhigh"),
            ("opus_opus55_high", "Opus 5.5\nhigh")]
    arms = [a for a in arms if a[0] in s["per_bug"][0]]
    rows = sorted(s["per_bug"], key=lambda r: (-sum(r[a]["found"] for a, _ in arms), r["label"].lower()))
    fig, ax = plt.subplots(figsize=(6.6, 9.2), dpi=160)
    for i, r in enumerate(rows):
        for j, (a, _) in enumerate(arms):
            ax.add_patch(plt.Rectangle((j + 0.06, i + 0.08), 0.88, 0.84,
                                       color=BLUE if r[a]["found"] else EMPTY, linewidth=0))
        ax.text(len(arms) + 0.2, i + 0.5, f"{sum(r[a]['found'] for a, _ in arms)}/{len(arms)}",
                va="center", fontsize=8.5, color=MUTED)
    ax.set_xlim(0, len(arms) + 0.9)
    ax.set_ylim(len(rows), -0.2)
    ax.set_yticks([i + 0.5 for i in range(len(rows))], [r["label"] for r in rows], fontsize=8.5)
    ax.set_xticks([j + 0.5 for j in range(len(arms))], [n for _, n in arms], fontsize=8.5)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    totals = [sum(r[a]["found"] for r in rows) for a, _ in arms]
    for j, t in enumerate(totals):
        ax.text(j + 0.5, len(rows) + 0.6, str(t), ha="center", va="top", fontsize=9, color=INK)
    ax.text(-0.1, len(rows) + 0.6, "found (of 30)", ha="right", va="top", fontsize=8.5, color=MUTED)
    ax.legend(handles=[Patch(color=BLUE, label="found the maintainer's bug"), Patch(color=EMPTY, label="missed")],
              loc="upper center", bbox_to_anchor=(0.45, -0.045), ncol=2, frameon=False, fontsize=8.5)
    ax.set_title("Pilot, 30 BugsInPy bugs: which run found which bug", loc="left", fontsize=11, color=INK, pad=34)
    fig.tight_layout()
    fig.savefig(OUT / "pilot30_overlap.png")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    s = json.loads(SCORES.read_text())
    cost_vs_found(s)
    overlap_grid(s)
    for p in sorted(OUT.glob("*.png")):
        print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
