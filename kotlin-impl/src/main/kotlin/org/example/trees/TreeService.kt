package org.example.trees

import jakarta.enterprise.context.ApplicationScoped
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.eclipse.microprofile.config.inject.ConfigProperty
import org.example.infrastructure.TreeProcessingException
import org.jboss.logging.Logger

/**
 * BFS level-order traversal — Kotlin coroutines edition.
 *
 * Concurrency model:
 *   [withContext(Dispatchers.Default)] dispatches the CPU-bound BFS to Kotlin's
 *   work-stealing coroutine scheduler (backed by ForkJoinPool.commonPool()).
 *   This is the direct counterpart to Java's @RunOnVirtualThread (Virtual Thread +
 *   ForkJoinPool) and lets us compare scheduler overhead under the same JVM runtime.
 *
 * Primitive optimisation:
 *   [IntArray] maps to JVM `int[]` — no per-element boxing during BFS traversal.
 *   Boxing is deferred to [IntArray.toList()] at the level boundary, once per level
 *   instead of once per node, reducing GC pressure vs ArrayList<Integer>.
 *
 * Security: identical depth / node-count guards as the Java implementation.
 */
@ApplicationScoped
open class TreeService {

    private val log: Logger = Logger.getLogger(TreeService::class.java)

    @ConfigProperty(name = "tree.max-depth", defaultValue = "500")
    var maxDepth: Int = 500   // Security constraint: max tree levels. Env: TREE_MAX_DEPTH

    @ConfigProperty(name = "tree.max-nodes", defaultValue = "10000")
    var maxNodes: Int = 10000 // Security constraint: max total nodes. Env: TREE_MAX_NODES

    suspend fun solveLevelOrder(root: TreeNode): List<List<Int>> = withContext(Dispatchers.Default) {
        val result = ArrayList<List<Int>>(32)
        // ArrayDeque: O(1) amortised add/removeFirst, no iterator allocation in the loop
        val queue = ArrayDeque<TreeNode>(256)
        queue.add(root)
        var totalNodes = 0

        while (queue.isNotEmpty()) {
            if (result.size >= maxDepth) {
                log.error("Tree depth exceeded maximum limit")
                throw TreeProcessingException("Tree depth exceeds security limits (Max: $maxDepth)")
            }

            val levelSize: Int = queue.size
            totalNodes += levelSize
            if (totalNodes > maxNodes) {
                log.error("Tree node count exceeded maximum limit")
                throw TreeProcessingException("Tree node count exceeds security limits (Max: $maxNodes)")
            }

            // IntArray → JVM int[]: contiguous heap block, cache-friendly, zero boxing per iteration
            val levelValues = IntArray(levelSize)
            for (i in 0..<levelSize) {
                val node = queue.removeFirst()
                levelValues[i] = node.value          // primitive int write — no Integer allocation
                node.left?.let { queue.add(it) }
                node.right?.let { queue.add(it) }
            }
            // Boxing happens once here (level boundary) when wrapping for the REST response
            result.add(levelValues.toList())
        }

        result
    }
}
