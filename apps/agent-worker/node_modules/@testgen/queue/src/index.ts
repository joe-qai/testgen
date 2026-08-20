import { Queue } from 'bullmq';

export type WorkflowQueueInput = { runId: string; organizationId: string; projectId: string };
export interface QueueAdapter { enqueueWorkflowRun(input: WorkflowQueueInput): Promise<void>; cancelWorkflowRun(runId: string): Promise<void>; healthCheck(): Promise<boolean>; }

export class BullMQQueueAdapter implements QueueAdapter {
  private readonly queue: Queue;
  constructor(connection = process.env.REDIS_URL ?? 'redis://localhost:6380') { this.queue = new Queue('workflow-runs', { connection: { url: connection } as any }); }
  async enqueueWorkflowRun(input: WorkflowQueueInput) { await this.queue.add('workflow-run', input, { jobId: input.runId, removeOnComplete: 100, removeOnFail: 100 }); }
  async cancelWorkflowRun(runId: string) { const job = await this.queue.getJob(runId); if (job) await job.remove(); }
  async healthCheck() { try { await this.queue.getJobCounts(); return true; } catch { return false; } }
}

export class PlatformQueueAdapter implements QueueAdapter {
  async enqueueWorkflowRun(): Promise<void> { throw new Error('Platform queue adapter is not configured'); }
  async cancelWorkflowRun(): Promise<void> { throw new Error('Platform queue adapter is not configured'); }
  async healthCheck(): Promise<boolean> { return false; }
}
