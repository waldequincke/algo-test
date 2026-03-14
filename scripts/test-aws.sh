#!/bin/bash
# Smoke-test runner — all 7 implementations against AWS App Runner endpoints.
#
# For JVM services (Java Quarkus, Kotlin Quarkus, Spring Boot) a warm-up pass
# is executed first so the JIT has time to compile the hot BFS path before the
# measured run.  Native/interpreted services skip the warm-up.
#
# Usage:
#   ./scripts/test-aws.sh
#
# Override any host via environment variable:
#   JAVA_HOST=abc.us-east-1.awsapprunner.com ./scripts/test-aws.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Host configuration ─────────────────────────────────────────────────────────
if [ -f "${SCRIPT_DIR}/aws.env" ]; then
    set -a; source "${SCRIPT_DIR}/aws.env"; set +a
fi

JAVA_HOST="${JAVA_HOST:-}"
KOTLIN_HOST="${KOTLIN_HOST:-}"
NODEJS_HOST="${NODEJS_HOST:-}"
NODEJS_WT_HOST="${NODEJS_WT_HOST:-}"
SPRING_HOST="${SPRING_HOST:-}"
PYTHON_HOST="${PYTHON_HOST:-}"
GO_HOST="${GO_HOST:-}"

if [ -z "$JAVA_HOST" ] || [ -z "$KOTLIN_HOST" ] || \
   [ -z "$NODEJS_HOST" ] || [ -z "$NODEJS_WT_HOST" ] || \
   [ -z "$SPRING_HOST" ] || [ -z "$PYTHON_HOST" ] || [ -z "$GO_HOST" ]; then
    echo "Error: one or more service hosts are not set."
    echo ""
    echo "Export the following variables before running:"
    echo "  export JAVA_HOST=<host>          # e.g. abc.us-east-1.awsapprunner.com"
    echo "  export KOTLIN_HOST=<host>"
    echo "  export NODEJS_HOST=<host>"
    echo "  export NODEJS_WT_HOST=<host>"
    echo "  export SPRING_HOST=<host>"
    echo "  export PYTHON_HOST=<host>"
    echo "  export GO_HOST=<host>"
    exit 1
fi

PROTOCOL="${PROTOCOL:-https}"

# ── Tuning ─────────────────────────────────────────────────────────────────────
WARMUP_REQUESTS=15   # JVM warm-up iterations before measured run
MEASURED_REQUESTS=5  # timed requests per test case (results averaged)

# ── Test payloads ──────────────────────────────────────────────────────────────
P_STANDARD='{"value":1,"left":{"value":2,"left":{"value":4},"right":{"value":5}},"right":{"value":3,"right":{"value":6}}}'
P_HEAVY="$(cat "${SCRIPT_DIR}/../test-data/heavy_tree.json")"
P_SINGLE='{"value":42}'
P_EMPTY_BODY=''
P_MALFORMED='{bad json}'

# ── Counters ───────────────────────────────────────────────────────────────────
PASS=0; FAIL=0

# ── Helpers ────────────────────────────────────────────────────────────────────
ok()   { echo "  ✓ $*"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }

warmup() {
    local url="$1" n="$2"
    echo "  [warm-up] sending ${n} requests to prime the JIT..."
    for _ in $(seq 1 "$n"); do
        curl -s -o /dev/null -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$P_STANDARD" || true
    done
}

request() {
    local url="$1" payload="$2"
    if [ -n "$payload" ]; then
        curl -si --max-time 10 -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$payload"
    else
        curl -si --max-time 10 -X POST "$url" \
            -H "Content-Type: application/json"
    fi
}

http_code()  { echo "$1" | grep "^HTTP" | awk '{print $2}'; }
runtime_ms() { echo "$1" | grep -i "^x-runtime-ms:" | tr -d '\r' | awk '{print $2}'; }

avg_runtime() {
    local url="$1" n="$2" payload="${3:-$P_STANDARD}"
    local sum=0 count=0
    for _ in $(seq 1 "$n"); do
        r=$(request "$url" "$payload")
        ms=$(runtime_ms "$r")
        if [ -n "$ms" ]; then
            sum=$(awk "BEGIN{printf \"%.6f\", $sum + $ms}")
            count=$((count+1))
        fi
    done
    [ "$count" -gt 0 ] && awk "BEGIN{printf \"%.3f\", $sum / $count}" || echo "n/a"
}

# ── Test suite per service ─────────────────────────────────────────────────────
test_service() {
    local name="$1" host="$2" is_jvm="$3"
    local url="${PROTOCOL}://${host}/api/v1/trees/level-order"

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    printf  "║  %-52s║\n" "${name}  →  ${host}"
    echo "╚══════════════════════════════════════════════════════╝"

    [ "$is_jvm" = "true" ] && warmup "$url" "$WARMUP_REQUESTS"

    echo "  [functional]"

    # Standard tree (7 nodes)
    r=$(request "$url" "$P_STANDARD")
    code=$(http_code "$r"); body=$(echo "$r" | tail -1); ms=$(runtime_ms "$r")
    if [ "$code" = "200" ] && echo "$body" | grep -qF '[[1],[2,3],[4,5,6]]'; then
        ok "standard tree  → [[1],[2,3],[4,5,6]]  (${ms}ms)"
    else
        fail "standard tree: HTTP $code  $body"
    fi

    # Large tree (500 nodes)
    r=$(request "$url" "$P_HEAVY")
    code=$(http_code "$r"); ms=$(runtime_ms "$r")
    if [ "$code" = "200" ]; then
        ok "large tree     → 200  (${ms}ms)"
    else
        body=$(echo "$r" | tail -1)
        fail "large tree: HTTP $code  $body"
    fi

    # Single node
    r=$(request "$url" "$P_SINGLE")
    code=$(http_code "$r"); body=$(echo "$r" | tail -1)
    if [ "$code" = "200" ] && echo "$body" | grep -qF '[[42]]'; then
        ok "single node    → [[42]]"
    else
        fail "single node: HTTP $code  $body"
    fi

    # Empty body → 400
    r=$(request "$url" "$P_EMPTY_BODY")
    code=$(http_code "$r"); body=$(echo "$r" | tail -1)
    if [ "$code" = "400" ] && echo "$body" | grep -q '"error"'; then
        ok "empty body     → 400 {\"error\":...}"
    else
        fail "empty body: HTTP $code  $body"
    fi

    # Malformed JSON → 400
    r=$(request "$url" "$P_MALFORMED")
    code=$(http_code "$r")
    if [ "$code" = "400" ]; then
        ok "malformed JSON → 400"
    else
        fail "malformed: HTTP $code (expected 400)"
    fi

    echo "  [timing] averaging ${MEASURED_REQUESTS} requests (standard tree)..."
    avg_s=$(avg_runtime "$url" "$MEASURED_REQUESTS" "$P_STANDARD")
    echo "  ⏱  standard  avg X-Runtime-Ms = ${avg_s}ms"

    echo "  [timing] averaging ${MEASURED_REQUESTS} requests (large tree 500 nodes)..."
    avg_l=$(avg_runtime "$url" "$MEASURED_REQUESTS" "$P_HEAVY")
    echo "  ⏱  large     avg X-Runtime-Ms = ${avg_l}ms"
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║      AWS Smoke Test — all 7 implementations          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "Protocol  : $PROTOCOL"
echo "Warm-up   : ${WARMUP_REQUESTS} requests (JVM services only)"
echo "Timing    : ${MEASURED_REQUESTS} requests averaged (standard + large tree)"
echo "Started   : $(date)"

test_service "Java 25   · Quarkus + Virtual Threads" "$JAVA_HOST"      "true"
test_service "Kotlin    · Quarkus + Coroutines"      "$KOTLIN_HOST"    "true"
test_service "Spring 4  · WebFlux + Netty"           "$SPRING_HOST"    "true"
test_service "Node.js   · Event Loop (Fastify)"      "$NODEJS_HOST"    "false"
test_service "Node.js   · Worker Threads (Fastify)"  "$NODEJS_WT_HOST" "false"
test_service "Python    · FastAPI + uvloop"           "$PYTHON_HOST"    "false"
test_service "Go        · Fiber v2"                  "$GO_HOST"        "false"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  Results : ${PASS} passed, ${FAIL} failed"
echo "  Finished: $(date)"
echo "══════════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ] && echo "  ALL TESTS PASSED" || { echo "  SOME TESTS FAILED"; exit 1; }
