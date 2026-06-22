---
change: stabilize-rag-generation-baseline
design-doc: docs/superpowers/specs/2026-06-22-rag-generation-baseline-design.md
base-ref: 6f2b7df0aaedb55e8dd36af046e645ce41784714
---

# RAG 生成基线稳定化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复 Phase 2 的全局召回与 ITEM 精准召回合并路径，保持可恢复降级，并消除全局缺陷上下文重复。

**Architecture:** 保留 `GenerationService` 现有全局召回，在 ITEM 循环内用标题和测试点执行缺陷精准召回。局部上下文优先与全局上下文精确去重后传给 `generate_item_cases`，不改动底层检索算法或外部接口。

**Tech Stack:** Python 3.14、Flask 服务层、HybridRetriever、QueryOptimizer、RetrievalEvaluator、pytest、unittest.mock。

## Global Constraints

- 测试失败必须先完成逻辑审查；错误或陈旧测试先修正，只有有效测试才能驱动生产代码修改。
- 不添加代码注释，不修改 REST API、数据库 schema、WebSocket 事件、前端或底层检索算法。
- 所有新增方法参数与返回值使用类型提示，使用 `Optional[Type]` 和 `Dict[str, Any]`。
- ITEM 低相似度最多扩检一次；可恢复异常不得阻断用例生成。
- 合并上下文时 ITEM 局部结果优先，完全相同的段落只保留一次。

## 文件结构

- Create: `docs/superpowers/reviews/2026-06-22-rag-generation-test-audit.md` — 记录 9 个基线失败测试的逻辑来源与处置结论。
- Modify: `tests/test_rag_generation_deep_integration.py` — 修正错误 mock，并补齐 ITEM 召回、合并及 Phase 2 接入断言。
- Modify: `src/services/generation_service.py` — 实现 ITEM 精准召回、上下文合并、Phase 2 接入和缺陷去重。
- Modify: `openspec/changes/stabilize-rag-generation-baseline/tasks.md` — 每个验收单元通过后勾选对应任务。

---

### Task 1: 审查并校正失败测试基线

**Files:**
- Create: `docs/superpowers/reviews/2026-06-22-rag-generation-test-audit.md`
- Modify: `tests/test_rag_generation_deep_integration.py:1-209`
- Modify: `openspec/changes/stabilize-rag-generation-baseline/tasks.md:1-4`

**Interfaces:**
- Consumes: `HybridRetriever.retrieve(collection: str, query: str, top_k: int) -> Dict[str, Any]`，`RetrievalEvaluator.generate_quality_report(vector_results, keyword_results, fused_results) -> Dict[str, Any]`。
- Produces: 经审查的 9 个测试及审查记录；后续任务只允许以其中标记为“实现缺陷”的断言驱动代码。

- [ ] **Step 1: 运行目标测试并保存失败清单**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -v --tb=short`

Expected: 9 tests collected；8 个因 `_perform_item_rag_recall` 缺失失败，缺陷去重测试因同一内容出现两次失败。

- [ ] **Step 2: 创建逐项逻辑审查记录**

Create `docs/superpowers/reviews/2026-06-22-rag-generation-test-audit.md` with this table:

```markdown
# RAG 生成失败测试逻辑审查

| 测试 | 规格依据 | 结论 | 处置 |
|---|---|---|---|
| test_query_construction_with_points | 两层 RAG / ITEM 含测试点 | 实现缺陷 | 保留 |
| test_query_construction_without_points | 两层 RAG / ITEM 无测试点 | 实现缺陷 | 保留 |
| test_no_hybrid_retriever_returns_empty | 稳定降级 / 检索器不可用 | 实现缺陷 | 补充稳定结构断言 |
| test_query_optimizer_fallback | 稳定降级 / 优化器异常 | 实现缺陷 | 保留 |
| test_no_rag_results_placeholder | 稳定降级 / 无结果 | 测试陈旧 | evaluator 必须返回 no_results 后再断言占位文本 |
| test_citation_instruction_in_context | 引用提示 | 实现缺陷 | 保留 |
| test_defect_not_duplicated | 全局缺陷不重复 | 实现缺陷 | 保留 |
| test_low_similarity_triggers_expanded_retrieval | 低相似度单次扩检 | 测试错误 | mock 从三次返回改为两次并断言 top_k=[5, 10] |
| test_no_results_sets_degraded | 稳定降级 / 无结果 | 实现缺陷 | 保留 |
```

- [ ] **Step 3: 修正无结果测试的质量报告 mock**

Replace its evaluator response with:

```python
service._retrieval_evaluator.generate_quality_report.return_value = {
    "quality_alert": "no_results"
}
```

- [ ] **Step 4: 修正低相似度测试的检索返回与断言**

Use exactly two responses because ITEM 检索只查 `defects`，质量告警最多触发一次扩检：

```python
service._hybrid_retriever.retrieve.side_effect = [
    {"results": [{"id": "D1", "content": "defect1", "score": 0.3}]},
    {
        "results": [
            {"id": "D1", "content": "defect1", "score": 0.3},
            {"id": "D2", "content": "defect2", "score": 0.4},
        ]
    },
]

assert [call.kwargs["top_k"] for call in service._hybrid_retriever.retrieve.call_args_list] == [5, 10]
```

- [ ] **Step 5: 运行测试确认剩余失败均对应实现缺口**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -v --tb=short`

Expected: `_perform_item_rag_recall` 相关测试仍因方法缺失失败；`test_defect_not_duplicated` 仍因重复内容失败；不再出现 mock 序列耗尽或无结果质量报告矛盾。

- [ ] **Step 6: 勾选 OpenSpec 测试审查任务并提交**

Update `tasks.md` items 1.1 and 1.2 to `[x]`, then run:

```bash
git add docs/superpowers/reviews/2026-06-22-rag-generation-test-audit.md tests/test_rag_generation_deep_integration.py openspec/changes/stabilize-rag-generation-baseline/tasks.md
git commit -m "test: audit rag generation failures"
```

### Task 2: 实现 ITEM 精准召回和有限降级

**Files:**
- Modify: `tests/test_rag_generation_deep_integration.py:6-126,165-209`
- Modify: `src/services/generation_service.py:4317`
- Modify: `openspec/changes/stabilize-rag-generation-baseline/tasks.md:6-10`

**Interfaces:**
- Consumes: `self._hybrid_retriever.retrieve(collection="defects", query=query, top_k=top_k)` 和 `self._retrieval_evaluator.generate_quality_report(results, [], results)`。
- Produces: `_perform_item_rag_recall(item_title: str, item_points: List[Any], top_k: int = 5) -> Dict[str, Any]`，返回 `rag_context`、`results`、`quality_alert`、`degraded`、`stats`。

- [ ] **Step 1: 扩充稳定结构与字典测试点的失败断言**

Add:

```python
def test_query_construction_normalizes_dict_points(self):
    self.service._hybrid_retriever = MagicMock()
    self.service._hybrid_retriever.retrieve.return_value = {"results": []}
    self.service._init_rag_components = MagicMock()
    self.service._retrieval_evaluator = MagicMock()
    self.service._retrieval_evaluator.generate_quality_report.return_value = {
        "quality_alert": "no_results"
    }

    result = self.service._perform_item_rag_recall(
        "登录模块", [{"title": "密码输入"}, {"name": "验证码校验"}], 5
    )

    query = self.service._hybrid_retriever.retrieve.call_args.kwargs["query"]
    assert query == "登录模块 密码输入 验证码校验"
    assert set(result) >= {"rag_context", "results", "quality_alert", "degraded", "stats"}
```

- [ ] **Step 2: 运行新增测试验证红灯**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py::TestPerformItemRagRecall -v --tb=short`

Expected: FAIL because `_perform_item_rag_recall` is absent.

- [ ] **Step 3: 实现查询规范化、优化器回退与稳定结果骨架**

The existing typing import already contains `List`; add these focused methods near `_perform_rag_recall`:

```python
def _normalize_item_points(self, item_points: List[Any]) -> List[str]:
    normalized = []
    for point in item_points:
        if isinstance(point, dict):
            value = point.get("title", point.get("name", ""))
        else:
            value = str(point)
        value = str(value).strip()
        if value:
            normalized.append(value)
    return normalized

def _perform_item_rag_recall(
    self, item_title: str, item_points: List[Any], top_k: int = 5
) -> Dict[str, Any]:
    self._init_rag_components()
    raw_query = " ".join(
        part for part in [item_title.strip(), *self._normalize_item_points(item_points)] if part
    )
    query = raw_query
    if self._query_optimizer:
        try:
            keywords = self._query_optimizer.extract_keywords(raw_query)
            if keywords:
                query = " ".join([raw_query, *keywords])
        except Exception as e:
            logger.warning("ITEM RAG query optimization failed: %s", str(e))
    empty = {
        "rag_context": "",
        "results": {"defects": []},
        "quality_alert": None,
        "degraded": False,
        "stats": {"query": query, "result_count": 0, "retrieval_count": 0},
    }
    if not self._hybrid_retriever:
        return empty
    return self._retrieve_item_rag(query, top_k, empty)
```

- [ ] **Step 4: 实现单次扩检、质量报告和上下文格式化**

Add:

```python
def _retrieve_item_rag(
    self, query: str, top_k: int, empty: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        response = self._hybrid_retriever.retrieve(
            collection="defects", query=query, top_k=top_k
        )
        defects = response.get("results", []) if isinstance(response, dict) else response or []
        retrieval_count = 1
        quality_alert = None
        if self._retrieval_evaluator:
            report = self._retrieval_evaluator.generate_quality_report(
                defects, [], defects
            )
            quality_alert = report.get("quality_alert")
        if quality_alert == "low_similarity":
            expanded = self._hybrid_retriever.retrieve(
                collection="defects", query=query, top_k=top_k * 2
            )
            defects = (
                expanded.get("results", [])
                if isinstance(expanded, dict)
                else expanded or []
            )
            retrieval_count += 1
        return {
            "rag_context": self._format_item_rag_context(defects),
            "results": {"defects": defects},
            "quality_alert": quality_alert,
            "degraded": quality_alert in {"no_results", "low_similarity"},
            "stats": {
                "query": query,
                "result_count": len(defects),
                "retrieval_count": retrieval_count,
            },
        }
    except Exception as e:
        logger.warning("ITEM RAG retrieval failed: %s", str(e))
        failed = dict(empty)
        failed["degraded"] = True
        failed["quality_alert"] = "retrieval_error"
        return failed

def _format_item_rag_context(self, results: List[Dict[str, Any]]) -> str:
    if not results:
        return "无历史参考数据"
    blocks = ["## 当前 ITEM 召回的历史资料"]
    for index, result in enumerate(results, 1):
        source_id = result.get("id", f"defect_{index}")
        blocks.append(
            f"### 来源 {source_id}\n{result.get('content', '')}"
        )
    blocks.append("引用标注要求：如采用历史资料，请在结果中提供 citation。")
    return "\n\n".join(blocks)
```

- [ ] **Step 5: 运行 ITEM 召回测试并确认绿灯**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -k "PerformItemRagRecall or RagContextFormatting or QualityAlertDegradation" -v --tb=short`

Expected: all selected tests PASS；低相似度的 `top_k` sequence is `[5, 10]`.

- [ ] **Step 6: 勾选召回稳定化任务并提交**

Update `tasks.md` items 2.1 and 2.2 to `[x]`, then run:

```bash
git add src/services/generation_service.py tests/test_rag_generation_deep_integration.py openspec/changes/stabilize-rag-generation-baseline/tasks.md
git commit -m "feat: restore item rag retrieval"
```

### Task 3: 合并上下文并接入 Phase 2

**Files:**
- Modify: `tests/test_rag_generation_deep_integration.py`
- Modify: `src/services/generation_service.py:2355-2391,4380-4426`
- Modify: `openspec/changes/stabilize-rag-generation-baseline/tasks.md:8-14`

**Interfaces:**
- Consumes: `_perform_item_rag_recall(item_title: str, item_points: List[Any], top_k: int = 5) -> Dict[str, Any]`。
- Produces: `_merge_rag_contexts(global_context: str, item_result: Dict[str, Any]) -> str`；Phase 2 的 `generate_item_cases(..., rag_context=merged_rag_context)`。

- [ ] **Step 1: 写局部优先和精确去重红灯测试**

Add:

```python
def test_merge_rag_contexts_prefers_item_and_deduplicates_exact_blocks(self):
    from src.services.generation_service import GenerationService

    service = GenerationService.__new__(GenerationService)
    merged = service._merge_rag_contexts(
        "共享段落\n\n全局段落",
        {"rag_context": "局部段落\n\n共享段落"},
    )

    assert merged.index("局部段落") < merged.index("全局段落")
    assert merged.count("共享段落") == 1
```

- [ ] **Step 2: 写 ITEM 生成编排的上下文传递测试**

Add:

```python
def test_generate_item_with_rag_passes_merged_context(self):
    from src.services.generation_service import GenerationService

    service = GenerationService.__new__(GenerationService)
    service._perform_item_rag_recall = MagicMock(
        return_value={"rag_context": "ITEM-RAG"}
    )
    service._merge_rag_contexts = MagicMock(return_value="ITEM-RAG\n\nGLOBAL-RAG")
    service.generate_item_cases = MagicMock(return_value=[{"title": "case"}])
    item = {"title": "模块A", "points": ["点A"]}

    cases = service._generate_item_cases_with_rag(
        item=item,
        global_context={"requirement_content": "需求"},
        recent_cases=[],
        task_id="task-1",
        global_rag_context="GLOBAL-RAG",
    )

    service._perform_item_rag_recall.assert_called_once_with(
        item_title="模块A", item_points=["点A"], top_k=5
    )
    service._merge_rag_contexts.assert_called_once_with(
        "GLOBAL-RAG", {"rag_context": "ITEM-RAG"}
    )
    assert service.generate_item_cases.call_args.kwargs["rag_context"] == "ITEM-RAG\n\nGLOBAL-RAG"
    assert cases == [{"title": "case"}]
```

- [ ] **Step 3: 运行新增测试验证红灯**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -k "merge_rag_contexts or phase2_uses_item" -v --tb=short`

Expected: FAIL because `_merge_rag_contexts` and `_generate_item_cases_with_rag` are absent.

- [ ] **Step 4: 实现局部优先的精确段落去重**

Add:

```python
def _merge_rag_contexts(
    self, global_context: str, item_result: Dict[str, Any]
) -> str:
    item_context = str(item_result.get("rag_context", "")).strip()
    blocks = []
    seen = set()
    for context in (item_context, global_context.strip()):
        for block in context.split("\n\n"):
            normalized = block.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                blocks.append(normalized)
    return "\n\n".join(blocks)
```

- [ ] **Step 5: 删除全局缺陷的第二段重复拼接分支**

In `_perform_rag_recall`, remove the second `defect_results = ...` plus its repeated `if defect_results:` formatting block, while retaining the first block, `retrieved_defects`, adjustment handling and exception boundary.

- [ ] **Step 6: 实现 ITEM 生成编排并接入循环**

Add near `generate_item_cases`:

```python
def _generate_item_cases_with_rag(
    self,
    item: Dict[str, Any],
    global_context: Dict[str, Any],
    recent_cases: List[Dict[str, Any]],
    task_id: str,
    global_rag_context: str,
) -> List[Dict[str, Any]]:
    item_title = item.get("title", item.get("name", ""))
    item_points = item.get("points", [])
    item_rag_result = self._perform_item_rag_recall(
        item_title=item_title, item_points=item_points, top_k=5
    )
    merged_rag_context = self._merge_rag_contexts(
        global_rag_context, item_rag_result
    )
    return self.generate_item_cases(
        item=item,
        global_context=global_context,
        recent_cases=recent_cases,
        task_id=task_id,
        rag_context=merged_rag_context,
    )
```

Replace the existing direct `self.generate_item_cases(...)` call inside the per-ITEM `try` with:

```python
item_cases = self._generate_item_cases_with_rag(
    item=item,
    global_context=global_context,
    recent_cases=recent_cases,
    task_id=task_id,
    global_rag_context=rag_context,
)
```

Do not move global recall into the loop.

- [ ] **Step 7: 运行合并、去重与流程测试**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -v --tb=short`

Expected: all tests PASS，including defect count 1 and distinct merged context per ITEM.

- [ ] **Step 8: 勾选接入任务并提交**

Update `tasks.md` items 2.3, 3.1 and 3.2 to `[x]`, then run:

```bash
git add src/services/generation_service.py tests/test_rag_generation_deep_integration.py openspec/changes/stabilize-rag-generation-baseline/tasks.md
git commit -m "feat: integrate item rag into phase two"
```

### Task 4: RAG 与全量回归验证

**Files:**
- Modify: `openspec/changes/stabilize-rag-generation-baseline/tasks.md:16-20`

**Interfaces:**
- Consumes: Task 1-3 的生产实现与测试。
- Produces: 已通过的目标测试、RAG 回归和全量回归证据；全部勾选的 OpenSpec tasks。

- [ ] **Step 1: 运行目标深度集成测试**

Run: `python -m pytest tests/test_rag_generation_deep_integration.py -v --tb=short`

Expected: all tests PASS.

- [ ] **Step 2: 运行 RAG 相关测试集**

Run: `python -m pytest tests/ -k "rag or retrieval" -v --tb=short`

Expected: all collected, non-empty tests PASS. Empty placeholder tests remain outside this change and must not be converted into production-code requirements.

- [ ] **Step 3: 运行全量测试**

Run: `python -m pytest tests/ -v --tb=short`

Expected: all valid tests PASS. If a test fails, reapply Task 1 logic audit before changing production code.

- [ ] **Step 4: 检查范围与变更内容**

Run:

```bash
git diff --check
git diff --stat 6f2b7df0aaedb55e8dd36af046e645ce41784714..HEAD
```

Expected: no whitespace errors；变更仅涉及计划列出的实现、测试、审查和 OpenSpec task 文件。

- [ ] **Step 5: 勾选回归任务并提交**

Update `tasks.md` items 4.1 and 4.2 to `[x]`, then run:

```bash
git add openspec/changes/stabilize-rag-generation-baseline/tasks.md
git commit -m "test: verify rag generation baseline"
```
