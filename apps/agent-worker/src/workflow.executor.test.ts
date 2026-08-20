import { describe, expect, it } from 'vitest';
import { createMockLLMAdapter } from './llm/adapter.js';
import { executeWorkflow } from './workflow.executor.js';

describe('workflow executor', () => {
  it('runs the 4-node workflow with mock LLM and records per-node runs', async () => {
    const llm = createMockLLMAdapter();
    const result = await executeWorkflow({ projectId: '00000000-0000-0000-0000-000000000001', title: '登录模块', content: '验证登录功能' }, { llm });
    expect(result.nodeRuns.map((node) => node.nodeName)).toEqual(['prepare_input', 'analyze_content', 'review_analysis', 'build_result']);
    expect(result.nodeRuns.every((node) => node.status === 'SUCCEEDED')).toBe(true);
    expect(result.nodeRuns.every((node) => node.attempt === 1)).toBe(true);
    expect(result.output.summary.length).toBeGreaterThan(0);
    expect(result.output.recommendations.length).toBeGreaterThan(0);
    expect(result.usage.inputTokens ?? 0).toBeGreaterThan(0);
  });

  it('persists node runs even when a node fails after retries', async () => {
    const llm = new MockLLMWithFailure();
    const result = await executeWorkflow({ projectId: '00000000-0000-0000-0000-000000000002', title: '失败模块', content: '内容' }, { llm, maxAttempts: 2 });
    const failedRuns = result.nodeRuns.filter((node) => node.status === 'FAILED');
    expect(failedRuns.length).toBeGreaterThan(0);
    expect(failedRuns.every((node) => node.error)).toBe(true);
  });

  it('can be interrupted: retries exhausted on a failing node throws', async () => {
    const llm = new MockLLMWithFailure('always');
    await expect(executeWorkflow({ projectId: '00000000-0000-0000-0000-000000000003', title: '总失败', content: 'x' }, { llm, maxAttempts: 1 })).rejects.toThrow();
  });
});

class MockLLMWithFailure {
  private calls = 0;
  constructor(private readonly mode: 'once' | 'always' = 'once') {}
  async complete() {
    this.calls += 1;
    if (this.mode === 'always') throw new Error('LLM down');
    if (this.calls === 1) throw new Error('LLM down once');
    return { text: '恢复后的结果', usage: { inputTokens: 5, outputTokens: 1 } };
  }
}