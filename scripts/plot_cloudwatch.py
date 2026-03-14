#!/usr/bin/env python3
"""
Fetches AWS App Runner CloudWatch metrics for all 7 services
and generates dark-themed PNG charts.

Usage:
    python3 scripts/plot_cloudwatch.py

Requires: boto3, matplotlib
    pip3 install --user boto3 matplotlib
"""

import os
import sys
import datetime
from pathlib import Path
from typing import Optional

import boto3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# ── Config ────────────────────────────────────────────────────────────────────

REGION       = "us-east-1"
NAMESPACE    = "AWS/AppRunner"
SCRIPT_DIR   = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
OUT_DIR      = PROJECT_ROOT / "images"

# Default lookback when called standalone (covers full heptatlón + buffer)
LOOKBACK_MINUTES = 120

# Service names + IDs (both dimensions required by App Runner CloudWatch metrics)
SERVICES = {
    "Java Quarkus (VT)":   ("tree-service-java",       "5efe5c38881d4617b49c5747e232a323"),
    "Kotlin Quarkus (CR)": ("tree-service-kotlin",     "e72d7808e22d4ac7ab235ae7cef8fbcb"),
    "Spring Boot (VT)":    ("tree-service-spring",     "91c695da9c07454b804117f013576659"),
    "Go (Fiber)":          ("tree-service-go",         "f8431123068b498ab6b99e66f19f83e0"),
    "Node.js EL":          ("tree-service-nodejs",     "ea973270bcbe46d29e1f9c5dd1efc4b8"),
    "Node.js WT":          ("tree-service-nodejs-wt",  "a3f6cd99148d4e88bdbdf45a39ad743c"),
    "Python (FastAPI)":    ("tree-service-python",     "83b2c2863ac44af99069a9f5dcf0f87b"),
}

COLORS = {
    "Java Quarkus (VT)":   "#2196F3",
    "Kotlin Quarkus (CR)": "#FF9800",
    "Spring Boot (VT)":    "#9C27B0",
    "Go (Fiber)":          "#00BCD4",
    "Node.js EL":          "#4CAF50",
    "Node.js WT":          "#F44336",
    "Python (FastAPI)":    "#FFEB3B",
}

# ── Dark theme ────────────────────────────────────────────────────────────────

BG   = "#0d1117"
GRID = "#21262d"
TEXT = "#c9d1d9"


def _dark(fig, axes):
    fig.patch.set_facecolor(BG)
    for ax in (axes if hasattr(axes, "__iter__") else [axes]):
        ax.set_facecolor(BG)
        ax.tick_params(colors=TEXT, labelsize=8)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        ax.title.set_color(TEXT)
        ax.grid(True, color=GRID, ls="--", alpha=0.5, linewidth=0.6)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID)
        leg = ax.get_legend()
        if leg:
            leg.get_frame().set_facecolor("#161b22")
            leg.get_frame().set_edgecolor("#30363d")
            for t in leg.get_texts():
                t.set_color(TEXT)


def _fmt_xaxis(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", color=TEXT)


# ── CloudWatch helpers ────────────────────────────────────────────────────────

cw = boto3.client("cloudwatch", region_name=REGION)


def get_metric(service_name: str, service_id: str, metric: str, stat: str,
               period: int = 60,
               extended_stat: Optional[str] = None,
               start: Optional[datetime.datetime] = None,
               end: Optional[datetime.datetime] = None) -> tuple:
    """Returns (timestamps, values) lists."""
    if end is None:
        end = datetime.datetime.now(datetime.timezone.utc)
    if start is None:
        start = end - datetime.timedelta(minutes=LOOKBACK_MINUTES)

    kwargs = dict(
        Namespace  = NAMESPACE,
        MetricName = metric,
        Dimensions = [
            {"Name": "ServiceName", "Value": service_name},
            {"Name": "ServiceID",   "Value": service_id},
        ],
        StartTime  = start,
        EndTime    = end,
        Period     = period,
    )
    if extended_stat:
        kwargs["ExtendedStatistics"] = [extended_stat]
    else:
        kwargs["Statistics"] = [stat]

    resp = cw.get_metric_statistics(**kwargs)
    pts  = sorted(resp["Datapoints"], key=lambda d: d["Timestamp"])
    ts   = [p["Timestamp"] for p in pts]
    if extended_stat:
        vals = [p["ExtendedStatistics"].get(extended_stat, 0) for p in pts]
    else:
        vals = [p.get(stat, 0) for p in pts]
    return ts, vals


# ── Individual chart generators ───────────────────────────────────────────────

def _save(fig, name: str):
    path = OUT_DIR / name
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  saved → {path.name}")


def plot_cpu(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "CPUUtilization", "Average", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("CPU Utilization — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("percent · %", color=TEXT)
    ax.set_ylim(0, 105)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "cpu-utilization.png")


def plot_memory(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "MemoryUtilization", "Average", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("Memory Utilization — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("percent · %", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "memory-utilization.png")


def plot_active_instances(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "ActiveInstances", "Maximum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("Active Instances — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("instances · Count", color=TEXT)
    ax.set_ylim(0, 2.5)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "active-instances.png")


def plot_concurrency(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "Concurrency", "Maximum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("Concurrency at Instance — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("concurrent requests · Count", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "concurrency.png")


def plot_request_count(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "Requests", "Sum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("Request Count — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("requests/min · Count", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "request-count-overview.png")


def plot_latency_p99(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "RequestLatency", "p99",
                              extended_stat="p99", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("Request Latency p99 — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("ms · Milliseconds", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "request-latency.png")


def plot_2xx(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "2xxStatusResponses", "Sum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("HTTP 2xx Responses — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("count/min · Count", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "2xx-response-count.png")


def plot_4xx(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "4xxStatusResponses", "Sum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("HTTP 4xx Responses — All 7 Services", color=TEXT, fontsize=11)
    ax.set_ylabel("count/min · Count", color=TEXT)
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "4xx-response-count.png")


def plot_5xx(start=None, end=None):
    fig, ax = plt.subplots(figsize=(12, 4))
    for label, (svc, sid) in SERVICES.items():
        ts, vals = get_metric(svc, sid, "5xxStatusResponses", "Sum", start=start, end=end)
        if ts:
            ax.plot(ts, vals, color=COLORS[label], label=label, linewidth=1.5)
    ax.set_title("HTTP 5xx Responses — All 7 Services (expect zero)", color=TEXT, fontsize=11)
    ax.set_ylabel("count/min · Count", color=TEXT)
    ax.set_ylim(0, max(1, ax.get_ylim()[1]))
    _fmt_xaxis(ax)
    ax.legend(loc="upper left", fontsize=7)
    _dark(fig, ax)
    plt.tight_layout()
    _save(fig, "5xx-response-count-zero.png")


# ── CSV export of raw CloudWatch data ─────────────────────────────────────────

CW_METRICS = [
    ("CPUUtilization",      "Average",  None),
    ("MemoryUtilization",   "Average",  None),
    ("ActiveInstances",     "Maximum",  None),
    ("Concurrency",         "Maximum",  None),
    ("Requests",            "Sum",      None),
    ("2xxStatusResponses",  "Sum",      None),
    ("4xxStatusResponses",  "Sum",      None),
    ("5xxStatusResponses",  "Sum",      None),
    ("RequestLatency",      "p99",      "p99"),
    ("RequestLatency",      "p50",      "p50"),
]


def fetch_cloudwatch_csv(start=None, end=None) -> Path:
    """Fetches all CW_METRICS for all services and saves cloudwatch_results_2026.csv."""
    import csv as csv_mod
    rows = []
    for label, (svc, sid) in SERVICES.items():
        for metric, stat, ext_stat in CW_METRICS:
            col = f"{metric}_{stat}"
            ts_list, val_list = get_metric(svc, sid, metric, stat,
                                           extended_stat=ext_stat,
                                           start=start, end=end)
            for ts, val in zip(ts_list, val_list):
                rows.append({
                    "service":    label,
                    "timestamp":  ts.isoformat(),
                    "metric":     col,
                    "value":      round(val, 4) if isinstance(val, float) else val,
                })

    csv_out = PROJECT_ROOT / "cloudwatch_results_2026.csv"
    if rows:
        with open(csv_out, "w", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=["service", "timestamp", "metric", "value"])
            writer.writeheader()
            writer.writerows(rows)
    return csv_out


# ── Public entry point (importable from benchmark.py) ─────────────────────────

def generate_all(start=None, end=None):
    """Generate all charts + CSV. start/end are UTC datetimes; None = use LOOKBACK_MINUTES."""
    plot_cpu(start, end)
    plot_memory(start, end)
    plot_active_instances(start, end)
    plot_concurrency(start, end)
    plot_request_count(start, end)
    plot_latency_p99(start, end)
    plot_2xx(start, end)
    plot_4xx(start, end)
    plot_5xx(start, end)
    csv_path = fetch_cloudwatch_csv(start, end)
    print(f"  CSV  → {csv_path.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching CloudWatch metrics (last {LOOKBACK_MINUTES} min) ...")
    generate_all()
    print("Done.")


if __name__ == "__main__":
    main()
