import { describe, expect, it } from 'vitest';
import { createMockLLMAdapter } from './llm/adapter.js';
import { DemoWorkflowProcessor } from './workflow-processor.js';

describe('demo workflow processor', () => {
  it('executes a queued demo job and returns structured output with node runs', async () => {
    const processor = new DemoWorkflowProcessor(createMockLLMAdapter());
    const result = await processor.process({ runId: 'run-1', input: { projectId: '00000000-0000-0000-0000-000000000001', title: '演示', content: '内容' } });
    expect(result.status).toBe('SUCCEEDED');
    expect(result.output.recommendations).toHaveLength(2);
    expect(result.nodeRuns.map((node) => node.nodeName)).toEqual(['prepare_input', 'analyze_content', 'review_analysis', 'build_result']);
    expect(result.nodeRuns.every((node) => node.status === 'SUCCEEDED')).toBe(true);
    expect(result.usage.inputTokens ?? 0).toBeGreaterThan(0);
  });

  it('returns FAILED status with recorded node error when the workflow errors', async () => {
    const processor = new DemoWorkflowProcessor(createMockLLMAdapter());
    const result = await processor.process({ runId: 'run-2', input: { projectId: '00000000-0000-0000-0000-00000000badformat', title: '', content: '' } as never });
    expect(result.status).toBe('FAILED');
    expect(result.error).toBeTruthy();
  });
});