---
comet_change: stabilize-platform-foundation
role: technical-design
canonical_spec: openspec
---

# Design Doc: Platform Stability Foundation

## Overview

本设计为 TestGen 平台建立稳定性基线，包括统一 API 错误契约、数据库查询索引优化和基础可观测能力。三项能力在同一个 change 中统一设计和回归验证，共同构成平台稳定性基础。

## Architecture

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Flask Application                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Request Lifecycle Hooks                  │  │
│  │  • before_request: 分配 request_id                 │  │
│  │  • after_request: 统一错误格式 + 收集指标          │  │
│  │  • teardown_request: 清理请求上下文                │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │         Global Error Handler                       │  │
│  │  • 捕获未处理异常                                   │  │
│  │  • 记录堆栈日志                                     │  │
│  │  • 返回标准 500 响应                                │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │           API Blueprint (/api/*)                   │  │
│  │  • 现有业务路由（保持不变）                         │  │
│  │  • 新增健康检查端点                                 │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │         Metrics Collector                          │  │
│  │  • 线程安全计数器                                   │  │
│  │  • 请求/错误/耗时统计                               │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Database (SQLite)                          │
│  • 现有表结构                                           │
│  • 新增索引（幂等迁移）                                 │
└─────────────────────────────────────────────────────────┘
```

### 核心组件

1. **错误契约层**
   - `ErrorResponse` 类：标准错误响应结构
   - 全局异常处理器：`@app.errorhandler(Exception)`
   - 响应归一化钩子：`@app.after_request`

2. **索引迁移层**
   - `IndexMigration` 类：幂等索引创建
   - 白名单配置：目标索引定义
   - 启动时自动执行

3. **健康检查层**
   - `/health/live`：存活检查（轻量）
   - `/health/ready`：就绪检查（数据库连通性）
   - `/metrics`：JSON 格式指标

4. **指标收集层**
   - `MetricsCollector` 类：线程安全计数器
   - 请求生命周期集成：自动收集

## Data Flow

### 错误处理流程

```
Client Request
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  @app.before_request                                      │
│  • 生成/透传 request_id (UUID v4)                        │
│  • 存储到 g.request_id                                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
Route Handler (业务逻辑)
    │
    ├── 正常响应 ──► 返回业务数据
    │
    └── 异常 ──► 抛出 Exception
                    │
                    ▼
        ┌─────────────────────────────────────────────────────────┐
        │  @app.errorhandler(Exception)                            │
        │  • 捕获未处理异常                                        │
        │  • 记录完整堆栈到日志 (logger.error)                    │
        │  • db_session.rollback()                                │
        │  • 返回标准 500 响应:                                    │
        │    {"error": "服务器内部错误", "code": "INTERNAL_ERROR", │
        │     "request_id": "<uuid>"}                             │
        └─────────────────────────────────────────────────────────┘
                    │
                    ▼
        ┌─────────────────────────────────────────────────────────┐
        │  @app.after_request                                     │
        │  • 仅处理 /api 路径                                      │
        │  • 检查响应是否为 JSON 且状态码 >= 400                   │
        │  • 补充 request_id (如果缺失)                           │
        │  • 对于 5xx，确保 error 字段不包含异常文本               │
        │  • 收集指标 (状态码、耗时)                               │
        └─────────────────────────────────────────────────────────┘
                    │
                    ▼
Client Response
```

### 索引迁移流程

```
Application Startup (create_app)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  init_database(db_path)                                  │
│  • 创建所有表 (Base.metadata.create_all)                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  IndexMigration.migrate(engine)                          │
│  • 遍历白名单索引定义                                     │
│  • 执行 CREATE INDEX IF NOT EXISTS                       │
│  • 记录成功/失败日志                                     │
│  • 失败不影响应用启动                                     │
└─────────────────────────────────────────────────────────┘
    │
    ▼
Application Ready
```

### 健康检查流程

```
┌─────────────────────────────────────────────────────────┐
│  GET /health/live                                        │
│  • 返回 200 + {"status": "ok"}                          │
│  • 不访问数据库                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  GET /health/ready                                       │
│  • 执行 SELECT 1                                         │
│  • 成功: 200 + {"status": "ok", "database": "connected"} │
│  • 失败: 503 + {"status": "not_ready",                   │
│              "database": "disconnected"}                │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  GET /metrics                                            │
│  • 返回 JSON 指标:                                       │
│    {"total_requests": N, "error_count": E,              │
│     "status_codes": {200: X, 400: Y, 500: Z},           │
│     "total_latency_ms": T, "uptime_seconds": U}         │
└─────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. API 错误契约

#### 错误响应格式

```python
{
    "error": "错误描述",
    "code": "ERROR_CODE",
    "request_id": "uuid-v4",
    "details": {}  # 可选
}
```

#### 核心组件

**ErrorResponse 类**

```python
class ErrorResponse:
    @staticmethod
    def create(message, code, request_id, details=None):
        response = {
            "error": message,
            "code": code,
            "request_id": request_id
        }
        if details:
            response["details"] = details
        return response
```

**全局异常处理器**

```python
@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    request_id = getattr(g, 'request_id', str(uuid.uuid4()))
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)

    if db_session:
        db_session.rollback()

    error_response = ErrorResponse.create(
        message="服务器内部错误",
        code="INTERNAL_ERROR",
        request_id=request_id
    )
    return jsonify(error_response), 500
```

**响应归一化钩子**

```python
@app.after_request
def normalize_error_response(response):
    if not request.path.startswith('/api'):
        return response

    if response.status_code < 400:
        return response

    try:
        data = response.get_json()
        if not data:
            return response

        request_id = getattr(g, 'request_id', str(uuid.uuid4()))

        if 'request_id' not in data:
            data['request_id'] = request_id

        if response.status_code >= 500 and 'error' in data:
            data['error'] = "服务器内部错误"

        if 'code' not in data:
            data['code'] = f"HTTP_{response.status_code}"

        response.data = json.dumps(data)
        response.content_type = 'application/json'
    except Exception:
        pass

    return response
```

**请求 ID 分配**

```python
@app.before_request
def assign_request_id():
    if 'X-Request-ID' in request.headers:
        g.request_id = request.headers['X-Request-ID']
    else:
        g.request_id = str(uuid.uuid4())
    g.start_time = time.time()
```

### 2. 数据库查询索引

#### 索引白名单

```python
INDEX_WHITELIST = [
    {
        "table": "requirements",
        "columns": ["created_at", "status"],
        "name": "idx_requirements_created_status"
    },
    {
        "table": "test_cases",
        "columns": ["requirement_id", "status"],
        "name": "idx_cases_requirement_status"
    },
    {
        "table": "generation_tasks",
        "columns": ["requirement_id", "status", "created_at"],
        "name": "idx_tasks_requirement_status_created"
    }
]
```

#### IndexMigration 类

```python
class IndexMigration:
    def __init__(self, engine, index_whitelist):
        self.engine = engine
        self.index_whitelist = index_whitelist

    def migrate(self):
        with self.engine.connect() as conn:
            for index_def in self.index_whitelist:
                try:
                    self._create_index_if_not_exists(conn, index_def)
                    logger.info(f"Index {index_def['name']} created or already exists")
                except Exception as e:
                    logger.error(f"Failed to create index {index_def['name']}: {str(e)}")

    def _create_index_if_not_exists(self, conn, index_def):
        table = index_def['table']
        columns = index_def['columns']
        name = index_def['name']

        columns_str = ', '.join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns_str})"
        conn.execute(sql)
```

#### 集成到应用启动

```python
def create_app():
    app = Flask(__name__)

    engine = init_database(db_path)
    IndexMigration(engine, INDEX_WHITELIST).migrate()

    return app
```

### 3. 健康检查端点

#### 存活检查

```python
@app.route('/health/live')
def health_live():
    return jsonify({"status": "ok"}), 200
```

#### 就绪检查

```python
@app.route('/health/ready')
def health_ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({
            "status": "ok",
            "database": "connected"
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "not_ready",
            "database": "disconnected"
        }), 503
```

#### 指标端点

```python
@app.route('/metrics')
def metrics():
    return jsonify(metrics_collector.get_metrics()), 200
```

### 4. 指标收集器

#### MetricsCollector 类

```python
class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_requests = 0
        self.error_count = 0
        self.status_codes = {}
        self.total_latency_ms = 0
        self.start_time = time.time()

    def record_request(self, status_code, latency_ms):
        with self.lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms

            if status_code >= 400:
                self.error_count += 1

            if status_code not in self.status_codes:
                self.status_codes[status_code] = 0
            self.status_codes[status_code] += 1

    def get_metrics(self):
        with self.lock:
            uptime = time.time() - self.start_time
            return {
                "total_requests": self.total_requests,
                "error_count": self.error_count,
                "status_codes": self.status_codes.copy(),
                "total_latency_ms": self.total_latency_ms,
                "uptime_seconds": uptime,
                "avg_latency_ms": self.total_latency_ms / self.total_requests if self.total_requests > 0 else 0
            }
```

#### 集成到响应钩子

```python
@app.after_request
def collect_metrics(response):
    if hasattr(g, 'start_time'):
        latency_ms = (time.time() - g.start_time) * 1000
        metrics_collector.record_request(response.status_code, latency_ms)
    return response
```

## Testing Strategy

### 测试文件结构

```
tests/
├── test_error_contract.py          # 错误契约测试
├── test_index_migration.py         # 索引迁移测试
├── test_health_endpoints.py        # 健康检查测试
└── test_metrics_collector.py       # 指标收集测试
```

### 测试覆盖范围

#### 错误契约测试

- 正常响应保持不变（200 状态码）
- 4xx 响应包含 `error`、`code`、`request_id`
- 5xx 响应不泄露异常堆栈信息
- 未处理异常返回标准 500 响应
- 请求 ID 在整个请求生命周期中保持一致
- 非 JSON 错误响应能被正确处理
- 数据库异常触发回滚

#### 索引迁移测试

- 新数据库创建时包含所有目标索引
- 旧数据库升级时幂等添加缺失索引
- 重复执行迁移不报错
- 迁移失败不影响应用启动
- 索引确实提升查询性能

#### 健康检查测试

- `/health/live` 始终返回 200
- `/health/ready` 数据库正常时返回 200
- `/health/ready` 数据库异常时返回 503
- `/metrics` 返回有效 JSON 结构
- 指标数据随请求递增

#### 指标收集测试

- 线程安全：并发请求计数准确
- 耗时统计正确记录
- 状态码分类准确
- 重启后指标清零

### TDD 方法

1. 运行现有测试，记录基线
2. 编写失败测试（红阶段）
3. 实现最小改动使测试通过（绿阶段）
4. 重构优化

## Risk Mitigation

### 主要风险及缓解措施

1. **响应归一化影响现有调用方**
   - 缓解：保持 `error` 字段类型，明确 5xx 文本不稳定，增加契约测试

2. **索引迁移失败影响可用性**
   - 缓解：使用事务和幂等语句，失败不影响业务表，记录明确日志

3. **健康检查增加数据库压力**
   - 缓解：就绪检查只执行 `SELECT 1`，不访问业务表

4. **进程内指标不适合多进程聚合**
   - 缓解：在接口元数据中标明进程级语义，完整监控留待后续

5. **响应钩子遇到非 JSON 错误响应**
   - 缓解：仅处理 `/api` 且状态码 >= 400 的响应，对无法解析的响应构造标准错误体

## Boundary Conditions

### 错误处理边界

- 非 `/api` 路径不进行响应归一化
- 状态码 < 400 的响应不处理
- 无法解析为 JSON 的响应构造标准错误体
- WebSocket 请求不归一化（SocketIO 路径）

### 索引迁移边界

- 只处理白名单中定义的索引
- 不删除已存在的索引
- 不修改表结构
- 迁移失败不阻止应用启动

### 健康检查边界

- 存活检查不依赖任何外部资源
- 就绪检查只验证数据库连通性
- 不检查 LLM、向量库等依赖
- 指标接口不调用任何业务逻辑

### 指标收集边界

- 只收集 HTTP 层面指标
- 不收集业务层面指标（如生成任务数）
- 不跨进程聚合
- 重启后清零

## Rollback Plan

1. 移除请求钩子和新接口
2. 索引可保留且不影响旧代码
3. 必要时通过显式迁移删除索引

## Success Criteria

- 所有测试通过
- 错误响应符合统一契约
- 索引迁移幂等且不破坏现有数据
- 健康检查端点正常工作
- 指标收集线程安全且准确
- 现有功能不受影响