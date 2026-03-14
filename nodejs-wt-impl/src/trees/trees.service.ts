import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as os from 'os';
import * as path from 'path';
import { WorkerPool } from '../infrastructure/worker-pool';
import { TreeProcessingException } from '../infrastructure/tree-processing.exception';
import { TreeNodeDto } from './dto/tree-node.dto';

/**
 * BFS level-order traversal — Worker Threads edition.
 *
 * Concurrency model:
 *   WorkerPool pre-spawns os.availableParallelism() OS threads at startup.
 *   Each solveLevelOrder() call dispatches the CPU-bound BFS to an idle thread,
 *   keeping the event loop free for I/O and new incoming connections.
 *   This is the direct Node.js counterpart to:
 *     Java:   @RunOnVirtualThread  (ForkJoinPool)
 *     Kotlin: withContext(Dispatchers.Default)  (ForkJoinPool.commonPool())
 *
 * Path resolution:
 *   The worker is a plain .js file. nest-cli.json copies it to dist/ via the
 *   "assets" option, so path.resolve(__dirname, ...) works in both dev and prod.
 */
@Injectable()
export class TreesService implements OnModuleDestroy {
  private readonly logger = new Logger(TreesService.name);
  private readonly maxDepth: number;
  private readonly maxNodes: number;
  private readonly pool: WorkerPool<number[][]>;

  constructor(private readonly config: ConfigService) {
    this.maxDepth = this.config.get<number>('TREE_MAX_DEPTH', 500);
    this.maxNodes = this.config.get<number>('TREE_MAX_NODES', 10_000);

    const threads = os.availableParallelism();
    this.pool = new WorkerPool<number[][]>(
      path.resolve(__dirname, 'workers', 'level-order.worker.js'),
      threads,
    );

    this.logger.log(
      `Worker thread pool ready — ${threads} threads (os.availableParallelism())`,
    );
  }

  async onModuleDestroy(): Promise<void> {
    await this.pool.destroy();
  }

  async solveLevelOrder(root: TreeNodeDto): Promise<number[][]> {
    try {
      return await this.pool.run({ root, maxDepth: this.maxDepth, maxNodes: this.maxNodes });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      throw new TreeProcessingException(message);
    }
  }
}
