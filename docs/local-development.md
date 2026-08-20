# 新平台本地开发

TestGen Agent 平台为 pnpm + Turborepo monorepo：`apps/api`（NestJS）、`apps/agent-worker`（LangGraph.js Worker）、`apps/web`（React + Vite），以及 8 个共享包（`contracts`/`database`/`workflow`/`auth`/`queue`/`storage`/`config`/`ui`）。

## 启动基础设施

```bash
docker compose -f docker/docker-compose.yml up -d
```

PostgreSQL 使用 `localhost:5433`，Redis 使用 `localhost:6380`，避免与现有项目服务冲突。

**没有 Docker/PG 时 API 也能跑**：不设置 `DATABASE_URL` 时，API 使用内存 store（WorkflowRun / Organization / Project），便于本地无数据库开发。

## 初始化环境

```bash
Copy-Item .env.example .env
pnpm install
```

不要把真实密钥提交到 Git。启用飞书 OAuth 前，需要配置 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 并将 `FEISHU_ENABLED` 设置为 `true`。

## 构建与类型检查

```bash
pnpm typecheck
pnpm build
```

先构建共享包（`@testgen/contracts`、`@testgen/workflow`、`@testgen/database`、`@testgen/auth`、`@testgen/queue`），再构建应用，避免 workspace 引用 dist 过期：

```bash
pnpm --filter @testgen/contracts --filter @testgen/workflow --filter @testgen/database --filter @testgen/auth --filter @testgen/queue build
```

## 运行 API

方法一（推荐，避免 tsx 装饰器元数据问题）——先编译再用 node 运行：

```bash
cd apps/api
npx tsc -p tsconfig.json && node dist/main.js
# 访问 http://localhost:3001
```

方法二（dev 热重载，`tsx watch`；注意 tsx 基于 esbuild 不生成 `design:paramtypes`，如遇 DI 注入 undefined 请改用方法一）：

```bash
cd apps/api && pnpm dev
```

启动时若配置了 `DATABASE_URL`，会自动执行数据库迁移（`runMigrations`）与种子初始化（`runSeed`，创建平台管理员 `admin@example.com` / `Admin#123456`，可用环境变量覆盖）。

## 运行 Agent Worker

```bash
cd apps/agent-worker
WORKER_PROCESS=true REDIS_URL=redis://localhost:6380 pnpm start
```

Worker 消费 `workflow-runs` 队列（BullMQ），使用 LangGraph.js 执行 4 节点工作流（prepare_input → analyze_content → review_analysis → build_result），每个节点有独立运行记录、重试与 Token 统计。默认使用 Mock LLM，可在 `apps/agent-worker/src/llm/adapter.ts` 接入真实 LLM Provider。

## 运行 Web 前端

```bash
cd apps/web && pnpm dev
# 访问 http://localhost:5173，登录页默认账号 admin@example.com / Admin#123456
```

## 测试

```bash
# 各包单测（含 API 的 workflow-runs / org-project / auth / authorization / SSE，及 Worker 的 node-runner / workflow-executor）
pnpm --filter @testgen/api test
pnpm --filter @testgen/agent-worker test
pnpm --filter @testgen/workflow test
pnpm --filter @testgen/contracts test
```

## 关键接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 本地登录（email + password） |
| POST | `/api/v1/auth/refresh` | Refresh Token 轮换 |
| GET | `/api/v1/health/live` | 存活检查 |
| POST | `/api/v1/workflow-runs` | 创建 Workflow Run（幂等键，投递队列） |
| GET | `/api/v1/workflow-runs/:id/stream` | SSE 实时事件流（Last-Event-ID 断线补偿） |
| POST | `/api/v1/workflow-runs/:id/complete` | Worker 回调：标记成功 |
| POST | `/api/v1/workflow-runs/:id/fail` | Worker 回调：标记失败 |
| GET/POST | `/api/v1/organizations` | 组织列表 / 创建 |
| GET/POST | `/api/v1/projects` | 项目列表 / 创建 |