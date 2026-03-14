package org.example.trees;

/**
 * Binary tree node — Java Record.
 *
 * {@code int value} compiles to a JVM primitive {@code int} field: no boxing on read/write.
 * Jackson 2.15+ deserialises records via the canonical constructor without
 * {@code @JsonCreator}: missing fields map to Java defaults (0 for int, null for refs),
 * so {@code {}} deserialises to {@code TreeNode(0, null, null)}.
 */
public record TreeNode(
    int value,
    TreeNode left,
    TreeNode right
) {}
