import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TreeProcessingException } from '../infrastructure/tree-processing.exception';
import { TreeNodeDto } from './dto/tree-node.dto';

/**
 * BFS level-order traversal — Node.js event-loop edition.
 *
 * Concurrency model:
 *   Node.js runs on a single-threaded event loop backed by libuv's thread pool
 *   for I/O. CPU-bound work (this BFS) runs synchronously on the event loop —
 *   directly comparable to Java's VirtualThread scheduler and Kotlin's
 *   Dispatchers.Default (ForkJoinPool) under the same load profile.
 *
 * Queue optimisation:
 *   Uses a head-pointer on a plain Array instead of Array.shift() to achieve
 *   O(1) amortised dequeue (no per-element copy). Equivalent to Java's
 *   ArrayDeque / Kotlin's ArrayDeque.
 *
 * Security: identical depth / node-count guards as Java and Kotlin implementations.
 */
@Injectable()
export class TreesService {
  private readonly logger = new Logger(TreesService.name);
  private readonly maxDepth: number;
  private readonly maxNodes: number;

  constructor(private readonly config: ConfigService) {
    this.maxDepth = this.config.get<number>('TREE_MAX_DEPTH', 500);
    this.maxNodes = this.config.get<number>('TREE_MAX_NODES', 10_000);
  }

  solveLevelOrder(root: TreeNodeDto): number[][] {
    const result: number[][] = [];
    // Plain array with head pointer: O(1) amortised dequeue, no element shifting
    const queue: TreeNodeDto[] = [root];
    let head = 0;
    let totalNodes = 0;

    while (head < queue.length) {
      if (result.length >= this.maxDepth) {
        this.logger.error('Tree depth exceeded maximum limit');
        throw new TreeProcessingException(
          `Tree depth exceeds security limits (Max: ${this.maxDepth})`,
        );
      }

      const levelSize = queue.length - head;
      totalNodes += levelSize;

      if (totalNodes > this.maxNodes) {
        this.logger.error('Tree node count exceeded maximum limit');
        throw new TreeProcessingException(
          `Tree node count exceeds security limits (Max: ${this.maxNodes})`,
        );
      }

      // Pre-sized array + index assignment: no dynamic growth, matches worker.js pattern
      const levelValues = new Array<number>(levelSize);
      const levelEnd = head + levelSize;

      for (let i = 0; head < levelEnd; head++, i++) {
        const node = queue[head];
        levelValues[i] = node.value ?? 0;
        if (node.left  != null) queue.push(node.left);
        if (node.right != null) queue.push(node.right);
      }

      result.push(levelValues);
    }

    return result;
  }
}
