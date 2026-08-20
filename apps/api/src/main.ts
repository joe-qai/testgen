import 'reflect-metadata';
import { Controller, Get, Injectable, Module } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AuthController } from './auth.controller.js';
import { OrganizationsController } from './organizations.controller.js';
import { ProjectsController } from './projects.controller.js';
import { WorkflowRunsController } from './workflow-runs.controller.js';
import { WorkflowRunService } from './workflow-runs.service.js';
import { OrganizationsService } from './organizations.service.js';
import { ProjectsService } from './projects.service.js';
import { createMemoryWorkflowRunStore } from './workflow-runs.memory-store.js';
import { createMemoryOrganizationStore, createMemoryProjectStore } from './org-project.memory-store.js';
import { createDatabase, runMigrations, runSeed, PostgresWorkflowRunStore, PostgresOrganizationStore, PostgresProjectStore, type Database, type OrganizationStore, type ProjectStore } from '@testgen/database';
import type { WorkflowRunStore } from '@testgen/workflow';

let databaseInstance: { db: Database; pool: { end(): Promise<unknown> } } | null = null;

function getDatabase() {
  if (!databaseInstance) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) throw new Error('DATABASE_URL is required for PostgreSQL mode');
    databaseInstance = createDatabase(connectionString);
  }
  return databaseInstance;
}

function resolveRunStore(): WorkflowRunStore {
  if (process.env.DATABASE_URL) {
    return new PostgresWorkflowRunStore(getDatabase().db);
  }
  return createMemoryWorkflowRunStore();
}

function resolveOrganizationStore(): OrganizationStore {
  if (process.env.DATABASE_URL) {
    return new PostgresOrganizationStore(getDatabase().db);
  }
  return createMemoryOrganizationStore();
}

function resolveProjectStore(): ProjectStore {
  if (process.env.DATABASE_URL) {
    return new PostgresProjectStore(getDatabase().db);
  }
  return createMemoryProjectStore();
}

@Injectable()
export class AppService {
  health() { return { status: 'ok', service: 'testgen-api' }; }
}

@Controller('api/v1/health')
export class HealthController {
  constructor(private readonly appService: AppService) {}
  @Get('live') live() { return this.appService.health(); }
}

@Module({
  controllers: [HealthController, AuthController, OrganizationsController, ProjectsController, WorkflowRunsController],
  providers: [
    AppService,
    { provide: WorkflowRunService, useFactory: () => new WorkflowRunService(resolveRunStore()) },
    { provide: OrganizationsService, useFactory: () => new OrganizationsService(resolveOrganizationStore()) },
    { provide: ProjectsService, useFactory: () => new ProjectsService(resolveProjectStore()) },
  ],
})
export class AppModule {}

if (process.env.NODE_ENV !== 'test') {
  if (process.env.DATABASE_URL) {
    const { db, pool } = getDatabase();
    await runMigrations(db);
    await runSeed(db);
    await pool.end();
    databaseInstance = null;
  }
  const app = await NestFactory.create(AppModule);
  app.enableCors();
  await app.listen(Number(process.env.PORT ?? 3001));
}