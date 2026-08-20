import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Worker } from 'bullmq';
import { DemoWorkflowProcessor } from './workflow-processor.js';

dotenv.config({ path: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../.env') });

export function createWorkflowWorker(redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6380') {
  const processor = new DemoWorkflowProcessor();
  return new Worker('workflow-runs', async (job) => processor.process(job.data), { connection: { url: redisUrl } as any });
}

if (process.env.WORKER_PROCESS === 'true') {
  const worker = createWorkflowWorker();
  worker.on('completed', (job) => console.log(`Workflow completed: ${job.id}`));
  worker.on('failed', (job, error) => console.error(`Workflow failed: ${job?.id}`, error.message));
  console.log('Agent Worker ready: BullMQ + LangGraph.js');
}
