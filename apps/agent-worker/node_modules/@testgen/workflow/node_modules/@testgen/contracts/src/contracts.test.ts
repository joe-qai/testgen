import { describe, expect, it } from 'vitest';
import { DemoAgentInputSchema, WorkflowRunStatusSchema } from './index.js';

describe('shared contracts', () => {
  it('accepts supported workflow statuses', () => {
    expect(WorkflowRunStatusSchema.parse('RUNNING')).toBe('RUNNING');
  });
  it('rejects incomplete demo input', () => {
    expect(() => DemoAgentInputSchema.parse({ title: 'x' })).toThrow();
  });
});
