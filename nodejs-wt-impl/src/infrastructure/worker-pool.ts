import { Worker } from 'worker_threads';

type WorkerMessage<T> =
  | { ok: true; result: T }
  | { ok: false; error: string };

interface Task<T> {
  data: unknown;
  resolve: (value: T) => void;
  reject: (reason: Error) => void;
}

/**
 * Fixed-size worker thread pool — pure Node.js 24 worker_threads, no external deps.
 *
 * Design:
 *   - Pre-spawns `size` threads at construction time (no per-request spawn cost).
 *   - Idle threads are kept in a LIFO stack for CPU cache locality.
 *   - Pending requests are queued in FIFO order when all threads are busy.
 *   - Worker errors (thrown inside the worker) are communicated via an envelope
 *     { ok, result|error } so that a single 'message' handler covers both paths.
 *     This is safer than relying on the 'error' event, which only fires for
 *     uncaught exceptions that escape the worker's message handler.
 *
 * Comparable to:
 *   Java:   ForkJoinPool (backs @RunOnVirtualThread and Dispatchers.Default)
 *   Kotlin: Dispatchers.Default (ForkJoinPool.commonPool())
 */
export class WorkerPool<T = unknown> {
  private readonly workers: Worker[] = [];
  private readonly idle: Worker[] = [];
  private readonly queue: Task<T>[] = [];
  private readonly pending = new Map<Worker, Task<T>>();

  constructor(filename: string, size: number) {
    for (let i = 0; i < size; i++) {
      const worker = new Worker(filename);
      this.wire(worker);
      this.workers.push(worker);
      this.idle.push(worker);
    }
  }

  private wire(worker: Worker): void {
    worker.on('message', (msg: WorkerMessage<T>) => {
      const task = this.pending.get(worker)!;
      this.pending.delete(worker);

      if (msg.ok) {
        task.resolve(msg.result);
      } else {
        task.reject(new Error(msg.error));
      }

      this.release(worker);
    });

    // Fires only for crashes that escape the message handler (e.g. OOM)
    worker.on('error', (err: Error) => {
      const task = this.pending.get(worker);
      if (task) {
        this.pending.delete(worker);
        task.reject(err);
        this.release(worker);
      }
    });
  }

  private dispatch(worker: Worker, task: Task<T>): void {
    this.pending.set(worker, task);
    worker.postMessage(task.data);
  }

  private release(worker: Worker): void {
    const next = this.queue.shift();
    if (next) {
      this.dispatch(worker, next);
    } else {
      this.idle.push(worker); // LIFO: most-recently-used thread first
    }
  }

  run(data: unknown): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const task: Task<T> = { data, resolve, reject };
      const worker = this.idle.pop(); // LIFO pop
      if (worker) {
        this.dispatch(worker, task);
      } else {
        this.queue.push(task); // FIFO queue when all threads busy
      }
    });
  }

  async destroy(): Promise<void> {
    await Promise.all(this.workers.map((w) => w.terminate()));
  }
}
