#!/usr/bin/env python3
"""
Heptatlón de Performance — AWS Benchmark Runner
================================================

Runs wrk2 load tests against all 7 implementations hosted on AWS App Runner,
then fires one probe request per service to capture the X-Runtime-Ms /
X-Runtime-Nanoseconds response headers reported by each implementation.

Requirements:
    pip install pandas matplotlib
    brew install wrk2   # or build from source

Usage:
    python3 scripts/benchmark.py

Override any host via environment variable:
    JAVA_QUARKUS_HOST=xxx.awsapprunner.com python3 scripts/benchmark.py
"""

import matplotlib
matplotlib.use("Agg")  # headless — must come before pyplot import

import datetime
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "test-data"
LUA_SCRIPT   = SCRIPT_DIR / "wrk2" / "post-payload.lua"
API_PATH     = "/api/v1/trees/level-order"

# ── Service registry ──────────────────────────────────────────────────────────
# Each value is read from an env var first; placeholder used as fallback so the
# script is self-contained and fails clearly rather than silently.

def _host(env_var: str, placeholder: str) -> str:
    return os.environ.get(env_var, placeholder)

SERVICES: dict[str, str] = {
    "Java 25 (Quarkus)":        _host("JAVA_HOST",    "java-quarkus-url.awsapprunner.com"),
    "Java 25 (Spring 4)":       _host("SPRING_HOST",  "java-spring-url.awsapprunner.com"),
    "Kotlin (Quarkus)":         _host("KOTLIN_HOST",         "kotlin-url.awsapprunner.com"),
    "Go (Fiber)":               _host("GO_HOST",             "go-url.awsapprunner.com"),
    "Node.js (Event Loop)":     _host("NODEJS_HOST",         "node-el-url.awsapprunner.com"),
    "Node.js (Worker Threads)": _host("NODEJS_WT_HOST",      "node-wt-url.awsapprunner.com"),
    "Python (FastAPI)":         _host("PYTHON_HOST",         "python-url.awsapprunner.com"),
}

# ── Benchmark scenarios ───────────────────────────────────────────────────────

SCENARIOS: dict[str, Path] = {
    "Small Tree (7 nodes)":    DATA_DIR / "test-tree.json",
    "Large Tree (500 nodes)":  DATA_DIR / "heavy_tree.json",
}

# ── wrk2 tuning ───────────────────────────────────────────────────────────────

WRK_THREADS      = 4
WRK_CONNECTIONS  = 50
THROUGHPUT_RATE  = 500   # req/s — target rate for measurement (-R flag, wrk2 only)
MEASURE_SECS     = 90
COOLDOWN_SECS    = 10

# ── Warmup strategy ───────────────────────────────────────────────────────────
# Phase 0: brute-force curl pre-warmup (fires N parallel curls in a tight loop)
#          — primes the JVM class loader and allocates initial heap before wrk2.
# Phases 1-3: progressive wrk2 ramps — gives the JIT profiling data at multiple
#             throughput levels before reaching the target rate.
PRE_WARMUP_SECS    = 60
WARMUP_PHASES      = [
    (200, 60),   # (req/s, seconds)
    (350, 60),
    (500, 60),
]
PRE_WARMUP_PARALLEL = 8   # concurrent curl workers in the brute-force phase

# ── wrk2 output parsers ───────────────────────────────────────────────────────

_PCT_PATTERNS: dict[str, re.Pattern] = {
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
    if unit == "us":
        return value / 1_000
    if unit == "s":
        return value * 1_000
    return value  # already ms


def parse_wrk2(output: str) -> dict:
    stats: dict = {}
    for label, pat in _PCT_PATTERNS.items():
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

# ── wrk2 runner ───────────────────────────────────────────────────────────────

def run_wrk2(url: str, payload_file: Path, duration: int, measure: bool,
             rate: int = THROUGHPUT_RATE) -> str:
    """
    Runs wrk2 at the given rate.  measure=True adds --latency for HDR histogram.
    Returns stdout (wrk2 report). Prints stderr warnings on non-zero exit.
    """
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
    """
    Fires `parallel` curl workers in a tight loop for `duration` seconds.
    No rate limiting — goal is to saturate class-loading and initial heap
    allocation before the JIT profiling phases begin.
    """
    # Each worker: loop curl until the sentinel file disappears.
    # A background shell creates the sentinel, sleeps, then removes it.
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

# ── Single-request probe ──────────────────────────────────────────────────────

def probe(service_name: str, url: str, payload_file: Path) -> dict:
    """
    Fires one POST request and captures the X-Runtime-Ms /
    X-Runtime-Nanoseconds headers that every implementation sets.
    Uses curl -d @file to avoid shell-quoting issues with large payloads.
    """
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

    # Body: last non-empty line of the response
    lines   = [l for l in raw.splitlines() if l.strip()]
    preview = lines[-1][:120] if lines else ""

    return {
        "service":         service_name,
        "http_status":     status,
        "x_runtime_ms":    _header("X-Runtime-Ms"),
        "x_runtime_ns":    _header("X-Runtime-Nanoseconds"),
        "response_preview": preview,
    }

# ── Charting ──────────────────────────────────────────────────────────────────

PERCENTILE_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#F44336", "#9C27B0"]
PERCENTILE_COLS   = ["p50", "p90", "p95", "p99", "p99_9"]
PERCENTILE_LABELS = ["p50", "p90", "p95", "p99", "p99.9"]

# ── Dark theme constants ───────────────────────────────────────────────────────
_BG   = "#0d1117"
_GRID = "#21262d"
_TEXT = "#c9d1d9"


def _apply_dark(fig, ax):
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_TEXT)
    ax.xaxis.label.set_color(_TEXT)
    ax.yaxis.label.set_color(_TEXT)
    ax.title.set_color(_TEXT)
    ax.grid(True, which="both", color=_GRID, ls="--", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    leg = ax.get_legend()
    if leg:
        leg.get_frame().set_facecolor("#161b22")
        leg.get_frame().set_edgecolor("#30363d")
        for text in leg.get_texts():
            text.set_color(_TEXT)


def plot_scenario(df: pd.DataFrame, scenario_name: str) -> Path:
    sub  = df[df["scenario"] == scenario_name].copy()
    cols = [c for c in PERCENTILE_COLS if c in sub.columns]
    if sub.empty or not cols:
        return None

    rename = dict(zip(PERCENTILE_COLS, PERCENTILE_LABELS))
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
    _apply_dark(fig, ax)
    plt.tight_layout()

    safe = scenario_name.lower().translate(str.maketrans(" ()", "___")).strip("_")
    path = PROJECT_ROOT / "images" / f"benchmark_{safe}.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path


def plot_probe(probe_results: list[dict], payload_label: str) -> Path:
    """Bar chart of X-Runtime-Ms values from the single probe request."""
    valid = [r for r in probe_results if r.get("x_runtime_ms") is not None]
    if not valid:
        return None

    services = [r["service"] for r in valid]
    values   = [float(r["x_runtime_ms"]) for r in valid]

    fig, ax = plt.subplots(figsize=(11, 5))
    bars = ax.bar(services, values, color="#2196F3", edgecolor=_GRID)
    ax.bar_label(bars, fmt="%.3f ms", padding=3, fontsize=9, color=_TEXT)
    ax.set_title(f"BFS Processing Time (X-Runtime-Ms) — {payload_label}", fontsize=13)
    ax.set_ylabel("ms")
    ax.set_xlabel("")
    plt.xticks(rotation=25, ha="right", color=_TEXT)
    _apply_dark(fig, ax)
    plt.tight_layout()

    path = PROJECT_ROOT / "images" / "probe_runtime_ms.png"
    plt.savefig(path, dpi=150, facecolor=_BG)
    plt.close()
    return path

# ── Main ──────────────────────────────────────────────────────────────────────

def _sep(char="═", width=62):
    print(char * width)


def main() -> None:
    # Sanity-check: wrk2 must be on PATH
    if subprocess.run("which wrk2", shell=True, capture_output=True).returncode != 0:
        sys.exit("✗  wrk2 not found on PATH. Install with: brew install wrk2")

    bench_start_utc = datetime.datetime.now(datetime.timezone.utc)

    # Warn about placeholder hosts
    placeholders = [n for n, h in SERVICES.items() if "awsapprunner.com" in h and "-url" in h]
    if placeholders:
        print("⚠  The following services still use placeholder hosts:")
        for n in placeholders:
            print(f"   {n}")
        print("   Set the corresponding env vars or edit SERVICES in this script.\n")

    warmup_total = PRE_WARMUP_SECS + sum(s for _, s in WARMUP_PHASES)
    total_secs   = len(SERVICES) * len(SCENARIOS) * (warmup_total + COOLDOWN_SECS + MEASURE_SECS)
    warmup_desc  = f"{PRE_WARMUP_SECS}s curl + " + " + ".join(f"{s}s@{r}" for r, s in WARMUP_PHASES)
    _sep()
    print(f"  Heptatlón de Performance — AWS Benchmark Runner")
    _sep()
    print(f"  Services    : {len(SERVICES)}")
    print(f"  Scenarios   : {len(SCENARIOS)}")
    print(f"  Rate        : {THROUGHPUT_RATE} req/s  (t={WRK_THREADS}, c={WRK_CONNECTIONS})")
    print(f"  Warmup      : {warmup_desc}")
    print(f"  Cooldown    : {COOLDOWN_SECS}s · measure {MEASURE_SECS}s")
    print(f"  Est. runtime: ~{total_secs // 60} min")
    print()

    results: list[dict] = []

    for scenario_name, payload_file in SCENARIOS.items():
        print(f"\n{'─'*62}")
        print(f"  SCENARIO: {scenario_name}  ({payload_file.name})")
        print(f"{'─'*62}")

        for svc_name, host in SERVICES.items():
            url = f"https://{host}{API_PATH}"
            print(f"\n  [{svc_name}]")
            print(f"    host: {host}")

            total_warmup = PRE_WARMUP_SECS + sum(s for _, s in WARMUP_PHASES)
            print(f"    › pre-warmup curl ({PRE_WARMUP_SECS}s, {PRE_WARMUP_PARALLEL} workers) ...")
            pre_warmup_curl(url, payload_file, PRE_WARMUP_SECS)

            for rate, secs in WARMUP_PHASES:
                print(f"    › warm-up  ({secs}s @ {rate} req/s) ...")
                run_wrk2(url, payload_file, secs, measure=False, rate=rate)

            print(f"    › cooldown ({COOLDOWN_SECS}s) ...")
            time.sleep(COOLDOWN_SECS)

            print(f"    › measure  ({MEASURE_SECS}s) ...")
            raw    = run_wrk2(url, payload_file, MEASURE_SECS, measure=True)
            stats  = parse_wrk2(raw)

            if stats:
                err_str = ""
                total_err = stats.get("errors_non2xx", 0) + stats.get("errors_timeout", 0)
                if total_err:
                    err_str = f"  ⚠ {total_err} errors"
                print(
                    f"    ✓  p50={stats.get('p50','?')}ms  "
                    f"p95={stats.get('p95','?')}ms  "
                    f"p99={stats.get('p99','?')}ms  "
                    f"p99.9={stats.get('p99_9','?')}ms  "
                    f"{stats.get('req_sec','?')} req/s"
                    f"{err_str}"
                )
            else:
                print("    ✗  Could not parse wrk2 output")

            stats["service"]  = svc_name
            stats["scenario"] = scenario_name
            results.append(stats)

    # ── Persist benchmark results ─────────────────────────────────────────────
    df      = pd.DataFrame(results)
    csv_out = PROJECT_ROOT / "benchmark_results_2026.csv"
    df.to_csv(csv_out, index=False)
    print(f"\n\n  CSV  → {csv_out}")

    for scenario_name in SCENARIOS:
        chart = plot_scenario(df, scenario_name)
        if chart:
            print(f"  PNG  → {chart}")

    # ── Single-request probe per service ─────────────────────────────────────
    # Fires one POST with the Large Tree payload and prints/saves the
    # X-Runtime-Ms / X-Runtime-Nanoseconds headers set by every implementation.
    large_payload = DATA_DIR / "heavy_tree.json"

    print(f"\n\n{'═'*62}")
    print(f"  PROBE: single request · Large Tree (500 nodes)")
    print(f"  Captures X-Runtime-Ms / X-Runtime-Nanoseconds per service")
    print(f"{'═'*62}\n")

    probe_results: list[dict] = []
    for svc_name, host in SERVICES.items():
        url    = f"https://{host}{API_PATH}"
        result = probe(svc_name, url, large_payload)
        probe_results.append(result)

        icon = "✓" if result["http_status"] == 200 else "✗"
        print(f"  {icon}  {svc_name}")
        print(f"       HTTP              : {result['http_status']}")
        print(f"       X-Runtime-Ms      : {result['x_runtime_ms']} ms")
        print(f"       X-Runtime-Ns      : {result['x_runtime_ns']} ns")
        print(f"       Response preview  : {result['response_preview']}")
        print()

    probe_df  = pd.DataFrame(probe_results)
    probe_csv = PROJECT_ROOT / "probe_results_2026.csv"
    probe_df.to_csv(probe_csv, index=False)
    print(f"  CSV  → {probe_csv}")

    probe_chart = plot_probe(probe_results, "Large Tree (500 nodes)")
    if probe_chart:
        print(f"  PNG  → {probe_chart}")

    # ── CloudWatch metrics ────────────────────────────────────────────────────
    bench_end_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"\n\n{'═'*62}")
    print(f"  CLOUDWATCH: fetching all metrics for benchmark window")
    print(f"  {bench_start_utc.strftime('%H:%M:%S')} → {bench_end_utc.strftime('%H:%M:%S')} UTC")
    print(f"{'═'*62}\n")
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import plot_cloudwatch
        plot_cloudwatch.generate_all(start=bench_start_utc, end=bench_end_utc)
    except Exception as e:
        print(f"  ⚠  CloudWatch unavailable: {e}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'═'*62}")
    ok_probes = sum(1 for r in probe_results if r["http_status"] == 200)
    print(f"  Heptatlón completado.")
    print(f"  Probes OK      : {ok_probes}/{len(probe_results)}")
    print(f"  Results CSV    : {csv_out.name}")
    print(f"  Probe CSV      : {probe_csv.name}")
    print(f"  CloudWatch CSV : cloudwatch_results_2026.csv")
    print(f"{'═'*62}")


if __name__ == "__main__":
    main()
