'use strict';

/**
 * Worker thread — runs on a dedicated OS thread from the pool.
 *
 * Communication protocol (envelope pattern):
 *   IN  ← parentPort.on('message', { root, maxDepth, maxNodes })
 *   OUT → parentPort.postMessage({ ok: true,  result: number[][] })
 *       → parentPort.postMessage({ ok: false, error:  string    })
 *
 * Using an envelope instead of relying on the worker 'error' event is safer:
 * the 'error' event only fires for uncaught exceptions that escape this handler,
 * whereas a try/catch + ok flag covers all expected business-logic errors.
 *
 * Queue optimisation: head-pointer on a plain Array → O(1) amortised dequeue.
 */
const { parentPort } = require('worker_threads');

parentPort.on('message', function ({ root, maxDepth, maxNodes }) {
  try {
    parentPort.postMessage({ ok: true, result: levelOrder(root, maxDepth, maxNodes) });
  } catch (err) {
    parentPort.postMessage({ ok: false, error: err.message });
  }
});

function levelOrder(root, maxDepth, maxNodes) {
  const result = [];
  const queue = [root];
  let head = 0;
  let totalNodes = 0;

  while (head < queue.length) {
    if (result.length >= maxDepth) {
      throw new Error(`Tree depth exceeds security limits (Max: ${maxDepth})`);
    }

    const levelSize = queue.length - head;
    totalNodes += levelSize;

    if (totalNodes > maxNodes) {
      throw new Error(`Tree node count exceeds security limits (Max: ${maxNodes})`);
    }

    const levelValues = new Array(levelSize);
    const levelEnd = head + levelSize;

    for (let i = 0; head < levelEnd; head++, i++) {
      const node = queue[head];
      levelValues[i] = node.value ?? 0;
      if (node.left != null) queue.push(node.left);
      if (node.right != null) queue.push(node.right);
    }

    result.push(levelValues);
  }

  return result;
}
