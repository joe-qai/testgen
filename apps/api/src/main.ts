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
import { AuthService } from './auth.service.js';
import { FeishuOAuthService } from './feishu-oauth.service.js';
import { createMemoryWorkflowRunStore } from './workflow-runs.memory-store.js';
import { createMemoryOrganizationStore, createMemoryProjectStore } from './org-project.memory-store.js';
import { createDatabase, runMigrations, runSeed, PostgresWorkflowRunStore, PostgresOrganizationStore, PostgresProjectStore, type Database, type OrganizationStore, type ProjectStore } from '@testgen/database';
import type { WorkflowRunStore } from '@testgen/workflow';
import type { QueueAdapter } from '@testgen/queue';
import { BullMQQueueAdapter } from '@testgen/queue';
import { SseEventBus } from './sse-event-bus.js';

const eventBus = new SseEventBus();

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

function resolveQueue(): QueueAdapter | undefined {
  const redisUrl = process.env.REDIS_URL;
  if (redisUrl) {
    return new BullMQQueueAdapter(redisUrl);
  }
  return undefined;
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
    { provide: SseEventBus, useValue: eventBus },
    { provide: WorkflowRunService, useFactory: () => new WorkflowRunService(resolveRunStore(), undefined, undefined, resolveQueue(), eventBus) },
    { provide: OrganizationsService, useFactory: () => new OrganizationsService(resolveOrganizationStore()) },
    { provide: ProjectsService, useFactory: () => new ProjectsService(resolveProjectStore()) },
    {
      provide: AuthService,
      useFactory: async () => {
        const service = new AuthService(process.env.JWT_ACCESS_SECRET ?? 'development-access-secret-please-change-32', process.env.JWT_REFRESH_SECRET ?? 'development-refresh-secret-please-change-32');
        await service.createUser({ email: process.env.BOOTSTRAP_ADMIN_EMAIL ?? 'admin@example.com', password: process.env.BOOTSTRAP_ADMIN_PASSWORD ?? 'Admin#123456', displayName: process.env.BOOTSTRAP_ADMIN_NAME ?? '平台管理员' }).catch(() => undefined);
        return service;
      },
    },
    {
      provide: FeishuOAuthService,
      useFactory: () => {
        const appId = process.env.FEISHU_APP_ID;
        const appSecret = process.env.FEISHU_APP_SECRET;
        if (!appId || !appSecret) return undefined;
        const redirectUri = process.env.FEISHU_REDIRECT_URI ?? 'http://localhost:5173/api/v1/auth/feishu/callback';
        return new FeishuOAuthService({ appId, appSecret, redirectUri });
      },
    },
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