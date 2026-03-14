#!/usr/bin/env python3
"""
Generates benchmark-percentile-curves.png — dual-panel latency percentile
curve chart (dark theme) from the 2026 heptathlon benchmark results.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent.parent / "images" / "benchmark-percentile-curves.png"

# ── Data ──────────────────────────────────────────────────────────────────────
# (p50, p90, p99, p99.9) in ms; None = wrk2 timed out / no data

SMALL = {
    "Java Quarkus (VT)":      (3.23,   4.70,   53.82,  254.08),
    "Kotlin Quarkus (CR)":    (3.51,   6.62,   21.26,  141.57),
    "Spring Boot (VT)":       (3.83,   7.76,   39.01,  133.25),
    "Go (Fiber)":             (4.06,   7.05,   24.67,   87.23),
    "Node.js EL":             (3.93,   5.86,  294.65,  671.23),
    "Node.js WT":             (4.95,  13.26,   47.20,  138.24),
    "Python (FastAPI)":       (13.36, 2280.0, 3090.0, 3570.0),
}

LARGE = {
    "Java Quarkus (VT)":      (5.79,    7.50,   65.79,  195.84),
    "Kotlin Quarkus (CR)":    (4.88,   18.91,  486.65,  708.09),
    "Spring Boot (VT)":       (1850.0, 5110.0, 6140.0, 6810.0),
    "Go (Fiber)":             (5.11,   15.04,   43.04,  236.67),
    "Node.js EL":             (35650.0, None,   None,   None),
    "Node.js WT":             (36830.0, None,   None,   None),
    "Python (FastAPI)":       (33340.0, None,   None,   None),
}

COLORS = {
    "Java Quarkus (VT)":   "#2196F3",   # blue
    "Kotlin Quarkus (CR)": "#FF9800",   # orange
    "Spring Boot (VT)":    "#9C27B0",   # purple
    "Go (Fiber)":          "#00BCD4",   # cyan
    "Node.js EL":          "#4CAF50",   # green
    "Node.js WT":          "#F44336",   # red
    "Python (FastAPI)":    "#FFEB3B",   # yellow
}

MARKERS = {
    "Java Quarkus (VT)":   "o",
    "Kotlin Quarkus (CR)": "s",
    "Spring Boot (VT)":    "^",
    "Go (Fiber)":          "D",
    "Node.js EL":          "v",
    "Node.js WT":          "P",
    "Python (FastAPI)":    "*",
}

PCTS      = ["p50", "p90", "p99", "p99.9"]
PCT_X     = [0, 1, 2, 3]
PCT_LABEL = ["p50", "p90", "p99", "p99.9"]

BG   = "#0d1117"
GRID = "#21262d"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(v):
    if v is None:
        return ""
    if v >= 1000:
        return f"{v/1000:.1f} s"
    if v >= 1:
        return f"{v:.1f} ms"
    return f"{v:.2f} ms"


def _plot_panel(ax, data, title, subtitle):
    ax.set_facecolor(BG)
    ax.set_yscale("log")
    # Two-line title: bold white + smaller gray via two separate Text artists
    ax.set_title("", pad=34)   # reserve vertical space
    ax.text(0.5, 1.10, title,    transform=ax.transAxes, ha="center", va="bottom",
            color="white",   fontsize=11, fontweight="bold")
    ax.text(0.5, 1.02, subtitle, transform=ax.transAxes, ha="center", va="bottom",
            color="#8b949e", fontsize=8)

    ax.set_xticks(PCT_X)
    ax.set_xticklabels(PCT_LABEL, color="#c9d1d9", fontsize=10)
    ax.tick_params(axis="y", colors="#c9d1d9", labelsize=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda v, _: (f"{v/1000:.0f} s" if v >= 1000 else f"{v:.0f} ms") if v >= 1 else f"{v:.1f} ms"
    ))
    ax.grid(True, which="both", color=GRID, linewidth=0.6, linestyle="--")
    ax.set_xlim(-0.3, 3.3)
    ax.set_xlabel("Percentile", color="#8b949e", fontsize=9)
    ax.set_ylabel("Latency (log scale)", color="#8b949e", fontsize=9)

    for name, vals in data.items():
        color  = COLORS[name]
        marker = MARKERS[name]
        xs, ys = [], []
        for i, v in enumerate(vals):
            if v is not None:
                xs.append(PCT_X[i])
                ys.append(v)

        if not ys:
            continue

        ax.plot(xs, ys, color=color, marker=marker,
                linewidth=1.8, markersize=6, label=name, zorder=3)

        # value labels
        for x, y, v in zip(xs, ys, [vals[i] for i in range(len(vals)) if vals[i] is not None]):
            offset_y = y * 1.18
            ax.annotate(
                _fmt(v),
                xy=(x, y), xytext=(x, offset_y),
                color=color, fontsize=6.5, ha="center", va="bottom",
                zorder=4,
            )

    # legend
    ax.legend(
        loc="upper left", fontsize=7.5,
        facecolor="#161b22", edgecolor="#30363d",
        labelcolor="white", framealpha=0.9,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(16, 7))
fig.patch.set_facecolor(BG)

fig.suptitle(
    "Heptatlón de Performance — Latency Percentile Curves\n"
    "wrk2 · 500 req/s · 90 s · EC2 same-region · AWS App Runner (1 vCPU / 2 GB) · March 2026",
    color="white", fontsize=12, fontweight="bold", y=1.01,
)

_plot_panel(
    ax_a, SMALL,
    "Scenario A — Small Tree (7 nodes)",
    "All 7 services sustain 500 req/s · framework overhead dominates",
)

_plot_panel(
    ax_b, LARGE,
    "Scenario B — Large Tree (500 nodes, ~15 KB)",
    "Node.js / Python saturate under CPU load · JVM + Go stay stable",
)

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=BG)
plt.close()
print(f"Saved → {OUT}")
