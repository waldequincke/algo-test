import { Injectable, NestMiddleware } from '@nestjs/common';
import { FastifyReply, FastifyRequest } from 'fastify';

/**
 * Rejects POST requests with no body — mirrors Java/Kotlin behaviour where
 * Jackson deserialises an absent body as null and the controller throws
 * TreeProcessingException("Root node cannot be null").
 *
 * Checking Content-Length is the only reliable way to tell them apart:
 *   - No body sent  → Content-Length absent or 0 → 400
 *   - '{}' body sent → Content-Length: 2          → 200 (valid TreeNodeDto)
 */
@Injectable()
export class RequireBodyMiddleware implements NestMiddleware {
  use(req: FastifyRequest, res: FastifyReply, next: () => void): void {
    const len = parseInt((req.headers['content-length'] as string) ?? '0', 10);
    if (len === 0) {
      res.status(400).send({ error: 'Root node cannot be null' });
      return;
    }
    next();
  }
}
