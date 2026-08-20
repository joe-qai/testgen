import type { WorkflowRunStatus, WorkflowEventType } from '@testgen/contracts';

export type WorkflowRunRecord = {
  id: string;
  organizationId: string;
  projectId: string;
  workflowDefinitionId: string | null;
  workflowVersionId: string | null;
  workflowCode: string;
  requestedBy: string;
  status: WorkflowRunStatus;
  inputData: Record<string, unknown>;
  outputData: Record<string, unknown> | null;
  errorData: Record<string, unknown> | null;
  currentNode: string | null;
  progress: number;
  idempotencyKey: string;
  queuedAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type WorkflowEventRecord = {
  id: string;
  runId: string;
  sequence: number;
  eventType: WorkflowEventType;
  nodeName: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type WorkflowRunQuery = {
  organizationId: string;
  projectId?: string;
  page: number;
  limit: number;
};

export interface WorkflowRunStore {
  create(run: WorkflowRunRecord): Promise<WorkflowRunRecord>;
  update(id: string, patch: Partial<Omit<WorkflowRunRecord, 'id' | 'createdAt'>>): Promise<WorkflowRunRecord>;
  findById(id: string): Promise<WorkflowRunRecord | null>;
  findByIdempotencyKey(organizationId: string, requestedBy: string, idempotencyKey: string): Promise<WorkflowRunRecord | null>;
  findByQuery(query: WorkflowRunQuery): Promise<{ items: WorkflowRunRecord[]; total: number }>;
  listEvents(runId: string): Promise<WorkflowEventRecord[]>;
  appendEvent(event: WorkflowEventRecord): Promise<WorkflowEventRecord>;
  nextSequence(runId: string): Promise<number>;
}