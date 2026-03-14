package org.example.trees;

/**
 * Represents a node in a binary tree.
 * Using Java Records for immutability and concise syntax.
 */
public record TreeNode(
    int value,
    TreeNode left,
    TreeNode right
) {
}
