package org.example.infrastructure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import tools.jackson.core.StreamReadConstraints;
import tools.jackson.core.json.JsonFactory;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.util.concurrent.Executors;

@Configuration
public class InfrastructureConfig {

    /**
     * Layer 1 defense: reject JSON nested beyond 1 000 levels at parse time,
     * before any TreeNode object is allocated.
     * Mirrors JacksonSecurityCustomizer in the Quarkus implementations.
     */
    private static final int MAX_JSON_NESTING_DEPTH = 1_000;

    @Bean
    public ObjectMapper objectMapper() {
        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(
                StreamReadConstraints.builder()
                    .maxNestingDepth(MAX_JSON_NESTING_DEPTH)
                    .build()
            )
            .build();
        return JsonMapper.builder(factory)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
    }

    /**
     * Reactor {@link Scheduler} backed by a virtual-thread-per-task executor.
     * Every {@code subscribeOn()} call spawns a fresh Project Loom Virtual Thread —
     * cheap to create, no pool size limit.
     *
     * {@code destroyMethod = "dispose"} makes Spring call {@link Scheduler#dispose()}
     * on context close, which in turn calls {@code shutdown()} on the underlying
     * {@link ExecutorService} — no separate executor bean needed.
     */
    @Bean(destroyMethod = "dispose")
    public Scheduler virtualThreadScheduler() {
        return Schedulers.fromExecutorService(
            Executors.newVirtualThreadPerTaskExecutor(),
            "virtual-thread"
        );
    }
}
