package org.example.trees;

import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.example.infrastructure.TreeProcessingException;
import org.jboss.logging.Logger;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

@ApplicationScoped
public class TreeService {
    private static final Logger LOG = Logger.getLogger(TreeService.class);

    @ConfigProperty(name = "tree.max-depth", defaultValue = "500")
    int maxDepth;   // Security constraint: max tree levels. Env: TREE_MAX_DEPTH

    @ConfigProperty(name = "tree.max-nodes", defaultValue = "10000")
    int maxNodes;   // Security constraint: max total nodes (prevents wide-tree DoS). Env: TREE_MAX_NODES

    /**
     * Performs a level-order traversal (BFS) of a binary tree.
     * Depth validation is integrated into the BFS pass.
     *
     * Primitive optimisation:
     *   {@code int[]} maps to JVM {@code int[]}: no per-element boxing during BFS.
     *   Boxing is deferred to the level boundary ({@link #toIntegerList}), once per
     *   level instead of once per node, halving GC allocation vs plain ArrayList.
     *
     * @param root The root node of the tree (non-null; caller enforces this)
     * @return A list of lists containing node values level by level
     */
    public List<List<Integer>> solveLevelOrder(TreeNode root) {
        LOG.debug("Starting level-order traversal...");

        List<List<Integer>> result = new ArrayList<>(32);
        // ArrayDeque: O(1) amortised add/poll, no iterator allocation in the loop
        ArrayDeque<TreeNode> queue = new ArrayDeque<>(256);
        queue.add(root);
        int totalNodes = 0;

        while (!queue.isEmpty()) {
            if (result.size() >= maxDepth) {
                LOG.error("Tree depth exceeded maximum limit");
                throw new TreeProcessingException("Tree depth exceeds security limits (Max: " + maxDepth + ")");
            }

            int levelSize = queue.size();
            totalNodes += levelSize;
            if (totalNodes > maxNodes) {
                LOG.error("Tree node count exceeded maximum limit");
                throw new TreeProcessingException("Tree node count exceeds security limits (Max: " + maxNodes + ")");
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

        LOG.debugf("Traversal completed. Processed %d levels, %d nodes.", result.size(), totalNodes);
        return result;
    }

    /** Boxes a primitive int[] into a List<Integer> in a single pass. */
    private static List<Integer> toIntegerList(int[] values) {
        List<Integer> list = new ArrayList<>(values.length);
        for (int v : values) list.add(v);
        return list;
    }
}
