import type { LLMAdapter } from './llm/adapter.js';
import { createMockLLMAdapter } from './llm/adapter.js';
import { executeWorkflow } from './workflow.executor.js';
import type { NodeRunRecord } from './node-runner.js';

export type DemoJob = { runId: string; input: { projectId: string; title: string; content: string } };
export type DemoJobResult = {
  runId: string;
  status: 'SUCCEEDED' | 'FAILED';
  output: { summary: string; review: string; recommendations: string[] };
  nodeRuns: NodeRunRecord[];
  usage: { inputTokens?: number; outputTokens?: number };
  error?: string;
};

export class DemoWorkflowProcessor {
  constructor(private readonly llm: LLMAdapter = createMockLLMAdapter()) {}

  async process(job: DemoJob): Promise<DemoJobResult> {
    try {
      const result = await executeWorkflow(job.input, { llm: this.llm, maxAttempts: 2 });
      return { runId: job.runId, status: 'SUCCEEDED', output: result.output, nodeRuns: result.nodeRuns, usage: result.usage };
    } catch (error) {
      return { runId: job.runId, status: 'FAILED', output: { summary: '', review: '', recommendations: [] }, nodeRuns: [], usage: { inputTokens: 0, outputTokens: 0 }, error: error instanceof Error ? error.message : 'Unknown workflow error' };
    }
  }
}