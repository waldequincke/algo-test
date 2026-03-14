package org.example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TreeResourceTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    @DisplayName("Should return level order traversal and benchmark headers")
    void testLevelOrderEndpoint() {
        String payload = """
            {"value": 1, "left": {"value": 2}, "right": {"value": 3}}
            """;

        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Runtime-Ms")
            .expectBody()
                .jsonPath("$[0][0]").isEqualTo(1)
                .jsonPath("$[1][0]").isEqualTo(2)
                .jsonPath("$[1][1]").isEqualTo(3);
    }

    @Test
    @DisplayName("Should return single-element result for a leaf node")
    void testSingleLeafNode() {
        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {"value": 42}
                """)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Runtime-Ms")
            .expectBody()
                .jsonPath("$[0][0]").isEqualTo(42);
    }

    @Test
    @DisplayName("Should process a node with value=0 when body is {value:0}")
    void testNodeWithZeroValueDefault() {
        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"value\": 0}")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Runtime-Ms")
            .expectBody()
                .jsonPath("$[0][0]").isEqualTo(0);
    }

    @Test
    @DisplayName("Should return 400 when request body is empty")
    void testNullBodyReturns400() {
        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    @DisplayName("Should return 400 for malformed JSON")
    void testMalformedJsonReturns400() {
        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{this is not json}")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    @DisplayName("Should process a right-skewed tree near the depth limit")
    void testRightSkewedTreeAtDepthLimit() {
        // Right-skewed tree of exactly MAX_DEPTH (500) levels as raw JSON — must succeed
        String json = buildRightSkewedJson(500);

        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(json)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Runtime-Ms");
    }

    @Test
    @DisplayName("Should throw exception when tree depth exceeds MAX_DEPTH")
    void testMaxDepthValidation() {
        // Left-skewed tree of 502 levels as raw JSON — exceeds MAX_DEPTH=500
        String json = buildLeftSkewedJson(502);

        client.post().uri("/api/v1/trees/level-order")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(json)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.error").value((String s) -> s.startsWith("Tree depth exceeds security limits"));
    }

    /** Builds {"value":1,"right":{"value":2,"right":...}} with {@code depth} levels. */
    private static String buildRightSkewedJson(int depth) {
        StringBuilder sb = new StringBuilder();
        for (int i = 1; i <= depth; i++) {
            sb.append("{\"value\":").append(i);
            if (i < depth) sb.append(",\"right\":");
        }
        for (int i = 0; i < depth; i++) sb.append('}');
        return sb.toString();
    }

    /** Builds {"value":1,"left":{"value":2,"left":...}} with {@code depth} levels. */
    private static String buildLeftSkewedJson(int depth) {
        StringBuilder sb = new StringBuilder();
        for (int i = 1; i <= depth; i++) {
            sb.append("{\"value\":").append(i);
            if (i < depth) sb.append(",\"left\":");
        }
        for (int i = 0; i < depth; i++) sb.append('}');
        return sb.toString();
    }
}
