#!/usr/bin/env python3
"""
Heptatlón Combinado — Phase 1 + Phase 2 (intercalado por servicio)
===================================================================
Por cada servicio ejecuta en orden:
  1. Phase 1 · Small Tree  — warmup completo → medición 90s @ 500 req/s
  2. Phase 1 · Large Tree  — warmup completo → medición 90s @ 500 req/s
  3. Phase 2 · Saturation  — step-up con Large Tree (servicio caliente)

Esto garantiza que la saturación corre inmediatamente después del warmup
del mismo servicio, evitando el scale-down de App Runner entre fases.

Usage:
    python3 scripts/heptathlon.py

Override any host via env var:
    JAVA_HOST=xxx.awsapprunner.com python3 scripts/heptathlon.py

Outputs:
    heptathlon_benchmark_2026.csv     — Phase 1 latency results
    heptathlon_saturation_2026.csv    — Phase 2 saturation results
    heptathlon_probe_2026.csv         — single-probe X-Runtime-Ms results
    images/hepta_*.png                — charts
"""

import matplotlib
matplotlib.use("Agg")

import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "test-data"
LUA_SCRIPT   = SCRIPT_DIR / "wrk2" / "post-payload.lua"
API_PATH     = "/api/v1/trees/level-order"

# ── Service registry ───────────────────────────────────────────────────────────
def _host(env_var: str, default: str) -> str:
    return os.environ.get(env_var, default)

SERVICES: dict[str, str] = {
    "Java 25 (Quarkus)":        _host("JAVA_HOST",      "<your-java-service>.us-east-1.awsapprunner.com"),
    "Java 25 (Spring 4)":       _host("SPRING_HOST",    "<your-spring-service>.us-east-1.awsapprunner.com"),
    "Kotlin (Quarkus)":         _host("KOTLIN_HOST",    "<your-kotlin-service>.us-east-1.awsapprunner.com"),
    "Go (Fiber)":               _host("GO_HOST",        "<your-go-service>.us-east-1.awsapprunner.com"),
    "Node.js (Event Loop)":     _host("NODEJS_HOST",    "<your-nodejs-service>.us-east-1.awsapprunner.com"),
    "Node.js (Worker Threads)": _host("NODEJS_WT_HOST", "<your-nodejs-wt-service>.us-east-1.awsapprunner.com"),
    "Python (FastAPI)":         _host("PYTHON_HOST",    "<your-python-service>.us-east-1.awsapprunner.com"),
}

# ── Payloads ───────────────────────────────────────────────────────────────────
SMALL_TREE = DATA_DIR / "test-tree.json"
LARGE_TREE = DATA_DIR / "heavy_tree.json"

SCENARIOS: dict[str, Path] = {
    "Small Tree (7 nodes)":   SMALL_TREE,
    "Large Tree (500 nodes)": LARGE_TREE,
}

# ── Phase 1 — throughput benchmark config ─────────────────────────────────────
WRK_THREADS     = 4
WRK_CONNECTIONS = 50
THROUGHPUT_RATE = 500      # req/s
MEASURE_SECS    = 90
COOLDOWN_SECS   = 10

PRE_WARMUP_SECS     = 60
PRE_WARMUP_PARALLEL = 8
WARMUP_PHASES       = [
    (200, 60),
    (350, 60),
    (500, 60),
]

# ── Phase 2 — saturation config ───────────────────────────────────────────────
SAT_RATES         = [50, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000]
SAT_STEP_SECS     = 45
P99_THRESHOLD_MS  = 500.0

# ── Dark theme ─────────────────────────────────────────────────────────────────
_BG   = "#0d1117"
_GRID = "#21262d"
_TEXT = "#c9d1d9"

COLORS = [
    "#42A5F5", "#FF8A65", "#CE93D8",
    "#4DD0E1", "#81C784", "#F48FB1", "#FFD54F",
]

# Per-service color and marker — consistent across all charts
SERVICE_COLORS: dict[str, str] = {
    "Java 25 (Quarkus)":        "#42A5F5",  # blue
    "Java 25 (Spring 4)":       "#FF8A65",  # coral orange
    "Kotlin (Quarkus)":         "#CE93D8",  # lavender
    "Go (Fiber)":               "#4DD0E1",  # cyan
    "Node.js (Event Loop)":     "#81C784",  # soft green
    "Node.js (Worker Threads)": "#F48FB1",  # pink
    "Python (FastAPI)":         "#FFD54F",  # amber
}

SERVICE_MARKERS: dict[str, str] = {
    "Java 25 (Quarkus)":        "o",
    "Java 25 (Spring 4)":       "s",
    "Kotlin (Quarkus)":         "^",
    "Go (Fiber)":               "D",
    "Node.js (Event Loop)":     "v",
    "Node.js (Worker Threads)": "p",
    "Python (FastAPI)":         "*",
}

PERCENTILE_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#F44336", "#9C27B0"]
PERCENTILE_COLS   = ["p50", "p90", "p95", "p99", "p99_9"]
PERCENTILE_LABELS = ["p50", "p90", "p95", "p99", "p99.9"]

# ── wrk2 regex parsers ─────────────────────────────────────────────────────────
_PCT = {
    "p50":   re.compile(r"50\.000%\s+([\d.]+)(ms|us|s)"),
    "p90":   re.compile(r"90\.000%\s+([\d.]+)(ms|us|s)"),
    "p95":   re.compile(r"95\.000%\s+([\d.]+)(ms|us|s)"),
    "p99":   re.compile(r"99\.000%\s+([\d.]+)(ms|us|s)"),
    "p99_9": re.compile(r"99\.900%\s+([\d.]+)(ms|us|s)"),
}
_RPS_RE    = re.compile(r"Requests/sec:\s+([\d.]+)")
_ERRORS_RE = re.compile(r"Non-2xx or 3xx responses:\s+(\d+)")
_SOCK_RE   = re.compile(r"Socket errors:.*?timeout\s+(\d+)", re.DOTALL)


def _to_ms(value: float, unit: str) -> float:
    if unit == "us": return value / 1_000
    if unit == "s":  return value * 1_000
    return value


def parse_wrk2(output: str) -> dict:
    stats: dict = {}
    for label, pat in _PCT.items():
        m = pat.search(output)
        if m:
            stats[label] = round(_to_ms(float(m.group(1)), m.group(2)), 3)
    m = _RPS_RE.search(output)
    if m:
        stats["req_sec"] = float(m.group(1))
    m = _ERRORS_RE.search(output)
    stats["errors_non2xx"] = int(m.group(1)) if m else 0
    m = _SOCK_RE.search(output)
    stats["errors_timeout"] = int(m.group(1)) if m else 0
    return stats


def run_wrk2(url: str, payload_file: Path, duration: int,
             measure: bool, rate: int = THROUGHPUT_RATE) -> str:
    flags = "--latency" if measure else ""
    cmd = (
        f"WRK_PAYLOAD=$(cat {payload_file}) "
        f"wrk2 -t{WRK_THREADS} -c{WRK_CONNECTIONS} "
        f"-d{duration}s -R{rate} "
        f"{flags} -s {LUA_SCRIPT} {url}"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and result.stderr.strip():
        for line in result.stderr.splitlines():
            if "WRK_PAYLOAD not set" not in line:
                print(f"    ⚠  wrk2: {line}")
    return result.stdout


def pre_warmup_curl(url: str, payload_file: Path, duration: int,
                    parallel: int = PRE_WARMUP_PARALLEL) -> None:
    cmd = (
        f"SENTINEL=$(mktemp); "
        f"(sleep {duration} && rm -f \"$SENTINEL\") & "
        f"for i in $(seq 1 {parallel}); do "
        f"  ( while [ -f \"$SENTINEL\" ]; do "
        f"      curl -s -o /dev/null -X POST {url} "
        f"           -H 'Content-Type: application/json' "
        f"           -d @{payload_file}; "
        f"    done ) & "
        f"done; "
        f"wait"
    )
    subprocess.run(cmd, shell=True, capture_output=True)


def probe(service_name: str, url: str, payload_file: Path) -> dict:
    cmd = [
        "curl", "-si", "--max-time", "10",
        "-X", "POST", url,
        "-H", "Content-Type: application/json",
        "-d", f"@{payload_file}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout

    def _header(name: str) -> Optional[str]:
        m = re.search(rf"^{re.escape(name)}:\s*(.+)", raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    status_m = re.search(r"^HTTP/\S+\s+(\d+)", raw, re.MULTILINE)
    status   = int(status_m.group(1)) if status_m else 0
    lines    = [l for l in raw.splitlines() if l.strip()]
    preview  = lines[-1][:120] if lines else ""

    return {
        "service":          service_name,
        "http_status":      status,
        "x_runtime_ms":     _header("X-Runtime-Ms"),
        "x_runtime_ns":     _header("X-Runtime-Nanoseconds"),
        "response_preview": preview,
    }


# ── Per-service combined run ───────────────────────────────────────────────────

def run_service(svc_name: str, host: str) -> tuple[list[dict], list[dict]]:
    """
    Runs the full heptathlon for a single service:
      Phase 1 · Small Tree → Phase 1 · Large Tree → Phase 2 · Saturation
    Returns (benchmark_rows, saturation_rows).
    """
    url = f"https://{host}{API_PATH}"
    bench_rows: list[dict] = []
    sat_rows:   list[dict] = []

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    for scenario_name, payload_file in SCENARIOS.items():
        print(f"\n    [Phase 1 · {scenario_name}]")

        print(f"      › pre-warmup curl ({PRE_WARMUP_SECS}s, {PRE_WARMUP_PARALLEL} workers) ...")
        pre_warmup_curl(url, payload_file, PRE_WARMUP_SECS)

        for rate, secs in WARMUP_PHASES:
            print(f"      › warm-up ({secs}s @ {rate} req/s) ...")
            run_wrk2(url, payload_file, secs, measure=False, rate=rate)

        print(f"      › cooldown ({COOLDOWN_SECS}s) ...")
        time.sleep(COOLDOWN_SECS)

        print(f"      › measure  ({MEASURE_SECS}s @ {THROUGHPUT_RATE} req/s) ...")
        raw   = run_wrk2(url, payload_file, MEASURE_SECS, measure=True)
        stats = parse_wrk2(raw)

        if stats:
            total_err = stats.get("errors_non2xx", 0) + stats.get("errors_timeout", 0)
            err_str   = f"  ⚠ {total_err} errors" if total_err else ""
            print(
                f"      ✓  p50={stats.get('p50','?')}ms  "
                f"p95={stats.get('p95','?')}ms  "
                f"p99={stats.get('p99','?')}ms  "
                f"p99.9={stats.get('p99_9','?')}ms  "
                f"{stats.get('req_sec','?')} req/s{err_str}"
            )
        else:
            print("      ✗  Could not parse wrk2 output")

        stats["service"]  = svc_name
        stats["scenario"] = scenario_name
        bench_rows.append(stats)

    # ── Phase 2 — saturation (service is hot from Large Tree warmup) ──────────
    print(f"\n    [Phase 2 · Saturation · Large Tree — service hot]")
    last_ok_rate  = 0
    saturated_at  = None

    for rate in SAT_RATES:
        print(f"      › {rate:>5} req/s ({SAT_STEP_SECS}s) ...", end=" ", flush=True)
        raw   = run_wrk2(url, LARGE_TREE, SAT_STEP_SECS, measure=True, rate=rate)
        stats = parse_wrk2(raw)

        p99    = stats.get("p99")
        errors = stats.get("errors_non2xx", 0) + stats.get("errors_timeout", 0)
        rps    = stats.get("req_sec", 0)

        saturated = (p99 is not None and p99 > P99_THRESHOLD_MS) or errors > 0
        status    = "SATURATED" if saturated else "ok"
        p99_str   = f"{p99:.1f}ms" if p99 is not None else "n/a"
        err_str   = f"  ⚠ {errors} errors" if errors > 0 else ""
        print(f"p50={stats.get('p50','?')}ms  p99={p99_str}  {rps:.0f} req/s  [{status}]{err_str}")

        sat_rows.append({
            "service":   svc_name,
            "rate":      rate,
            "p50":       stats.get("p50"),
            "p90":       stats.get("p90"),
            "p99":       p99,
            "p99_9":     stats.get("p99_9"),
            "req_sec":   rps,
            "errors":    errors,
            "saturated": saturated,
        })

        if saturated:
            saturated_at = rate
            break
        else:
            last_ok_rate = rate

    if saturated_at:
        print(f"      ✓ Max sustainable: {last_ok_rate} req/s  (saturated at {saturated_at} req/s)")
    else:
        print(f"      ✓ Did not saturate up to {SAT_RATES[-1]} req/s")

    return bench_rows, sat_rows


# ── Charts ─────────────────────────────────────────────────────────────────────

def _dark(fig, ax):
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_TEXT)
    ax.xaxis.label.set_color(_TEXT)
    ax.yaxis.label.set_color(_TEXT)
    ax.title.set_color(_TEXT)
    ax.grid(True, which="both", color=_GRID, ls="--", alpha=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    leg = ax.get_legend()
    if leg:
        leg.get_frame().set_facecolor("#161b22")
        leg.get_frame().set_edgecolor("#30363d")
        for t in leg.get_texts():
            t.set_color(_TEXT)


def plot_benchmark_scenario(df: pd.DataFrame, scenario_name: str) -> Path:
    sub  = df[df["scenario"] == scenario_name].copy()
    cols = [c for c in PERCENTILE_COLS if c in sub.columns]
    if sub.empty or not cols:
        return None

    rename  = dict(zip(PERCENTILE_COLS, PERCENTILE_LABELS))
    plot_df = sub.set_index("service")[cols].rename(columns=rename)

    fig, ax = plt.subplots(figsize=(13, 6))
    plot_df.plot(kind="bar", ax=ax, color=PERCENTILE_COLORS[:len(cols)])
    ax.set_title(
        f"Latency — {scenario_name} @ {THROUGHPUT_RATE} req/s  "
        f"(t={WRK_THREADS}, c={WRK_CONNECTIONS}, {MEASURE_SECS}s)",
        fontsize=13,
    )
    ax.set_ylabel("Latency (ms) — log scale")
    ax.set_xlabel("")
    ax.set_yscale("log")
    plt.xticks(rotation=25, ha="right", color=_TEXT)
    _dark(fig, ax)
    plt.tight_layout()

    safe = scenario_name.lower().translate(str.maketrans(" ()", "___")).strip("_")
    path = PROJECT_ROOT / "images" / f"hepta_benchmark_{safe}.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path


def plot_saturation_curves(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(13, 6))
    for svc, grp in df.groupby("service", sort=False):
        grp   = grp.sort_values("rate")
        color  = SERVICE_COLORS.get(svc, "#FFFFFF")
        marker = SERVICE_MARKERS.get(svc, "o")
        ax.plot(grp["rate"], grp["p99"], marker=marker, label=svc,
                color=color, linewidth=1.8, markersize=6,
                markerfacecolor=color, markeredgecolor=_BG, markeredgewidth=0.8)
        sat = grp[grp["saturated"] == True]
        if not sat.empty:
            ax.scatter(sat["rate"], sat["p99"], color=color,
                       marker="X", s=140, zorder=5, edgecolors=_BG, linewidths=0.8)

    ax.axhline(P99_THRESHOLD_MS, color="#F44336", ls="--", lw=1,
               label=f"p99 threshold ({P99_THRESHOLD_MS:.0f}ms)")
    ax.set_title(
        f"Saturation Curves — Large Tree (500 nodes)\n"
        f"p99 latency vs target rate  (t={WRK_THREADS}, c={WRK_CONNECTIONS}, {SAT_STEP_SECS}s/step)  ✕ = saturation point",
        fontsize=12, color=_TEXT,
    )
    ax.set_xlabel("Target rate (req/s)")
    ax.set_ylabel("p99 latency (ms) — log scale")
    ax.set_yscale("log")
    ax.legend(fontsize=8, loc="upper left")
    _dark(fig, ax)
    plt.tight_layout()
    path = PROJECT_ROOT / "images" / "hepta_saturation_curves.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path


def plot_saturation_max(df: pd.DataFrame) -> Path:
    records = []
    for svc, grp in df.groupby("service", sort=False):
        ok       = grp[grp["saturated"] == False]
        max_rate = ok["rate"].max() if not ok.empty else 0
        records.append({"service": svc, "max_rate": max_rate})

    summary = pd.DataFrame(records).sort_values("max_rate", ascending=False)

    fig, ax = plt.subplots(figsize=(11, 5))
    bar_colors = [SERVICE_COLORS.get(svc, "#FFFFFF") for svc in summary["service"]]
    bars = ax.bar(summary["service"], summary["max_rate"],
                  color=bar_colors, edgecolor=_GRID)
    ax.bar_label(bars, fmt="%d req/s", padding=4, fontsize=9, color=_TEXT)
    ax.set_title("Max Sustainable Throughput — Large Tree (500 nodes)",
                 fontsize=12, color=_TEXT)
    ax.set_ylabel("req/s")
    plt.xticks(rotation=20, ha="right", color=_TEXT)
    _dark(fig, ax)
    plt.tight_layout()
    path = PROJECT_ROOT / "images" / "hepta_saturation_max.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path


def plot_probe(probe_results: list[dict]) -> Optional[Path]:
    valid = [r for r in probe_results if r.get("x_runtime_ms") is not None]
    if not valid:
        return None

    services = [r["service"] for r in valid]
    values   = [float(r["x_runtime_ms"]) for r in valid]

    fig, ax = plt.subplots(figsize=(11, 5))
    bars = ax.bar(services, values, color="#2196F3", edgecolor=_GRID)
    ax.bar_label(bars, fmt="%.3f ms", padding=3, fontsize=9, color=_TEXT)
    ax.set_title("BFS Processing Time (X-Runtime-Ms) — Large Tree (500 nodes)",
                 fontsize=13)
    ax.set_ylabel("ms")
    plt.xticks(rotation=25, ha="right", color=_TEXT)
    _dark(fig, ax)
    plt.tight_layout()
    path = PROJECT_ROOT / "images" / "hepta_probe_runtime_ms.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sep(char="═", width=66):
    print(char * width)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if subprocess.run("which wrk2", shell=True, capture_output=True).returncode != 0:
        sys.exit("✗  wrk2 not found on PATH.")

    warmup_secs_per_scenario = PRE_WARMUP_SECS + sum(s for _, s in WARMUP_PHASES) + COOLDOWN_SECS + MEASURE_SECS
    sat_secs_per_service     = len(SAT_RATES) * SAT_STEP_SECS   # worst case
    total_per_service        = len(SCENARIOS) * warmup_secs_per_scenario + sat_secs_per_service
    est_total                = len(SERVICES) * total_per_service

    _sep()
    print(f"  Heptatlón Combinado — Phase 1 + Phase 2 (intercalado por servicio)")
    _sep()
    print(f"  Services   : {len(SERVICES)}")
    print(f"  Rate       : {THROUGHPUT_RATE} req/s  (t={WRK_THREADS}, c={WRK_CONNECTIONS})")
    warmup_desc = f"{PRE_WARMUP_SECS}s curl + " + " + ".join(f"{s}s@{r}" for r, s in WARMUP_PHASES)
    print(f"  Warmup     : {warmup_desc} + {COOLDOWN_SECS}s cooldown  (per scenario)")
    print(f"  Measure    : {MEASURE_SECS}s")
    print(f"  Sat rates  : {SAT_RATES}")
    print(f"  Sat step   : {SAT_STEP_SECS}s  · threshold p99 > {P99_THRESHOLD_MS}ms")
    print(f"  Est. max   : ~{est_total // 60} min (stops early at saturation)")
    print()

    bench_start = datetime.datetime.now(datetime.timezone.utc)
    print(f"  Start UTC  : {bench_start.strftime('%Y-%m-%dT%H:%M:%SZ')}")

    all_bench: list[dict] = []
    all_sat:   list[dict] = []

    for svc_name, host in SERVICES.items():
        _sep("─", 66)
        print(f"  SERVICE: {svc_name}")
        print(f"  host   : {host}")
        _sep("─", 66)

        bench_rows, sat_rows = run_service(svc_name, host)
        all_bench.extend(bench_rows)
        all_sat.extend(sat_rows)

    bench_end = datetime.datetime.now(datetime.timezone.utc)

    # ── Probe — single request per service after all load tests ───────────────
    _sep()
    print(f"  PROBE: single request · Large Tree (500 nodes)")
    _sep()

    probe_results: list[dict] = []
    for svc_name, host in SERVICES.items():
        url    = f"https://{host}{API_PATH}"
        result = probe(svc_name, url, LARGE_TREE)
        probe_results.append(result)
        icon = "✓" if result["http_status"] == 200 else "✗"
        print(f"  {icon}  {svc_name:<28}  X-Runtime-Ms: {result['x_runtime_ms']} ms")

    # ── Persist CSVs ──────────────────────────────────────────────────────────
    bench_df  = pd.DataFrame(all_bench)
    sat_df    = pd.DataFrame(all_sat)
    probe_df  = pd.DataFrame(probe_results)

    bench_csv = PROJECT_ROOT / "heptathlon_benchmark_2026.csv"
    sat_csv   = PROJECT_ROOT / "heptathlon_saturation_2026.csv"
    probe_csv = PROJECT_ROOT / "heptathlon_probe_2026.csv"

    bench_df.to_csv(bench_csv, index=False)
    sat_df.to_csv(sat_csv,     index=False)
    probe_df.to_csv(probe_csv, index=False)

    # Save time window for CloudWatch
    window_file = PROJECT_ROOT / "heptathlon_window.json"
    with open(window_file, "w") as f:
        json.dump({"start": bench_start.isoformat(), "end": bench_end.isoformat()}, f)

    # ── Charts ────────────────────────────────────────────────────────────────
    _sep()
    print(f"  CSV  → {bench_csv.name}")
    print(f"  CSV  → {sat_csv.name}")
    print(f"  CSV  → {probe_csv.name}")

    for scenario_name in SCENARIOS:
        path = plot_benchmark_scenario(bench_df, scenario_name)
        if path:
            print(f"  PNG  → {path.name}")

    path = plot_saturation_curves(sat_df)
    if path:
        print(f"  PNG  → {path.name}")

    path = plot_saturation_max(sat_df)
    if path:
        print(f"  PNG  → {path.name}")

    path = plot_probe(probe_results)
    if path:
        print(f"  PNG  → {path.name}")

    # ── CloudWatch ────────────────────────────────────────────────────────────
    _sep()
    print(f"  CLOUDWATCH: fetching metrics for heptathlon window")
    print(f"  {bench_start.strftime('%H:%M:%S')} → {bench_end.strftime('%H:%M:%S')} UTC")
    _sep()
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import plot_cloudwatch
        plot_cloudwatch.generate_all(
            start=bench_start, end=bench_end, prefix="hepta_"
        )
    except Exception as e:
        print(f"  ⚠  CloudWatch unavailable: {e}")
        print(f"  Run locally with: python3 scripts/plot_cloudwatch.py --prefix hepta_")

    # ── Summary ───────────────────────────────────────────────────────────────
    _sep()
    print(f"\n  PHASE 1 SUMMARY — {THROUGHPUT_RATE} req/s")
    print(f"  {'Service':<28} {'Scenario':<22} {'p50':>7} {'p99':>8} {'p99.9':>9}")
    print(f"  {'─'*28} {'─'*22} {'─'*7} {'─'*8} {'─'*9}")
    for _, row in bench_df.iterrows():
        p50   = f"{row['p50']:.1f}ms"   if pd.notna(row.get('p50'))   else "n/a"
        p99   = f"{row['p99']:.1f}ms"   if pd.notna(row.get('p99'))   else "n/a"
        p99_9 = f"{row['p99_9']:.1f}ms" if pd.notna(row.get('p99_9')) else "n/a"
        print(f"  {row['service']:<28} {row['scenario']:<22} {p50:>7} {p99:>8} {p99_9:>9}")

    print(f"\n  PHASE 2 SUMMARY — Max Sustainable Throughput")
    print(f"  {'Service':<28} {'Max req/s':>10}  {'p99 at max':>12}")
    print(f"  {'─'*28} {'─'*10}  {'─'*12}")
    for svc, grp in sat_df.groupby("service", sort=False):
        ok = grp[grp["saturated"] == False]
        if ok.empty:
            print(f"  {svc:<28} {'<50':>10}  {'n/a':>12}")
        else:
            best    = ok.loc[ok["rate"].idxmax()]
            p99_str = f"{best['p99']:.1f}ms" if pd.notna(best["p99"]) else "n/a"
            print(f"  {svc:<28} {int(best['rate']):>10}  {p99_str:>12}")

    elapsed = bench_end - bench_start
    print(f"\n  Heptatlón completado en {int(elapsed.total_seconds() // 60)} min.")
    _sep()


if __name__ == "__main__":
    main()
