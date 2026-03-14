package org.example.infrastructure;

import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.jackson.ObjectMapperCustomizer;
import jakarta.inject.Singleton;

/**
 * Enforces Jackson parser-level security constraints to prevent
 * Recursive DoS attacks via deeply nested JSON payloads.
 *
 * This is Layer 1 of the defense-in-depth strategy:
 *   1. Parser Level (here)   — rejects JSON nested beyond 1,000 levels
 *   2. Application Level     — TreeService rejects trees deeper than MAX_DEPTH (500)
 */
@Singleton
public class JacksonSecurityCustomizer implements ObjectMapperCustomizer {

    private static final int MAX_JSON_NESTING_DEPTH = 1000;

    @Override
    public void customize(ObjectMapper mapper) {
        mapper.getFactory().setStreamReadConstraints(
            StreamReadConstraints.builder()
                .maxNestingDepth(MAX_JSON_NESTING_DEPTH)
                .build()
        );
    }
}
