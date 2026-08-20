import { describe, expect, it } from 'vitest';
import { DemoWorkflowProcessor } from './workflow-processor.js';

describe('demo workflow processor', () => {
  it('executes a queued demo job and returns structured output', async () => {
    const processor = new DemoWorkflowProcessor();
    const result = await processor.process({ runId: 'run-1', input: { projectId: '00000000-0000-0000-0000-000000000001', title: '演示', content: '内容' } });
    expect(result.status).toBe('SUCCEEDED');
    expect(result.output.recommendations).toHaveLength(2);
  });
});
