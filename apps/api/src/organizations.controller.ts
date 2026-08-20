import { Body, Controller, Get, Post } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';
import { OrganizationsService } from './organizations.service.js';

@Controller('api/v1/organizations')
export class OrganizationsController {
  constructor(private readonly service: OrganizationsService) {}

  @Get()
  async list() {
    const organizations = await this.service.listForUser('bootstrap-user');
    return { data: organizations, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post()
  async create(@Body() body: { name: string }) {
    if (!body.name?.trim()) {
      return { data: null, meta: { requestId: createOpaqueToken(8) }, error: { code: 'VALIDATION_ERROR', message: 'name is required' } };
    }
    const organization = await this.service.create({ name: body.name, createdBy: 'bootstrap-user' });
    return { data: organization, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Post('switch')
  switchOrganization(@Body() body: { organizationId?: string }) {
    return { data: { organizationId: body.organizationId ?? null }, meta: { requestId: createOpaqueToken(8) }, error: null };
  }
}