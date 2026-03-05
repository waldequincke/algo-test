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
    private static final int MAX_DEPTH = 500; // Security constraint

    /**
     * Performs a level-order traversal (BFS) of a binary tree.
     * Optimized for Java 25 using Switch Expressions and pattern matching.
     * * @param root The root node of the tree
     *
     * @return A list of lists containing node values level by level
     */
    public List<List<Integer>> solveLevelOrder(TreeNode root) {
        LOG.info("Starting level-order traversal processing...");
        validateTreeDepth(root, 0);

        List<List<Integer>> result = performTransversal(root);

        LOG.infof("Traversal completed. Processed %d levels.", result.size());

        return result;
    }

    private void validateTreeDepth(TreeNode node, int depth) {
        if (node == null) return;
        if (depth > MAX_DEPTH) {
            LOG.error("Tree depth exceeded maximum limit");
            throw new TreeProcessingException("Tree depth exceeds security limits (Max: " + MAX_DEPTH + ")");
        }
        validateTreeDepth(node.left(), depth + 1);
        validateTreeDepth(node.right(), depth + 1);
    }

    private List<List<Integer>> performTransversal(TreeNode root) {
        return switch (root) {
            case null -> List.of();
            default -> {
                List<List<Integer>> result = new ArrayList<>();
                Queue<TreeNode> queue = new ArrayDeque<>();
                queue.add(root);

                while (!queue.isEmpty()) {
                    int levelSize = queue.size();
                    List<Integer> currentLevel = new ArrayList<>(levelSize);

                    for (int i = 0; i < levelSize; i++) {
                        TreeNode node = queue.poll();
                        currentLevel.add(node.value());

                        if (node.left() != null) queue.add(node.left());
                        if (node.right() != null) queue.add(node.right());
                    }
                    result.add(List.copyOf(currentLevel));
                }
                yield List.copyOf(result);
            }
        };
    }
}
