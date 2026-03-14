package org.example.trees

import jakarta.inject.Inject
import jakarta.ws.rs.Consumes
import jakarta.ws.rs.POST
import jakarta.ws.rs.Path
import jakarta.ws.rs.Produces
import jakarta.ws.rs.core.MediaType
import jakarta.ws.rs.core.Response
import org.eclipse.microprofile.openapi.annotations.Operation
import org.eclipse.microprofile.openapi.annotations.tags.Tag
import org.example.infrastructure.TreeProcessingException

/**
 * REST endpoint — suspend function runs on Kotlin's coroutine scheduler.
 *
 * Quarkus RESTEasy Reactive dispatches suspend functions onto the Vert.x event-loop
 * context; [TreeService.solveLevelOrder] then switches to [kotlinx.coroutines.Dispatchers.Default]
 * (ForkJoinPool-backed) for the CPU-bound BFS — directly comparable to the Java side's
 * @RunOnVirtualThread which also uses ForkJoinPool under the hood.
 *
 * No @RunOnVirtualThread here: the goal is to exercise Kotlin's coroutine scheduler,
 * not Virtual Threads, so we can isolate the scheduler cost in the benchmark headers.
 */
@Path("/api/v1/trees")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@Tag(name = "Tree Algorithms", description = "Endpoints for processing binary tree structures")
open class TreeResource {

    @Inject
    lateinit var treeService: TreeService

    @POST
    @Path("/level-order")
    @Operation(
        summary = "Level Order Traversal",
        description = "Returns a list of lists representing the level-order traversal of the input tree."
    )
    suspend fun getLevelOrder(root: TreeNode?): Response {
        if (root == null) throw TreeProcessingException("Root node cannot be null")

        val startTime = System.nanoTime()
        val result = treeService.solveLevelOrder(root)
        val durationNs = System.nanoTime() - startTime
        val durationMs = durationNs / 1_000_000.0

        return Response.ok(result)
            .header("X-Runtime-Ms", "%.3f".format(durationMs))
            .header("X-Runtime-Nanoseconds", durationNs)
            .build()
    }
}
