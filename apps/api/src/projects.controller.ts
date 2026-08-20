import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';
import { ProjectsService } from './projects.service.js';

@Controller('api/v1/projects')
export class ProjectsController {
  constructor(private readonly service: ProjectsService) {}

  @Get()
  async list() {
    const projects = await this.service.list('demo-org');
    return { data: projects, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get(':id')
  async detail(@Param('id') id: string) {
    const project = await this.service.detail(id);
    if (!project) return { data: null, meta: { requestId: createOpaqueToken(8) }, error: { code: 'NOT_FOUND', message: 'Project not found' } };
    return { data: project, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get(':id/members')
  async members(@Param('id') id: string) {
    const members = await this.service.listMembers(id);
    return { data: members, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post()
  async create(@Body() body: { key?: string; name?: string }) {
    if (!body.name?.trim() || !body.key?.trim()) {
      return { data: null, meta: { requestId: createOpaqueToken(8) }, error: { code: 'VALIDATION_ERROR', message: 'key and name are required' } };
    }
    const project = await this.service.create({ organizationId: 'demo-org', key: body.key, name: body.name, ownerId: 'bootstrap-user', actorId: 'bootstrap-user' });
    return { data: project, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post(':id/members')
  async addMember(@Param('id') id: string, @Body() body: { userId: string }) {
    if (!body.userId) return { data: null, meta: { requestId: createOpaqueToken(8) }, error: { code: 'VALIDATION_ERROR', message: 'userId is required' } };
    const member = await this.service.addMember({ organizationId: 'demo-org', projectId: id, userId: body.userId, actorId: 'bootstrap-user' });
    return { data: member, meta: { requestId: createOpaqueToken(8) }, error: null };
  }
}