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
            .header("X-Runtime-Ms", notNullValue()) // Validates your benchmark exists
            .body("[0][0]", is(1))
            .body("[1][0]", is(2))
            .body("[1][1]", is(3));
    }

    @Test
    @DisplayName("Should work with an empty root")
    public void testEmptyObjectValidation() {
        String payload = "{}";

        given()
            .contentType("application/json")
            .body(payload)
            .when()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue()) // Validates your benchmark exists
            .body("[0][0]", is(0));
    }

    @Test
    @DisplayName("Should throw exception when tree depth exceeds MAX_DEPTH")
    public void testMaxDepthValidation() {
        // Generate a very deep left-skewed tree (1001 nodes)
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
            .statusCode(400) // Your TreeExceptionHandler maps this
            .body("error", startsWith("Tree depth exceeds security limits"));
    }
}
