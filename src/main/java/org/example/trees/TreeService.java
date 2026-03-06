package org.example.trees;

import jakarta.enterprise.context.ApplicationScoped;
import org.example.infrastructure.TreeProcessingException;
import org.jboss.logging.Logger;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

@ApplicationScoped
public class TreeService {
    private static final Logger LOG = Logger.getLogger(TreeService.class);
    private static final int MAX_DEPTH = 500;        // Security constraint: max tree levels
    private static final int MAX_NODES = 10_000;     // Security constraint: max total nodes (prevents wide-tree DoS)

    /**
     * Performs a level-order traversal (BFS) of a binary tree.
     * Depth validation is integrated into the BFS pass — no separate recursive
     * pre-check — eliminating both the double O(N) traversal and the risk of a
     * StackOverflowError inside the validator itself.
     *
     * @param root The root node of the tree
     * @return A list of lists containing node values level by level
     */
    public List<List<Integer>> solveLevelOrder(TreeNode root) {
        LOG.debug("Starting level-order traversal...");

        if (root == null) return List.of();

        List<List<Integer>> result = new ArrayList<>();
        Queue<TreeNode> queue = new ArrayDeque<>();
        queue.add(root);
        int totalNodes = 0;

        while (!queue.isEmpty()) {
            if (result.size() >= MAX_DEPTH) {
                LOG.error("Tree depth exceeded maximum limit");
                throw new TreeProcessingException("Tree depth exceeds security limits (Max: " + MAX_DEPTH + ")");
            }

            int levelSize = queue.size();
            totalNodes += levelSize;
            if (totalNodes > MAX_NODES) {
                LOG.error("Tree node count exceeded maximum limit");
                throw new TreeProcessingException("Tree node count exceeds security limits (Max: " + MAX_NODES + ")");
            }

            List<Integer> currentLevel = new ArrayList<>(levelSize);

            for (int i = 0; i < levelSize; i++) {
                TreeNode node = queue.poll();
                currentLevel.add(node.value());
                if (node.left() != null) queue.add(node.left());
                if (node.right() != null) queue.add(node.right());
            }
            result.add(List.copyOf(currentLevel));
        }

        LOG.debugf("Traversal completed. Processed %d levels, %d nodes.", result.size(), totalNodes);
        return List.copyOf(result);
    }
}
