package org.example.infrastructure;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebInputException;

import java.util.Map;

/**
 * Maps domain and framework exceptions to {@code 400 {"error": "..."}} responses.
 * Mirrors TreeExceptionHandler in the Quarkus implementations.
 *
 * {@link ServerWebInputException} covers:
 *   - Missing request body ({@code @RequestBody required=false} → null path)
 *   - Malformed JSON (Jackson {@code DecodingException} wrapped by WebFlux)
 *   - Type-mismatch errors during deserialization
 */
@RestControllerAdvice
public class TreeExceptionHandler {

    @ExceptionHandler(TreeProcessingException.class)
    public ResponseEntity<Map<String, String>> handleTreeProcessingException(
            TreeProcessingException ex) {
        return ResponseEntity.badRequest()
            .body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<Map<String, String>> handleServerWebInputException(
            ServerWebInputException ex) {
        String message = ex.getReason() != null ? ex.getReason() : "Invalid request body";
        return ResponseEntity.badRequest()
            .body(Map.of("error", message));
    }
}
