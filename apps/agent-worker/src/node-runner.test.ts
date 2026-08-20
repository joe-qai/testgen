import { describe, expect, it, vi } from 'vitest';
import { createNodeRunner, type NodeRunRecord } from './node-runner.js';

describe('node runner', () => {
  it('executes a handler and emits a SUCCEEDED node run record with usage', async () => {
    const records: NodeRunRecord[] = [];
    const handler = async () => ({ length: 5 });
    const run = createNodeRunner({
      nodeName: 'analyze_content',
      handler: async () => ({ result: (await handler()).length, usage: { inputTokens: 10, outputTokens: 2 } }),
      onNodeRun: (record) => records.push(record),
    });
    const output = await run({ input: {} });
    expect(output).toEqual({ result: 5, usage: { inputTokens: 10, outputTokens: 2 } });
    expect(records).toHaveLength(1);
    expect(records[0].nodeName).toBe('analyze_content');
    expect(records[0].status).toBe('SUCCEEDED');
    expect(records[0].attempt).toBe(1);
    expect(records[0].usage).toEqual({ inputTokens: 10, outputTokens: 2 });
    expect(records[0].error).toBeNull();
  });

  it('retries on failure up to maxAttempts then emits SUCCEEDED', async () => {
    const records: NodeRunRecord[] = [];
    let calls = 0;
    const run = createNodeRunner({
      nodeName: 'retry_node',
      handler: async () => {
        calls += 1;
        if (calls < 3) throw new Error(`attempt ${calls} failed`);
        return { ok: true, usage: { inputTokens: 1 } };
      },
      maxAttempts: 3,
      onNodeRun: (record) => records.push(record),
    });
    const output = await run({});
    expect(calls).toBe(3);
    expect(output).toEqual({ ok: true, usage: { inputTokens: 1 } });
    expect(records).toHaveLength(3);
    expect(records[0].status).toBe('FAILED');
    expect(records[1].status).toBe('FAILED');
    expect(records[2].status).toBe('SUCCEEDED');
    expect(records.map((r) => r.attempt)).toEqual([1, 2, 3]);
  });

  it('throws after exhausting all retries', async () => {
    const records: NodeRunRecord[] = [];
    const run = createNodeRunner({
      nodeName: 'always_fail',
      handler: async () => { throw new Error('boom'); },
      maxAttempts: 2,
      onNodeRun: (record) => records.push(record),
    });
    await expect(run({})).rejects.toThrow('boom');
    expect(records).toHaveLength(2);
    expect(records.every((r) => r.status === 'FAILED')).toBe(true);
    expect(records.every((r) => r.error === 'boom')).toBe(true);
  });
});