import { Body, Controller, Get, Param, Post, Query, Req, Res } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';
import { WorkflowRunService } from './workflow-runs.service.js';
import { SseEventBus } from './sse-event-bus.js';

type StreamRequest = { headers: Record<string, string | string[] | undefined> };
type StreamResponse = {
  setHeader(name: string, value: string): void;
  write(value: string): void;
  end(): void;
  once?(event: string, listener: () => void): void;
};

@Controller('api/v1/workflow-runs')
export class WorkflowRunsController {
  constructor(private readonly service: WorkflowRunService, private readonly eventBus: SseEventBus) {}

  @Post()
  async create(@Body() body: { organizationId: string; projectId: string; workflowCode?: string; idempotencyKey: string; input?: Record<string, unknown> }) {
    const run = await this.service.create({ ...body, workflowCode: body.workflowCode ?? 'demo-agent', input: body.input ?? {}, requestedBy: 'bootstrap-user' });
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get()
  async list(@Query() query: { organizationId?: string; projectId?: string; page?: string; limit?: string }) {
    const organizationId = query.organizationId ?? 'demo-org';
    const page = Math.max(1, Number(query.page ?? 1));
    const limit = Math.min(100, Math.max(1, Number(query.limit ?? 20)));
    const result = await this.service.findByQuery({ organizationId, projectId: query.projectId, page, limit });
    return { data: result.items, meta: { requestId: createOpaqueToken(8), page, limit, total: result.total }, error: null };
  }

  @Get(':id')
  async detail(@Param('id') id: string) {
    const run = await this.service.get(id);
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get(':id/events')
  async events(@Param('id') id: string) {
    const events = await this.service.events(id);
    return { data: events, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post(':id/cancel')
  async cancel(@Param('id') id: string) {
    const run = await this.service.cancel(id);
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post(':id/complete')
  async complete(@Param('id') id: string, @Body() body: { output?: Record<string, unknown> }) {
    const run = await this.service.complete(id, body.output ?? {});
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post(':id/fail')
  async fail(@Param('id') id: string, @Body() body: { error?: string }) {
    const run = await this.service.fail(id, body.error ?? 'Workflow failed');
    return { data: run, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get(':id/stream')
  async stream(@Param('id') id: string, @Req() request: StreamRequest, @Res() response: StreamResponse) {
    response.setHeader('Content-Type', 'text/event-stream');
    response.setHeader('Cache-Control', 'no-cache');
    response.setHeader('Connection', 'keep-alive');
    const after = Number(request.headers['last-event-id'] ?? -1);
    const events = await this.service.events(id);
    for (const event of events.filter((item) => item.sequence > after)) {
      response.write(`id: ${event.sequence}\nevent: ${event.eventType}\ndata: ${JSON.stringify(event)}\n\n`);
    }
    const unsubscribe = this.eventBus.subscribe(id, (chunk) => response.write(chunk));
    response.once?.('close', () => unsubscribe());
    response.write(`: connected - listening for live events on run ${id}\n\n`);
  }
}