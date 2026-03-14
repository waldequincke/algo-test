import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { Readable } from 'node:stream';
import { AppModule } from './app.module';
import { TreeExceptionFilter } from './infrastructure/tree-exception.filter';
import { TimingInterceptor } from './infrastructure/timing.interceptor';

const MAX_JSON_NESTING_DEPTH = 1_000;
const MAX_BODY_SIZE = 10 * 1024 * 1024; // 10 MB

/**
 * Layer 1 defense: reject JSON nested beyond MAX_JSON_NESTING_DEPTH at parse
 * time, before any object is allocated — mirrors JacksonSecurityCustomizer.
 */
function measureJsonDepth(json: string): number {
  let maxDepth = 0;
  let depth = 0;
  let inString = false;

  for (let i = 0; i < json.length; i++) {
    const ch = json[i];
    if (ch === '\\' && inString) { i++; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === '{' || ch === '[') maxDepth = Math.max(maxDepth, ++depth);
    else if (ch === '}' || ch === ']') depth--;
  }

  return maxDepth;
}

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter({ bodyLimit: MAX_BODY_SIZE }),
  );

  // Layer 1: JSON depth guard applied at parse time (before deserialization).
  const fastify = app.getHttpAdapter().getInstance();
  fastify.addHook('preParsing', async (request: any, reply: any, payload: any) => {
    const contentType: string = request.headers['content-type'] ?? '';
    if (!contentType.includes('application/json')) return;

    const chunks: Buffer[] = [];
    let totalSize = 0;
    for await (const chunk of payload) {
      const buf: Buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      totalSize += buf.length;
      if (totalSize > MAX_BODY_SIZE) {
        await reply.status(413).send({ error: 'Request body too large' });
        return Readable.from([]);
      }
      chunks.push(buf);
    }

    const raw = Buffer.concat(chunks);
    const depth = measureJsonDepth(raw.toString('utf8'));
    if (depth > MAX_JSON_NESTING_DEPTH) {
      await reply.status(400).send({
        error: `JSON nesting depth exceeds security limit (max: ${MAX_JSON_NESTING_DEPTH})`,
      });
      return Readable.from([]);
    }

    return Readable.from(raw);
  });

  app.useGlobalPipes(new ValidationPipe({ transform: true, whitelist: true }));
  app.useGlobalFilters(new TreeExceptionFilter());
  app.useGlobalInterceptors(new TimingInterceptor());

  const document = SwaggerModule.createDocument(
    app,
    new DocumentBuilder()
      .setTitle('Algo Test — Node.js Worker Threads')
      .setDescription('BFS level-order tree traversal — worker thread pool benchmark endpoint')
      .setVersion('1.0.0')
      .build(),
  );
  SwaggerModule.setup('q/swagger-ui', app, document);

  const port = process.env.PORT ?? 8083;
  await app.listen(port, '0.0.0.0');
}

bootstrap();
