import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { FastifyReply } from 'fastify';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

/**
 * Adds X-Runtime-Ms and X-Runtime-Nanoseconds response headers.
 * Mirrors the benchmarking headers in Java's TreeResource and Kotlin's TreeResource.
 *
 * process.hrtime.bigint() → nanosecond-resolution monotonic clock,
 * equivalent to System.nanoTime() on the JVM.
 */
@Injectable()
export class TimingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const startNs = process.hrtime.bigint();
    const response = context.switchToHttp().getResponse<FastifyReply>();

    return next.handle().pipe(
      tap(() => {
        const durationNs = process.hrtime.bigint() - startNs;
        const durationMs = Number(durationNs) / 1_000_000;
        response.header('X-Runtime-Ms', durationMs.toFixed(3));
        response.header('X-Runtime-Nanoseconds', durationNs.toString());
      }),
    );
  }
}
