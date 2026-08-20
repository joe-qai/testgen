import { describe, expect, it } from 'vitest';
import { InMemoryWorkflowRunService } from './workflow-runs.service.js';

describe('workflow run service', () => {
  it('creates an idempotent queued run and emits an event', () => {
    const service = new InMemoryWorkflowRunService();
    const input = { organizationId: 'org-1', projectId: 'project-1', requestedBy: 'user-1', workflowCode: 'demo-agent', idempotencyKey: 'idem-12345678', input: { title: 'Demo', content: 'Content' } };
    const first = service.create(input);
    const second = service.create(input);
    expect(first.id).toBe(second.id);
    expect(first.status).toBe('QUEUED');
    expect(service.events(first.id)).toHaveLength(1);
  });

  it('rejects cancellation of a completed run', () => {
    const service = new InMemoryWorkflowRunService();
    const run = service.create({ organizationId: 'org-1', projectId: 'project-1', requestedBy: 'user-1', workflowCode: 'demo-agent', idempotencyKey: 'idem-87654321', input: {} });
    service.transition(run.id, 'RUNNING');
    service.transition(run.id, 'SUCCEEDED');
    expect(() => service.cancel(run.id)).toThrow('terminal');
  });
});
