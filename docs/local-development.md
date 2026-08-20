# 新平台本地开发

## 启动基础设施

```bash
docker compose -f docker/docker-compose.yml up -d
```

PostgreSQL 使用 `localhost:5433`，Redis 使用 `localhost:6380`，避免与现有项目服务冲突。

## 初始化环境

```bash
Copy-Item .env.example .env
pnpm install
```

不要把真实密钥提交到 Git。启用飞书 OAuth 前，需要配置 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 并将 `FEISHU_ENABLED` 设置为 `true`。

## 验证基础骨架

```bash
pnpm typecheck
pnpm build
```

当前阶段只验证 Monorepo 和基础设施配置，真实 NestJS API、数据库迁移和 Agent Worker 将在后续任务中实现。
