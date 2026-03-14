package org.example.infrastructure;

import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

import java.util.Map;

@Provider
public class TreeExceptionHandler implements ExceptionMapper<TreeProcessingException> {
    @Override
    public Response toResponse(TreeProcessingException exception) {
        return Response.status(Response.Status.BAD_REQUEST)
            .type(MediaType.APPLICATION_JSON_TYPE)
            .entity(Map.of("error", exception.getMessage()))
            .build();
    }
}
