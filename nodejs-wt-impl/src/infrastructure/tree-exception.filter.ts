import { ExceptionFilter, Catch, ArgumentsHost } from '@nestjs/common';
import { FastifyReply } from 'fastify';
import { TreeProcessingException } from './tree-processing.exception';

/**
 * Maps TreeProcessingException → HTTP 400 { "error": "..." }
 * Mirrors Java's TreeExceptionHandler / Kotlin's TreeExceptionHandler.
 */
@Catch(TreeProcessingException)
export class TreeExceptionFilter implements ExceptionFilter {
  catch(exception: TreeProcessingException, host: ArgumentsHost): void {
    host
      .switchToHttp()
      .getResponse<FastifyReply>()
      .status(400)
      .send({ error: exception.message });
  }
}
