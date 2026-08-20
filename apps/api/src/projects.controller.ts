import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { createOpaqueToken } from '@testgen/auth';

@Controller('api/v1/projects')
export class ProjectsController {
  @Get() list() { return { data: [], meta: { requestId: createOpaqueToken(8) }, error: null }; }
  @Get(':id') detail(@Param('id') id: string) { return { data: { id, status: 'ACTIVE' }, meta: { requestId: createOpaqueToken(8) }, error: null }; }
  @Post() create(@Body() body: { key?: string; name?: string }) { return { data: { id: createOpaqueToken(16), key: body.key, name: body.name, status: 'ACTIVE' }, meta: { requestId: createOpaqueToken(8) }, error: null }; }
}
