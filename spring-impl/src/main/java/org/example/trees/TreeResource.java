package org.example.trees;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.example.infrastructure.TreeProcessingException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

import java.util.List;

/**
 * REST endpoint — imperative BFS dispatched to a Virtual Thread via Reactor.
 *
 * Architecture:
 *   Netty event-loop receives the HTTP request (non-blocking I/O).
 *   {@code Mono.fromCallable} wraps the synchronous BFS call.
 *   {@code subscribeOn(virtualThreadScheduler)} moves execution to a Project Loom
 *   Virtual Thread (backed by {@code Executors.newVirtualThreadPerTaskExecutor()}).
 *
 * This gives us the best of both worlds:
 *   - Netty's efficient non-blocking I/O (vs Tomcat's thread-per-request I/O model)
 *   - Virtual Threads for CPU-bound work (no reactive callback chains in business logic)
 *
 * The programming model inside {@code fromCallable} is 100% imperative/synchronous —
 * no Mono/Flux in TreeService — matching the target benchmark profile.
 *
 * Comparable to:
 *   Quarkus Java:   @RunOnVirtualThread   (Netty + VirtualThread)
 *   Quarkus Kotlin: withContext(Dispatchers.Default)
 */
@RestController
@RequestMapping("/api/v1/trees")
@Tag(name = "Tree Algorithms", description = "Endpoints for processing binary tree structures")
public class TreeResource {

    private final TreeService treeService;
    private final Scheduler virtualThreadScheduler;

    public TreeResource(TreeService treeService, Scheduler virtualThreadScheduler) {
        this.treeService = treeService;
        this.virtualThreadScheduler = virtualThreadScheduler;
    }

    @PostMapping("/level-order")
    @Operation(
        summary = "Level Order Traversal",
        description = "Returns a list of lists representing the level-order traversal of the input tree."
    )
    public Mono<ResponseEntity<List<List<Integer>>>> getLevelOrder(
            @RequestBody(required = false) TreeNode root) {

        if (root == null) {
            return Mono.error(new TreeProcessingException("Root node cannot be null"));
        }

        return Mono.fromCallable(() -> {
            long startNs = System.nanoTime();
            List<List<Integer>> result = treeService.solveLevelOrder(root);
            long durationNs = System.nanoTime() - startNs;

            return ResponseEntity.ok()
                .header("X-Runtime-Ms",          String.format("%.3f", durationNs / 1_000_000.0))
                .header("X-Runtime-Nanoseconds", String.valueOf(durationNs))
                .<List<List<Integer>>>body(result);
        }).subscribeOn(virtualThreadScheduler);
    }
}
