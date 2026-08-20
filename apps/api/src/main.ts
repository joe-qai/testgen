import 'reflect-metadata';
import { Controller, Get, Injectable, Module } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AuthController } from './auth.controller.js';
import { OrganizationsController } from './organizations.controller.js';
import { ProjectsController } from './projects.controller.js';
import { WorkflowRunsController } from './workflow-runs.controller.js';
import { InMemoryWorkflowRunService } from './workflow-runs.service.js';

@Injectable()
export class AppService {
  health() { return { status: 'ok', service: 'testgen-api' }; }
}

@Controller('api/v1/health')
export class HealthController {
  constructor(private readonly appService: AppService) {}
  @Get('live') live() { return this.appService.health(); }
}

@Module({ controllers: [HealthController, AuthController, OrganizationsController, ProjectsController, WorkflowRunsController], providers: [AppService, InMemoryWorkflowRunService] })
export class AppModule {}

if (process.env.NODE_ENV !== 'test') {
  const app = await NestFactory.create(AppModule);
  app.enableCors();
  await app.listen(Number(process.env.PORT ?? 3001));
}
