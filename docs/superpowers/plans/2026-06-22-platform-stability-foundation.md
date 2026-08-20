# Platform Stability Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 TestGen 平台建立稳定性基线，包括统一 API 错误契约、数据库查询索引优化和基础可观测能力

**Architecture:** 使用 Flask 请求生命周期钩子实现错误归一化，启动时执行幂等索引迁移，新增健康检查端点和进程内指标收集器

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, SQLite, pytest

## Global Constraints

- Python 3.14+
- Flask 应用，不引入额外框架
- SQLite 数据库，不迁移到其他数据库
- 不引入 Alembic、Redis、Celery、Prometheus 或 Grafana
- 不修改前端框架、RAG、多 Agent 或生成管道行为
- 遵循现有代码风格和命名规范
- 使用 TDD 方法：先写失败测试，再实现最小改动

---

## File Structure

```
src/
  api/
    routes.py                    # 修改：添加错误处理钩子
  database/
    models.py                    # 修改：添加索引声明
  monitoring/
    error_response.py            # 创建：错误响应类
    index_migration.py           # 创建：索引迁移类
    metrics_collector.py         # 创建：指标收集器类
app.py                           # 修改：集成错误处理、索引迁移、健康检查
tests/
  test_error_contract.py         # 创建：错误契约测试
  test_index_migration.py        # 创建：索引迁移测试
  test_health_endpoints.py       # 创建：健康检查测试
  test_metrics_collector.py      # 创建：指标收集测试
```

---

### Task 1: 基线测试与审计

**Files:**
- Test: 运行现有测试套件
- Modify: `openspec/changes/stabilize-platform-foundation/tasks.md`

**Interfaces:**
- Consumes: 现有测试框架
- Produces: 基线测试结果记录

- [ ] **Step 1: 运行现有测试套件**

```bash
python -m pytest tests/ -v
```

Expected: 记录所有测试结果，识别与本 change 无关的既有失败

- [ ] **Step 2: 检查工作区是否有未提交改动**

```bash
git status
```

Expected: 确认工作区干净或记录未提交改动

- [ ] **Step 3: 更新 tasks.md 标记基线审计完成**

在 `openspec/changes/stabilize-platform-foundation/tasks.md` 中勾选第一个任务：

```markdown
- [x] 1.1 运行现有测试并记录基线，确认与本 change 无关的既有失败和工作区改动
```

- [ ] **Step 4: 提交基线审计记录**

```bash
git add openspec/changes/stabilize-platform-foundation/tasks.md
git commit -m "chore: 完成基线测试审计"
```

---

### Task 2: 创建 ErrorResponse 类

**Files:**
- Create: `src/monitoring/error_response.py`
- Test: `tests/test_error_contract.py`

**Interfaces:**
- Consumes: 无
- Produces: `ErrorResponse.create(message, code, request_id, details=None)` → `dict`

- [ ] **Step 1: 创建监控模块目录**

```bash
mkdir -p src/monitoring
```

- [ ] **Step 2: 编写 ErrorResponse 类的失败测试**

创建 `tests/test_error_contract.py`:

```python
import pytest
from src.monitoring.error_response import ErrorResponse


def test_error_response_basic():
    result = ErrorResponse.create("测试错误", "TEST_ERROR", "req-123")
    assert result == {
        "error": "测试错误",
        "code": "TEST_ERROR",
        "request_id": "req-123"
    }


def test_error_response_with_details():
    result = ErrorResponse.create(
        "测试错误",
        "TEST_ERROR",
        "req-123",
        {"field": "value"}
    )
    assert result == {
        "error": "测试错误",
        "code": "TEST_ERROR",
        "request_id": "req-123",
        "details": {"field": "value"}
    }


def test_error_response_without_details():
    result = ErrorResponse.create("测试错误", "TEST_ERROR", "req-123")
    assert "details" not in result
```

- [ ] **Step 3: 运行测试验证失败**

```bash
python -m pytest tests/test_error_contract.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.monitoring.error_response'"

- [ ] **Step 4: 创建 ErrorResponse 类**

创建 `src/monitoring/error_response.py`:

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

- [ ] **Step 5: 运行测试验证通过**

```bash
python -m pytest tests/test_error_contract.py -v
```

Expected: PASS

- [ ] **Step 6: 提交 ErrorResponse 类**

```bash
git add src/monitoring/error_response.py tests/test_error_contract.py
git commit -m "feat: 添加 ErrorResponse 类"
```

---

### Task 3: 创建 MetricsCollector 类

**Files:**
- Create: `src/monitoring/metrics_collector.py`
- Test: `tests/test_metrics_collector.py`

**Interfaces:**
- Consumes: 无
- Produces: `MetricsCollector.record_request(status_code, latency_ms)` → `None`
- Produces: `MetricsCollector.get_metrics()` → `dict`

- [ ] **Step 1: 编写 MetricsCollector 的失败测试**

创建 `tests/test_metrics_collector.py`:

```python
import pytest
import time
import threading
from src.monitoring.metrics_collector import MetricsCollector


def test_metrics_collector_initialization():
    collector = MetricsCollector()
    metrics = collector.get_metrics()
    assert metrics["total_requests"] == 0
    assert metrics["error_count"] == 0
    assert metrics["status_codes"] == {}
    assert metrics["total_latency_ms"] == 0
    assert metrics["uptime_seconds"] > 0


def test_metrics_collector_record_request():
    collector = MetricsCollector()
    collector.record_request(200, 100)
    collector.record_request(404, 50)
    collector.record_request(500, 200)

    metrics = collector.get_metrics()
    assert metrics["total_requests"] == 3
    assert metrics["error_count"] == 2
    assert metrics["status_codes"] == {200: 1, 404: 1, 500: 1}
    assert metrics["total_latency_ms"] == 350
    assert metrics["avg_latency_ms"] == pytest.approx(116.67, rel=1e-2)


def test_metrics_collector_thread_safety():
    collector = MetricsCollector()

    def record_requests():
        for i in range(100):
            collector.record_request(200, 10)

    threads = [threading.Thread(target=record_requests) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    metrics = collector.get_metrics()
    assert metrics["total_requests"] == 1000
    assert metrics["error_count"] == 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_metrics_collector.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.monitoring.metrics_collector'"

- [ ] **Step 3: 创建 MetricsCollector 类**

创建 `src/monitoring/metrics_collector.py`:

```python
import threading
import time


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

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_metrics_collector.py -v
```

Expected: PASS

- [ ] **Step 5: 提交 MetricsCollector 类**

```bash
git add src/monitoring/metrics_collector.py tests/test_metrics_collector.py
git commit -m "feat: 添加 MetricsCollector 类"
```

---

### Task 4: 创建 IndexMigration 类

**Files:**
- Create: `src/monitoring/index_migration.py`
- Test: `tests/test_index_migration.py`

**Interfaces:**
- Consumes: SQLAlchemy engine
- Produces: `IndexMigration.__init__(engine, index_whitelist)` → `None`
- Produces: `IndexMigration.migrate()` → `None`

- [ ] **Step 1: 编写 IndexMigration 的失败测试**

创建 `tests/test_index_migration.py`:

```python
import pytest
import tempfile
import os
from sqlalchemy import create_engine, text
from src.monitoring.index_migration import IndexMigration


INDEX_WHITELIST = [
    {
        "table": "test_table",
        "columns": ["col1", "col2"],
        "name": "idx_test_col1_col2"
    }
]


def test_index_migration_creates_index():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.commit()

        migration = IndexMigration(engine, INDEX_WHITELIST)
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_col1_col2'"
            ))
            indexes = result.fetchall()
            assert len(indexes) == 1


def test_index_migration_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.commit()

        migration = IndexMigration(engine, INDEX_WHITELIST)

        migration.migrate()
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_col1_col2'"
            ))
            indexes = result.fetchall()
            assert len(indexes) == 1


def test_index_migration_handles_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine(f"sqlite:///{db_path}")

        invalid_whitelist = [
            {
                "table": "nonexistent_table",
                "columns": ["col1"],
                "name": "idx_invalid"
            }
        ]

        migration = IndexMigration(engine, invalid_whitelist)

        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            indexes = result.fetchall()
            assert len(indexes) == 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_index_migration.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.monitoring.index_migration'"

- [ ] **Step 3: 创建 IndexMigration 类**

创建 `src/monitoring/index_migration.py`:

```python
from src.utils import get_logger

logger = get_logger(__name__)


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

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_index_migration.py -v
```

Expected: PASS

- [ ] **Step 5: 提交 IndexMigration 类**

```bash
git add src/monitoring/index_migration.py tests/test_index_migration.py
git commit -m "feat: 添加 IndexMigration 类"
```

---

### Task 5: 集成错误处理到 Flask 应用

**Files:**
- Modify: `app.py`
- Test: `tests/test_error_contract.py`

**Interfaces:**
- Consumes: `ErrorResponse.create()`, `MetricsCollector.record_request()`
- Produces: Flask 请求生命周期钩子

- [ ] **Step 1: 编写错误处理集成的失败测试**

在 `tests/test_error_contract.py` 中添加:

```python
import pytest
import json
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_error_response_includes_request_id(client):
    response = client.get('/api/nonexistent')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'request_id' in data
    assert 'code' in data


def test_error_response_normalizes_5xx(client):
    response = client.get('/api/trigger-error')
    assert response.status_code == 500
    data = json.loads(response.data)
    assert data['error'] == "服务器内部错误"
    assert data['code'] == "INTERNAL_ERROR"
    assert 'request_id' in data


def test_normal_response_unchanged(client):
    response = client.get('/health/live')
    assert response.status_code == 200
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_error_contract.py::test_error_response_includes_request_id -v
```

Expected: FAIL (端点不存在或响应格式不正确)

- [ ] **Step 3: 在 app.py 中集成错误处理**

在 `app.py` 中添加:

```python
import uuid
import time
import threading
from flask import g, request
from src.monitoring.error_response import ErrorResponse
from src.monitoring.metrics_collector import MetricsCollector

metrics_collector = MetricsCollector()


@app.before_request
def assign_request_id():
    if 'X-Request-ID' in request.headers:
        g.request_id = request.headers['X-Request-ID']
    else:
        g.request_id = str(uuid.uuid4())
    g.start_time = time.time()


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


@app.after_request
def normalize_error_response(response):
    if not request.path.startswith('/api'):
        return response

    if response.status_code < 400:
        if hasattr(g, 'start_time'):
            latency_ms = (time.time() - g.start_time) * 1000
            metrics_collector.record_request(response.status_code, latency_ms)
        return response

    try:
        data = response.get_json()
        if not data:
            if hasattr(g, 'start_time'):
                latency_ms = (time.time() - g.start_time) * 1000
                metrics_collector.record_request(response.status_code, latency_ms)
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

    if hasattr(g, 'start_time'):
        latency_ms = (time.time() - g.start_time) * 1000
        metrics_collector.record_request(response.status_code, latency_ms)

    return response
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_error_contract.py -v
```

Expected: PASS

- [ ] **Step 5: 提交错误处理集成**

```bash
git add app.py tests/test_error_contract.py
git commit -m "feat: 集成错误处理到 Flask 应用"
```

---

### Task 6: 添加数据库索引到模型

**Files:**
- Modify: `src/database/models.py`
- Test: `tests/test_index_migration.py`

**Interfaces:**
- Consumes: SQLAlchemy Index
- Produces: 模型索引声明

- [ ] **Step 1: 编写索引声明的失败测试**

在 `tests/test_index_migration.py` 中添加:

```python
from src.database.models import Base, Requirement, TestCase, GenerationTask


def test_models_have_indexes():
    indexes = [idx for idx in Base.metadata.indexes]
    index_names = [idx.name for idx in indexes]

    assert "idx_requirements_created_status" in index_names
    assert "idx_cases_requirement_status" in index_names
    assert "idx_tasks_requirement_status_created" in index_names
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_index_migration.py::test_models_have_indexes -v
```

Expected: FAIL (索引不存在)

- [ ] **Step 3: 在 models.py 中添加索引声明**

在 `src/database/models.py` 中为相应模型添加索引:

```python
from sqlalchemy import Index

class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(Enum(RequirementStatus), default=RequirementStatus.PENDING_ANALYSIS)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_requirements_created_status', 'created_at', 'status'),
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    title = Column(String(200), nullable=False)
    steps = Column(Text, nullable=False)
    expected_result = Column(Text, nullable=False)
    status = Column(Enum(CaseStatus), default=CaseStatus.DRAFT)
    priority = Column(Enum(Priority), default=Priority.P2)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_cases_requirement_status', 'requirement_id', 'status'),
    )


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id = Column(Integer, primary_key=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.RUNNING)
    phase = Column(Enum(GenerationPhase), default=GenerationPhase.RAG)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_tasks_requirement_status_created', 'requirement_id', 'status', 'created_at'),
    )
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_index_migration.py::test_models_have_indexes -v
```

Expected: PASS

- [ ] **Step 5: 提交索引声明**

```bash
git add src/database/models.py tests/test_index_migration.py
git commit -m "feat: 添加数据库索引到模型"
```

---

### Task 7: 集成索引迁移到应用启动

**Files:**
- Modify: `app.py`
- Test: `tests/test_index_migration.py`

**Interfaces:**
- Consumes: `IndexMigration.migrate()`
- Produces: 应用启动时自动迁移

- [ ] **Step 1: 编写索引迁移集成的失败测试**

在 `tests/test_index_migration.py` 中添加:

```python
def test_index_migration_on_app_startup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        app = create_app(db_path=db_path)

        with app.app_context():
            engine = db_session.get_bind()
            result = engine.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ))
            indexes = result.fetchall()
            assert len(indexes) >= 3
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_index_migration.py::test_index_migration_on_app_startup -v
```

Expected: FAIL (索引迁移未集成)

- [ ] **Step 3: 在 app.py 中集成索引迁移**

修改 `app.py` 的 `create_app` 函数:

```python
from src.monitoring.index_migration import IndexMigration

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


def create_app(db_path="data/testgen.db"):
    app = Flask(__name__)
    CORS(app)

    app.config["UPLOAD_FOLDER"] = "data/uploads"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["UI_FOLDER"] = "src/ui"

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    engine = init_database(db_path)

    IndexMigration(engine, INDEX_WHITELIST).migrate()

    return app
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_index_migration.py -v
```

Expected: PASS

- [ ] **Step 5: 提交索引迁移集成**

```bash
git add app.py tests/test_index_migration.py
git commit -m "feat: 集成索引迁移到应用启动"
```

---

### Task 8: 添加健康检查端点

**Files:**
- Modify: `app.py`
- Test: `tests/test_health_endpoints.py`

**Interfaces:**
- Consumes: 数据库引擎
- Produces: `/health/live`, `/health/ready`, `/metrics` 端点

- [ ] **Step 1: 编写健康检查的失败测试**

创建 `tests/test_health_endpoints.py`:

```python
import pytest
import json
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_live_endpoint(client):
    response = client.get('/health/live')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == {"status": "ok"}


def test_health_ready_endpoint_success(client):
    response = client.get('/health/ready')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_metrics_endpoint(client):
    response = client.get('/metrics')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "total_requests" in data
    assert "error_count" in data
    assert "status_codes" in data
    assert "uptime_seconds" in data
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_health_endpoints.py -v
```

Expected: FAIL (端点不存在)

- [ ] **Step 3: 在 app.py 中添加健康检查端点**

在 `app.py` 中添加:

```python
@app.route('/health/live')
def health_live():
    return jsonify({"status": "ok"}), 200


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


@app.route('/metrics')
def metrics():
    return jsonify(metrics_collector.get_metrics()), 200
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_health_endpoints.py -v
```

Expected: PASS

- [ ] **Step 5: 提交健康检查端点**

```bash
git add app.py tests/test_health_endpoints.py
git commit -m "feat: 添加健康检查端点"
```

---

### Task 9: 运行完整测试套件

**Files:**
- Test: 所有测试文件

**Interfaces:**
- Consumes: 所有已实现功能
- Produces: 测试通过确认

- [ ] **Step 1: 运行完整测试套件**

```bash
python -m pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 2: 检查测试覆盖率**

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing
```

Expected: 覆盖率报告显示新增代码有良好覆盖

- [ ] **Step 3: 更新 tasks.md 标记所有任务完成**

在 `openspec/changes/stabilize-platform-foundation/tasks.md` 中勾选所有任务

- [ ] **Step 4: 提交最终测试结果**

```bash
git add openspec/changes/stabilize-platform-foundation/tasks.md
git commit -m "test: 完成所有测试验证"
```

---

### Task 10: 代码审查准备

**Files:**
- 所有修改的文件

**Interfaces:**
- Consumes: 所有实现代码
- Produces: 代码审查请求

- [ ] **Step 1: 检查代码质量**

```bash
flake8 src/monitoring/ app.py
black --check src/monitoring/ app.py
```

Expected: 无错误或警告

- [ ] **Step 2: 运行安全检查**

```bash
bandit -r src/monitoring/
```

Expected: 无高严重性问题

- [ ] **Step 3: 生成变更摘要**

```bash
git diff --stat HEAD~10
```

Expected: 显示所有变更文件和行数

- [ ] **Step 4: 提交代码审查准备**

```bash
git add .
git commit -m "chore: 准备代码审查"
```

---

## Self-Review

**Spec coverage:**
- ✅ API 错误契约：Task 2, 5
- ✅ 数据库索引：Task 4, 6, 7
- ✅ 健康检查：Task 8
- ✅ 指标收集：Task 3
- ✅ 测试覆盖：Task 1, 9

**Placeholder scan:**
- ✅ 无 TBD、TODO 或占位符
- ✅ 所有步骤包含具体代码和命令
- ✅ 所有文件路径明确

**Type consistency:**
- ✅ ErrorResponse.create() 签名一致
- ✅ MetricsCollector 方法签名一致
- ✅ IndexMigration 方法签名一致

**Execution Handoff**

Plan complete and saved to `docs/superpowers/plans/2026-06-22-platform-stability-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?