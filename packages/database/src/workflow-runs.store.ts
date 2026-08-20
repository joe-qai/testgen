import { eq, and, desc, count, sql } from 'drizzle-orm';
import * as schema from './schema.js';
import type { Database as TestgenDatabase } from './client.js';
import type { WorkflowRunStore, WorkflowRunRecord, WorkflowEventRecord, WorkflowRunQuery } from '@testgen/workflow';
import { WorkflowRunStatusSchema } from '@testgen/contracts';

type Db = TestgenDatabase;

function rowToRun(row: typeof schema.workflowRuns.$inferSelect): WorkflowRunRecord {
  return {
    id: row.id,
    organizationId: row.organizationId,
    projectId: row.projectId,
    workflowDefinitionId: row.workflowDefinitionId,
    workflowVersionId: row.workflowVersionId,
    workflowCode: row.workflowCode ?? 'demo-agent',
    requestedBy: row.requestedBy,
    status: WorkflowRunStatusSchema.parse(row.status),
    inputData: row.inputData as Record<string, unknown>,
    outputData: row.outputData as Record<string, unknown> | null,
    errorData: row.errorData as Record<string, unknown> | null,
    currentNode: row.currentNode,
    progress: row.progress,
    idempotencyKey: row.idempotencyKey,
    queuedAt: row.queuedAt ? row.queuedAt.toISOString() : null,
    startedAt: row.startedAt ? row.startedAt.toISOString() : null,
    completedAt: row.completedAt ? row.completedAt.toISOString() : null,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

function rowToEvent(row: typeof schema.workflowEvents.$inferSelect): WorkflowEventRecord {
  return {
    id: row.id,
    runId: row.workflowRunId,
    sequence: row.sequence,
    eventType: row.eventType as WorkflowEventRecord['eventType'],
    nodeName: row.nodeName,
    payload: row.payload as Record<string, unknown>,
    createdAt: row.createdAt.toISOString(),
  };
}

export class PostgresWorkflowRunStore implements WorkflowRunStore {
  constructor(private readonly db: Db) {}

  async create(run: WorkflowRunRecord): Promise<WorkflowRunRecord> {
    await this.db.insert(schema.workflowRuns).values({
      id: run.id,
      organizationId: run.organizationId,
      projectId: run.projectId,
      workflowDefinitionId: run.workflowDefinitionId,
      workflowVersionId: run.workflowVersionId,
      workflowCode: run.workflowCode,
      requestedBy: run.requestedBy,
      status: run.status,
      inputData: run.inputData,
      outputData: run.outputData,
      errorData: run.errorData,
      currentNode: run.currentNode,
      progress: run.progress,
      idempotencyKey: run.idempotencyKey,
      queuedAt: run.queuedAt ? new Date(run.queuedAt) : null,
      startedAt: run.startedAt ? new Date(run.startedAt) : null,
      completedAt: run.completedAt ? new Date(run.completedAt) : null,
    });
    return run;
  }

  async update(id: string, patch: Partial<Omit<WorkflowRunRecord, 'id' | 'createdAt'>>): Promise<WorkflowRunRecord> {
    const [row] = await this.db
      .update(schema.workflowRuns)
      .set({
        ...(patch.status ? { status: patch.status } : {}),
        ...(patch.outputData !== undefined ? { outputData: patch.outputData } : {}),
        ...(patch.errorData !== undefined ? { errorData: patch.errorData } : {}),
        ...(patch.currentNode !== undefined ? { currentNode: patch.currentNode } : {}),
        ...(patch.progress !== undefined ? { progress: patch.progress } : {}),
        ...(patch.queuedAt !== undefined ? { queuedAt: patch.queuedAt ? new Date(patch.queuedAt) : null } : {}),
        ...(patch.startedAt !== undefined ? { startedAt: patch.startedAt ? new Date(patch.startedAt) : null } : {}),
        ...(patch.completedAt !== undefined ? { completedAt: patch.completedAt ? new Date(patch.completedAt) : null } : {}),
      })
      .where(eq(schema.workflowRuns.id, id))
      .returning();
    if (!row) throw new Error(`Run not found: ${id}`);
    return rowToRun(row);
  }

  async findById(id: string): Promise<WorkflowRunRecord | null> {
    const [row] = await this.db.select().from(schema.workflowRuns).where(eq(schema.workflowRuns.id, id)).limit(1);
    return row ? rowToRun(row) : null;
  }

  async findByIdempotencyKey(organizationId: string, requestedBy: string, idempotencyKey: string): Promise<WorkflowRunRecord | null> {
    const [row] = await this.db
      .select()
      .from(schema.workflowRuns)
      .where(and(eq(schema.workflowRuns.organizationId, organizationId), eq(schema.workflowRuns.requestedBy, requestedBy), eq(schema.workflowRuns.idempotencyKey, idempotencyKey)))
      .limit(1);
    return row ? rowToRun(row) : null;
  }

  async findByQuery(query: WorkflowRunQuery): Promise<{ items: WorkflowRunRecord[]; total: number }> {
    const base = and(eq(schema.workflowRuns.organizationId, query.organizationId), query.projectId ? eq(schema.workflowRuns.projectId, query.projectId) : undefined);
    const [totalRow] = await this.db.select({ value: count() }).from(schema.workflowRuns).where(base);
    const rows = await this.db
      .select()
      .from(schema.workflowRuns)
      .where(base)
      .orderBy(desc(schema.workflowRuns.createdAt))
      .limit(query.limit)
      .offset((query.page - 1) * query.limit);
    return { items: rows.map(rowToRun), total: totalRow?.value ?? 0 };
  }

  async listEvents(runId: string): Promise<WorkflowEventRecord[]> {
    const rows = await this.db
      .select()
      .from(schema.workflowEvents)
      .where(eq(schema.workflowEvents.workflowRunId, runId))
      .orderBy(schema.workflowEvents.sequence);
    return rows.map(rowToEvent);
  }

  async appendEvent(event: WorkflowEventRecord): Promise<WorkflowEventRecord> {
    const run = await this.findById(event.runId);
    if (!run) throw new Error(`Run not found: ${event.runId}`);
    await this.db.insert(schema.workflowEvents).values({
      id: event.id,
      workflowRunId: event.runId,
      organizationId: run.organizationId,
      projectId: run.projectId,
      sequence: event.sequence,
      eventType: event.eventType,
      nodeName: event.nodeName,
      payload: event.payload,
      createdAt: new Date(event.createdAt),
    });
    return event;
  }

  async nextSequence(runId: string): Promise<number> {
    const [row] = await this.db
      .select({ value: sql<number>`coalesce(max(${schema.workflowEvents.sequence}), -1) + 1` })
      .from(schema.workflowEvents)
      .where(eq(schema.workflowEvents.workflowRunId, runId));
    return row?.value ?? 0;
  }
}