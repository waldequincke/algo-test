package org.example;

import io.quarkus.test.junit.QuarkusTest;
import org.example.trees.TreeNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.is;
import static org.hamcrest.CoreMatchers.startsWith;
import static org.hamcrest.Matchers.notNullValue;

@QuarkusTest
public class TreeResourceTest {

    @Test
    @DisplayName("Should return level order traversal and benchmark headers")
    public void testLevelOrderEndpoint() {
        String payload = "{\"value\": 1, \"left\": {\"value\": 2}, \"right\": {\"value\": 3}}";

        given()
            .contentType("application/json")
            .body(payload)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", is(1))
            .body("[1][0]", is(2))
            .body("[1][1]", is(3));
    }

    @Test
    @DisplayName("Should return single-element result for a leaf node")
    public void testSingleLeafNode() {
        String payload = "{\"value\": 42}";

        given()
            .contentType("application/json")
            .body(payload)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", is(42));
    }

    @Test
    @DisplayName("Should process a node with value=0 (default int) when only value field is absent")
    public void testNodeWithZeroValueDefault() {
        // {} deserializes to TreeNode(value=0, left=null, right=null) — documents the behaviour explicitly
        String payload = "{}";

        given()
            .contentType("application/json")
            .body(payload)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", is(0));
    }

    @Test
    @DisplayName("Should return 400 when request body is empty")
    public void testNullBodyReturns400() {
        given()
            .contentType("application/json")
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400);
    }

    @Test
    @DisplayName("Should return 400 for malformed JSON")
    public void testMalformedJsonReturns400() {
        given()
            .contentType("application/json")
            .body("{this is not json}")
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400);
    }

    @Test
    @DisplayName("Should process a right-skewed tree near the depth limit")
    public void testRightSkewedTreeAtDepthLimit() {
        // Build a right-skewed tree of exactly MAX_DEPTH (500) levels — should succeed
        TreeNode leaf = new TreeNode(500, null, null);
        for (int i = 499; i >= 1; i--) {
            leaf = new TreeNode(i, null, leaf);
        }

        given()
            .contentType("application/json")
            .body(leaf)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue());
    }

    @Test
    @DisplayName("Should throw exception when tree depth exceeds MAX_DEPTH")
    public void testMaxDepthValidation() {
        // Build a left-skewed tree of 502 levels (exceeds MAX_DEPTH=500)
        TreeNode deepTree = new TreeNode(1, null, null);
        for (int i = 0; i < 501; i++) {
            deepTree = new TreeNode(i, deepTree, null);
        }

        given()
            .contentType("application/json")
            .body(deepTree)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400)
            .body("error", startsWith("Tree depth exceeds security limits"));
    }
}
