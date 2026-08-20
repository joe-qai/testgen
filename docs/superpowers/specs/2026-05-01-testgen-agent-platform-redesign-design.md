# TestGen Agent 平台重构设计

## 目标

将现有 Flask/Jinja2/Python 多模式测试用例生成系统重构为可导入飞书 Aily 妙搭技术栈的完整多组织项目管理型 Agent 平台。新平台不保留 AutoGen，不依赖 Python，使用 LangGraph.js 和 TypeScript Agent 实现工作流与多角色协作。

## 最终技术栈

- 前端：React 19、TypeScript、Vite、Tailwind CSS 4、shadcn/ui、React Router DOM v6、TanStack Query、Zustand、ReactECharts、Framer Motion
- 平台后端：NestJS 10、Node.js 22+、Drizzle ORM、PostgreSQL
- Agent：LangGraph.js、LangChain.js、Zod、自研 TypeScript Agent Team
- 异步任务：BullMQ + Redis，保留平台任务适配器
- 存储：本地存储适配器与 Dataloom 适配器
- 权限：RBAC + PostgreSQL RLS
- 仓库：pnpm workspace + Turborepo monorepo

## 总体架构

```text
React Web
    │ REST / SSE / WebSocket
    ▼
NestJS Platform API
    ├── 认证、组织、权限、项目
    ├── Workflow Run、事件、审计
    ├── 队列和存储适配器
    └── PostgreSQL
             ▲
             │
LangGraph.js Worker
    ├── 节点执行
    ├── Agent Team
    ├── 运行事件
    └── 任务结果
```

NestJS 负责平台业务与 API，LangGraph.js Worker 负责长时间 Agent 工作流。前端不直接访问数据库、LLM 或 Agent 内部对象。

## 产品信息架构

```text
工作台
项目管理
Agent 中心
  ├── Agent 工作流
  ├── 运行记录
  └── LLM 对话
测试资产
  ├── 需求管理
  └── 用例管理
知识中心
  ├── SKILL 管理
  └── RAG 知识库
平台管理
  ├── LLM 与 Prompt 配置
  ├── 用户管理
  ├── 角色与权限
  └── 审计与统计
```

第一阶段启用工作台、项目管理、Agent 任务、个人设置，其余模块保留建设中入口。

## 多租户与认证

采用多组织、多租户模型。用户可以属于多个组织，并在每个组织中拥有不同角色。支持本地账号密码与飞书 OAuth 双认证，一个平台飞书应用服务多个飞书租户。

本地账号由平台管理员创建，通过一次性激活链接设置密码。首个平台管理员由环境变量幂等初始化，不传递明文初始密码。

认证包含短时 Access Token、Refresh Token 轮换、服务端 Refresh Token 哈希、OAuth state 防 CSRF 和完整审计。

组织映射使用 `tenant_key`、`open_id`、`union_id`。首次飞书租户登录按平台策略匹配或创建组织，并进入待审核或初始化流程，不默认授予无限权限。

## 权限与 RLS

权限分为平台级、组织级、项目级和资源级。系统角色包括：

- `platform_admin`
- `organization_admin`
- `organization_member`
- `organization_viewer`
- `project_admin`
- `project_manager`
- `tester`
- `reviewer`
- `project_viewer`

权限编码使用 `resource:action`。核心资源包含 `organization_id`，项目资源同时包含 `project_id`。请求在事务中设置 `app.user_id`、`app.organization_id`、`app.project_id` 和平台管理员标识，使用事务级上下文避免连接池泄漏。

应用层通过 NestJS Guard 做友好权限校验，数据库 RLS 做最终隔离。组织 A 用户不能读取组织 B 资源，项目成员不能读取无权项目，切换组织后旧上下文不能继续访问新组织资源。

## Monorepo 边界

```text
apps/web          React 前端
apps/api          NestJS API
apps/agent-worker LangGraph.js Worker
packages/contracts  Zod Schema、DTO、事件协议
packages/database   Drizzle Schema、迁移、Repository
packages/auth       认证与权限共享逻辑
packages/workflow   工作流运行模型与协议
packages/queue      BullMQ 与平台队列适配器
packages/storage    本地与 Dataloom 存储适配器
packages/config     配置读取与校验
packages/ui         通用 UI 组件
```

共享协议包是前端、API 和 Worker 的唯一契约来源，避免状态、字段和事件协议漂移。

## 核心数据模型

第一阶段数据库包含：

- 身份：`users`、`user_identities`、`refresh_tokens`
- 组织：`organizations`、`organization_members`、`feishu_tenants`
- 权限：`roles`、`permissions`、`role_permissions`、平台/组织/项目角色关系
- 项目：`projects`、`project_members`、项目角色关系
- 工作流：`workflow_definitions`、`workflow_versions`、`workflow_runs`、`workflow_node_runs`、`workflow_events`、`workflow_interrupts`
- 治理：`audit_logs`

使用 UUID 主键、UTC `timestamptz`、字符串状态枚举、软删除或归档和租户组合索引。所有长任务使用统一 `Workflow Run` 模型。

## Workflow Run 协议

状态统一为：

```text
CREATED → QUEUED → RUNNING → SUCCEEDED
                         ├── FAILED
                         └── CANCELLED
```

预留 `WAITING_HUMAN`。

接口统一为：

```text
POST /api/v1/workflow-runs
GET  /api/v1/workflow-runs/:id
GET  /api/v1/workflow-runs/:id/events
GET  /api/v1/workflow-runs/:id/stream
POST /api/v1/workflow-runs/:id/resume
POST /api/v1/workflow-runs/:id/cancel
POST /api/v1/workflow-runs/:id/retry
```

事件类型包括 `RUN_STARTED`、`NODE_STARTED`、`NODE_PROGRESS`、`AGENT_MESSAGE`、`NODE_COMPLETED`、`REVIEW_RESULT`、`RUN_COMPLETED` 和 `RUN_FAILED`。事件按运行维度使用递增序列，支持 SSE 断线补偿、REST 轮询和运行回放。

## 第一阶段演示 Agent

第一阶段交付基础平台闭环和一个真实异步演示 Agent 任务，不实现真实测试需求分析、测试用例生成和 RAG。

流程：

```text
START → prepare_input → analyze_content → review_analysis → build_result → END
```

任务创建后经 NestJS 权限校验、Workflow Run 持久化和队列提交，由 Worker 原子抢占并执行 LangGraph.js。每个节点有独立运行记录、事件、错误和重试信息。可使用 Mock LLM 验证链路，也预留真实 LLM Adapter。

演示任务输出摘要、评审结果和建议列表。前端运行详情页展示运行概览、节点时间线、实时事件、结果、错误、Token 使用量和可执行操作。

取消采用协作式取消：API 标记取消请求，Worker 在节点边界检查。重复提交使用幂等键返回原有运行 ID。

## 基础设施双模式

本地/自建模式使用 PostgreSQL、Redis + BullMQ、本地文件存储、NestJS、Worker 和 React。妙搭模式使用 PostgreSQL、平台任务能力、Dataloom 和相同的应用协议。业务代码只依赖 `DatabaseAdapter`、`QueueAdapter`、`FileStorageAdapter`、`EventBusAdapter` 等抽象，通过环境变量切换实现。

## 前端设计

采用后台布局：顶部组织切换、全局搜索、通知和用户菜单；左侧按产品域分组；内容区包含面包屑、标题、操作区和内容卡片。

第一阶段路由：

```text
/login
/auth/feishu/callback
/organizations/select
/dashboard
/projects
/projects/new
/projects/:projectId
/projects/:projectId/members
/workflow-runs
/workflow-runs/:runId
/settings/profile
```

TanStack Query 管理服务端数据，Zustand 只管理当前组织、Token、界面偏好等客户端状态。权限使用统一权限编码和 `usePermissions()`，不在页面散落角色判断。任务详情优先 SSE，断开后使用 `Last-Event-ID` 补事件，再降级 REST 轮询。

## 测试与质量门禁

使用 Vitest 做单元和集成测试，Playwright 做端到端测试。必须覆盖认证、Token 轮换、组织切换、项目权限、RLS 隔离、Workflow 状态、队列、Worker、事件顺序、SSE 恢复、幂等提交和审计日志。

质量命令：

```text
pnpm lint
pnpm typecheck
pnpm test
pnpm test:integration
pnpm build
pnpm test:e2e
pnpm audit
pnpm db:check
```

跨组织访问失败、RLS 测试失败、协议类型错误、无迁移的表变更、无权限测试的新增权限均禁止合并。

## 阶段性交付

1. M0：pnpm monorepo、三应用、共享包、PostgreSQL、Redis、基础 CI。
2. M1：本地登录、飞书 OAuth 骨架、组织、成员、RBAC、RLS、项目、审计。
3. M2：Workflow Run、Queue、状态转换、取消、幂等、运行事件。
4. M3：LangGraph.js 演示 Worker、节点记录、SSE、React 运行详情和自动化测试。
5. 后续：需求与用例资产、真实测试用例生成、RAG、LLM 对话、Skill、模型配置、用户管理完善、妙搭自动化集成。

## 旧项目处理

旧 Flask/Python 项目不作为新系统运行时依赖，仅作为领域字段、业务规则、LLM Provider、RAG、导出和历史数据迁移参考。新系统直接使用 PostgreSQL。旧数据迁移工具独立管理，支持批次号、源记录 ID、失败重试和导入校验。

## 第一阶段最终验收

平台首次启动自动初始化管理员；管理员可本地登录、创建组织和项目、管理成员和角色；成员可切换组织并按权限访问项目；用户可创建演示 Workflow Run；Worker 通过 LangGraph.js 异步执行并持久化节点与事件；React 可显示实时进度和结构化结果；刷新后事件不丢失；重复提交不创建重复任务；跨组织和跨项目越权被阻断；关键操作写入审计日志。
