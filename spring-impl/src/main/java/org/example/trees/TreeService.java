package org.example.trees;

import org.example.infrastructure.TreeProcessingException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

/**
 * BFS level-order traversal — Spring Boot edition.
 *
 * Concurrency model:
 *   This method is purely synchronous. TreeResource dispatches it to the
 *   virtual-thread Scheduler via {@code Mono.fromCallable(...).subscribeOn(...)},
 *   so each request runs on a fresh Project Loom Virtual Thread while Netty's
 *   event-loop threads remain free for I/O — directly comparable to Quarkus
 *   Java's {@code @RunOnVirtualThread} and Kotlin's {@code Dispatchers.Default}.
 *
 * Primitive optimisation (mirrors kotlin-impl):
 *   {@code int[]} maps to JVM {@code int[]}: no per-element boxing during BFS.
 *   Boxing is deferred to the level boundary ({@link #toIntegerList}), once per
 *   level instead of once per node, halving GC allocation vs plain ArrayList.
 *
 * Security: depth and node-count guards run inline (single BFS pass).
 */
@Service
public class TreeService {

    private static final Logger log = LoggerFactory.getLogger(TreeService.class);

    @Value("${tree.max-depth:500}")
    private int maxDepth;   // Env: TREE_MAX_DEPTH

    @Value("${tree.max-nodes:10000}")
    private int maxNodes;   // Env: TREE_MAX_NODES

    public List<List<Integer>> solveLevelOrder(TreeNode root) {
        List<List<Integer>> result = new ArrayList<>(32);
        // ArrayDeque: O(1) amortised add/poll, no iterator allocation in the loop
        ArrayDeque<TreeNode> queue = new ArrayDeque<>(256);
        queue.add(root);
        int totalNodes = 0;

        while (!queue.isEmpty()) {
            if (result.size() >= maxDepth) {
                log.error("Tree depth exceeded maximum limit");
                throw new TreeProcessingException(
                    "Tree depth exceeds security limits (Max: " + maxDepth + ")");
            }

            int levelSize = queue.size();
            totalNodes += levelSize;

            if (totalNodes > maxNodes) {
                log.error("Tree node count exceeded maximum limit");
                throw new TreeProcessingException(
                    "Tree node count exceeds security limits (Max: " + maxNodes + ")");
            }

            // int[]: contiguous heap block, cache-friendly, zero boxing per iteration
            int[] levelValues = new int[levelSize];
            for (int i = 0; i < levelSize; i++) {
                TreeNode node = queue.poll();
                levelValues[i] = node.value();          // primitive write — no Integer allocation
                if (node.left()  != null) queue.add(node.left());
                if (node.right() != null) queue.add(node.right());
            }
            // Boxing happens once here (level boundary) when wrapping for the REST response
            result.add(toIntegerList(levelValues));
        }

        return result;
    }

    /** Boxes a primitive int[] into an unmodifiable List<Integer> in a single pass. */
    private static List<Integer> toIntegerList(int[] values) {
        List<Integer> list = new ArrayList<>(values.length);
        for (int v : values) list.add(v);
        return List.copyOf(list);
    }
}
