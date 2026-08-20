import { Body, Controller, Get, Param, Post, Req, Res } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';
import { InMemoryWorkflowRunService } from './workflow-runs.service.js';

type StreamRequest = { headers: Record<string, string | string[] | undefined> };
type StreamResponse = { setHeader(name: string, value: string): void; write(value: string): void; end(): void };

@Controller('api/v1/workflow-runs')
export class WorkflowRunsController {
  constructor(private readonly service: InMemoryWorkflowRunService) {}

  @Post()
  create(@Body() body: { organizationId: string; projectId: string; workflowCode?: string; idempotencyKey: string; input?: Record<string, unknown> }) {
    const run = this.service.create({ ...body, workflowCode: body.workflowCode ?? 'demo-agent', input: body.input ?? {}, requestedBy: 'bootstrap-user' });
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get(':id')
  detail(@Param('id') id: string) { return { data: this.service.get(id), meta: { requestId: createOpaqueToken(8) }, error: null }; }

  @Get(':id/events')
  events(@Param('id') id: string) { return { data: this.service.events(id), meta: { requestId: createOpaqueToken(8) }, error: null }; }

  @Post(':id/cancel')
  cancel(@Param('id') id: string) { return { data: this.service.cancel(id), meta: { requestId: createOpaqueToken(8) }, error: null }; }

  @Get(':id/stream')
  stream(@Param('id') id: string, @Req() request: StreamRequest, @Res() response: StreamResponse) {
    response.setHeader('Content-Type', 'text/event-stream');
    response.setHeader('Cache-Control', 'no-cache');
    response.setHeader('Connection', 'keep-alive');
    const after = Number(request.headers['last-event-id'] ?? 0);
    for (const event of this.service.events(id).filter((item) => item.sequence > after)) response.write(`id: ${event.sequence}\nevent: ${event.eventType}\ndata: ${JSON.stringify(event)}\n\n`);
    response.end();
  }
}
