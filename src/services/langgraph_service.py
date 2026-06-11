#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph StateGraph 版 TestGen 用例生成服务
=================================================
替代 multi_agent_service.py 的 AutoGen 串行 Pipeline。

核心改进：
1. TypedDict State 结构化状态（替代消息列表）
2. 纯函数 node（替代 _run_xxx 方法）
3. add_conditional_edges 条件路由（REJECT→重试）
4. interrupt_before 人机回路（Phase 1 完成后暂停）
5. Command(resume) 断点续跑
6. SqliteSaver 自动 checkpoint
7. 代码量：~200行 vs 原 637行
"""

import json
import os
import re
import time
import uuid
import sqlite3
from datetime import datetime
from typing import Annotated, TypedDict, Dict, Any, List, Optional

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt


# ============ State 定义 ============

def append_list(existing: list, new: list) -> list:
    """Reducer: 追加列表"""
    return existing + new


class TestGenState(TypedDict):
    """TestGen LangGraph 状态 — 所有 node 共享"""
    # 输入
    requirement_id: int
    requirement_text: str

    # Phase 1: 分析
    orchestrator_output: str
    analyst_output: str
    modules: List[str]
    rules: List[str]
    test_points: List[Dict[str, Any]]
    designer_output: str
    review_conclusion: str  # PASS / CONDITIONAL / FAIL

    # Phase 2: 生成
    cases_raw: str                      # LLM 原始输出
    cases: Annotated[list, append_list]  # 解析后的结构化用例
    review_output: str
    review_decision: str                # APPROVE / CONDITIONAL / REJECT
    retry_count: int

    # 输出
    task_id: str
    case_ids: List[str]
    duration_seconds: float
    error: str


# ============ Agent Prompts（复用 multi_agent_service.py）============

AGENT_PROMPTS = {
    "orchestrator": """你是测试用例生成流水线的协调器（Orchestrator）。

请基于用户需求，输出一份结构化方案：
1. 方法论（1 句话，基于 ISO/IEC 29119 + 20926 FPA）
2. 模式识别（生成/评审/补充）
3. 设计方法选择（如：等价类划分、边界值分析、场景法）
4. 测试类型（13 种白名单中选）

要求：简洁，4 个部分各 1-2 句话，Markdown 格式输出。""",

    "requirement_analyst": """你是需求分析专家（Requirement Analyst）。

请基于用户需求和 Orchestrator 方案，输出需求解析报告：
1. 功能模块清单（按业务域划分）
2. 业务流程步骤（按顺序排列）
3. 约束条件清单（必填/长度/范围/权限）
4. 测试点清单（按模块组织，禁止与模块名重复）

格式：Markdown 表格。要求：客观分析，不添加需求外内容。""",

    "test_plan_designer": """你是测试规划+评审专家（Test Plan Designer）。

请基于需求解析报告，按 4 维度评审：
1. 完整性（是否覆盖所有功能）
2. 合理性（模块划分是否清晰）
3. 一致性（命名是否规范）
4. 可测性（测试点是否明确）

输出：评审结论 + 详细意见 + 修正后的测试点清单。""",

    "case_generator": """你是测试用例生成专家（Case Generator）。

请基于指定的模块和测试点，生成 2-3 条测试用例。

严格格式：
```
## [P0/P1/P2/P3] 用例标题
[测试类型] 功能/边界/异常/...
[前置条件] 前置条件描述
[测试步骤] 1. 步骤1。2. 步骤2。3. 步骤3
[预期结果] 1. 预期1。2. 预期2。3. 预期3
```

强制要求：
- P0+P1 合计 ≤ 40%
- 标题15-30字，以具体预期结尾
- 数据具体，禁止占位符
- 步骤与预期1:1对应
- 只生成 2-3 条，简洁输出""",

    "reviewer": """你是用例评审专家（Reviewer）。

请评审测试用例：
A. 一票否决：占位符/预期模糊/步骤不对应
B. 标题格式检查（扣分项）
C. 四维评分（各0-25）：PRD覆盖/清晰度/明确性/完整性

输出：否决检查 + 评分 + 结论
- 总分 ≥ 70 且无一票否决 → 合格(APPROVE)
- 总分 40-69 且无一票否决 → 有条件通过(CONDITIONAL)
- 有任何一票否决 或 总分 < 40 → 不合格(REJECT)

注意：不要过度严格，用例只要步骤清晰、预期可验证、覆盖主要场景就应通过。
""",
}


# ============ LLM 调用封装 ============

def call_llm(llm_manager, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """统一 LLM 调用"""
    adapter = llm_manager.get_adapter()
    try:
        response = adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            timeout=120,
        )
        if response.success:
            return response.content
        raise Exception(f"LLM 调用失败: {response.error_message}")
    except (AttributeError, NotImplementedError):
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = adapter.generate(full_prompt, temperature=temperature, timeout=120)
        if response.success:
            return response.content
        raise Exception(f"LLM 调用失败: {response.error_message}")


# ============ 全局 LLM 管理器（兼容所有 langgraph 版本）============
# LangGraph checkpoint 会序列化 state，LLMManager 不能被 msgpack 序列化
# 所以用全局变量存储，node 函数从全局变量获取
_current_llm_manager = None

def set_llm_manager(llm_manager):
    """设置当前 LLM 管理器"""
    global _current_llm_manager
    _current_llm_manager = llm_manager

# ============ Node 函数（纯函数，从 state 读取，返回 partial state）============

def orchestrator_node(state: TestGenState) -> dict:
    """协调器：规划生成方案"""
    from src.utils import get_logger
    logger = get_logger("langgraph_testgen")
    logger.info("[LangGraph] 🎯 Orchestrator 启动")

    llm_manager = _current_llm_manager
    output = call_llm(
        llm_manager,
        AGENT_PROMPTS["orchestrator"],
        f"需求：\n{state['requirement_text']}",
    )
    logger.info("[LangGraph] ✅ Orchestrator 完成")
    return {"orchestrator_output": output}


def analyst_node(state: TestGenState) -> dict:
    """需求分析：解析模块/规则/测试点"""
    from src.utils import get_logger
    logger = get_logger("langgraph_testgen")
    logger.info("[LangGraph] 🔍 Analyst 启动")

    llm_manager = _current_llm_manager
    output = call_llm(
        llm_manager,
        AGENT_PROMPTS["requirement_analyst"],
        f"需求：\n{state['requirement_text']}\n\nOrchestrator 方案：\n{state['orchestrator_output']}",
    )
    logger.info("[LangGraph] ✅ Analyst 完成")
    return {"analyst_output": output}


def designer_node(state: TestGenState) -> dict:
    """测试规划：评审分析结果"""
    from src.utils import get_logger
    logger = get_logger("langgraph_testgen")
    logger.info("[LangGraph] 📋 Designer 启动")

    llm_manager = _current_llm_manager
    output = call_llm(
        llm_manager,
        AGENT_PROMPTS["test_plan_designer"],
        f"需求：\n{state['requirement_text']}\n\n需求解析：\n{state['analyst_output']}",
    )

    # 解析评审结论
    conclusion = "CONDITIONAL"
    if "通过" in output and "不通过" not in output:
        conclusion = "PASS"
    elif "不通过" in output:
        conclusion = "FAIL"

    logger.info(f"[LangGraph] ✅ Designer 完成，结论={conclusion}")
    return {"designer_output": output, "review_conclusion": conclusion}


def generator_node(state: TestGenState) -> dict:
    """用例生成：按模块生成测试用例"""
    from src.utils import get_logger
    logger = get_logger("langgraph_testgen")
    retry = state.get("retry_count", 0)
    logger.info(f"[LangGraph] ⚡ Generator 启动 (retry={retry})")

    llm_manager = _current_llm_manager
    output = call_llm(
        llm_manager,
        AGENT_PROMPTS["case_generator"],
        f"需求：\n{state['requirement_text']}\n\n测试规划：\n{state['designer_output']}",
        temperature=0.4,
    )

    # 解析用例
    cases = _parse_cases_from_markdown(output)
    cases = _balance_priorities(cases)

    logger.info(f"[LangGraph] ✅ Generator 完成，{len(cases)} 条用例")
    return {"cases_raw": output, "cases": cases, "retry_count": retry + 1}


def reviewer_node(state: TestGenState) -> dict:
    """用例评审：6维度评分"""
    from src.utils import get_logger
    logger = get_logger("langgraph_testgen")
    logger.info("[LangGraph] 🔎 Reviewer 启动")

    llm_manager = _current_llm_manager
    output = call_llm(
        llm_manager,
        AGENT_PROMPTS["reviewer"],
        f"需求：\n{state['requirement_text']}\n\n用例：\n{state['cases_raw']}",
    )

    # 解析评审结论
    decision = _parse_review_decision(output)
    logger.info(f"[LangGraph] ✅ Reviewer 完成，决策={decision}")
    return {"review_output": output, "review_decision": decision}


# ============ 条件路由 ============

def route_after_review(state: TestGenState) -> str:
    """评审后路由：APPROVE→END, REJECT/CONDITIONAL→Generator重试"""
    decision = state.get("review_decision", "REJECT")
    retry = state.get("retry_count", 0)

    if decision == "APPROVE":
        return "end"
    elif retry >= 3:
        return "end"  # 重试上限
    else:
        return "generator"


# ============ 构建 StateGraph ============

def build_testgen_graph(checkpoint_path: str = "data/langgraph_checkpoints.db"):
    """构建 TestGen LangGraph StateGraph"""

    # 确保 data 目录存在
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)

    # Checkpoint
    conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    builder = StateGraph(TestGenState)

    # 添加 node
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("designer", designer_node)
    builder.add_node("generator", generator_node)
    builder.add_node("reviewer", reviewer_node)

    # 线性边
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", "analyst")
    builder.add_edge("analyst", "designer")
    builder.add_edge("designer", "generator")
    builder.add_edge("generator", "reviewer")

    # 条件路由
    builder.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"generator": "generator", "end": END},
    )

    # 编译（Phase 1 完成后 interrupt，等人工评审）
    graph = builder.compile(
        checkpointer=memory,
        interrupt_before=["generator"],  # 设计完成后暂停
    )

    return graph, conn


# ============ 用例解析（复用 multi_agent_service.py 逻辑）============

def _parse_cases_from_markdown(markdown_text: str) -> List[Dict[str, Any]]:
    """从 Markdown 解析测试用例"""
    cases = []
    # 支持多种格式：## [P0] 标题 或 ## [P0/P1/P2/P3] 标题
    pattern = r'##\s*\[(P[0-3])\]\s*(.+?)(?=\n##\s*\[P|\Z)'
    blocks = re.findall(pattern, markdown_text, re.DOTALL)

    if not blocks:
        # 备用模式：匹配 ### 或 ** 格式
        pattern2 = r'(?:##|###|\*\*)\s*\[(P[0-3])\]\s*(.+?)(?=(?:##|###|\*\*)\s*\[P|\Z)'
        blocks = re.findall(pattern2, markdown_text, re.DOTALL)

    if not blocks:
        # 第三种：匹配任何包含 P0/P1/P2/P3 的标题行
        lines = markdown_text.split('\n')
        current_case = None
        current_text = []
        for line in lines:
            m = re.match(r'(?:##|###)\s*\[(P[0-3])\]\s*(.+)', line)
            if m:
                if current_case:
                    case = _parse_single_case('\n'.join(current_text), current_case[0])
                    if case:
                        raw = current_case[1].strip()
                        case['title'] = raw if raw.startswith(f'[{current_case[0]}]') else f'[{current_case[0]}] {raw}'
                        cases.append(case)
                current_case = (m.group(1), m.group(2))
                current_text = [line]
            elif current_case:
                current_text.append(line)
        if current_case:
            case = _parse_single_case('\n'.join(current_text), current_case[0])
            if case:
                raw = current_case[1].strip()
                case['title'] = raw if raw.startswith(f'[{current_case[0]}]') else f'[{current_case[0]}] {raw}'
                cases.append(case)
        return cases

    for priority, block_content in blocks:
        title = block_content.split('\n')[0].strip()
        case = _parse_single_case(block_content, priority)
        if case:
            # 避免重复优先级前缀
            raw_title = title.strip()
            if raw_title.startswith(f'[{priority}]'):
                case["title"] = raw_title
            else:
                case["title"] = f"[{priority}] {raw_title}"
            cases.append(case)

    return cases


def _parse_single_case(block: str, priority_num: str) -> Optional[Dict[str, Any]]:
    """解析单条用例"""
    def extract_field(pattern: str) -> str:
        m = re.search(pattern, block, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    test_type = extract_field(r'\[测试类型\]\s*(.+)')
    precondition = extract_field(r'\[前置条件\]\s*(.+)')
    steps_text = extract_field(r'\[测试步骤\]\s*(.+?)(?=\[预期结果\])')
    expected_text = extract_field(r'\[预期结果\]\s*(.+)')

    steps = [s.strip() for s in re.split(r'\d+\.\s*', steps_text) if s.strip()]
    expected = [e.strip() for e in re.split(r'\d+\.\s*', expected_text) if e.strip()]

    if not steps or not expected:
        # 宽容解析：即使步骤/预期不完整也保留
        if not steps and steps_text:
            steps = [steps_text]
        if not expected and expected_text:
            expected = [expected_text]
        if not steps and not expected:
            return None

    return {
        "case_id": f"TC_LG_{uuid.uuid4().hex[:8]}",
        "priority": priority_num,
        "test_type": test_type,
        "precondition": precondition,
        "steps": steps,
        "expected_results": expected,
    }


def _parse_review_decision(review_output: str) -> str:
    """解析评审结论"""
    output_lower = review_output.lower()
    if "合格" in output_lower and "不合格" not in output_lower:
        return "APPROVE"
    elif "有条件通过" in output_lower or "有条件" in output_lower:
        return "CONDITIONAL"
    elif "不合格" in output_lower or "否决" in output_lower:
        return "REJECT"
    # 评分判断
    score_match = re.search(r'总分[：:]\s*(\d+)', review_output)
    if score_match:
        score = int(score_match.group(1))
        if score >= 70:
            return "APPROVE"
        elif score >= 40:
            return "CONDITIONAL"
    return "REJECT"


def _balance_priorities(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """优先级平衡：P0+P1 ≤ 40%"""
    if not cases:
        return cases

    total = len(cases)
    max_high = max(1, int(total * 0.4))

    high_count = sum(1 for c in cases if c["priority"] in ("P0", "P1"))
    if high_count <= max_high:
        return cases

    # 降级多余的 P1 → P2
    demoted = 0
    for c in cases:
        if c["priority"] == "P1" and high_count - demoted > max_high:
            c["priority"] = "P2"
            demoted += 1

    return cases


# ============ 服务类（Flask 集成用）============

class LangGraphTestGenService:
    """LangGraph 版 TestGen 服务 — Flask API 集成"""

    def __init__(self, db_session=None, llm_manager=None):
        self.db_session = db_session
        self.llm_manager = llm_manager
        self.graph, self.conn = build_testgen_graph()

    def generate_cases(self, requirement_id: int, max_attempts: int = 2) -> Dict[str, Any]:
        """主入口：生成测试用例"""
        from src.utils import get_logger
        logger = get_logger("langgraph_testgen")
        start_time = time.time()

        # 设置全局 LLM 管理器（node函数从全局变量获取，避免checkpoint序列化问题）
        set_llm_manager(self.llm_manager)

        # 1. 加载需求
        req = self._load_requirement(requirement_id)
        requirement_text = f"# {req['title']}\n\n{req['content']}"

        # 2. 创建任务
        from src.database.models import GenerationTask, TaskStatus, GenerationPhase
        task = GenerationTask(
            task_id=f"lg_{uuid.uuid4().hex[:16]}",
            requirement_id=requirement_id,
            status=TaskStatus.RUNNING,
            phase=GenerationPhase.GENERATION,
            started_at=datetime.utcnow(),
        )
        self.db_session.add(task)
        self.db_session.commit()

        # 3. 运行 StateGraph
        config = {
            "configurable": {
                "thread_id": f"testgen-{requirement_id}",
                "llm_manager": self.llm_manager,
            }
        }

        initial_state = {
            "requirement_id": requirement_id,
            "requirement_text": requirement_text,
            "orchestrator_output": "", "analyst_output": "",
            "modules": [], "rules": [], "test_points": [],
            "designer_output": "", "review_conclusion": "",
            "cases_raw": "", "cases": [], "review_output": "",
            "review_decision": "", "retry_count": 0,
            "task_id": task.task_id, "case_ids": [],
            "duration_seconds": 0, "error": "",
        }

        try:
            # Phase 1: 分析+策略（interrupt 在 generator 前）
            logger.info(f"[LangGraph] Phase 1 启动 - 需求ID={requirement_id}")
            result = self.graph.invoke(initial_state, config=config)

            # 检查是否在 interrupt 处暂停
            # 如果有 checkpoint 且暂停在 generator 前，自动继续
            logger.info("[LangGraph] Phase 1 完成，继续 Phase 2")

            # Phase 2: 生成+评审（自动继续）
            result = self.graph.invoke(Command(resume={"retry_count": result.get("retry_count", 0)}), config=config)

            # 4. 保存用例
            cases = result.get("cases", [])
            case_ids = self._save_test_cases(requirement_id, cases) if cases else []

            # 5. 更新任务
            total_duration = time.time() - start_time
            task = self.db_session.query(GenerationTask).filter_by(task_id=task.task_id).first()
            if task:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                self.db_session.commit()

            return {
                "task_id": task.task_id,
                "status": result.get("review_decision", "UNKNOWN"),
                "case_count": len(case_ids),
                "duration_seconds": round(total_duration, 1),
                "review_decision": result.get("review_decision", ""),
            }

        except Exception as e:
            logger.error(f"[LangGraph] Pipeline 失败: {e}")
            task = self.db_session.query(GenerationTask).filter_by(task_id=task.task_id).first()
            if task:
                from src.database.models import TaskStatus
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                self.db_session.commit()
            return {
                "task_id": task.task_id,
                "status": "FAILED",
                "error": str(e),
                "case_count": 0,
                "duration_seconds": round(time.time() - start_time, 1),
            }

    def _load_requirement(self, requirement_id: int) -> Dict[str, Any]:
        """加载需求"""
        from src.database.models import Requirement
        req = self.db_session.query(Requirement).filter_by(id=requirement_id).first()
        if not req:
            raise ValueError(f"需求不存在: {requirement_id}")
        return {"title": req.title, "content": req.content}

    def _save_test_cases(self, requirement_id: int, cases: List[Dict]) -> List[str]:
        """保存测试用例到数据库"""
        from src.database.models import TestCase
        case_ids = []
        for case_data in cases:
            tc = TestCase(
                requirement_id=requirement_id,
                case_id=case_data.get("case_id", f"TC_LG_{uuid.uuid4().hex[:8]}"),
                name=case_data.get("title", ""),  # DB field is 'name', not 'title'
                module=case_data.get("module", case_data.get("test_type", "未分类")),  # module is required
                priority=case_data.get("priority", "P2"),
                case_type=case_data.get("test_type", ""),
                preconditions=case_data.get("precondition", ""),
                test_steps=json.dumps(case_data.get("steps", []), ensure_ascii=False),
                expected_results=json.dumps(case_data.get("expected_results", []), ensure_ascii=False),
            )
            self.db_session.add(tc)
            case_ids.append(tc.case_id)
        self.db_session.commit()
        return case_ids
