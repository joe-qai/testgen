import { z } from 'zod';

export const WorkflowRunStatusSchema = z.enum(['CREATED','QUEUED','RUNNING','WAITING_HUMAN','SUCCEEDED','FAILED','CANCELLED']);
export type WorkflowRunStatus = z.infer<typeof WorkflowRunStatusSchema>;
export const WorkflowEventTypeSchema = z.enum(['RUN_STARTED','NODE_STARTED','NODE_PROGRESS','AGENT_MESSAGE','NODE_COMPLETED','REVIEW_RESULT','RUN_COMPLETED','RUN_FAILED','RUN_CANCELED']);
export type WorkflowEventType = z.infer<typeof WorkflowEventTypeSchema>;
export const WorkflowEventSchema = z.object({ id:z.string().uuid(), runId:z.string().uuid(), sequence:z.number().int().nonnegative(), eventType:WorkflowEventTypeSchema, nodeName:z.string().nullable(), payload:z.record(z.unknown()), createdAt:z.string().datetime() });
export const DemoAgentInputSchema = z.object({ projectId:z.string().uuid(), title:z.string().min(1).max(200), content:z.string().min(1).max(50000) });
export const DemoAgentOutputSchema = z.object({ summary:z.string(), review:z.string(), recommendations:z.array(z.string()) });
export const ApiErrorSchema = z.object({ code:z.string(), message:z.string(), requestId:z.string().optional(), details:z.record(z.unknown()).optional() });
export const IdempotencyKeySchema = z.string().min(8).max(200);
export const PaginationSchema = z.object({ page:z.number().int().positive().default(1), limit:z.number().int().positive().max(100).default(20) });
export const ApiResponseSchema = <T extends z.ZodTypeAny>(schema:T) => z.object({ data:schema, meta:z.object({ requestId:z.string() }), error:z.null() });
export type WorkflowEvent = z.infer<typeof WorkflowEventSchema>;
export type DemoAgentInput = z.infer<typeof DemoAgentInputSchema>;
export type DemoAgentOutput = z.infer<typeof DemoAgentOutputSchema>;
