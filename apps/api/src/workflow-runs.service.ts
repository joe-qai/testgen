import { assertTransition } from '@testgen/workflow';
import { WorkflowEventTypeSchema, WorkflowRunStatus, WorkflowRunStatusSchema } from '@testgen/contracts';

export type WorkflowRunInput = { organizationId: string; projectId: string; requestedBy: string; workflowCode: string; idempotencyKey: string; input: Record<string, unknown> };
export type WorkflowRun = WorkflowRunInput & { id: string; status: WorkflowRunStatus; progress: number; createdAt: string };
export type WorkflowEvent = { id: string; runId: string; sequence: number; eventType: string; payload: Record<string, unknown>; createdAt: string };

export class InMemoryWorkflowRunService {
  private readonly runs = new Map<string, WorkflowRun>();
  private readonly eventsByRun = new Map<string, WorkflowEvent[]>();
  private key(input: WorkflowRunInput) { return `${input.organizationId}:${input.requestedBy}:${input.idempotencyKey}`; }
  create(input: WorkflowRunInput): WorkflowRun {
    const existing = [...this.runs.values()].find((run) => this.key(run) === this.key(input));
    if (existing) return existing;
    const run: WorkflowRun = { ...input, id: crypto.randomUUID(), status: 'QUEUED', progress: 0, createdAt: new Date().toISOString() };
    this.runs.set(run.id, run);
    this.emit(run.id, 'RUN_STARTED', { status: run.status });
    return run;
  }
  get(id: string) { const run = this.runs.get(id); if (!run) throw new Error('Workflow run not found'); return run; }
  events(id: string) { return this.eventsByRun.get(id) ?? []; }
  transition(id: string, next: WorkflowRunStatus) { const run = this.get(id); assertTransition(run.status, next); run.status = WorkflowRunStatusSchema.parse(next); if (next === 'SUCCEEDED' || next === 'FAILED' || next === 'CANCELLED') run.progress = 100; this.emit(id, next === 'SUCCEEDED' ? 'RUN_COMPLETED' : 'NODE_PROGRESS', { status: next, progress: run.progress }); return run; }
  cancel(id: string) { const run = this.get(id); if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(run.status)) throw new Error('Workflow run is terminal'); return this.transition(id, 'CANCELLED'); }
  private emit(runId: string, eventType: string, payload: Record<string, unknown>) { const parsed = WorkflowEventTypeSchema.safeParse(eventType); if (!parsed.success) throw new Error(`Unsupported event type: ${eventType}`); const events = this.eventsByRun.get(runId) ?? []; events.push({ id: crypto.randomUUID(), runId, sequence: events.length + 1, eventType: parsed.data, payload, createdAt: new Date().toISOString() }); this.eventsByRun.set(runId, events); }
}
