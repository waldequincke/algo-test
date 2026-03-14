#!/usr/bin/env python3
"""
Single-request probe — captures X-Runtime-Ms / X-Runtime-Nanoseconds
from all 7 implementations.  Python 3.9-compatible.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

SCRIPT_DIR   = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "test-data"
API_PATH     = "/api/v1/trees/level-order"

def _host(env_var: str, placeholder: str) -> str:
    return os.environ.get(env_var, placeholder)

SERVICES = {
    "Java 25 (Quarkus)":        _host("JAVA_HOST",     "java-quarkus-url.awsapprunner.com"),
    "Java 25 (Spring 4)":       _host("SPRING_HOST",   "java-spring-url.awsapprunner.com"),
    "Kotlin (Quarkus)":         _host("KOTLIN_HOST",   "kotlin-url.awsapprunner.com"),
    "Go (Fiber)":               _host("GO_HOST",       "go-url.awsapprunner.com"),
    "Node.js (Event Loop)":     _host("NODEJS_HOST",   "node-el-url.awsapprunner.com"),
    "Node.js (Worker Threads)": _host("NODEJS_WT_HOST","node-wt-url.awsapprunner.com"),
    "Python (FastAPI)":         _host("PYTHON_HOST",   "python-url.awsapprunner.com"),
}


def probe(service_name, url, payload_file):
    cmd = [
        "curl", "-si", "--max-time", "30",
        "-X", "POST", url,
        "-H", "Content-Type: application/json",
        "-d", "@{}".format(payload_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout

    def _header(name):  # type: Optional[str]
        m = re.search(r"^{}:\s*(.+)".format(re.escape(name)), raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    status_m = re.search(r"^HTTP/\S+\s+(\d+)", raw, re.MULTILINE)
    status   = int(status_m.group(1)) if status_m else 0

    lines   = [l for l in raw.splitlines() if l.strip()]
    preview = lines[-1][:120] if lines else ""

    return {
        "service":          service_name,
        "http_status":      status,
        "x_runtime_ms":     _header("X-Runtime-Ms"),
        "x_runtime_ns":     _header("X-Runtime-Nanoseconds"),
        "response_preview": preview,
    }


def main():
    large_payload = DATA_DIR / "heavy_tree.json"
    small_payload = DATA_DIR / "test-tree.json"

    print("=" * 62)
    print("  PROBE: single request per service")
    print("  Payload: Large Tree (500 nodes)")
    print("=" * 62)
    print()

    results = []
    for svc_name, host in SERVICES.items():
        url    = "https://{}{}".format(host, API_PATH)
        result = probe(svc_name, url, large_payload)
        results.append(result)

        icon = "OK" if result["http_status"] == 200 else "FAIL"
        print("[{}]  {}".format(icon, svc_name))
        print("     HTTP              : {}".format(result["http_status"]))
        print("     X-Runtime-Ms      : {} ms".format(result["x_runtime_ms"]))
        print("     X-Runtime-Ns      : {} ns".format(result["x_runtime_ns"]))
        print("     Response preview  : {}".format(result["response_preview"][:80]))
        print()

    print()
    print("  PROBE: single request per service")
    print("  Payload: Small Tree (7 nodes)")
    print("=" * 62)
    print()

    results_small = []
    for svc_name, host in SERVICES.items():
        url    = "https://{}{}".format(host, API_PATH)
        result = probe(svc_name, url, small_payload)
        results_small.append(result)

        icon = "OK" if result["http_status"] == 200 else "FAIL"
        print("[{}]  {}".format(icon, svc_name))
        print("     X-Runtime-Ms (small): {} ms".format(result["x_runtime_ms"]))
        print()

    # Save CSV
    import csv
    csv_out = PROJECT_ROOT / "probe_results_2026.csv"
    with open(csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["service","http_status","x_runtime_ms","x_runtime_ns","response_preview","scenario"])
        writer.writeheader()
        for r in results:
            r["scenario"] = "Large Tree (500 nodes)"
            writer.writerow(r)
        for r in results_small:
            r["scenario"] = "Small Tree (7 nodes)"
            writer.writerow(r)

    print("CSV -> {}".format(csv_out))
    print("Done.")


if __name__ == "__main__":
    main()
