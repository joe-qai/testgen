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
from datetime import datetime, timezone
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
    requirement_review_output: str  # 6维度需求评审HTML报告

    # Phase 2: 生成
    cases_raw: str  # LLM 原始输出
    cases: Annotated[list, append_list]  # 解析后的结构化用例
    review_output: str
    review_decision: str  # APPROVE / CONDITIONAL / REJECT
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
    # ---- 6维度需求评审专家 ----
    "review_pm": """你是拥有10年产品经验的PM。请从产品完整性角度分析以下需求：
1. 核心功能是否完整（是否有遗漏的关键功能点）
2. 用户场景是否完整（正常流/异常流/边界流）
3. 业务规则是否明确（有无模糊或矛盾之处）
请给出：完整性评分(0-100)、主要发现(3-5条)、改进建议。纯文本输出。""",
    "review_qa": """你是拥有8年经验的测试主管。请从可测试性角度分析以下需求：
1. 测试点是否可提取（需求描述是否足以设计测试用例）
2. 输入条件是否明确（边界值/枚举值/范围是否清晰）
3. 预期结果是否可验证（是否有明确的验收标准）
请给出：可测性评分(0-100)、主要发现(3-5条)、改进建议。纯文本输出。""",
    "review_cto": """你是拥有12年经验的CTO。请从技术可行性角度分析以下需求：
1. 技术风险点（依赖/性能/安全性）
2. 实现复杂度评估（高/中/低）
3. 是否有技术盲区（未考虑的技术限制）
请给出：可行性评分(0-100)、主要风险(3-5条)、技术建议。纯文本输出。""",
    "review_dev": """你是刚入职的新手开发者。请用朴素的语言分析以下需求：
1. 哪些地方容易理解错误（歧义表达）
2. 哪些地方没有讲清楚（缺少细节）
3. 作为开发者你需要知道什么但需求没说
请给出：清晰度评分(0-100)、主要歧义(3-5条)、需要澄清的问题。纯文本输出。""",
    "review_code": """你是代码审查专家。请从一致性角度分析以下需求：
1. 术语使用是否统一（同一概念是否用不同名称）
2. 规格是否自洽（前后是否有矛盾）
3. 与行业标准是否一致（命名/分类是否符合惯例）
请给出：一致性评分(0-100)、主要问题(3-5条)、修正建议。纯文本输出。""",
    "review_architect": """你是拥有15年经验的业务架构师。请从逻辑性角度分析以下需求：
1. 业务流程是否闭环（有没有断点或死循环）
2. 模块划分是否合理（职责是否清晰）
3. 依赖关系是否合理（是否存在循环依赖）
请给出：逻辑性评分(0-100)、主要问题(3-5条)、架构建议。纯文本输出。""",
}


# ============ LLM 调用封装 ============


def call_llm(
    llm_manager, system_prompt: str, user_prompt: str, temperature: float = 0.3
) -> str:
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
        response = adapter.generate(
            full_prompt, temperature=temperature, timeout=120
        )
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


def requirement_review_node(state: TestGenState) -> dict:
    """6维度需求评审：生成HTML分析报告"""
    from src.utils import get_logger

    logger = get_logger("langgraph_testgen")
    logger.info("[LangGraph] 📊 6维度需求评审启动")

    llm_manager = _current_llm_manager
    requirement_text = state['requirement_text']

    # 六维度并行调用（控制 rate limit）
    dimensions = [
        ("完整性", "review_pm", "10年产品经理", "#FF6B6B"),
        ("可测性", "review_qa", "8年测试主管", "#4ECDC4"),
        ("可行性", "review_cto", "12年CTO", "#45B7D1"),
        ("清晰度", "review_dev", "新手开发者", "#96CEB4"),
        ("一致性", "review_code", "代码审查专家", "#FFEAA7"),
        ("逻辑性", "review_architect", "15年业务架构师", "#DDA0DD"),
    ]

    # 使用线程池并行调用，每个维度独立超时，总耗时约等于单个最慢调用
    import concurrent.futures as _cfx
    results = []
    call_errors = {}

    def _call_one(dim):
        name, prompt_key, persona, color = dim
        try:
            output = call_llm(
                llm_manager,
                AGENT_PROMPTS[prompt_key],
                requirement_text,
                temperature=0.3,
            )
            import re as _re
            score_match = _re.search(r'(\d{1,3})\s*分', output)
            score = int(score_match.group(1)) if score_match else 50
            return {"name": name, "persona": persona, "color": color,
                    "score": min(100, max(0, score)), "content": output, "error": None}
        except Exception as e:
            return {"name": name, "persona": persona, "color": color,
                    "score": 0, "content": f"评审失败: {e}", "error": str(e)}

    with _cfx.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_call_one, d): d[0] for d in dimensions}
        for future in _cfx.as_completed(futures):
            results.append(future.result())

    # 按原始顺序排序
    order = {d[0]: i for i, d in enumerate(dimensions)}
    results.sort(key=lambda r: order.get(r["name"], 99))
    call_errors = {r["name"]: r["content"] for r in results if r.get("error")}

    # 合成综合评分
    total_score = sum(r["score"] for r in results) // len(results) if results else 0
    verdict = "优秀" if total_score >= 80 else "良好" if total_score >= 60 else "需改进"

    html = _generate_review_html(requirement_text, results, total_score, verdict)
    logger.info(f"[LangGraph] ✅ 6维度需求评审完成，综合评分={total_score}，verdict={verdict}")
    return {"requirement_review_output": html}


def _md_to_html(text: str) -> str:
    """简单 Markdown → HTML（仅处理加粗、列表、标题、换行）"""
    import re as _re
    # 转义 HTML 特殊字符（保留后续 markdown 标记）
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 标题
    text = _re.sub(r"^### (.+)$", r"<strong>\1</strong>", text, flags=_re.MULTILINE)
    text = _re.sub(r"^## (.+)$", r"<strong style='font-size:14px;'>\1</strong>", text, flags=_re.MULTILINE)
    # 加粗
    text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # 有序/无序列表
    lines = text.split("\n")
    result = []
    in_list = False
    for line in lines:
        m_bullet = _re.match(r"^[\s]*[-*] (.+)$", line)
        m_ol = _re.match(r"^\d+\.\s+(.+)$", line)
        if m_bullet:
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append(f'<li>{m_bullet.group(1)}</li>')
        elif m_ol:
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append(f'<li>{m_ol.group(1)}</li>')
        else:
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append(line if line.strip() else "<br>")
    if in_list:
        result.append("</ul>")
    return "\n".join(result)


def _generate_review_html(
    requirement_text: str,
    results: List[Dict],
    total_score: int,
    verdict: str,
) -> str:
    """生成六维度需求评审HTML报告 — 左右两栏布局"""
    color_map = {
        "优秀": "#22c55e",
        "良好": "#3b82f6",
        "需改进": "#f59e0b",
    }
    primary_color = color_map.get(verdict, "#6b7280")

    rows = []
    for r in results:
        score_color = (
            "#22c55e" if r["score"] >= 80
            else "#3b82f6" if r["score"] >= 60
            else "#f59e0b" if r["score"] >= 40
            else "#ef4444"
        )
        # 简单 Markdown 转 HTML
        content_html = _md_to_html(r["content"])
        rows.append(f"""
        <div class="dim-row">
            <div class="dim-left" style="border-left-color:{r['color']};">
                <div class="dim-label">{r['name']}</div>
                <div class="dim-persona">{r['persona']}</div>
                <div class="dim-score-val" style="color:{score_color};">{r['score']}分</div>
                <div class="dim-score-bar"><div class="dim-score-fill" style="width:{r['score']}%;background:{score_color};"></div></div>
            </div>
            <div class="dim-right">{content_html}</div>
        </div>""")

    text_escaped = requirement_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>需求评审报告</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'PingFang SC','Microsoft YaHei','Segoe UI',sans-serif; background:#0b1120; color:#e2e8f0; padding:20px; line-height:1.7; }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  .hdr {{ text-align:center; padding:24px 0 20px; border-bottom:1px solid #1e2d4a; margin-bottom:20px; }}
  .hdr h1 {{ font-size:22px; color:#f1f5f9; letter-spacing:1px; }}
  .hdr .sub {{ color:#64748b; font-size:12px; margin-top:4px; }}
  .score-area {{ display:flex; align-items:center; justify-content:center; gap:20px; margin:16px 0 20px; }}
  .circle {{ width:88px; height:88px; border-radius:50%; background:conic-gradient({primary_color} {total_score*3.6}deg, #1e2d4a 0); display:flex; align-items:center; justify-content:center; position:relative; flex-shrink:0; }}
  .circle::before {{ content:''; position:absolute; width:72px; height:72px; border-radius:50%; background:#0b1120; }}
  .circle span {{ position:relative; z-index:1; font-size:26px; font-weight:800; color:{primary_color}; }}
  .score-meta {{ font-size:13px; color:#94a3b8; }}
  .score-meta strong {{ color:#f1f5f9; font-size:16px; display:block; margin-bottom:2px; }}
  .req-box {{ background:#1e2d4a; border-radius:8px; padding:12px 16px; font-size:13px; color:#94a3b8; margin-bottom:20px; white-space:pre-wrap; word-break:break-all; max-height:120px; overflow-y:auto; }}
  .req-box strong {{ color:#f1f5f9; }}
  .sec-title {{ font-size:14px; color:#f1f5f9; font-weight:600; margin-bottom:12px; padding-left:10px; border-left:3px solid #3b82f6; }}
  .dim-row {{ display:flex; gap:0; margin-bottom:10px; border-radius:10px; overflow:hidden; background:#1e2d4a; border:1px solid #253554; }}
  .dim-left {{ width:160px; min-width:160px; padding:14px 12px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; border-left:4px solid; background:#0f1a2e; text-align:center; }}
  .dim-label {{ font-size:15px; font-weight:700; color:#f8fafc; }}
  .dim-persona {{ font-size:10px; color:#64748b; background:#1e2d4a; padding:2px 8px; border-radius:10px; }}
  .dim-score-val {{ font-size:22px; font-weight:800; }}
  .dim-score-bar {{ width:80%; height:4px; background:#253554; border-radius:2px; overflow:hidden; }}
  .dim-score-fill {{ height:100%; border-radius:2px; transition:width 0.6s; }}
  .dim-right {{ flex:1; padding:14px 16px; font-size:13px; color:#cbd5e1; white-space:pre-wrap; word-break:break-word; }}
  .ft {{ text-align:center; color:#334155; font-size:11px; margin-top:20px; padding-top:12px; border-top:1px solid #1e2d4a; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>📋 需求六维度智能评审报告</h1>
    <div class="sub">基于多维度专家视角的综合分析</div>
  </div>
  <div class="score-area">
    <div class="circle"><span>{total_score}</span></div>
    <div class="score-meta">
      <strong>综合评分：{verdict}</strong>
      由6位不同角色专家独立评审后合成
    </div>
  </div>
  <div class="req-box"><strong>需求原文：</strong>{text_escaped}</div>
  <div class="sec-title">🧠 六维度专家分析详情</div>
  {''.join(rows)}
  <div class="ft">TestGen AI · 智能需求评审系统 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
</body></html>"""
    return html


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
    conclusion_detail = ""
    if "通过" in output and "不通过" not in output:
        conclusion = "PASS"
    elif "不通过" in output:
        conclusion = "FAIL"
    # 提取评审详情（取前200字）
    conclusion_detail = output[:200]

    logger.info(
        f"[LangGraph] ✅ Designer 完成，结论={conclusion}, 详情={conclusion_detail[:50]}"
    )
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


def build_testgen_graph(
    checkpoint_path: str = None,
):
    """构建 TestGen LangGraph StateGraph"""
    import tempfile as _tf

    # 如果没有指定路径，使用临时文件（每个实例独立 checkpoint）
    if checkpoint_path is None:
        fd, checkpoint_path = _tf.mkstemp(suffix='.db', prefix='lg_checkpoint_')
        os.close(fd)

    # Checkpoint
    conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    builder = StateGraph(TestGenState)

    # 添加 node
    builder.add_node("requirement_review", requirement_review_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("designer", designer_node)
    builder.add_node("generator", generator_node)
    builder.add_node("reviewer", reviewer_node)

    # 线性边
    builder.add_edge(START, "requirement_review")
    builder.add_edge("requirement_review", "orchestrator")
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
    pattern = r"##\s*\[(P[0-3])\]\s*(.+?)(?=\n##\s*\[P|\Z)"
    blocks = re.findall(pattern, markdown_text, re.DOTALL)

    if not blocks:
        # 备用模式：匹配 ### 或 ** 格式
        pattern2 = r"(?:##|###|\*\*)\s*\[(P[0-3])\]\s*(.+?)(?=(?:##|###|\*\*)\s*\[P|\Z)"
        blocks = re.findall(pattern2, markdown_text, re.DOTALL)

    if not blocks:
        # 第三种：匹配任何包含 P0/P1/P2/P3 的标题行
        lines = markdown_text.split("\n")
        current_case = None
        current_text = []
        for line in lines:
            m = re.match(r"(?:##|###)\s*\[(P[0-3])\]\s*(.+)", line)
            if m:
                if current_case:
                    case = _parse_single_case(
                        "\n".join(current_text), current_case[0]
                    )
                    if case:
                        raw = current_case[1].strip()
                        case["title"] = (
                            raw
                            if raw.startswith(f"[{current_case[0]}]")
                            else f"[{current_case[0]}] {raw}"
                        )
                        cases.append(case)
                current_case = (m.group(1), m.group(2))
                current_text = [line]
            elif current_case:
                current_text.append(line)
        if current_case:
            case = _parse_single_case("\n".join(current_text), current_case[0])
            if case:
                raw = current_case[1].strip()
                case["title"] = (
                    raw
                    if raw.startswith(f"[{current_case[0]}]")
                    else f"[{current_case[0]}] {raw}"
                )
                cases.append(case)
        return cases

    for priority, block_content in blocks:
        title = block_content.split("\n")[0].strip()
        case = _parse_single_case(block_content, priority)
        if case:
            # 避免重复优先级前缀
            raw_title = title.strip()
            if raw_title.startswith(f"[{priority}]"):
                case["title"] = raw_title
            else:
                case["title"] = f"[{priority}] {raw_title}"
            cases.append(case)

    return cases


def _parse_single_case(
    block: str, priority_num: str
) -> Optional[Dict[str, Any]]:
    """解析单条用例"""

    def extract_field(pattern: str) -> str:
        m = re.search(pattern, block, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    test_type = extract_field(r"\[测试类型\]\s*(.+)")
    precondition = extract_field(r"\[前置条件\]\s*(.+)")
    steps_text = extract_field(r"\[测试步骤\]\s*(.+?)(?=\[预期结果\])")
    expected_text = extract_field(r"\[预期结果\]\s*(.+)")

    steps = [s.strip() for s in re.split(r"\d+\.\s*", steps_text) if s.strip()]
    expected = [
        e.strip() for e in re.split(r"\d+\.\s*", expected_text) if e.strip()
    ]

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
    score_match = re.search(r"总分[：:]\s*(\d+)", review_output)
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

    def __init__(self, db_session=None, llm_manager=None, checkpoint_path=None):
        self.db_session = db_session
        self.llm_manager = llm_manager
        self.graph, self.conn = build_testgen_graph(checkpoint_path)

    def generate_cases(
        self, requirement_id: int, max_attempts: int = 2
    ) -> Dict[str, Any]:
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
        from src.database.models import (
            GenerationTask,
            TaskStatus,
            GenerationPhase,
        )

        task = GenerationTask(
            task_id=f"lg_{uuid.uuid4().hex[:16]}",
            requirement_id=requirement_id,
            status=TaskStatus.RUNNING,
            phase=GenerationPhase.GENERATION,
            started_at=datetime.now(timezone.utc),
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
            "orchestrator_output": "",
            "analyst_output": "",
            "modules": [],
            "rules": [],
            "test_points": [],
            "designer_output": "",
            "review_conclusion": "",
            "requirement_review_output": "",
            "cases_raw": "",
            "cases": [],
            "review_output": "",
            "review_decision": "",
            "retry_count": 0,
            "task_id": task.task_id,
            "case_ids": [],
            "duration_seconds": 0,
            "error": "",
        }

        try:
            # Phase 1: 分析+策略（interrupt 在 generator 前）
            logger.info(f"[LangGraph] Phase 1 启动 - 需求ID={requirement_id}")
            result = self.graph.invoke(initial_state, config=config)

            # 检查 Designer 结论
            designer_conclusion = result.get(
                "review_conclusion", "CONDITIONAL"
            )
            designer_output = result.get("designer_output", "")
            logger.info(
                f"[LangGraph] Phase 1 完成，Designer结论={designer_conclusion}"
            )

            # FAIL 时终止流程，返回失败原因
            if designer_conclusion == "FAIL":
                logger.warning(
                    f"[LangGraph] Designer FAIL，终止生成。详情: {designer_output[:200]}"
                )
                task = (
                    self.db_session.query(GenerationTask)
                    .filter_by(task_id=task.task_id)
                    .first()
                )
                if task:
                    task.status = TaskStatus.FAILED
                    task.error_message = (
                        f"Designer评审不通过: {designer_output[:500]}"
                    )
                    self.db_session.commit()
                return {
                    "task_id": task.task_id,
                    "status": "FAILED",
                    "error": "Designer评审不通过，请修改需求后重试",
                    "designer_conclusion": designer_conclusion,
                    "designer_detail": designer_output[:500],
                    "case_count": 0,
                    "duration_seconds": round(time.time() - start_time, 1),
                }

            # Phase 2: 生成+评审（自动继续）
            logger.info("[LangGraph] 继续 Phase 2")
            result = self.graph.invoke(
                Command(resume={"retry_count": result.get("retry_count", 0)}),
                config=config,
            )

            # 4. 不自动入库 — 先返回用例数据，等用户确认后再入库
            cases = result.get("cases", [])

            # 5. 更新任务状态为待确认
            total_duration = time.time() - start_time
            task = (
                self.db_session.query(GenerationTask)
                .filter_by(task_id=task.task_id)
                .first()
            )
            if task:
                task.status = (
                    TaskStatus.COMPLETED
                )  # Pipeline完成，但用例待人工确认
                task.completed_at = datetime.now(timezone.utc)
                self.db_session.commit()

            return {
                "task_id": task.task_id,
                "status": result.get("review_decision", "UNKNOWN"),
                "case_count": len(cases),
                "duration_seconds": round(total_duration, 1),
                "review_decision": result.get("review_decision", ""),
                # 每个node的输出摘要
                "orchestrator_summary": result.get("orchestrator_output", "")[
                    :300
                ],
                "analyst_summary": result.get("analyst_output", "")[:300],
                "designer_summary": result.get("designer_output", "")[:300],
                "generator_summary": result.get("cases_raw", "")[:300],
                "reviewer_summary": result.get("review_output", "")[:300],
                # 返回完整用例数据，前端显示后用户确认再入库
                "cases_preview": cases,
                "need_confirm": True,  # 标记需要人工确认入库
            }

        except Exception as e:
            logger.error(f"[LangGraph] Pipeline 失败: {e}")
            task = (
                self.db_session.query(GenerationTask)
                .filter_by(task_id=task.task_id)
                .first()
            )
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

        req = (
            self.db_session.query(Requirement)
            .filter_by(id=requirement_id)
            .first()
        )
        if not req:
            raise ValueError(f"需求不存在: {requirement_id}")
        return {"title": req.title, "content": req.content}

    def _save_test_cases(
        self, requirement_id: int, cases: List[Dict]
    ) -> List[str]:
        """保存测试用例到数据库"""
        from src.database.models import TestCase

        case_ids = []
        for case_data in cases:
            tc = TestCase(
                requirement_id=requirement_id,
                case_id=case_data.get(
                    "case_id", f"TC_LG_{uuid.uuid4().hex[:8]}"
                ),
                name=case_data.get(
                    "title", ""
                ),  # DB field is 'name', not 'title'
                module=case_data.get(
                    "module", case_data.get("test_type", "未分类")
                ),  # module is required
                priority=case_data.get("priority", "P2"),
                case_type=case_data.get("test_type", ""),
                preconditions=case_data.get("precondition", ""),
                test_steps=json.dumps(
                    case_data.get("steps", []), ensure_ascii=False
                ),
                expected_results=json.dumps(
                    case_data.get("expected_results", []), ensure_ascii=False
                ),
                status=2,  # CaseStatus.PENDING_REVIEW
            )
            self.db_session.add(tc)
            case_ids.append(tc.case_id)
        self.db_session.commit()
        return case_ids

    def confirm_and_save_cases(
        self, requirement_id: int, cases: List[Dict]
    ) -> Dict[str, Any]:
        """人工确认后入库用例"""
        # 用更长的ID避免碰撞
        for case_data in cases:
            if not case_data.get("case_id"):
                case_data["case_id"] = f"TC_LG_{uuid.uuid4().hex[:12]}"
        case_ids = self._save_test_cases(requirement_id, cases)
        return {
            "saved_count": len(case_ids),
            "case_ids": case_ids,
        }
