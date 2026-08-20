import { Body, Controller, Get, Post } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';

@Controller('api/v1/organizations')
export class OrganizationsController {
  @Get() list() { return { data: [], meta: { requestId: createOpaqueToken(8) }, error: null }; }
  @Post('switch') switchOrganization(@Body() body: { organizationId?: string }) { return { data: { organizationId: body.organizationId ?? null }, meta: { requestId: createOpaqueToken(8) }, error: null }; }
}
