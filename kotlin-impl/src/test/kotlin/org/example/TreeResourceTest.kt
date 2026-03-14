package org.example

import io.quarkus.test.junit.QuarkusTest
import io.restassured.RestAssured.given
import org.example.trees.TreeNode
import org.hamcrest.CoreMatchers.`is`
import org.hamcrest.CoreMatchers.startsWith
import org.hamcrest.Matchers.notNullValue
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test

@QuarkusTest
class TreeResourceTest {

    @Test
    @DisplayName("Should return level order traversal and benchmark headers")
    fun testLevelOrderEndpoint() {
        val payload = """{"value": 1, "left": {"value": 2}, "right": {"value": 3}}"""

        given()
            .contentType("application/json")
            .body(payload)
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", `is`(1))
            .body("[1][0]", `is`(2))
            .body("[1][1]", `is`(3))
    }

    @Test
    @DisplayName("Should return single-element result for a leaf node")
    fun testSingleLeafNode() {
        given()
            .contentType("application/json")
            .body("""{"value": 42}""")
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", `is`(42))
    }

    @Test
    @DisplayName("Should process a node with value=0 when only value field is absent")
    fun testNodeWithZeroValueDefault() {
        // {} deserialises to TreeNode(value=0, left=null, right=null) via Jackson Kotlin module
        given()
            .contentType("application/json")
            .body("{}")
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
            .body("[0][0]", `is`(0))
    }

    @Test
    @DisplayName("Should return 400 when request body is empty")
    fun testNullBodyReturns400() {
        given()
            .contentType("application/json")
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400)
    }

    @Test
    @DisplayName("Should return 400 for malformed JSON")
    fun testMalformedJsonReturns400() {
        given()
            .contentType("application/json")
            .body("{this is not json}")
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400)
    }

    @Test
    @DisplayName("Should process a right-skewed tree near the depth limit")
    fun testRightSkewedTreeAtDepthLimit() {
        // Right-skewed tree of exactly MAX_DEPTH (500) levels — must succeed
        var leaf = TreeNode(500)
        for (i in 499 downTo 1) {
            leaf = TreeNode(i, null, leaf)
        }

        given()
            .contentType("application/json")
            .body(leaf)
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(200)
            .header("X-Runtime-Ms", notNullValue())
    }

    @Test
    @DisplayName("Should throw exception when tree depth exceeds MAX_DEPTH")
    fun testMaxDepthValidation() {
        // Left-skewed tree of 502 levels — exceeds MAX_DEPTH=500
        var deepTree = TreeNode(1)
        for (i in 0..500) {
            deepTree = TreeNode(i, deepTree, null)
        }

        given()
            .contentType("application/json")
            .body(deepTree)
            .`when`()
            .post("/api/v1/trees/level-order")
            .then()
            .statusCode(400)
            .body("error", startsWith("Tree depth exceeds security limits"))
    }
}
