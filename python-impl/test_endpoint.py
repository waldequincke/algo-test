"""
Integration-style unit tests for the /api/v1/trees/level-order endpoint.
Uses FastAPI's TestClient (sync wrapper over httpx) — no live server needed.
Mirrors nodejs-impl/src/trees/trees.controller.spec.ts case-for-case,
plus HTTP-layer cases that have no equivalent in the controller spec.
"""

import json

import pytest
from fastapi.testclient import TestClient

from main import MAX_JSON_NESTING_DEPTH, app

client = TestClient(app, raise_server_exceptions=False)

URL = "/api/v1/trees/level-order"


def post(body: dict | str | bytes) -> object:
    """Helper: POST JSON body, return parsed response."""
    if isinstance(body, (dict,)):
        raw = json.dumps(body).encode()
    elif isinstance(body, str):
        raw = body.encode()
    else:
        raw = body
    return client.post(URL, content=raw, headers={"Content-Type": "application/json"})


# ── Happy path ────────────────────────────────────────────────────────────────

class TestLevelOrderHappyPath:

    def test_returns_200_with_correct_traversal(self):
        #     1
        #    / \
        #   2   3
        r = post({"value": 1, "left": {"value": 2}, "right": {"value": 3}})
        assert r.status_code == 200
        assert r.json() == [[1], [2, 3]]

    def test_single_node_returns_single_level(self):
        r = post({"value": 42})
        assert r.status_code == 200
        assert r.json() == [[42]]

    def test_empty_object_uses_default_value_zero(self):
        # {} → TreeNode(value=0) — mirrors NestJS whitelist+transform behaviour
        r = post({})
        assert r.status_code == 200
        assert r.json() == [[0]]

    def test_deep_tree_returns_all_levels(self):
        # Right-skewed: 1 → 2 → 3
        r = post({"value": 1, "right": {"value": 2, "right": {"value": 3}}})
        assert r.status_code == 200
        assert r.json() == [[1], [2], [3]]

    def test_runtime_headers_present(self):
        r = post({"value": 1})
        assert "x-runtime-ms" in r.headers
        assert "x-runtime-nanoseconds" in r.headers

    def test_runtime_ms_is_non_negative_float(self):
        r = post({"value": 1})
        ms = float(r.headers["x-runtime-ms"])
        assert ms >= 0.0

    def test_runtime_nanoseconds_is_positive_integer(self):
        r = post({"value": 1})
        ns = int(r.headers["x-runtime-nanoseconds"])
        assert ns > 0

    def test_content_type_is_json(self):
        r = post({"value": 1})
        assert "application/json" in r.headers["content-type"]


# ── Security: empty / missing body ───────────────────────────────────────────

class TestEmptyBody:

    def test_empty_body_returns_400(self):
        r = client.post(URL, content=b"", headers={"Content-Type": "application/json"})
        assert r.status_code == 400

    def test_empty_body_error_message(self):
        r = client.post(URL, content=b"", headers={"Content-Type": "application/json"})
        assert r.json() == {"error": "Root node cannot be null"}


# ── Security: JSON depth guard ────────────────────────────────────────────────

class TestJsonDepthGuard:

    def test_depth_at_limit_not_rejected_by_json_guard(self):
        # Our JSON depth guard fires only at depth > MAX_JSON_NESTING_DEPTH.
        # A payload nested exactly at the limit should NOT produce the
        # "JSON nesting depth exceeds security limit" error message.
        #
        # Note: pydantic-core (Rust) has its own recursion limit (~200 levels)
        # that fires independently of our guard, so the response may still be
        # a 400 — but the cause must not be our guard.
        n = MAX_JSON_NESTING_DEPTH - 1
        body = ('{"value":1,"left":' * n + '{"value":99}' + '}' * n)
        r = post(body)
        assert "JSON nesting depth exceeds security limit" not in r.json().get("error", "")

    def test_depth_above_limit_returns_400(self):
        depth = MAX_JSON_NESTING_DEPTH + 1
        body = ('{"value":1,"left":' * depth
                + '{"value":99}'
                + '}' * depth)
        r = post(body)
        assert r.status_code == 400

    def test_depth_above_limit_error_message(self):
        depth = MAX_JSON_NESTING_DEPTH + 1
        body = ('{"value":1,"left":' * depth
                + '{"value":99}'
                + '}' * depth)
        r = post(body)
        assert "JSON nesting depth exceeds security limit" in r.json()["error"]


# ── Security: BFS depth / node-count guards ───────────────────────────────────

class TestBfsGuards:

    def test_tree_depth_exceeding_max_returns_400(self):
        import main as m
        original = m.TREE_MAX_DEPTH
        m.TREE_MAX_DEPTH = 2
        try:
            # 3-level tree with max_depth=2 → should reject
            body = {"value": 1, "left": {"value": 2, "left": {"value": 3}}}
            r = post(body)
            assert r.status_code == 400
            assert "Tree depth exceeds security limits" in r.json()["error"]
        finally:
            m.TREE_MAX_DEPTH = original

    def test_node_count_exceeding_max_returns_400(self):
        import main as m
        original = m.TREE_MAX_NODES
        m.TREE_MAX_NODES = 3
        try:
            body = {
                "value": 1,
                "left": {"value": 2},
                "right": {"value": 3, "left": {"value": 4}, "right": {"value": 5}},
            }
            r = post(body)
            assert r.status_code == 400
            assert "Tree node count exceeds security limits" in r.json()["error"]
        finally:
            m.TREE_MAX_NODES = original


# ── Error response shape ──────────────────────────────────────────────────────

class TestErrorShape:

    def test_error_response_has_error_key(self):
        """All 400 responses must use {"error": "..."} — mirrors every other impl."""
        r = client.post(URL, content=b"", headers={"Content-Type": "application/json"})
        body = r.json()
        assert "error" in body
        assert isinstance(body["error"], str)
