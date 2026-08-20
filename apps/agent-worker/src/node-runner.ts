import type { LLMUsage } from './llm/adapter.js';

export type NodeRunRecord = {
  nodeName: string;
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  attempt: number;
  startedAt: string;
  completedAt: string | null;
  error: string | null;
  usage: LLMUsage | null;
};

export type NodeHandler<TInput, TOutput> = (input: TInput) => Promise<TOutput & { usage?: LLMUsage }>;

export type CreateNodeRunnerOptions<TInput, TOutput> = {
  nodeName: string;
  handler: NodeHandler<TInput, TOutput>;
  maxAttempts?: number;
  onNodeRun?: (record: NodeRunRecord) => void;
};

export function createNodeRunner<TInput, TOutput>(options: CreateNodeRunnerOptions<TInput, TOutput>): (input: TInput) => Promise<TOutput & { usage?: LLMUsage }> {
  const { nodeName, handler, maxAttempts = 1, onNodeRun } = options;

  return async (input: TInput) => {
    let lastError: Error | null = null;
    let usage: LLMUsage | null = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const startedAt = new Date().toISOString();
      try {
        const result = await handler(input);
        usage = result.usage ?? null;
        const record: NodeRunRecord = { nodeName, status: 'SUCCEEDED', attempt, startedAt, completedAt: new Date().toISOString(), error: null, usage };
        onNodeRun?.(record);
        return result;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        const record: NodeRunRecord = { nodeName, status: 'FAILED', attempt, startedAt, completedAt: new Date().toISOString(), error: lastError.message, usage: null };
        onNodeRun?.(record);
        if (attempt >= maxAttempts) throw lastError;
      }
    }

    throw lastError ?? new Error(`Node ${nodeName} failed`);
  };
}

export function aggregateUsage(records: NodeRunRecord[]): LLMUsage {
  const inputTokens = records.reduce((sum, record) => sum + (record.usage?.inputTokens ?? 0), 0);
  const outputTokens = records.reduce((sum, record) => sum + (record.usage?.outputTokens ?? 0), 0);
  return { inputTokens, outputTokens };
}