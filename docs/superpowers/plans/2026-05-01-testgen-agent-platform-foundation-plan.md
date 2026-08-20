# TestGen Agent Platform Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable foundation of a multi-tenant TestGen Agent platform with React 19, NestJS 10, PostgreSQL RLS, BullMQ, and a LangGraph.js demo workflow.

**Architecture:** Create a pnpm/Turborepo monorepo with independent `web`, `api`, and `agent-worker` applications plus shared contracts, database, auth, workflow, queue, storage, config, and UI packages. NestJS owns authentication, tenant/project authorization, persistence, and workflow APIs; the worker executes serialized LangGraph.js jobs and persists node/event state; React consumes only versioned APIs and SSE/REST events.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui, React Router DOM v6, TanStack Query, Zustand, NestJS 10, Node.js 22+, Drizzle ORM, PostgreSQL, PostgreSQL RLS, BullMQ, Redis, LangGraph.js, LangChain.js, Zod, Vitest, Playwright, pnpm, Turborepo.

## Global Constraints

- Do not add AutoGen, Python, Flask, Jinja2, or Python runtime dependencies to the new platform.
- Use multi-organization tenancy; users may belong to multiple organizations with organization-specific roles.
- Support local account/password authentication and one shared Feishu OAuth application serving multiple Feishu tenants.
- Use platform, organization, and project LLM configuration scopes in the future-facing model; do not expose secrets to the browser.
- Use PostgreSQL RLS in the first phase, with transaction-local `app.user_id`, `app.organization_id`, `app.project_id`, and `app.is_platform_admin` context.
- Use UUID identifiers, UTC `timestamptz`, string statuses, organization/project composite indexes, and append-only audit logs.
- Use `packages/contracts` as the shared source of truth for Zod schemas, DTOs, statuses, errors, pagination, and workflow events.
- Use adapters for queue, storage, and events so local BullMQ/local storage can later be replaced by妙搭 platform services and Dataloom.
- Every long-running task uses the shared Workflow Run state machine and idempotency key.

## Phase 1 Tasks

### Task 1: Create the pnpm/Turborepo workspace

Create the root workspace, `apps/web`, `apps/api`, `apps/agent-worker`, and shared packages for contracts, database, auth, workflow, queue, storage, config, and UI. Add pnpm workspace globs, Turborepo build/typecheck/test dependencies, TypeScript base configuration, lint/format/test tooling, and minimal compilable entry points. Verify `pnpm install`, `pnpm typecheck`, and `pnpm build`.

### Task 2: Add shared configuration and contracts

Create Zod schemas and tests for auth, organizations, projects, Workflow Runs, events, errors, pagination, and demo Agent input/output. Define the shared workflow statuses, event types, response envelope, idempotency key, and `loadConfig(env)`.

### Task 3: Provision local infrastructure

Create Docker Compose PostgreSQL with persistent volume and health check, Redis with health check, `.env.example`, and local development documentation. Add `tools/check-infrastructure.ts`. Docker startup could not be executed in this environment because the `docker` command is unavailable; the configuration is ready for a Docker-enabled environment.

### Task 4: Implement Drizzle schema, seed, and PostgreSQL RLS

Create 21 Drizzle tables covering identity, tenancy, RBAC, projects, workflow definitions/versions/runs/node runs/events/interrupts, and audit logs. Add UUIDs, UTC timestamps, statuses, indexes, constraints, idempotency uniqueness, `setRlsContext`, `withTenantTransaction`, RLS helper functions, RLS policy SQL, and an idempotent bootstrap seed. Drizzle successfully generated `packages/database/migrations/0000_breezy_silk_fever.sql`; live migration/RLS integration requires PostgreSQL.

### Task 5: Implement authentication and organization context

Create token/hash helpers, NestJS health and auth API skeletons, local login response contract, organization listing/switching endpoints, and the foundation for Feishu OAuth. Full database-backed authentication, guards, token rotation, and OAuth callback exchange remain the next implementation increment.

### Task 6: Implement project and member APIs

Create project list/detail/create API skeletons and the database model needed for tenant-safe project/member management. Full persistence-backed CRUD, member roles, guards, and audit mutation handlers remain the next implementation increment.

### Task 7: Implement workflow contracts, queue adapters, and Run API

Create Workflow Run transition rules, node execution contracts, local BullMQ adapter, and platform queue adapter boundary. Full NestJS Workflow Run persistence API remains the next implementation increment.

### Task 8: Implement LangGraph.js Demo Worker

Create LangGraph.js demo workflow `prepare_input → analyze_content → review_analysis → build_result`, shared Zod validation, deterministic Mock LLM behavior, and worker package dependencies. Full BullMQ processor persistence and node/event writes remain the next implementation increment.

### Task 9: Add durable events and SSE

Design and reserve the event history/SSE boundary. Full event bus, Last-Event-ID replay, terminal stream close, and REST fallback remain the next implementation increment.

### Task 10: Build React authentication and application shell

Create React 19/Vite entry, application shell, responsive navigation, workbench cards, project and Agent task menu entries, and construction placeholders for future modules. Production auth routing and TanStack Query integration remain the next implementation increment.

### Task 11: Build project and member pages

Reserved for the next increment after API persistence and permissions are complete.

### Task 12: Build Workflow Run monitoring UI

Reserved for the next increment after Workflow Run API and SSE are complete.

### Task 13: Add end-to-end acceptance and quality gates

The new platform has passed TypeScript checks and production builds. PostgreSQL/Redis integration, RLS tests, worker integration, Playwright E2E, and CI remain pending until Docker/PostgreSQL/Redis are available and the remaining API/worker persistence increments are implemented.

## Verification Completed

```text
pnpm install --ignore-scripts  PASS
pnpm typecheck               PASS
pnpm build                   PASS
pnpm --filter @testgen/database db:generate  PASS
pnpm --filter @testgen/web build             PASS
```

## Current Limitations

- Existing Flask/Python implementation remains untouched as the legacy application.
- New NestJS API currently contains a health endpoint plus intentionally thin authentication, organization, and project API skeletons; these are not production authentication or authorization yet.
- Database Schema and RLS SQL are implemented, but live migrations and isolation tests need PostgreSQL.
- LangGraph.js demo graph is implemented and typechecked, but queue-connected worker persistence and event streaming are not complete.
- React shell is implemented and built, but full React Router, auth state, project screens, workflow monitoring, and SSE UI are pending.
- Docker is not installed in the current environment, so PostgreSQL/Redis runtime checks were not possible.
