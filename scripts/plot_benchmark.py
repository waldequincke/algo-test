#!/usr/bin/env python3
"""
Visualize wrk2 pentathlon benchmark results.
Run A: 7-node BST   (light payload — 37 µs BFS)
Run B: 499-node BST (heavy payload — realistic production load)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── Data ──────────────────────────────────────────────────────────────────────

PERCENTILES   = ["p50", "p90", "p99", "p99.9", "p99.99"]
PCT_X         = [50, 90, 99, 99.9, 99.99]   # numeric x-axis for log scale

SERVICES = [
    ("Java Quarkus (VT)",    "#1f77b4", "o"),
    ("Kotlin Quarkus (CR)",  "#ff7f0e", "s"),
    ("Spring Boot",          "#9467bd", "^"),
    ("Node.js EL",           "#2ca02c", "D"),
    ("Node.js WT",           "#d62728", "X"),
]

# latency in ms  [p50, p90, p99, p99.9, p99.99]
RUN_A = {
    "Java Quarkus (VT)":   [3.080,   4.140,   50.560,    137.090,   159.100],
    "Kotlin Quarkus (CR)": [2.970,   4.310,   23.340,     83.460,   122.050],
    "Spring Boot":         [4.780,  11.330,   19.810,     57.410,   577.530],
    "Node.js EL":          [3.540,   4.640,   15.570,    115.710,   566.270],
    "Node.js WT":          [5.120,  31.340,  911.360,  1_210.000, 1_380.000],
}

RUN_B = {
    "Java Quarkus (VT)":   [   3.690,    5.030,    23.500,    110.460,    186.880],
    "Kotlin Quarkus (CR)": [   4.390,    5.610,   249.730,    507.390,    630.270],
    "Spring Boot":         [   5.990,  842.240, 1_930.000,  2_380.000,  2_500.000],
    "Node.js EL":          [11_900, 22_890,   30_260,    34_570,    35_420],
    "Node.js WT":          [32_600, 55_200,   60_000,    60_600,    60_600],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_ms(v):
    if v >= 1_000:
        return f"{v/1_000:.1f} s"
    return f"{v:.1f} ms"

def add_value_labels(ax, x_vals, y_vals, color):
    for xv, yv in zip(x_vals, y_vals):
        ax.annotate(
            fmt_ms(yv),
            xy=(xv, yv), xytext=(0, 7),
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=6.5, color=color, alpha=0.85,
        )

# ── Figure: two side-by-side charts ──────────────────────────────────────────

fig, axes = plt.subplots(1, 2, figsize=(18, 7))
fig.patch.set_facecolor("#0d1117")

for ax, data, title, note in [
    (axes[0], RUN_A,
     "Run A — 7-node BST  (light · 37 µs BFS)",
     "All 5 services sustain 500 req/s  ·  framework overhead dominates"),
    (axes[1], RUN_B,
     "Run B — 499-node BST  (heavy · ~10 KB JSON)",
     "Node.js saturates event loop  ·  Java Virtual Threads win every percentile"),
]:
    ax.set_facecolor("#161b22")
    ax.spines[:].set_color("#30363d")
    ax.tick_params(colors="#8b949e")
    ax.yaxis.label.set_color("#8b949e")
    ax.xaxis.label.set_color("#8b949e")
    ax.title.set_color("#e6edf3")

    for label, color, marker in SERVICES:
        y = data[label]
        ax.plot(
            PCT_X, y,
            color=color, marker=marker,
            linewidth=2, markersize=7,
            label=label, zorder=3,
        )
        add_value_labels(ax, PCT_X, y, color)

    ax.set_yscale("log")
    ax.set_xscale("log")
    ax.set_xlim(40, 120)
    ax.set_xticks(PCT_X)
    ax.set_xticklabels(PERCENTILES, fontsize=9)
    ax.xaxis.set_minor_locator(ticker.NullLocator())

    # y-axis: human-readable ms / s labels
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda v, _: fmt_ms(v)
    ))
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())

    ax.set_xlabel("Percentile", fontsize=11)
    ax.set_ylabel("Latency  (log scale)", fontsize=11)
    ax.set_title(f"{title}\n{note}", fontsize=12, pad=14, color="#e6edf3")
    ax.grid(True, which="major", color="#21262d", linewidth=0.8, zorder=0)
    ax.grid(True, which="minor", color="#161b22", linewidth=0.4, zorder=0)

    legend = ax.legend(
        framealpha=0.15, facecolor="#161b22",
        edgecolor="#30363d", labelcolor="#c9d1d9",
        fontsize=9, loc="upper left",
    )

# ── Annotation: the dramatic gap in Run B ────────────────────────────────────
axes[1].annotate(
    "Node.js WT\np50 = 32.6 s",
    xy=(50, 32_600), xytext=(55, 8_000),
    arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.4),
    fontsize=8.5, color="#d62728",
)
axes[1].annotate(
    "Java stays flat\np99.99 = 187 ms",
    xy=(99.99, 186.880), xytext=(95, 50),
    arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=1.4),
    fontsize=8.5, color="#1f77b4",
)

fig.suptitle(
    "Pentathlon Benchmark — Latency Percentile Curves\n"
    "wrk2 · 500 req/s · 90 s · EC2 same-region · AWS App Runner (1 vCPU / 2 GB) · March 2026",
    fontsize=13, color="#e6edf3", y=1.01,
)

plt.tight_layout()
out = "/Users/waldemar/Documents/dev/java-kotlin/quarkus/algo-test/images/benchmark-percentile-curves.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")
