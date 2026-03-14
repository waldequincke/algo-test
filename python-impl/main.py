"""
Algo Test — Python FastAPI
BFS level-order tree traversal benchmark endpoint.

Stack : FastAPI + Uvicorn + uvloop + Pydantic v2 (Rust core) + orjson
Port  : 8085  (Java=8080 Kotlin=8081 Node=8082 NodeWT=8083 Spring=8084)

Security (mirrors JacksonSecurityCustomizer + TreeService):
  Layer 1a — Content-Length / body-size guard  (10 MB)
  Layer 1b — JSON nesting-depth guard           (1 000 levels)
  Layer 2  — Pydantic v2 structural validation
  Layer 3  — BFS depth / node-count guards      (500 levels / 10 000 nodes)
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Optional

import re

import orjson
from fastapi import FastAPI, Request
from starlette.responses import Response
from pydantic import BaseModel, ConfigDict

# ── Security constants ────────────────────────────────────────────────────────

MAX_JSON_NESTING_DEPTH: int = 1_000
MAX_BODY_SIZE: int = 10 * 1024 * 1024  # 10 MB

# Runtime-configurable via env vars (mirrors Java @ConfigProperty defaults)
TREE_MAX_DEPTH: int = int(os.getenv("TREE_MAX_DEPTH", "500"))
TREE_MAX_NODES: int = int(os.getenv("TREE_MAX_NODES", "10000"))


# ── Domain model ─────────────────────────────────────────────────────────────

class TreeNode(BaseModel):
    """
    Binary tree node — Pydantic v2 model.

    slots=True: each instance uses __slots__ instead of __dict__, cutting
    per-node memory overhead (~100 B → ~56 B on CPython 3.13).  This is
    meaningful when deserializing 10 000-node trees.

    extra="ignore": unknown JSON keys are silently discarded at the Rust
    validation layer without raising — mirrors NestJS whitelist:true.
    """
    model_config = ConfigDict(slots=True, extra="ignore")

    value: int = 0
    left: Optional[TreeNode] = None
    right: Optional[TreeNode] = None


# Resolve the self-referential forward reference after class body is complete.
TreeNode.model_rebuild()


# ── Domain exception ─────────────────────────────────────────────────────────

class TreeProcessingException(Exception):
    pass


# ── BFS algorithm ────────────────────────────────────────────────────────────

def _solve_level_order(root: TreeNode) -> list[list[int]]:
    """
    Iterative BFS — mirrors Java's TreeService.solveLevelOrder exactly.

    Queue  : collections.deque → O(1) real popleft (same as Java's ArrayDeque).
    Buffer : [0] * level_size — one allocation per level with index assignment;
             avoids the repeated capacity checks of list.append() per node.
             (No ArrayList(capacity) equivalent exists in CPython, but pre-sizing
             with multiplication still allocates the backing array in one shot.)

    Depth / node-count guards are integrated into the BFS pass — no separate
    recursive pre-check — mirroring Java's single-pass design.
    """
    result: list[list[int]] = []
    queue: deque[TreeNode] = deque()
    queue.append(root)
    total_nodes: int = 0

    while queue:
        if len(result) >= TREE_MAX_DEPTH:
            raise TreeProcessingException(
                f"Tree depth exceeds security limits (Max: {TREE_MAX_DEPTH})"
            )

        level_size: int = len(queue)
        total_nodes += level_size

        if total_nodes > TREE_MAX_NODES:
            raise TreeProcessingException(
                f"Tree node count exceeds security limits (Max: {TREE_MAX_NODES})"
            )

        # Pre-allocate buffer: one call to list.__new__ + memset equivalent.
        level_values: list[int] = [0] * level_size
        for i in range(level_size):
            node = queue.popleft()
            level_values[i] = node.value
            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

        result.append(level_values)

    return result


# ── Layer 1b: JSON nesting-depth guard ───────────────────────────────────────

# Matches only the characters that affect string/depth state:
#   \\.   → any backslash-escape (consume 2 chars in one step, C-speed)
#   "     → quote (enters/exits string mode)
#   [{]}  → structural brackets (change depth when outside a string)
#
# Using re.finditer means the engine skips all other bytes in C — for a 15 KB
# body with ~1 000 structural chars it produces ~1 000 Python iterations instead
# of ~15 000, which is the dominant gap vs the JVM on this hot path.
_RE_STRUCTURAL: re.Pattern[bytes] = re.compile(rb'\\.|"|[{}\[\]]')


def _measure_json_depth(data: bytes) -> int:
    """
    O(n) depth scan delegated to the C regex engine for the inner loop.

    The regex consumes each backslash-escape as a single token, so we never
    mis-classify an escaped quote or bracket — same correctness guarantee as
    the explicit i+=2 skip in the original byte loop.
    """
    max_depth: int = 0
    depth: int = 0
    in_string: bool = False

    for m in _RE_STRUCTURAL.finditer(data):
        b: int = m.group()[0]          # first byte as int — no str allocation
        if b == 0x5C:                  # backslash-escape token — skip entirely
            continue
        if b == 0x22:                  # " — toggle string mode
            in_string = not in_string
        elif not in_string:
            if b == 0x7B or b == 0x5B:   # { or [
                depth += 1
                if depth > max_depth:
                    max_depth = depth
                if depth > MAX_JSON_NESTING_DEPTH:  # early exit on attack input
                    return depth
            elif b == 0x7D or b == 0x5D:  # } or ]
                depth -= 1

    return max_depth


# ── FastAPI application ───────────────────────────────────────────────────────

_JSON = "application/json"


def _json_response(content: object, status_code: int = 200, headers: dict[str, str] | None = None) -> Response:
    """Serialize content with orjson and return a Starlette Response."""
    return Response(
        content=orjson.dumps(content),
        media_type=_JSON,
        status_code=status_code,
        headers=headers,
    )


app = FastAPI(
    title="Algo Test — Python",
    description="BFS level-order tree traversal benchmark endpoint",
    version="1.0.0",
    docs_url="/q/swagger-ui",
)


@app.get("/health")
async def health() -> Response:
    return Response(content=b'{"status":"UP"}', media_type="application/json")


@app.post("/api/v1/trees/level-order", status_code=200)
async def level_order(request: Request) -> Response:
    """
    POST /api/v1/trees/level-order

    Timing mirrors Java's TreeResource: the X-Runtime-* headers wrap only
    _solve_level_order, NOT deserialization — consistent with every other
    implementation in the benchmark suite.

    async def is correct here: the await request.body() yields back to the
    event loop while the OS delivers the request bytes.  The BFS itself is
    fast enough (≤500 nodes) that blocking the loop for its duration is
    acceptable — adding run_in_executor would introduce inter-process
    serialisation overhead that distorts the benchmark.
    """

    # ── Layer 1a: fast-path body-size guard (no body read yet) ────────────
    content_length = int(request.headers.get("content-length", "0"))
    if content_length > MAX_BODY_SIZE:
        return _json_response(
            status_code=413, content={"error": "Request body too large"}
        )

    body: bytes = await request.body()

    if not body:
        return _json_response(
            status_code=400, content={"error": "Root node cannot be null"}
        )

    if len(body) > MAX_BODY_SIZE:
        return _json_response(
            status_code=413, content={"error": "Request body too large"}
        )

    # ── Layer 1b: JSON nesting-depth guard ────────────────────────────────
    depth = _measure_json_depth(body)
    if depth > MAX_JSON_NESTING_DEPTH:
        return _json_response(
            status_code=400,
            content={
                "error": (
                    f"JSON nesting depth exceeds security limit"
                    f" (max: {MAX_JSON_NESTING_DEPTH})"
                )
            },
        )

    # ── Layer 2: Pydantic v2 structural validation (Rust core) ───────────
    try:
        root = TreeNode.model_validate_json(body)
    except Exception as exc:
        return _json_response(status_code=400, content={"error": str(exc)})

    # ── Layer 3 + BFS timing (mirrors Java's System.nanoTime() scope) ────
    start_ns: int = time.monotonic_ns()
    try:
        result = _solve_level_order(root)
    except TreeProcessingException as exc:
        return _json_response(status_code=400, content={"error": str(exc)})

    duration_ns: int = time.monotonic_ns() - start_ns
    duration_ms: float = duration_ns / 1_000_000

    return _json_response(
        content=result,
        headers={
            "X-Runtime-Ms": f"{duration_ms:.3f}",
            "X-Runtime-Nanoseconds": str(duration_ns),
        },
    )
