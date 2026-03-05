package org.example.trees;

import io.smallrye.common.annotation.RunOnVirtualThread;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.eclipse.microprofile.openapi.annotations.Operation;
import org.eclipse.microprofile.openapi.annotations.tags.Tag;
import org.example.infrastructure.TreeProcessingException;

import java.util.List;

@Path("/api/v1/trees")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@Tag(name = "Tree Algorithms", description = "Endpoints for processing binary tree structures")
public class TreeResource {

    @Inject
    TreeService treeService;

    @POST
    @Path("/level-order")
    @RunOnVirtualThread // Leverages Project Loom (Virtual Threads) for high-concurrency scaling
    @Operation(
        summary = "Level Order Traversal",
        description = "Returns a list of lists representing the level-order traversal of the input tree."
    )
    public Response getLevelOrder(TreeNode root) {
        if (root == null) throw new TreeProcessingException("Root node cannot be null");

        // Start benchmark
        long startTime = System.nanoTime();

        List<List<Integer>> result = treeService.solveLevelOrder(root);

        // End benchmark
        long durationNs = System.nanoTime() - startTime;
        double durationMs = durationNs / 1_000_000.0;

        return Response.ok(result)
            .header("X-Runtime-Ms", String.format("%.3f", durationMs))
            .header("X-Runtime-Nanoseconds", durationNs)
            .build();
    }
}
