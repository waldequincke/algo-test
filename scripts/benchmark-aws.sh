#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
#  Pentathlon Benchmark — all 5 implementations on AWS
#
#  Protocol (per service):
#    Phase 1 – Warm-up  : 60 s @ WARMUP_RATE req/s  (≈ 60 k requests)
#                         Triggers C1 → C2 JIT compilation on JVM services.
#    Phase 2 – Cooldown : 10 s silence
#                         Lets GC reclaim warm-up garbage; CPU settles.
#    Phase 3 – Benchmark: BENCH_DURATION s @ BENCH_RATE req/s
#                         Measured with HDR histogram (wrk2 --latency).
#
#  Output:
#    results/<timestamp>/
#      <svc>_warmup.txt      raw wrk2 warm-up output
#      <svc>_bench.txt       raw wrk2 benchmark output (percentiles inside)
#      <svc>_cw_latency.png  CloudWatch p99 latency graph (if IAM allows)
#      <svc>_cw_requests.png CloudWatch request count graph
#      summary.md            side-by-side comparison table (Markdown)
#      summary.csv           same data for spreadsheet import
#
#  Prerequisites (run setup-ec2.sh first):
#    wrk2, jq, aws CLI with CloudWatch read permissions
#
#  Usage:
#    export JAVA_HOST=abc.us-east-1.awsapprunner.com
#    export KOTLIN_HOST=...
#    export NODEJS_HOST=...
#    export NODEJS_WT_HOST=...
#    export SPRING_HOST=...
#    ./benchmark-aws.sh
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
LUA_SCRIPT="${SCRIPT_DIR}/wrk2/post-tree.lua"

# ── Load AWS config ────────────────────────────────────────────────────────────
if [ -f "${SCRIPT_DIR}/aws.env" ]; then
    set -a; source "${SCRIPT_DIR}/aws.env"; set +a
fi

# ── Service hosts (override via env) ──────────────────────────────────────────
JAVA_HOST="${JAVA_HOST:-}"
KOTLIN_HOST="${KOTLIN_HOST:-}"
NODEJS_HOST="${NODEJS_HOST:-}"
NODEJS_WT_HOST="${NODEJS_WT_HOST:-}"
SPRING_HOST="${SPRING_HOST:-}"
PROTOCOL="${PROTOCOL:-https}"

# ── Benchmark parameters ───────────────────────────────────────────────────────
THREADS="${THREADS:-4}"            # wrk2 threads (match EC2 vCPU count)
CONNECTIONS="${CONNECTIONS:-50}"   # concurrent HTTP connections
WARMUP_RATE="${WARMUP_RATE:-1000}" # req/s during warm-up  (60s × 1000 = 60k)
WARMUP_DURATION=60                 # seconds — fixed (gives > 50k requests)
COOLDOWN=10                        # seconds of silence between phases
BENCH_RATE="${BENCH_RATE:-500}"    # req/s during benchmark (tune to service capacity)
BENCH_DURATION="${BENCH_DURATION:-90}" # seconds of measured load

# ── Validate inputs ────────────────────────────────────────────────────────────
MISSING=""
for v in JAVA_HOST KOTLIN_HOST NODEJS_HOST NODEJS_WT_HOST SPRING_HOST; do
    eval val="\$$v"
    [ -z "$val" ] && MISSING="$MISSING $v"
done
if [ -n "$MISSING" ]; then
    echo "Error: missing host variables:$MISSING"
    echo ""
    echo "Export before running:"
    echo "  export JAVA_HOST=<host>.awsapprunner.com"
    echo "  export KOTLIN_HOST=..."
    echo "  export NODEJS_HOST=..."
    echo "  export NODEJS_WT_HOST=..."
    echo "  export SPRING_HOST=..."
    exit 1
fi

if ! command -v wrk2 &>/dev/null; then
    echo "Error: wrk2 not found. Run ./setup-ec2.sh first."
    exit 1
fi

# ── Results directory ──────────────────────────────────────────────────────────
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
RESULTS_DIR="${ROOT_DIR}/results/${TIMESTAMP}"
mkdir -p "$RESULTS_DIR"
echo "Results directory: $RESULTS_DIR"

# ── Helpers ────────────────────────────────────────────────────────────────────

# Parse a latency percentile line from wrk2 --latency output.
# wrk2 prints lines like:  " 99.000%    3.45ms" or "  99.000%  345.67us"
# Normalises everything to milliseconds (3 decimal places).
parse_pct() {
    local file="$1" pct="$2"
    local raw
    raw=$(grep -E "^\s+${pct}%" "$file" | head -1 | awk '{print $2}') || true
    if [ -z "$raw" ]; then echo "n/a"; return; fi
    if echo "$raw" | grep -q "us$"; then
        awk "BEGIN{printf \"%.3f\", ${raw%us} / 1000}"
    elif echo "$raw" | grep -q "ms$"; then
        printf "%.3f" "${raw%ms}"
    elif echo "$raw" | grep -q "s$"; then
        awk "BEGIN{printf \"%.3f\", ${raw%s} * 1000}"
    else
        echo "$raw"
    fi
}

parse_rps() {
    grep "Requests/sec:" "$1" | awk '{printf "%.2f", $2}' || echo "n/a"
}

parse_errors() {
    local non2xx timeouts
    non2xx=$(grep "Non-2xx" "$1" | awk '{print $NF}' || echo "0")
    timeouts=$(grep "Socket errors" "$1" | grep -oE "timeouts [0-9]+" | awk '{print $2}' || echo "0")
    echo "${non2xx:-0} / ${timeouts:-0}"
}

# Capture CloudWatch metric widget image for an App Runner service.
# Requires: IAM permission cloudwatch:GetMetricWidgetImage
capture_cw_image() {
    local svc="$1" metric="$2" stat="$3" title="$4" outfile="$5"
    local start_iso end_iso service_name
    service_name="tree-service-${svc}"
    start_iso=$(date -u -d "@${BENCH_START_TS}" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
                || date -u -r "${BENCH_START_TS}" +"%Y-%m-%dT%H:%M:%SZ")
    end_iso=$(date -u -d "@${BENCH_END_TS}" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
              || date -u -r "${BENCH_END_TS}" +"%Y-%m-%dT%H:%M:%SZ")

    local widget
    widget=$(cat <<EOF
{
  "view": "timeSeries",
  "stacked": false,
  "title": "${title} — ${svc}",
  "start": "${start_iso}",
  "end":   "${end_iso}",
  "period": 10,
  "width": 1200,
  "height": 400,
  "metrics": [
    ["AWS/AppRunner","${metric}","ServiceName","${service_name}",{"stat":"${stat}","label":"${stat}"}]
  ]
}
EOF
    )

    local encoded b64
    encoded=$(echo "$widget" | python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read()))" 2>/dev/null \
              || echo "$widget" | python -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read()))")

    if aws cloudwatch get-metric-widget-image \
            --metric-widget "$widget" \
            --output-format "png" \
            --region "${AWS_REGION}" \
            --query 'MetricWidgetImage' \
            --output text 2>/dev/null | base64 -d > "$outfile"; then
        echo "    ✓ CloudWatch image saved: $(basename "$outfile")"
    else
        echo "    ⚠ CloudWatch image unavailable (check IAM permissions)"
        rm -f "$outfile"
    fi
}

# ── Per-service benchmark ──────────────────────────────────────────────────────
run_benchmark() {
    local svc="$1" host="$2" is_jvm="$3"
    local url="${PROTOCOL}://${host}/api/v1/trees/level-order"
    local warmup_out="${RESULTS_DIR}/${svc}_warmup.txt"
    local bench_out="${RESULTS_DIR}/${svc}_bench.txt"

    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    printf  "║  %-64s║\n" " ${svc}  →  ${host}"
    echo "╚══════════════════════════════════════════════════════════════════╝"

    # ── Phase 1: Warm-up ──────────────────────────────────────────────────────
    if [ "$is_jvm" = "true" ]; then
        local warmup_reqs=$(( WARMUP_RATE * WARMUP_DURATION ))
        echo "  [Phase 1] JVM warm-up — ${WARMUP_DURATION}s @ ${WARMUP_RATE} req/s (~${warmup_reqs} requests)"
        echo "            Triggering C1 → C2 JIT compilation path..."
    else
        echo "  [Phase 1] V8 warm-up — ${WARMUP_DURATION}s @ ${WARMUP_RATE} req/s"
        echo "            (same protocol as JVM for methodological consistency)"
    fi

    wrk2 \
        -t"${THREADS}" \
        -c"${CONNECTIONS}" \
        -d"${WARMUP_DURATION}s" \
        -R"${WARMUP_RATE}" \
        --script="${LUA_SCRIPT}" \
        "${url}" > "$warmup_out" 2>&1 || true

    local warmup_rps
    warmup_rps=$(parse_rps "$warmup_out")
    echo "    warm-up throughput: ${warmup_rps} req/s"

    # ── Phase 2: Cooldown ─────────────────────────────────────────────────────
    echo "  [Phase 2] Cooldown — ${COOLDOWN}s silence (GC flush + CPU settle)"
    sleep "$COOLDOWN"

    # ── Phase 3: Benchmark ────────────────────────────────────────────────────
    echo "  [Phase 3] Benchmark — ${BENCH_DURATION}s @ ${BENCH_RATE} req/s  (HDR histogram)"
    BENCH_START_TS=$(date +%s)

    wrk2 \
        -t"${THREADS}" \
        -c"${CONNECTIONS}" \
        -d"${BENCH_DURATION}s" \
        -R"${BENCH_RATE}" \
        --latency \
        --script="${LUA_SCRIPT}" \
        "${url}" > "$bench_out" 2>&1 || true

    BENCH_END_TS=$(date +%s)

    # ── Parse results ─────────────────────────────────────────────────────────
    local p50 p90 p99 p999 p9999 rps errors
    p50=$(parse_pct   "$bench_out" "50.000")
    p90=$(parse_pct   "$bench_out" "90.000")
    p99=$(parse_pct   "$bench_out" "99.000")
    p999=$(parse_pct  "$bench_out" "99.900")
    p9999=$(parse_pct "$bench_out" "99.990")
    rps=$(parse_rps   "$bench_out")
    errors=$(parse_errors "$bench_out")

    echo ""
    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  Latency (ms)         Throughput                │"
    printf "  │  p50  = %-8s      %-26s│\n" "${p50}ms"  "req/s: ${rps}"
    printf "  │  p90  = %-8s      %-26s│\n" "${p90}ms"  "errors (non-2xx/timeout): ${errors}"
    printf "  │  p99  = %-8s                              │\n" "${p99}ms"
    printf "  │  p99.9= %-8s                              │\n" "${p999}ms"
    printf "  │  p99.99=%-8s                              │\n" "${p9999}ms"
    echo "  └─────────────────────────────────────────────────┘"

    # ── CloudWatch graphs ─────────────────────────────────────────────────────
    echo "  [CloudWatch] Capturing metric graphs..."
    capture_cw_image "$svc" "RequestLatency" "p99" "Request Latency p99" \
        "${RESULTS_DIR}/${svc}_cw_latency_p99.png"
    capture_cw_image "$svc" "RequestLatency" "p50" "Request Latency p50" \
        "${RESULTS_DIR}/${svc}_cw_latency_p50.png"
    capture_cw_image "$svc" "Requests" "Sum" "Request Count" \
        "${RESULTS_DIR}/${svc}_cw_requests.png"

    # Store for summary
    eval "RES_${svc}_p50=${p50}"
    eval "RES_${svc}_p90=${p90}"
    eval "RES_${svc}_p99=${p99}"
    eval "RES_${svc}_p999=${p999}"
    eval "RES_${svc}_p9999=${p9999}"
    eval "RES_${svc}_rps=${rps}"
    eval "RES_${svc}_errors=${errors}"
}

# ── Summary report ─────────────────────────────────────────────────────────────
write_summary() {
    local md="${RESULTS_DIR}/summary.md"
    local csv="${RESULTS_DIR}/summary.csv"

    cat > "$md" <<HEADER
# Benchmark Results — ${TIMESTAMP}

**Protocol:** ${WARMUP_DURATION}s warm-up (${WARMUP_RATE} req/s) → ${COOLDOWN}s cooldown → ${BENCH_DURATION}s benchmark (${BENCH_RATE} req/s)
**Threads:** ${THREADS}  **Connections:** ${CONNECTIONS}  **Tool:** wrk2

## Latency (milliseconds) — post warm-up steady state

| Implementation       | p50 (ms) | p90 (ms) | p99 (ms) | p99.9 (ms) | p99.99 (ms) | req/s | errors |
|----------------------|----------|----------|----------|------------|-------------|-------|--------|
HEADER

    echo "implementation,p50_ms,p90_ms,p99_ms,p999_ms,p9999_ms,rps,errors" > "$csv"

    for entry in \
        "java:Java Quarkus (Virtual Threads)" \
        "kotlin:Kotlin Quarkus (Coroutines)" \
        "nodejs:Node.js (Event Loop)" \
        "nodejs-wt:Node.js (Worker Threads)" \
        "spring:Spring Boot (WebFlux+Netty)"
    do
        local svc="${entry%%:*}"
        local label="${entry##*:}"
        eval p50="\${RES_${svc}_p50}"
        eval p90="\${RES_${svc}_p90}"
        eval p99="\${RES_${svc}_p99}"
        eval p999="\${RES_${svc}_p999}"
        eval p9999="\${RES_${svc}_p9999}"
        eval rps="\${RES_${svc}_rps}"
        eval errors="\${RES_${svc}_errors}"

        printf "| %-20s | %8s | %8s | %8s | %10s | %11s | %5s | %6s |\n" \
            "$label" "$p50" "$p90" "$p99" "$p999" "$p9999" "$rps" "$errors" >> "$md"
        echo "${svc},${p50},${p90},${p99},${p999},${p9999},${rps},${errors}" >> "$csv"
    done

    cat >> "$md" <<FOOTER

## CloudWatch Console Links

Open these URLs in the AWS Console during or after the benchmark to capture screenshots:

FOOTER

    for entry in \
        "java:tree-service-java" \
        "kotlin:tree-service-kotlin" \
        "nodejs:tree-service-nodejs" \
        "nodejs-wt:tree-service-nodejs-wt" \
        "spring:tree-service-spring"
    do
        local svc="${entry%%:*}"
        local svc_name="${entry##*:}"
        echo "- **${svc}**: https://${AWS_REGION}.console.aws.amazon.com/apprunner/home?region=${AWS_REGION}#/services (filter: ${svc_name})" >> "$md"
    done

    cat >> "$md" <<CW_NOTE

> For each service → **Metrics** tab → set time range to match the benchmark window.
> Key graphs to screenshot: **Request latency** (p50/p99) and **Request count**.

## Raw wrk2 output files

\`\`\`
$(ls "${RESULTS_DIR}"/*.txt 2>/dev/null | xargs -I{} basename {})
\`\`\`
CW_NOTE

    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo " BENCHMARK COMPLETE"
    echo "════════════════════════════════════════════════════════════════════"
    cat "$md"
    echo ""
    echo "Results saved to: $RESULTS_DIR"
    echo "  summary.md  — copy to your report"
    echo "  summary.csv — open in Excel / Google Sheets"
    echo "  *_bench.txt — full HDR histograms"
    echo "  *_cw_*.png  — CloudWatch graphs (if IAM allowed)"
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║        Pentathlon Benchmark — AWS  (wrk2 + HDR histogram)       ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo "Started     : $(date)"
echo "Protocol    : ${PROTOCOL}"
echo "Warm-up     : ${WARMUP_DURATION}s @ ${WARMUP_RATE} req/s per service"
echo "Cooldown    : ${COOLDOWN}s"
echo "Benchmark   : ${BENCH_DURATION}s @ ${BENCH_RATE} req/s"
echo "Threads     : ${THREADS}  Connections: ${CONNECTIONS}"
echo ""
echo "Services:"
echo "  Java Quarkus    → ${JAVA_HOST}"
echo "  Kotlin Quarkus  → ${KOTLIN_HOST}"
echo "  Node.js EL      → ${NODEJS_HOST}"
echo "  Node.js WT      → ${NODEJS_WT_HOST}"
echo "  Spring Boot     → ${SPRING_HOST}"

# Save run metadata
cat > "${RESULTS_DIR}/run-info.txt" <<META
timestamp=${TIMESTAMP}
protocol=${PROTOCOL}
warmup_rate=${WARMUP_RATE}
warmup_duration=${WARMUP_DURATION}
cooldown=${COOLDOWN}
bench_rate=${BENCH_RATE}
bench_duration=${BENCH_DURATION}
threads=${THREADS}
connections=${CONNECTIONS}
java_host=${JAVA_HOST}
kotlin_host=${KOTLIN_HOST}
nodejs_host=${NODEJS_HOST}
nodejs_wt_host=${NODEJS_WT_HOST}
spring_host=${SPRING_HOST}
META

# Run in sequence — JVM services get warm-up flag true
run_benchmark "java"      "${JAVA_HOST}"      "true"
run_benchmark "kotlin"    "${KOTLIN_HOST}"    "true"
run_benchmark "nodejs"    "${NODEJS_HOST}"    "false"
run_benchmark "nodejs-wt" "${NODEJS_WT_HOST}" "false"
run_benchmark "spring"    "${SPRING_HOST}"    "true"

write_summary
