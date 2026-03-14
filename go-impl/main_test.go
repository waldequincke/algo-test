package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

// ── helpers ───────────────────────────────────────────────────────────────────

func n(value int, left, right *TreeNode) *TreeNode {
	return &TreeNode{Value: value, Left: left, Right: right}
}

func leaf(value int) *TreeNode { return n(value, nil, nil) }

// newApp builds a Fiber app identical to main() for integration tests.
func newApp() *fiber.App {
	app := fiber.New(fiber.Config{
		BodyLimit:             maxBodySize,
		DisableStartupMessage: true,
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			code := fiber.StatusInternalServerError
			msg := err.Error()
			if e, ok := err.(*fiber.Error); ok {
				code = e.Code
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
	return app
}

// post sends a POST to the test app and returns the response.
func post(app *fiber.App, body string) *http.Response {
	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/trees/level-order",
		strings.NewReader(body),
	)
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req, -1)
	if err != nil {
		panic(err)
	}
	return resp
}

func readBody(resp *http.Response) string {
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	return string(b)
}

func jsonBody(resp *http.Response) map[string]any {
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	var m map[string]any
	_ = json.Unmarshal(b, &m)
	return m
}

// ── solveLevelOrder unit tests ────────────────────────────────────────────────

func TestSolveLevelOrder_SingleLeaf(t *testing.T) {
	result, err := solveLevelOrder(leaf(42))
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{42}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_ThreeNodeTree(t *testing.T) {
	//     1
	//    / \
	//   2   3
	result, err := solveLevelOrder(n(1, leaf(2), leaf(3)))
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{1}, {2, 3}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_RightSkewed(t *testing.T) {
	// 1 → 2 → 3
	result, err := solveLevelOrder(n(1, nil, n(2, nil, leaf(3))))
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{1}, {2}, {3}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_LeftSkewed(t *testing.T) {
	//      3
	//     /
	//    2
	//   /
	//  1
	result, err := solveLevelOrder(n(3, n(2, leaf(1), nil), nil))
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{3}, {2}, {1}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_CompleteBinaryTree(t *testing.T) {
	//            1
	//          /   \
	//        2       3
	//       / \     / \
	//      4   5   6   7
	result, err := solveLevelOrder(
		n(1,
			n(2, leaf(4), leaf(5)),
			n(3, leaf(6), leaf(7)),
		),
	)
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{1}, {2, 3}, {4, 5, 6, 7}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_DefaultValueZero(t *testing.T) {
	// Zero-value TreeNode → value=0, mirrors NestJS/Python default behaviour.
	result, err := solveLevelOrder(&TreeNode{})
	if err != nil {
		t.Fatal(err)
	}
	want := [][]int{{0}}
	if !equalMatrix(result, want) {
		t.Errorf("got %v, want %v", result, want)
	}
}

func TestSolveLevelOrder_DepthExceedsMax(t *testing.T) {
	// Build a 501-level chain (maxDepth + 1).
	root := leaf(501)
	for i := 500; i >= 1; i-- {
		root = n(i, root, nil)
	}
	_, err := solveLevelOrder(root)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "Tree depth exceeds security limits") {
		t.Errorf("unexpected error message: %v", err)
	}
}

func TestSolveLevelOrder_SucceedsAtExactMaxDepth(t *testing.T) {
	// 500-level chain — must NOT return an error.
	root := leaf(500)
	for i := 499; i >= 1; i-- {
		root = n(i, nil, root)
	}
	result, err := solveLevelOrder(root)
	if err != nil {
		t.Fatalf("unexpected error at exact max depth: %v", err)
	}
	if len(result) != 500 {
		t.Errorf("got %d levels, want 500", len(result))
	}
}

func TestSolveLevelOrder_NodeCountExceedsMax(t *testing.T) {
	// Temporarily lower the limit for the test — mirrors Node.js/Python pattern
	// of constructing a service with maxNodes=3.
	orig := treeMaxNodes
	treeMaxNodes = 3
	defer func() { treeMaxNodes = orig }()

	//     1
	//    / \
	//   2   3
	//      / \
	//     4   5   ← level 3 adds 2 → totalNodes = 3+2 = 5 > 3
	tree := n(1, leaf(2), n(3, leaf(4), leaf(5)))
	_, err := solveLevelOrder(tree)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "Tree node count exceeds security limits") {
		t.Errorf("unexpected error message: %v", err)
	}
}

// ── measureJSONDepth unit tests ───────────────────────────────────────────────

func TestMeasureJSONDepth_FlatObject(t *testing.T) {
	if d := measureJSONDepth([]byte(`{"value":1}`)); d != 1 {
		t.Errorf("got %d, want 1", d)
	}
}

func TestMeasureJSONDepth_NestedObject(t *testing.T) {
	if d := measureJSONDepth([]byte(`{"value":1,"left":{"value":2}}`)); d != 2 {
		t.Errorf("got %d, want 2", d)
	}
}

func TestMeasureJSONDepth_EscapedQuoteNotCounted(t *testing.T) {
	// The \" inside the string must not toggle string mode.
	data := []byte(`{"key":"val\"ue","nested":{"a":1}}`)
	if d := measureJSONDepth(data); d != 2 {
		t.Errorf("got %d, want 2", d)
	}
}

func TestMeasureJSONDepth_ArrayCounts(t *testing.T) {
	if d := measureJSONDepth([]byte(`[[1,2],[3,4]]`)); d != 2 {
		t.Errorf("got %d, want 2", d)
	}
}

func TestMeasureJSONDepth_EmptyObject(t *testing.T) {
	if d := measureJSONDepth([]byte(`{}`)); d != 1 {
		t.Errorf("got %d, want 1", d)
	}
}

func TestMeasureJSONDepth_AtLimit(t *testing.T) {
	data := []byte(
		strings.Repeat(`{"v":`, maxJSONNestingDepth) +
			`1` +
			strings.Repeat(`}`, maxJSONNestingDepth),
	)
	if d := measureJSONDepth(data); d != maxJSONNestingDepth {
		t.Errorf("got %d, want %d", d, maxJSONNestingDepth)
	}
}

func TestMeasureJSONDepth_AboveLimitEarlyExit(t *testing.T) {
	depth := maxJSONNestingDepth + 1
	data := []byte(
		strings.Repeat(`{"v":`, depth) +
			`1` +
			strings.Repeat(`}`, depth),
	)
	if d := measureJSONDepth(data); d <= maxJSONNestingDepth {
		t.Errorf("expected depth > %d, got %d", maxJSONNestingDepth, d)
	}
}

// ── HTTP endpoint integration tests ───────────────────────────────────────────

func TestEndpoint_HappyPath(t *testing.T) {
	app := newApp()
	resp := post(app, `{"value":1,"left":{"value":2},"right":{"value":3}}`)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status %d", resp.StatusCode)
	}
	var got [][]int
	_ = json.NewDecoder(resp.Body).Decode(&got)
	resp.Body.Close()
	want := [][]int{{1}, {2, 3}}
	if !equalMatrix(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
}

func TestEndpoint_SingleNode(t *testing.T) {
	app := newApp()
	resp := post(app, `{"value":42}`)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status %d", resp.StatusCode)
	}
	var got [][]int
	_ = json.NewDecoder(resp.Body).Decode(&got)
	resp.Body.Close()
	if !equalMatrix(got, [][]int{{42}}) {
		t.Errorf("got %v", got)
	}
}

func TestEndpoint_EmptyObjectDefaultsToZero(t *testing.T) {
	app := newApp()
	resp := post(app, `{}`)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status %d", resp.StatusCode)
	}
	var got [][]int
	_ = json.NewDecoder(resp.Body).Decode(&got)
	resp.Body.Close()
	if !equalMatrix(got, [][]int{{0}}) {
		t.Errorf("got %v", got)
	}
}

func TestEndpoint_RuntimeHeadersPresent(t *testing.T) {
	app := newApp()
	resp := post(app, `{"value":1}`)
	resp.Body.Close()
	if resp.Header.Get("X-Runtime-Ms") == "" {
		t.Error("missing X-Runtime-Ms header")
	}
	if resp.Header.Get("X-Runtime-Nanoseconds") == "" {
		t.Error("missing X-Runtime-Nanoseconds header")
	}
}

func TestEndpoint_ContentTypeIsJSON(t *testing.T) {
	app := newApp()
	resp := post(app, `{"value":1}`)
	resp.Body.Close()
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("unexpected Content-Type: %s", ct)
	}
}

func TestEndpoint_EmptyBodyReturns400(t *testing.T) {
	app := newApp()
	resp := post(app, ``)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status %d, want 400", resp.StatusCode)
	}
	body := jsonBody(resp)
	if body["error"] != "Root node cannot be null" {
		t.Errorf("unexpected error: %v", body["error"])
	}
}

func TestEndpoint_JSONDepthAboveLimitReturns400(t *testing.T) {
	app := newApp()
	depth := maxJSONNestingDepth + 1
	payload := strings.Repeat(`{"value":1,"left":`, depth) +
		`{"value":99}` +
		strings.Repeat(`}`, depth)
	resp := post(app, payload)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status %d, want 400", resp.StatusCode)
	}
	body := jsonBody(resp)
	msg, _ := body["error"].(string)
	if !strings.Contains(msg, "JSON nesting depth exceeds security limit") {
		t.Errorf("unexpected error: %v", msg)
	}
}

func TestEndpoint_JSONDepthAtLimitNotRejectedByDepthGuard(t *testing.T) {
	// At exactly maxJSONNestingDepth the depth guard must not fire.
	// encoding/json has its own recursion limit (~10 000 levels in Go's stdlib),
	// much higher than our 1 000-level guard, so the response for a 1 000-level
	// payload may still fail for other reasons — what we assert is that the
	// failure is NOT from our guard.
	app := newApp()
	n := maxJSONNestingDepth - 1
	payload := strings.Repeat(`{"value":1,"left":`, n) +
		`{"value":99}` +
		strings.Repeat(`}`, n)
	resp := post(app, payload)
	body := jsonBody(resp)
	msg, _ := body["error"].(string)
	if strings.Contains(msg, "JSON nesting depth exceeds security limit") {
		t.Errorf("depth guard fired at limit, should only fire above it: %v", msg)
	}
}

func TestEndpoint_BFSDepthExceededReturns400(t *testing.T) {
	orig := treeMaxDepth
	treeMaxDepth = 2
	defer func() { treeMaxDepth = orig }()

	app := newApp()
	// 3-level tree with treeMaxDepth=2 → BFS guard fires.
	resp := post(app, `{"value":1,"left":{"value":2,"left":{"value":3}}}`)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status %d, want 400", resp.StatusCode)
	}
	body := jsonBody(resp)
	msg, _ := body["error"].(string)
	if !strings.Contains(msg, "Tree depth exceeds security limits") {
		t.Errorf("unexpected error: %v", msg)
	}
}

func TestEndpoint_NodeCountExceededReturns400(t *testing.T) {
	orig := treeMaxNodes
	treeMaxNodes = 3
	defer func() { treeMaxNodes = orig }()

	app := newApp()
	resp := post(app,
		`{"value":1,"left":{"value":2},"right":{"value":3,"left":{"value":4},"right":{"value":5}}}`,
	)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status %d, want 400", resp.StatusCode)
	}
	body := jsonBody(resp)
	msg, _ := body["error"].(string)
	if !strings.Contains(msg, "Tree node count exceeds security limits") {
		t.Errorf("unexpected error: %v", msg)
	}
}

func TestEndpoint_ErrorResponseShape(t *testing.T) {
	// All 400 responses must use {"error": "..."} — consistent with every
	// other heptathlon implementation.
	app := newApp()
	resp := post(app, ``)
	body := jsonBody(resp)
	if _, ok := body["error"]; !ok {
		t.Error(`response missing "error" key`)
	}
	if _, ok := body["error"].(string); !ok {
		t.Error(`"error" value is not a string`)
	}
}

// ── sync.Pool correctness ─────────────────────────────────────────────────────

func TestQueuePool_ReusedBetweenCalls(t *testing.T) {
	// Run two traversals back-to-back and verify neither corrupts the other.
	// If releaseQueue is broken (e.g., old pointers leak into the next call),
	// the second traversal will return stale results.
	root1 := n(1, leaf(2), leaf(3))
	root2 := n(10, leaf(20), leaf(30))

	r1, err1 := solveLevelOrder(root1)
	r2, err2 := solveLevelOrder(root2)

	if err1 != nil || err2 != nil {
		t.Fatalf("errors: %v, %v", err1, err2)
	}
	want1 := [][]int{{1}, {2, 3}}
	want2 := [][]int{{10}, {20, 30}}
	if !equalMatrix(r1, want1) {
		t.Errorf("traversal 1: got %v, want %v", r1, want1)
	}
	if !equalMatrix(r2, want2) {
		t.Errorf("traversal 2: got %v, want %v", r2, want2)
	}
}

// ── benchmark ─────────────────────────────────────────────────────────────────

func BenchmarkSolveLevelOrder_499Nodes(b *testing.B) {
	root := buildBalancedBST(1, 499)
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_, _ = solveLevelOrder(root)
	}
}

func BenchmarkMeasureJSONDepth_15KB(b *testing.B) {
	// Approximate JSON size of a 499-node balanced BST (~15 KB).
	data, _ := json.Marshal(buildBalancedBST(1, 499))
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = measureJSONDepth(data)
	}
}

func BenchmarkEndpoint_499Nodes(b *testing.B) {
	app := newApp()
	payload, _ := json.Marshal(buildBalancedBST(1, 499))
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(
			http.MethodPost,
			"/api/v1/trees/level-order",
			bytes.NewReader(payload),
		)
		req.Header.Set("Content-Type", "application/json")
		resp, _ := app.Test(req, -1)
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}
}

// ── test helpers ──────────────────────────────────────────────────────────────

func equalMatrix(a, b [][]int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if len(a[i]) != len(b[i]) {
			return false
		}
		for j := range a[i] {
			if a[i][j] != b[i][j] {
				return false
			}
		}
	}
	return true
}

// buildBalancedBST mirrors the Python benchmark helper: build_tree(s, e).
func buildBalancedBST(s, e int) *TreeNode {
	if s > e {
		return nil
	}
	mid := (s + e) / 2
	return &TreeNode{
		Value: mid,
		Left:  buildBalancedBST(s, mid-1),
		Right: buildBalancedBST(mid+1, e),
	}
}

// Ensure fmt and http are used (suppress unused-import errors in some editors).
var _ = fmt.Sprintf
