// Algo Test — Go (Fiber v2 / fasthttp)
// BFS level-order tree traversal benchmark endpoint.
//
// Stack   : Go 1.23 · Fiber v2 (fasthttp) · encoding/json
// Port    : 8086  (Java=8080 Kotlin=8081 Node=8082 NodeWT=8083 Spring=8084 Python=8085)
//
// Security (mirrors every other implementation in the heptathlon):
//   Layer 1a — Fiber BodyLimit hard-rejects oversized bodies (10 MB)
//   Layer 1b — O(n) JSON nesting-depth guard (1 000 levels)
//   Layer 2  — encoding/json structural decode
//   Layer 3  — BFS depth / node-count guards (500 levels / 10 000 nodes)

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"runtime"
	"strconv"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ── Security constants ────────────────────────────────────────────────────────

const (
	maxJSONNestingDepth = 1_000
	maxBodySize         = 10 * 1024 * 1024 // 10 MB
)

// Runtime-configurable limits — mirrors Java @ConfigProperty defaults.
var (
	treeMaxDepth = envInt("TREE_MAX_DEPTH", 500)
	treeMaxNodes = envInt("TREE_MAX_NODES", 10_000)
)

// ── Domain model ──────────────────────────────────────────────────────────────

// TreeNode is a binary tree node.
//
// Left and Right are pointers so encoding/json represents absent children as
// nil without a zero-value ambiguity.  Pointer fields also mean the decoder
// allocates child nodes on the heap only when the JSON key is present —
// no dummy allocations for leaf nodes.
type TreeNode struct {
	Value int       `json:"value"`
	Left  *TreeNode `json:"left"`
	Right *TreeNode `json:"right"`
}

// ── BFS queue pool ────────────────────────────────────────────────────────────

// queuePool reuses the backing arrays for the BFS traversal queue across
// requests, eliminating the per-request heap allocation for the queue slice.
//
// Initial capacity: 512.
//   - A balanced BST with 499 nodes has at most 256 nodes on the bottom level.
//   - A pathologically wide tree can grow the slice, but the enlarged backing
//     array is returned to the pool and reused — cost is paid once, not per
//     request.
var queuePool = sync.Pool{
	New: func() any {
		s := make([]*TreeNode, 0, 512)
		return &s
	},
}

// ── BFS algorithm ─────────────────────────────────────────────────────────────

// solveLevelOrder performs an iterative BFS over root.
//
// Design mirrors Java's TreeService.solveLevelOrder exactly:
//   - Single-pass: depth and node-count guards are integrated into the BFS
//     loop — no separate recursive pre-check, no double O(N) traversal.
//   - Queue: pooled slice with a head-pointer for O(1) amortised dequeue,
//     equivalent to Java's ArrayDeque and Python's collections.deque.
//   - Level buffer: make([]int, levelSize) — one allocation per level with
//     direct index assignment; no per-node append or capacity-check overhead.
func solveLevelOrder(root *TreeNode) ([][]int, error) {
	// Acquire a pooled queue and reset its length (keep backing array).
	qPtr := queuePool.Get().(*[]*TreeNode)
	q := (*qPtr)[:0]
	q = append(q, root)
	head := 0

	// Pre-allocate result: log₂(500) ≈ 9 levels for a balanced BST.
	result := make([][]int, 0, 16)
	totalNodes := 0

	for head < len(q) {
		if len(result) >= treeMaxDepth {
			releaseQueue(qPtr, q)
			return nil, fmt.Errorf("Tree depth exceeds security limits (Max: %d)", treeMaxDepth)
		}

		levelSize := len(q) - head
		totalNodes += levelSize

		if totalNodes > treeMaxNodes {
			releaseQueue(qPtr, q)
			return nil, fmt.Errorf("Tree node count exceeds security limits (Max: %d)", treeMaxNodes)
		}

		// Pre-allocate the exact level buffer: one call to runtime.makeslice,
		// no growth.  Direct index assignment avoids the append overhead.
		level := make([]int, levelSize)
		for i := 0; i < levelSize; i++ {
			node := q[head]
			head++
			level[i] = node.Value
			if node.Left != nil {
				q = append(q, node.Left)
			}
			if node.Right != nil {
				q = append(q, node.Right)
			}
		}
		result = append(result, level)
	}

	releaseQueue(qPtr, q)
	return result, nil
}

// releaseQueue zeros all pointer slots in q (so the GC can collect the tree
// nodes immediately after the handler returns) then returns the slice to the
// pool with length reset to 0, preserving the backing-array capacity for the
// next request.
func releaseQueue(ptr *[]*TreeNode, q []*TreeNode) {
	clear(q) // Go 1.21 builtin: zeroes all elements in O(n) via runtime.memclr
	*ptr = q[:0]
	queuePool.Put(ptr)
}

// ── Layer 1b: JSON nesting-depth guard ────────────────────────────────────────

// measureJSONDepth performs an O(n) single-pass depth scan on raw bytes.
//
// Mirrors NestJS measureJsonDepth and Python _measure_json_depth.
// Returns on the first byte that pushes depth above maxJSONNestingDepth (early
// exit on attack input).  Operating on []byte avoids a UTF-8 decode step and
// lets the compiler keep b in a register for the inner loop.
func measureJSONDepth(data []byte) int {
	maxDepth, depth := 0, 0
	inString := false

	for i := 0; i < len(data); i++ {
		b := data[i]
		if b == '\\' && inString { // backslash-escape: skip next byte
			i++
			continue
		}
		if b == '"' {
			inString = !inString
			continue
		}
		if inString {
			continue
		}
		switch b {
		case '{', '[':
			depth++
			if depth > maxDepth {
				maxDepth = depth
			}
			if depth > maxJSONNestingDepth { // early exit on attack input
				return depth
			}
		case '}', ']':
			depth--
		}
	}
	return maxDepth
}

// ── Error response ────────────────────────────────────────────────────────────

type errorBody struct {
	Error string `json:"error"`
}

// ── HTTP handler ──────────────────────────────────────────────────────────────

func levelOrderHandler(c *fiber.Ctx) error {
	// c.Body() returns a reference to fasthttp's internal buffer — valid only
	// within this handler.  All operations (depth scan, Unmarshal) are
	// synchronous, so no copy is needed.
	body := c.Body()

	// Empty body — mirrors Java/Kotlin: "Root node cannot be null".
	if len(body) == 0 {
		return c.Status(fiber.StatusBadRequest).
			JSON(errorBody{Error: "Root node cannot be null"})
	}

	// Layer 1b: JSON nesting-depth guard (runs before any allocation).
	if d := measureJSONDepth(body); d > maxJSONNestingDepth {
		return c.Status(fiber.StatusBadRequest).JSON(errorBody{
			Error: fmt.Sprintf(
				"JSON nesting depth exceeds security limit (max: %d)",
				maxJSONNestingDepth,
			),
		})
	}

	// Layer 2: decode and validate structure via encoding/json.
	var root TreeNode
	if err := json.Unmarshal(body, &root); err != nil {
		return c.Status(fiber.StatusBadRequest).
			JSON(errorBody{Error: err.Error()})
	}

	// Layer 3 + BFS timing.
	// Timing scope mirrors Java's System.nanoTime() window: wraps only
	// solveLevelOrder, NOT JSON decoding — consistent across all implementations.
	start := time.Now()
	result, err := solveLevelOrder(&root)
	durationNs := time.Since(start).Nanoseconds()

	if err != nil {
		return c.Status(fiber.StatusBadRequest).
			JSON(errorBody{Error: err.Error()})
	}

	durationMs := float64(durationNs) / 1e6
	c.Set("X-Runtime-Ms", strconv.FormatFloat(durationMs, 'f', 3, 64))
	c.Set("X-Runtime-Nanoseconds", strconv.FormatInt(durationNs, 10))

	// Encode via encoding/json (Fiber's default JSONEncoder) and send.
	return c.Status(fiber.StatusOK).JSON(result)
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	// Go 1.21+ honours Linux CFS cpu.quota automatically when setting
	// GOMAXPROCS.  On App Runner (1 vCPU) this resolves to 1 — single OS
	// thread, no context-switch overhead.  Log it so the value is visible in
	// CloudWatch logs.
	log.Printf("GOMAXPROCS=%d  treeMaxDepth=%d  treeMaxNodes=%d",
		runtime.GOMAXPROCS(0), treeMaxDepth, treeMaxNodes)

	app := fiber.New(fiber.Config{
		// Layer 1a: Fiber/fasthttp hard-rejects bodies larger than 10 MB
		// before they reach the handler — equivalent to Fastify's bodyLimit.
		BodyLimit: maxBodySize,

		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,

		// Single-process on 1 vCPU.  Prefork forks the process N times to
		// bind the same port across cores — on a single vCPU this adds
		// fork() and IPC overhead with zero throughput benefit.
		Prefork: false,

		// Suppress the ASCII banner in production logs.
		DisableStartupMessage: true,

		// Custom error handler: ensures all error responses — including Fiber's
		// own 413 (BodyLimit) and 404 — use the {"error": "..."} shape that
		// every other heptathlon implementation returns.
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			code := fiber.StatusInternalServerError
			msg := err.Error()
			if e, ok := err.(*fiber.Error); ok {
				code = e.Code
				// Remap Fiber's "Request Entity Too Large" to our canonical message.
				if code == fiber.StatusRequestEntityTooLarge {
					msg = "Request body too large"
				} else {
					msg = e.Message
				}
			}
			return c.Status(code).JSON(errorBody{Error: msg})
		},
	})

	app.Post("/api/v1/trees/level-order", levelOrderHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8086"
	}
	log.Printf("Starting Algo Test — Go (Fiber v2) on :%s", port)
	if err := app.Listen(":" + port); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
