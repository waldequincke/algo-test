"""
Unit tests for _solve_level_order and _measure_json_depth.
Mirrors nodejs-impl/src/trees/trees.service.spec.ts case-for-case.
"""

import pytest

from main import (
    MAX_JSON_NESTING_DEPTH,
    TreeNode,
    TreeProcessingException,
    _measure_json_depth,
    _solve_level_order,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def node(value: int, left: TreeNode | None = None, right: TreeNode | None = None) -> TreeNode:
    return TreeNode(value=value, left=left, right=right)


# ── _solve_level_order ────────────────────────────────────────────────────────

class TestSolveLevelOrder:

    def test_single_leaf_node(self):
        assert _solve_level_order(node(42)) == [[42]]

    def test_three_node_tree(self):
        #     1
        #    / \
        #   2   3
        assert _solve_level_order(node(1, node(2), node(3))) == [[1], [2, 3]]

    def test_right_skewed_tree(self):
        # 1 → 2 → 3
        result = _solve_level_order(node(1, None, node(2, None, node(3))))
        assert result == [[1], [2], [3]]

    def test_left_skewed_tree(self):
        #      3
        #     /
        #    2
        #   /
        #  1
        result = _solve_level_order(node(3, node(2, node(1))))
        assert result == [[3], [2], [1]]

    def test_complete_binary_tree_three_levels(self):
        #            1
        #          /   \
        #        2       3
        #       / \     / \
        #      4   5   6   7
        result = _solve_level_order(
            node(1,
                 node(2, node(4), node(5)),
                 node(3, node(6), node(7)))
        )
        assert result == [[1], [2, 3], [4, 5, 6, 7]]

    def test_default_value_zero_when_no_value_set(self):
        # TreeNode() defaults value=0 — mirrors NestJS TreeNodeDto default
        assert _solve_level_order(TreeNode()) == [[0]]

    def test_raises_when_depth_exceeds_max(self):
        # Build a chain of 501 nodes (500 levels + root = 501 total)
        deep = node(501)
        for i in range(500, 0, -1):
            deep = node(i, deep)

        with pytest.raises(TreeProcessingException, match="Tree depth exceeds security limits"):
            _solve_level_order(deep)

    def test_succeeds_exactly_at_max_depth(self):
        # 500 levels — must not raise
        deep = node(500)
        for i in range(499, 0, -1):
            deep = node(i, None, deep)

        result = _solve_level_order(deep)
        assert len(result) == 500

    def test_raises_when_node_count_exceeds_max(self):
        """
        Use the function with a patched limit via monkeypatch (via pytest fixture)
        to avoid building 10 001 nodes in the test.
        Mirrors the NestJS pattern of constructing a smallService with maxNodes=3.
        """
        import main as m
        original = m.TREE_MAX_NODES
        m.TREE_MAX_NODES = 3
        try:
            #     1
            #    / \
            #   2   3
            #      / \
            #     4   5   ← level 3 adds 2 → totalNodes = 3+2 = 5 > 3
            tree = node(1, node(2), node(3, node(4), node(5)))
            with pytest.raises(TreeProcessingException, match="Tree node count exceeds security limits"):
                _solve_level_order(tree)
        finally:
            m.TREE_MAX_NODES = original


# ── _measure_json_depth ───────────────────────────────────────────────────────

class TestMeasureJsonDepth:

    def test_flat_object_depth_one(self):
        assert _measure_json_depth(b'{"value":1}') == 1

    def test_nested_object_depth_two(self):
        assert _measure_json_depth(b'{"value":1,"left":{"value":2}}') == 2

    def test_escaped_quote_inside_string_not_counted(self):
        # The \" inside the string must not toggle string mode
        assert _measure_json_depth(b'{"key":"val\\"ue","nested":{"a":1}}') == 2

    def test_array_counts_as_nesting(self):
        assert _measure_json_depth(b'[[1,2],[3,4]]') == 2

    def test_empty_object_depth_one(self):
        assert _measure_json_depth(b'{}') == 1

    def test_depth_at_limit_returns_depth(self):
        # Build a JSON string nested exactly MAX_JSON_NESTING_DEPTH deep
        data = (b'{"v":' * MAX_JSON_NESTING_DEPTH) + b'1' + (b'}' * MAX_JSON_NESTING_DEPTH)
        assert _measure_json_depth(data) == MAX_JSON_NESTING_DEPTH

    def test_depth_above_limit_triggers_early_exit(self):
        depth = MAX_JSON_NESTING_DEPTH + 1
        data = (b'{"v":' * depth) + b'1' + (b'}' * depth)
        assert _measure_json_depth(data) > MAX_JSON_NESTING_DEPTH
