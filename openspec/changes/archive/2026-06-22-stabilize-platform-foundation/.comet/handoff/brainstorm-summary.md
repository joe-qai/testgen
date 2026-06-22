# Brainstorm Summary

- Change: stabilize-platform-foundation
- Date: 2026-06-22

## 确认的技术方案

**方案 A：渐进式增强**

- **错误处理**：`@app.errorhandler(Exception)` 全局处理器 + `@app.after_request` 响应钩子
  - 全局处理器捕获未处理异常，记录日志，返回标准 500 响应
  - 响应钩子为所有 `/api` 路径补充 `request_id`，统一 4xx/5xx 格式
- **索引迁移**：在 `create_app()` 中调用幂等迁移函数，使用 `CREATE INDEX IF NOT EXISTS`
- **健康检查**：新增 `/health/live`、`/health/ready`、`/metrics` 三个公开端点
- **指标收集**：线程安全的 `MetricsCollector` 类，通过请求钩子自动收集

**关键决策：**
- 错误响应：立即统一为新格式，不保持向后兼容
- 索引迁移：启动时自动执行幂等迁移
- 健康检查：完全公开，无需认证
- 指标数据：接受重启后清零
- 实现方式：`@app.errorhandler` + `@app.after_request` 组合

## 关键取舍与风险

**主要取舍：**
1. 错误处理范围：全局钩子覆盖所有 `/api` 路径（少量性能开销 vs 全面覆盖）
2. 索引粒度：只覆盖已确认的高频查询字段（可能遗漏优化机会 vs 最小化成本）
3. 指标持久化：进程内指标，重启清零（无法跨重启聚合 vs 零外部依赖）

**主要风险及缓解：**
1. 响应归一化影响现有调用方 → 保持 `error` 字段类型，明确 5xx 文本不稳定，增加契约测试
2. 索引迁移失败影响可用性 → 使用事务和幂等语句，失败不影响业务表，记录明确日志
3. 健康检查增加数据库压力 → 就绪检查只执行 `SELECT 1`，不访问业务表
4. 进程内指标不适合多进程聚合 → 在接口元数据中标明进程级语义
5. 响应钩子遇到非 JSON 错误响应 → 仅处理 `/api` 且状态码 >= 400 的响应

## 测试策略

**测试文件：**
- `tests/test_error_contract.py`：错误契约测试
- `tests/test_index_migration.py`：索引迁移测试
- `tests/test_health_endpoints.py`：健康检查测试
- `tests/test_metrics_collector.py`：指标收集测试

**测试覆盖：**
- 错误契约：正常响应、4xx/5xx 格式、异常保护、请求 ID 一致性、非 JSON 处理、数据库回滚
- 索引迁移：新数据库、旧数据库升级、幂等性、迁移失败不影响启动
- 健康检查：存活/就绪/指标端点、数据库连通性、JSON 结构
- 指标收集：线程安全、耗时统计、状态码分类、重启清零

**测试方法：** TDD（先写失败测试，再实现最小改动）

## Spec Patch

无需回写 delta spec。当前 OpenSpec 产物已经充分覆盖验收场景、边界条件、关键约束和技术决策。