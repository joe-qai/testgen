import { runDemoAgent } from './main.js';

export type DemoJob = { runId: string; input: { projectId: string; title: string; content: string } };
export type DemoJobResult = { runId: string; status: 'SUCCEEDED' | 'FAILED'; output: Awaited<ReturnType<typeof runDemoAgent>>; error?: string };

export class DemoWorkflowProcessor {
  async process(job: DemoJob): Promise<DemoJobResult> {
    try {
      const output = await runDemoAgent(job.input);
      return { runId: job.runId, status: 'SUCCEEDED', output };
    } catch (error) {
      return { runId: job.runId, status: 'FAILED', output: { summary: '', review: '', recommendations: [] }, error: error instanceof Error ? error.message : 'Unknown workflow error' };
    }
  }
}
