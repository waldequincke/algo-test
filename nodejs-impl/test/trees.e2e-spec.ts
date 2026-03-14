import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import * as express from 'express';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';
import { TreeExceptionFilter } from '../src/infrastructure/tree-exception.filter';
import { TimingInterceptor } from '../src/infrastructure/timing.interceptor';

function buildRightSkewedTree(depth: number): object {
  let node: Record<string, unknown> = { value: depth };
  for (let i = depth - 1; i >= 1; i--) {
    node = { value: i, right: node };
  }
  return node;
}

function buildLeftSkewedTree(depth: number): object {
  let node: Record<string, unknown> = { value: depth };
  for (let i = depth - 1; i >= 1; i--) {
    node = { value: i, left: node };
  }
  return node;
}

describe('TreesController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleRef.createNestApplication({ bodyParser: false });
    app.use(express.json({ limit: '10mb' }));
    app.useGlobalPipes(new ValidationPipe({ transform: true, whitelist: true }));
    app.useGlobalFilters(new TreeExceptionFilter());
    app.useGlobalInterceptors(new TimingInterceptor());
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('should return level-order traversal and benchmark headers', async () => {
    const payload = { value: 1, left: { value: 2 }, right: { value: 3 } };

    const res = await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .send(payload)
      .expect(200);

    expect(res.headers['x-runtime-ms']).toBeDefined();
    expect(res.body[0][0]).toBe(1);
    expect(res.body[1][0]).toBe(2);
    expect(res.body[1][1]).toBe(3);
  });

  it('should return single-element result for a leaf node', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .send({ value: 42 })
      .expect(200);

    expect(res.headers['x-runtime-ms']).toBeDefined();
    expect(res.body[0][0]).toBe(42);
  });

  it('should process a node with value=0 when body is {}', async () => {
    // {} deserialises to TreeNodeDto(value=0, left=undefined, right=undefined)
    const res = await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .send({})
      .expect(200);

    expect(res.body[0][0]).toBe(0);
  });

  it('should return 400 when request body is missing', async () => {
    await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .set('Content-Type', 'application/json')
      .expect(400);
  });

  it('should return 400 for malformed JSON', async () => {
    await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .set('Content-Type', 'application/json')
      .send('{this is not json}')
      .expect(400);
  });

  it('should process a right-skewed tree at the depth limit (500 levels)', async () => {
    const tree = buildRightSkewedTree(500);

    const res = await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .send(tree)
      .expect(200);

    expect(res.headers['x-runtime-ms']).toBeDefined();
  });

  it('should return 400 when tree depth exceeds MAX_DEPTH', async () => {
    // Left-skewed tree of 502 levels — exceeds MAX_DEPTH=500
    const tree = buildLeftSkewedTree(502);

    const res = await request(app.getHttpServer())
      .post('/api/v1/trees/level-order')
      .send(tree)
      .expect(400);

    expect(res.body.error).toMatch(/Tree depth exceeds security limits/);
  });
});
