import { describe, expect, it } from 'vitest';
import { runDemoAgent } from './main.js';

describe('demo agent', () => {
  it('returns a structured result', async () => {
    const result = await runDemoAgent({ projectId: '00000000-0000-0000-0000-000000000001', title: '演示', content: '内容' });
    expect(result.recommendations.length).toBeGreaterThan(0);
  });
});
