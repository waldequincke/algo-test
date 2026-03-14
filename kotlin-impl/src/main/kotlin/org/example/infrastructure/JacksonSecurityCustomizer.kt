package org.example.infrastructure

import com.fasterxml.jackson.core.StreamReadConstraints
import com.fasterxml.jackson.databind.ObjectMapper
import io.quarkus.jackson.ObjectMapperCustomizer
import jakarta.inject.Singleton

/**
 * Layer 1 defense: rejects JSON nested beyond 1 000 levels at the parser level,
 * before any tree object is allocated — mirrors the Java implementation.
 */
@Singleton
class JacksonSecurityCustomizer : ObjectMapperCustomizer {

    override fun customize(mapper: ObjectMapper) {
        mapper.factory.setStreamReadConstraints(
            StreamReadConstraints.builder()
                .maxNestingDepth(MAX_JSON_NESTING_DEPTH)
                .build()
        )
    }

    companion object {
        private const val MAX_JSON_NESTING_DEPTH = 1_000
    }
}
