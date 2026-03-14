package org.example.trees

/**
 * Binary tree node.
 *
 * `val value: Int` compiles to a JVM primitive `int` field — no boxing on read/write.
 * Default values + Jackson Kotlin module allow deserialization without @JsonCreator.
 * `{}` deserialises to TreeNode(value=0, left=null, right=null), matching Java record behaviour.
 */
data class TreeNode(
    val value: Int = 0,
    val left: TreeNode? = null,
    val right: TreeNode? = null
)
