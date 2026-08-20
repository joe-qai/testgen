import { WorkflowRunStatus } from '@testgen/contracts';

const transitions: Record<WorkflowRunStatus, readonly WorkflowRunStatus[]> = {
  CREATED: ['QUEUED', 'CANCELLED'],
  QUEUED: ['RUNNING', 'FAILED', 'CANCELLED'],
  RUNNING: ['WAITING_HUMAN', 'SUCCEEDED', 'FAILED', 'CANCELLED'],
  WAITING_HUMAN: ['RUNNING', 'CANCELLED'],
  SUCCEEDED: [], FAILED: [], CANCELLED: [],
};

export function assertTransition(from: WorkflowRunStatus, to: WorkflowRunStatus): void {
  if (!transitions[from].includes(to)) throw new Error(`Invalid workflow transition: ${from} -> ${to}`);
}

export type NodeExecutionContext = { runId: string; organizationId: string; projectId: string; nodeName: string; attempt: number };
export type NodeExecutionResult<T> = { output: T; events: Array<Record<string, unknown>>; usage?: Record<string, number> };

export * from './store.js';
