import { describe, expect, it, vi } from 'vitest';
import type { WorkflowRunStore, WorkflowRunRecord, WorkflowEventRecord, WorkflowRunQuery } from '@testgen/workflow';
import type { QueueAdapter } from '@testgen/queue';
import { WorkflowRunService } from './workflow-runs.service.js';

class InMemoryStore implements WorkflowRunStore {
  runs = new Map<string, WorkflowRunRecord>();
  events = new Map<string, WorkflowEventRecord[]>();

  async create(run: WorkflowRunRecord): Promise<WorkflowRunRecord> {
    this.runs.set(run.id, run);
    return run;
  }
  async update(id: string, patch: Partial<Omit<WorkflowRunRecord, 'id' | 'createdAt'>>): Promise<WorkflowRunRecord> {
    const existing = this.runs.get(id);
    if (!existing) throw new Error(`Run not found: ${id}`);
    const updated = { ...existing, ...patch, updatedAt: new Date().toISOString() };
    this.runs.set(id, updated);
    return updated;
  }
  async findById(id: string): Promise<WorkflowRunRecord | null> {
    return this.runs.get(id) ?? null;
  }
  async findByIdempotencyKey(organizationId: string, requestedBy: string, idempotencyKey: string): Promise<WorkflowRunRecord | null> {
    for (const run of this.runs.values()) {
      if (run.organizationId === organizationId && run.requestedBy === requestedBy && run.idempotencyKey === idempotencyKey) return run;
    }
    return null;
  }
  async findByQuery(query: WorkflowRunQuery): Promise<{ items: WorkflowRunRecord[]; total: number }> {
    const all = [...this.runs.values()].filter((run) => run.organizationId === query.organizationId && (!query.projectId || run.projectId === query.projectId));
    const total = all.length;
    const items = all.slice((query.page - 1) * query.limit, query.page * query.limit);
    return { items, total };
  }
  async listEvents(runId: string): Promise<WorkflowEventRecord[]> {
    return this.events.get(runId) ?? [];
  }
  async appendEvent(event: WorkflowEventRecord): Promise<WorkflowEventRecord> {
    const list = this.events.get(event.runId) ?? [];
    list.push(event);
    this.events.set(event.runId, list);
    return event;
  }
  async nextSequence(runId: string): Promise<number> {
    return (this.events.get(runId) ?? []).length;
  }
}

function makeInput(overrides: Partial<{ organizationId: string; projectId: string; requestedBy: string; workflowCode: string; idempotencyKey: string; input: Record<string, unknown> }> = {}) {
  return {
    organizationId: 'org-1',
    projectId: 'project-1',
    requestedBy: 'user-1',
    workflowCode: 'demo-agent',
    idempotencyKey: 'idem-12345678',
    input: { title: 'Demo', content: 'Content' },
    ...overrides,
  };
}

describe('workflow run service', () => {
  it('creates an idempotent queued run and emits RUN_STARTED', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const input = makeInput();
    const first = await service.create(input);
    const second = await service.create(input);
    expect(first.id).toBe(second.id);
    expect(first.status).toBe('QUEUED');
    const events = await service.events(first.id);
    expect(events).toHaveLength(1);
    expect(events[0].eventType).toBe('RUN_STARTED');
  });

  it('transitions through statuses emitting events with increasing sequence', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-abcdef01' }));
    await service.transition(run.id, 'RUNNING');
    await service.transition(run.id, 'SUCCEEDED');
    const events = await service.events(run.id);
    expect(events.map((event) => event.eventType)).toEqual(['RUN_STARTED', 'NODE_STARTED', 'RUN_COMPLETED']);
    expect(events.map((event) => event.sequence)).toEqual([0, 1, 2]);
    const final = await service.get(run.id);
    expect(final.status).toBe('SUCCEEDED');
    expect(final.progress).toBe(100);
  });

  it('rejects cancellation of a completed run', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-87654321' }));
    await service.transition(run.id, 'RUNNING');
    await service.transition(run.id, 'SUCCEEDED');
    await expect(service.cancel(run.id)).rejects.toThrow('terminal');
  });

  it('filters runs by organization and project with pagination', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    await service.create(makeInput({ idempotencyKey: 'idem-aaaa0001' }));
    await service.create(makeInput({ idempotencyKey: 'idem-aaaa0002', projectId: 'project-2' }));
    await service.create(makeInput({ idempotencyKey: 'idem-aaaa0003', organizationId: 'org-2' }));
    const org1All = await service.findByQuery({ organizationId: 'org-1', page: 1, limit: 10 });
    expect(org1All.total).toBe(2);
    const org1Project1 = await service.findByQuery({ organizationId: 'org-1', projectId: 'project-1', page: 1, limit: 10 });
    expect(org1Project1.total).toBe(1);
    expect(org1Project1.items[0].projectId).toBe('project-1');
  });

  it('marks a cancel as CANCELLED at 100% progress and emits event', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-bbbb0001' }));
    await service.transition(run.id, 'RUNNING');
    const cancelled = await service.cancel(run.id);
    expect(cancelled.status).toBe('CANCELLED');
    expect(cancelled.progress).toBe(100);
    const events = await service.events(run.id);
    expect(events[events.length - 1].eventType).toBe('RUN_CANCELED');
  });

  it('enqueues a new run onto the queue exactly once', async () => {
    const store = new InMemoryStore();
    const enqueue = vi.fn<QueueAdapter['enqueueWorkflowRun']>(async () => {});
    const queue: QueueAdapter = { enqueueWorkflowRun: enqueue, cancelWorkflowRun: async () => {}, healthCheck: async () => true };
    const service = new WorkflowRunService(store, undefined, undefined, queue);
    const input = makeInput({ idempotencyKey: 'idem-cccc0001' });
    const first = await service.create(input);
    await service.create(input);
    expect(enqueue).toHaveBeenCalledTimes(1);
    expect(enqueue).toHaveBeenCalledWith({ runId: first.id, organizationId: 'org-1', projectId: 'project-1' });
  });

  it('does not fail creation when queue enqueue fails', async () => {
    const store = new InMemoryStore();
    const queue: QueueAdapter = { enqueueWorkflowRun: async () => { throw new Error('queue down'); }, cancelWorkflowRun: async () => {}, healthCheck: async () => false };
    const service = new WorkflowRunService(store, undefined, undefined, queue);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-dddd0001' }));
    expect(run.status).toBe('QUEUED');
  });

  it('records a completed run with output data', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-eeee0001' }));
    await service.transition(run.id, 'RUNNING');
    const completed = await service.complete(run.id, { summary: 'OK', review: 'PASS', recommendations: ['a'] });
    expect(completed.status).toBe('SUCCEEDED');
    expect(completed.progress).toBe(100);
    expect(completed.outputData).toEqual({ summary: 'OK', review: 'PASS', recommendations: ['a'] });
    const events = await service.events(run.id);
    expect(events[events.length - 1].eventType).toBe('RUN_COMPLETED');
  });

  it('records a failed run with error data', async () => {
    const store = new InMemoryStore();
    const service = new WorkflowRunService(store);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-ffff0001' }));
    await service.transition(run.id, 'RUNNING');
    const failed = await service.fail(run.id, 'boom');
    expect(failed.status).toBe('FAILED');
    expect(failed.progress).toBe(100);
    expect(failed.errorData).toEqual({ message: 'boom' });
  });

  it('publishes emitted events to the SSE bus for realtime delivery', async () => {
    const store = new InMemoryStore();
    const { SseEventBus } = await import('./sse-event-bus.js');
    const bus = new SseEventBus();
    const received: string[] = [];
    const service = new WorkflowRunService(store, undefined, undefined, undefined, bus);
    const run = await service.create(makeInput({ idempotencyKey: 'idem-aaaa0009' }));
    const unsubscribe = bus.subscribe(run.id, (chunk) => received.push(chunk));
    await service.transition(run.id, 'RUNNING');
    await service.complete(run.id, { summary: 'OK' });
    unsubscribe();
    expect(received.length).toBeGreaterThanOrEqual(1);
    expect(received[received.length - 1]).toContain('event: RUN_COMPLETED');
  });
});