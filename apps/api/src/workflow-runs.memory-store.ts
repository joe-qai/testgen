import type { WorkflowRunRecord, WorkflowEventRecord, WorkflowRunQuery, WorkflowRunStore } from '@testgen/workflow';

export function createMemoryWorkflowRunStore(): WorkflowRunStore {
  const runs = new Map<string, WorkflowRunRecord>();
  const events = new Map<string, WorkflowEventRecord[]>();

  return {
    async create(run) { runs.set(run.id, run); return run; },
    async update(id, patch) {
      const existing = runs.get(id);
      if (!existing) throw new Error(`Run not found: ${id}`);
      const updated = { ...existing, ...patch, updatedAt: new Date().toISOString() };
      runs.set(id, updated);
      return updated;
    },
    async findById(id) { return runs.get(id) ?? null; },
    async findByIdempotencyKey(organizationId, requestedBy, idempotencyKey) {
      for (const run of runs.values()) {
        if (run.organizationId === organizationId && run.requestedBy === requestedBy && run.idempotencyKey === idempotencyKey) return run;
      }
      return null;
    },
    async findByQuery(query: WorkflowRunQuery) {
      const all = [...runs.values()].filter((run) => run.organizationId === query.organizationId && (!query.projectId || run.projectId === query.projectId));
      const total = all.length;
      const items = all.slice((query.page - 1) * query.limit, query.page * query.limit);
      return { items, total };
    },
    async listEvents(runId) { return events.get(runId) ?? []; },
    async appendEvent(event) {
      const list = events.get(event.runId) ?? [];
      list.push(event);
      events.set(event.runId, list);
      return event;
    },
    async nextSequence(runId) { return (events.get(runId) ?? []).length; },
  };
}