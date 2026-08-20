import { assertTransition, type WorkflowRunStore, type WorkflowRunRecord } from '@testgen/workflow';
import { WorkflowRunStatus, WorkflowEventType } from '@testgen/contracts';
import type { QueueAdapter } from '@testgen/queue';
import type { SseEventBus } from './sse-event-bus.js';

export type WorkflowRunInput = { organizationId: string; projectId: string; requestedBy: string; workflowCode: string; idempotencyKey: string; input: Record<string, unknown> };

export class WorkflowRunService {
  constructor(
    private readonly store: WorkflowRunStore,
    private readonly now: () => Date = () => new Date(),
    private readonly idGenerator: () => string = () => crypto.randomUUID(),
    private readonly queue?: QueueAdapter,
    private readonly eventBus?: SseEventBus,
  ) {}

  async create(input: WorkflowRunInput) {
    const existing = await this.store.findByIdempotencyKey(input.organizationId, input.requestedBy, input.idempotencyKey);
    if (existing) return existing;
    const timestamp = this.now().toISOString();
    const run = {
      id: this.idGenerator(),
      organizationId: input.organizationId,
      projectId: input.projectId,
      workflowDefinitionId: null,
      workflowVersionId: null,
      workflowCode: input.workflowCode,
      requestedBy: input.requestedBy,
      status: 'QUEUED' as WorkflowRunStatus,
      inputData: input.input,
      outputData: null,
      errorData: null,
      currentNode: null,
      progress: 0,
      idempotencyKey: input.idempotencyKey,
      queuedAt: null,
      startedAt: null,
      completedAt: null,
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    await this.store.create(run);
    await this.emit(run.id, 'RUN_STARTED', { status: run.status });
    if (this.queue) {
      try {
        await this.queue.enqueueWorkflowRun({ runId: run.id, organizationId: run.organizationId, projectId: run.projectId });
      } catch (error) {
        const message = error instanceof Error ? error.message : 'unknown queue error';
        await this.emit(run.id, 'RUN_FAILED', { status: run.status, error: `queue enqueue failed: ${message}` });
      }
    }
    return run;
  }

  async get(id: string) {
    const run = await this.store.findById(id);
    if (!run) throw new Error('Workflow run not found');
    return run;
  }

  async events(id: string) {
    return this.store.listEvents(id);
  }

  async findByQuery(query: Parameters<WorkflowRunStore['findByQuery']>[0]) {
    return this.store.findByQuery(query);
  }

  async transition(id: string, next: WorkflowRunStatus) {
    const run = await this.get(id);
    assertTransition(run.status, next);
    const progress = next === 'SUCCEEDED' || next === 'FAILED' || next === 'CANCELLED' ? 100 : run.progress;
    const updated = await this.store.update(id, { status: next, progress });
    if (next === 'RUNNING') {
      await this.emit(id, 'NODE_STARTED', { status: next, progress });
    } else if (next === 'SUCCEEDED') {
      await this.emit(id, 'RUN_COMPLETED', { status: next, progress });
    }
    return updated;
  }

  async cancel(id: string) {
    const run = await this.get(id);
    if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(run.status)) throw new Error('Workflow run is terminal');
    const updated = await this.store.update(id, { status: 'CANCELLED', progress: 100, completedAt: this.now().toISOString() });
    await this.emit(id, 'RUN_CANCELED', { status: 'CANCELLED', progress: 100 });
    return updated;
  }

  async complete(id: string, output: Record<string, unknown>): Promise<WorkflowRunRecord> {
    const run = await this.get(id);
    assertTransition(run.status, 'SUCCEEDED');
    const updated = await this.store.update(id, { status: 'SUCCEEDED', progress: 100, outputData: output, completedAt: this.now().toISOString() });
    await this.emit(id, 'RUN_COMPLETED', { status: 'SUCCEEDED', progress: 100 });
    return updated;
  }

  async fail(id: string, error: string): Promise<WorkflowRunRecord> {
    const run = await this.get(id);
    assertTransition(run.status, 'FAILED');
    const updated = await this.store.update(id, { status: 'FAILED', progress: 100, errorData: { message: error }, completedAt: this.now().toISOString() });
    await this.emit(id, 'RUN_FAILED', { status: 'FAILED', progress: 100, error });
    return updated;
  }

  private async emit(runId: string, eventType: WorkflowEventType, payload: Record<string, unknown>) {
    const sequence = await this.store.nextSequence(runId);
    const event = {
      id: this.idGenerator(),
      runId,
      sequence,
      eventType,
      nodeName: null,
      payload,
      createdAt: this.now().toISOString(),
    };
    await this.store.appendEvent(event);
    this.eventBus?.publish(runId, event);
  }
}