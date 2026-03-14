# 🏁 The Performance Heptathlon: 7 Stacks, One Algorithm (2026)

### A rigorous study of CPU-bound BFS execution across 7 modern backends on AWS App Runner.

---

## 📌 Executive Summary

This repository benchmarks a **Breadth-First Search (BFS)** level-order tree traversal implemented identically across 7 backend stacks. The goal is to measure how concurrency models, runtime characteristics, and framework overhead affect **tail latency** under sustained constant-rate load.

The benchmark goes beyond "Hello World" by using a **500-node binary tree (~15 KB JSON)** as the heavy payload — enough CPU work to expose queuing collapse in event-loop runtimes while giving JIT compilers a meaningful hot path to optimize.

---

## 🏆 The Performance Leaderboard (Scenario B: 500 nodes)

| Implementation | p50 Latency | p99 Latency | Success Rate | BFS Algorithm Time* |
| :--- | :---: | :---: | :---: | :---: |
| **☕ Java 25 (Quarkus)** | **5.36 ms** | **165.38 ms** | **100%** | 0.052 ms |
| **🐹 Go (Fiber)** | **5.45 ms** | **220.80 ms** | **100%** | **0.023 ms** |
| **🦺 Kotlin (Quarkus)** | 4.66 ms | 358.91 ms | 100% | 0.174 ms |
| **☕ Java 25 (Spring 4)** | 822 ms | 8,930 ms | ⚠ 91% | 0.581 ms |
| **🟢 Node.js / 🐍 Python** | **> 26s** | **Collapse** | **Failed** | 35.28 ms (Node) |

*\* BFS time = `X-Runtime-Ms` header from a single warm request (pure algorithm time, excludes HTTP/JSON).*

---

## 🛠 The Contenders

| Stack | Language Version | Framework | Concurrency Model |
| :--- | :---: | :--- | :--- |
| ☕ **Java 25 (Quarkus)** | Java 25 | Quarkus 3.x + Netty | Virtual Threads (Project Loom) |
| ☕ **Java 25 (Spring 4)** | Java 25 | Spring Boot 4 + Netty | Virtual Threads (Project Loom) |
| 🦺 **Kotlin (Quarkus)** | Kotlin + JVM | Quarkus 3.x + Netty | Coroutines |
| 🐹 **Go (Fiber)** | Go 1.26 | Fiber v2 + fasthttp | Goroutines (M:N scheduler) |
| 🟢 **Node.js (Event Loop)** | Node.js 22 | Fastify | Single-threaded Event Loop |
| 🟢 **Node.js (Worker Threads)** | Node.js 22 | Fastify + Worker Pool | CPU offload via Worker Threads |
| 🐍 **Python (FastAPI)** | Python 3.14 | FastAPI + uvloop + orjson | Async + Pydantic v2 (Rust core) |

**Infrastructure:** All services deployed on **AWS App Runner — 1 vCPU / 2 GB RAM** (us-east-1).

---

## 🔬 Methodology

* **Load generator:** `wrk2` — constant open-loop rate to eliminate **Coordinated Omission bias**.
* **Target rate:** 500 req/s with 50 concurrent connections.
* **Warm-up Protocol:** 60s brute-force curl + progressive `wrk2` ramp (200 → 350 → 500 req/s) to ensure JIT saturation.
* **Measurement:** 90s window after a 10s cooldown.

---

## 🧠 Key Findings & Technical Insights

### 1. Java 25 (Quarkus) + Virtual Threads: The Consistent King
Java 25 (Quarkus) demonstrated remarkable stability. Its use of **Virtual Threads** (Project Loom) allowed it to absorb CPU work without thread-pool overhead, maintaining a 100% success rate even with the heavy 500-node payload. The **0.052 ms** BFS time shows aggressive JIT optimization of the hot path.

### 2. Go (Fiber): Fastest Pure Algorithm
Go achieved the fastest measured BFS time at **0.023 ms**. Its zero-allocation idioms and efficient pointer traversal kept GC pressure lower than any other stack, resulting in the best tail latency in several metrics.

### 3. The Node.js and Python "Collapse"
While performing well on small trees, both collapsed under the 500-node workload:
- **Event Loop Trap:** Node.js took ~35ms of pure JS execution per request. At 500 req/s (one every 2ms), the queue grew unboundedly, leading to latencies >26s.
- **The Worker Tax:** In Node.js, Worker Threads were actually slower than the Event Loop due to the `structuredClone` serialization overhead for IPC.
- **Python's Queuing:** Despite a fast isolated BFS (0.197 ms via Rust/Pydantic), the single-worker model couldn't handle the parallelism required, causing massive queuing.

### 4. The JIT Warm-up Lesson
One of the most instructive findings was the sensitivity of the JVM to "cold" states:
- **Spring Boot 4** showed a **22x improvement** in p99 latency (889ms → 39ms) once the C2 compiler optimized its instrumentation stack.
- **Go and Kotlin** remained consistent regardless of runtime age, as they rely less on runtime profile optimization.

---

## 📊 Detailed Results

### Scenario A — Small Tree (7 nodes) · 500 req/s
*Base framework overhead with trivial workload.*

| Implementation | p50 (ms) | p99 (ms) | p99.9 (ms) | BFS time |
| :--- | :---: | :---: | :---: | :---: |
| 🦺 **Kotlin (Quarkus)** | **2.81** | 112.83 | 350.21 | 0.052 ms |
| 🐹 **Go (Fiber)** | 3.24 | **40.38** | **202.75** | **0.007 ms** |
| 🐍 **Python (FastAPI)** | 3.57 | **12.32** | **18.50** | 0.010 ms |
| ☕ **Java 25 (Quarkus)** | 3.85 | 122.37 | 307.45 | 0.005 ms |

### Scenario B — Large Tree (500 nodes) · 500 req/s
*CPU saturation and object mapping stress test.*

| Implementation | p50 (ms) | p99 (ms) | p99.9 (ms) | Success Rate |
| :--- | :---: | :---: | :---: | :---: |
| ☕ **Java 25 (Quarkus)** | **5.36** | **165.38** | 372.22 | 100% |
| 🐹 **Go (Fiber)** | 5.45 | **220.80** | 417.02 | 100% |
| ☕ **Java 25 (Spring 4)** | 822 | 8,930 | 9,810 | 91% |

---

## 🛡 Security & Guardrails
All implementations enforce identical security constraints:
- **JSON nesting depth:** 1,000 levels (pre-parse check).
- **BFS depth guard:** 500 levels.
- **BFS node-count guard:** 10,000 nodes.
- **Max body size:** 10 MB.

---

## 🚀 How to Reproduce
1. **Deploy:** `bash scripts/deploy.sh all`
2. **Setup Env:** `source scripts/aws.env`
3. **Run Benchmark:** `python3 scripts/benchmark.py` (requires `wrk2`)

---
**Author:** Waldemar | Senior Software Engineer
*Focusing on high-performance distributed systems and cloud-native architectures.*
