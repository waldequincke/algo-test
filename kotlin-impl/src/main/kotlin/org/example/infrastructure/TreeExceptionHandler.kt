package org.example.infrastructure

import jakarta.ws.rs.core.MediaType
import jakarta.ws.rs.core.Response
import jakarta.ws.rs.ext.ExceptionMapper
import jakarta.ws.rs.ext.Provider

@Provider
class TreeExceptionHandler : ExceptionMapper<TreeProcessingException> {
    override fun toResponse(exception: TreeProcessingException): Response =
        Response.status(Response.Status.BAD_REQUEST)
            .type(MediaType.APPLICATION_JSON_TYPE)
            .entity(mapOf("error" to exception.message))
            .build()
}
