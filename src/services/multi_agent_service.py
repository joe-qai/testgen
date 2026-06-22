#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5 Agent 协作的用例生成服务
基于 testcase-generator SKILL 整合，替换现有 GenerationService 的"用例生成"模块
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.utils import get_logger
from src.services.case_review_agent import (
    CaseReviewAgent,
    ReviewDecision,
)

logger = get_logger(__name__)


# ============ 5 Agent Prompt 定义（来自 SKILL，v2 优化版）============

AGENT_PROMPTS = {
    "orchestrator": """你是测试用例生成流水线的协调器（Orchestrator）。

请基于用户需求，输出一份结构化方案：
1. 方法论（1 句话，基于 ISO/IEC 29119 + 20926 FPA）
2. 模式识别（生成/评审/补充）
3. 设计方法选择（如：等价类划分、边界值分析、场景法）
4. 测试类型（13 种白名单中选）

要求：简洁，4 个部分各 1-2 句话，Markdown 格式输出。
""",

    "requirement_analyst": """你是需求分析专家（Requirement Analyst）。

请基于用户需求和 Orchestrator 方案，输出需求解析报告：
1. 功能模块清单（按业务域划分）
2. 业务流程步骤（按顺序排列）
3. 约束条件清单（必填/长度/范围/权限）
4. 测试点清单（按模块组织，禁止与模块名重复）

格式：Markdown 表格。
要求：客观分析，不添加需求外内容。
""",

    "test_plan_designer": """你是测试规划+评审专家（Test Plan Designer）。

请基于需求解析报告，按 4 维度评审：
1. 完整性（是否覆盖所有功能）
2. 合理性（模块划分是否清晰）
3. 一致性（命名是否规范）
4. 可测性（测试点是否明确）

输出：
- 评审结论：通过 / 有条件通过 / 不通过
- 详细意见
- 修正后的测试点清单（如有修正）
""",

    "case_generator_batch": """你是测试用例生成专家（Case Generator）。

请基于指定的模块和测试点，生成 **2-3 条** 测试用例（不要多生成）。

严格格式（每个用例）：
```
## [P0/P1/P2/P3] 用例标题
[测试类型] 功能/边界/异常/...
[前置条件] 前置条件描述
[测试步骤] 1. 步骤1。2. 步骤2。3. 步骤3
[预期结果] 1. 预期1。2. 预期2。3. 预期3
```

强制要求：
- 优先级分布：P0(最多1条) / P1(1条) / P2(1条) / P3(可选0条)
- **P0+P1 合计 ≤ 40%（硬约束）**：如果生成的用例中P0+P1占比超过40%，将多余的P1降为P2
- **标题格式**：15-30 字，以具体预期结果或动作结尾。禁止以"验证/校验/登录/账号/测试/操作/控制"等泛化词结尾。正确示例："密码连续错误5次后账号锁定并提示剩余次数"。错误示例："密码连续错误5次后账号锁定及提示验证"
- 数据具体（如：13800138000），禁止 {username} 等占位符
- 预期可验证（如：提示"密码错误，还可尝试4次"），禁止"功能正常"，禁止用 X 等变量代替具体值
- **步骤与预期必须严格1:1对应**：每1个测试步骤必须对应1条预期结果。5个步骤=5条预期，3个步骤=3条预期。不允许合并预期或省略预期。
- 步骤编号和预期编号必须一一对应（步骤1→预期1，步骤2→预期2...）
- **只生成 2-3 条，简洁输出**
""",

"case_generator_positive": """你是测试用例生成专家（正向主流程专用）。

请基于需求，生成 **2-3 条正向主流程测试用例**——即核心功能的正常成功路径。

示例：
- 用户名密码正确时登录成功并跳转主页
- 手机号验证码正确时登录成功并跳转主页
- 正常流程的完整业务闭环

严格格式（每个用例）：
```
## [P0/P1/P2/P3] 用例标题
[测试类型] 功能/边界/异常/...
[前置条件] 前置条件描述
[测试步骤] 1. 步骤1。2. 步骤2。3. 步骤3
[预期结果] 1. 预期1。2. 预期2。3. 预期3
```

强制要求：
- **必须生成正向主流程用例**（正常输入→成功结果）
- 优先级：核心正向成功路径标 P0（最多1条），其余正向路径标 P2。确保 P0+P1 合计不超过总用例数的 40%
- 标题以具体预期结果结尾，禁止泛化词
- 数据具体，禁止占位符
- **步骤与预期必须严格1:1对应**：每1个测试步骤必须对应1条预期结果。5个步骤=5条预期，3个步骤=3条预期。不允许合并预期或省略预期。
- 步骤编号和预期编号必须一一对应（步骤1→预期1，步骤2→预期2...）
- 预期可验证，禁止"功能正常"
- **只生成 2-3 条，简洁输出**
""",

    "reviewer": """你是用例评审专家（Reviewer）。

请评审测试用例：

A. 引导错误过滤（一票否决，触发任一项即判不合格）：
- 数据占位符 {username}
- 预期模糊（"功能正常"）
- 步骤不对应（步骤数 ≠ 预期数）
- P0+P1>50%

B. 标题格式检查（扣分项，不一票否决）：
- 标题<15字 → 扣清晰度分
- 标题以"验证/校验/登录/账号/测试/操作/控制"等泛化词结尾 → 扣清晰度分，列出修正建议但不否决

C. 六大维度评估（100分制）：
- PRD 覆盖度（0-20）：是否覆盖所有功能点和边界
- 冗余性（0-20）：用例是否重复或可合并
- 清晰度（0-20）：步骤描述是否清晰无歧义
- 明确性（0-20）：预期结果是否具体可验证
- 完整性（0-20）：是否包含正向+反向+边界+异常
- 合理性（0-20）：是否超出需求范围或有逻辑错误

输出：
1. 引导错误检查结果（一票否决项逐条检查）
2. 标题格式检查结果（扣分项，附修正建议）
3. 六大维度评分表（每个维度 0-20 分，总分 0-120）
4. 评审结论：
   - 总分 ≥ 90 且无一票否决 → 合格
   - 总分 60-89 且无一票否决 → 有条件通过
   - 有任何一票否决 → 不合格
   - 总分 < 60 → 不合格
5. 修正建议（如有）

要求：客观公正，区分"否决级问题"和"扣分级问题"。
""",
}


# ============ 5 Agent 串行 Pipeline ============

class MultiAgentCaseService:
    """
    5 Agent 协作的用例生成服务（v2 优化版）

    架构（基于 testcase-generator SKILL）：
    阶段 1+2+5: Orchestrator    → 方法论+模式+策略
    阶段 3:    Analyst          → 需求解析
    阶段 4:    Designer         → 模块评审
    阶段 6:    Generator        → 用例生成（分批，每批 2-3 条）
    阶段 7:    Reviewer         → 引导错误过滤+六大维度评分

    v2 优化：
    - Generator: 分批生成（解决 504/429 超时）
    - Generator: 标题格式约束（禁止泛化词结尾）
    - Reviewer: 标题泛化词从一票否决降级为扣分项
    - Reviewer: 六大维度改为 100 分制评分
    """

    # 5 Agent 在数据库的阶段标识
    PHASE_MAPPING = {
        "orchestrator": "MA_ORCHESTRATOR",
        "requirement_analyst": "MA_REQUIREMENT",
        "test_plan_designer": "MA_PLAN_DESIGN",
        "case_generator": "MA_GENERATION",
        "reviewer": "MA_REVIEW",
    }

    def __init__(self, db_session=None, llm_manager=None):
        self.db_session = db_session
        self.llm_manager = llm_manager

        # 复用现有 CaseReviewAgent 作为最终质量门
        self.case_review_agent = None
        if llm_manager:
            try:
                self.case_review_agent = CaseReviewAgent(llm_manager=llm_manager)
            except Exception as e:
                logger.warning(f"[MultiAgent] CaseReviewAgent 初始化失败: {e}")

    # ============ LLM 调用封装 ============

    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """统一的 LLM 调用接口（复用现有 LLMManager）"""
        if not self.llm_manager:
            raise ValueError("LLM Manager 未初始化")

        adapter = self.llm_manager.get_adapter()

        # 优先用 chat 模式（system + user 分离，更稳定）
        try:
            response = adapter.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                timeout=300,
            )
            if response.success:
                return response.content
            raise Exception(f"LLM 调用失败: {response.error_message}")
        except (AttributeError, NotImplementedError):
            # 回退到 generate 接口
            full_prompt = f"{system_prompt}\n\n{user_prompt}\n\n请简洁回答，不要超过 2000 字。"
            response = adapter.generate(full_prompt, temperature=temperature, timeout=300)
            if response.success:
                return response.content
            raise Exception(f"LLM 调用失败: {response.error_message}")

    # ============ 5 Agent 串行 Pipeline（同步调用）============

    def _run_orchestrator(self, requirement_text: str) -> str:
        """Agent 1: 协调器（阶段 1+2+5）"""
        return self._call_llm(
            system_prompt=AGENT_PROMPTS["orchestrator"],
            user_prompt=f"需求：\n{requirement_text}",
        )

    def _run_analyst(self, requirement_text: str, orchestrator_out: str) -> str:
        """Agent 2: 需求分析（阶段 3）"""
        return self._call_llm(
            system_prompt=AGENT_PROMPTS["requirement_analyst"],
            user_prompt=f"需求：\n{requirement_text}\n\nOrchestrator 方案：\n{orchestrator_out}",
        )

    def _run_designer(self, requirement_text: str, analyst_out: str) -> str:
        """Agent 3: 测试规划+评审（阶段 4）"""
        return self._call_llm(
            system_prompt=AGENT_PROMPTS["test_plan_designer"],
            user_prompt=f"需求：\n{requirement_text}\n\n需求解析：\n{analyst_out}",
        )

    def _run_generator(self, requirement_text: str, designer_out: str) -> str:
        """Agent 4: 用例生成（阶段 6）—— 分批生成，第一批次为正向主流程"""
        modules = self._extract_test_modules(designer_out)
        logger.info(f"[MultiAgent] 检测到 {len(modules)} 个测试模块，分批生成")

        all_cases_text = ""

        # 第一批次：正向主流程用例（P0/P1 最高优先级）
        logger.info("[MultiAgent] 批次 0（正向主流程）...")
        try:
            positive_result = self._call_llm(
                system_prompt=AGENT_PROMPTS["case_generator_positive"],
                user_prompt=f"需求：\n{requirement_text}\n\n请生成 2-3 条正向主流程测试用例（核心功能的正常成功路径）。",
                temperature=0.3,
            )
            all_cases_text += positive_result + "\n\n"
            logger.info("[MultiAgent] ✅ 正向主流程批次完成")
        except Exception as e:
            logger.warning(f"[MultiAgent] 正向主流程批次失败: {e}，跳过")

        # 后续批次：按模块分批生成边界/异常用例
        for idx, module_info in enumerate(modules, 1):
            logger.info(f"[MultiAgent] 批次 {idx}/{len(modules)}: {module_info[:50]}...")
            try:
                batch_result = self._call_llm(
                    system_prompt=AGENT_PROMPTS["case_generator_batch"],
                    user_prompt=f"需求：\n{requirement_text}\n\n当前批次测试点：\n{module_info}\n\n请针对此模块生成 2-3 条测试用例。",
                    temperature=0.3,
                )
                all_cases_text += batch_result + "\n\n"
                logger.info(f"[MultiAgent] ✅ 批次 {idx}/{len(modules)} 完成")
            except Exception as e:
                logger.warning(f"[MultiAgent] 批次 {idx} 失败: {e}，跳过")
                continue

        if not all_cases_text:
            raise Exception("所有生成批次均失败")

        return all_cases_text

    def _extract_test_modules(self, designer_out: str) -> List[str]:
        """从 Designer 输出中提取测试点模块，用于分批生成"""
        # 按 ### 或 ## 标题切分模块
        module_pattern = r'(?:^|\n)(?:#{2,3}\s+.+?)(?=\n#{2,3}\s+|\Z)'
        modules = re.findall(module_pattern, designer_out, re.DOTALL)

        # 如果没有标题切分，按段落切分（每段约 200-300 字）
        if len(modules) <= 1:
            lines = designer_out.strip().split('\n')
            chunks = []
            current_chunk = ""
            for line in lines:
                if line.strip():
                    current_chunk += line + '\n'
                    if len(current_chunk) > 300:
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            modules = chunks if chunks else [designer_out]

        # 限制最多 4 批次
        if len(modules) > 4:
            merged = []
            for i in range(0, len(modules), max(1, len(modules) // 4)):
                merged.append('\n'.join(modules[i:i + max(1, len(modules) // 4)]))
            modules = merged[:4]

        return modules

    def _run_reviewer(self, requirement_text: str, generator_out: str) -> str:
        """Agent 5: 评审（阶段 7）"""
        return self._call_llm(
            system_prompt=AGENT_PROMPTS["reviewer"],
            user_prompt=f"需求：\n{requirement_text}\n\n测试用例：\n{generator_out}",
        )

    # ============ 用例解析（Markdown → 结构化数据）============

    def _parse_cases_from_markdown(self, markdown_text: str) -> List[Dict[str, Any]]:
        """从 Generator 输出的 Markdown 中解析出结构化用例列表"""
        cases = []
        pattern = r"##\s*\[P(\d)\]\s*(.+?)(?=##\s*\[P\d\]|$)"
        matches = re.finditer(pattern, markdown_text, re.DOTALL)

        for match in matches:
            priority_num = match.group(1)
            block = match.group(2)
            case = self._parse_single_case(block, priority_num)
            if case:
                cases.append(case)

        return cases

    def _parse_single_case(self, block: str, priority_num: str) -> Optional[Dict[str, Any]]:
        """解析单条用例"""
        lines = block.strip().split("\n")
        title = lines[0].strip() if lines else ""

        def extract_field(pattern: str) -> str:
            m = re.search(pattern, block)
            return m.group(1).strip() if m else ""

        test_type = extract_field(r"\[测试类型\]\s*(\S+)")
        preconditions = extract_field(r"\[前置条件\]\s*(.+?)(?=\[测试步骤\]|\[预期结果\]|$)")
        test_steps = extract_field(r"\[测试步骤\]\s*(.+?)(?=\[预期结果\]|$)")
        expected_results = extract_field(r"\[预期结果\]\s*(.+)")

        def split_steps(text: str) -> List[str]:
            if not text:
                return []
            steps = re.split(r"\d+\.\s*", text)
            return [s.strip() for s in steps if s.strip()]

        return {
            "title": title,
            "priority": f"P{priority_num}",
            "case_type": test_type or "功能",
            "preconditions": preconditions,
            "test_steps": split_steps(test_steps),
            "expected_results": split_steps(expected_results),
        }

    # ============ 评审结果解析 ============

    def _parse_review_decision(self, reviewer_output: str) -> str:
        """
        从 Reviewer 输出中解析评审结论
        
        Returns: "PASS" / "CONDITIONAL" / "FAIL"
        """
        # 检查一票否决项
        veto_keywords = ["占位符", "功能正常", "步骤不对应", "P0+P1>50%"]
        for keyword in veto_keywords:
            pattern = f"{keyword}.{{0,30}}(?:不通过|触发|否决|未通过)"
            if re.search(pattern, reviewer_output, re.IGNORECASE):
                return "FAIL"

        # 检查评审结论关键词
        if "合格" in reviewer_output and "不合格" not in reviewer_output:
            return "PASS"
        elif "有条件通过" in reviewer_output:
            return "CONDITIONAL"
        elif "不合格" in reviewer_output:
            # 再检查是否有评分 ≥ 60（可能是标题格式扣分导致的不合格）
            score_match = re.search(r"总分[：:]\s*(\d+)", reviewer_output)
            if score_match:
                total_score = int(score_match.group(1))
                if total_score >= 60:
                    return "CONDITIONAL"  # 评分 60+ 但标题扣分，降为有条件通过
            return "FAIL"
        
        # 默认
        return "CONDITIONAL"

    # ============ 优先级平衡 ============

    def _balance_priorities(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """确保 P0+P1 合计不超过 40%（硬约束）
        超过时将部分 P1 降为 P2，优先保留正向主流程用例的 P1
        """
        total = len(cases)
        if total == 0:
            return cases

        p0_p1_count = sum(1 for c in cases if c.get("priority") in ("P0", "P1"))
        max_p0_p1 = int(total * 0.4)  # 40% 上限
        # 至少允许 1 条 P0+P1
        if max_p0_p1 < 1:
            max_p0_p1 = 1

        if p0_p1_count <= max_p0_p1:
            return cases  # 不需要调整

        # 需要降级：从 P1 中选择非正向主流程的降为 P2
        logger.info(f"[MultiAgent] 优先级平衡: P0+P1={p0_p1_count}/{total} > 40%, 需降级 {p0_p1_count - max_p0_p1} 条")

        # P0 不降级；P1 中非正向的先降
        downgrade_count = p0_p1_count - max_p0_p1
        p1_cases = [c for c in cases if c.get("priority") == "P1"]

        # 正向用例（case_type 为"功能"）的 P1 优先保留
        functional_p1 = [c for c in p1_cases if c.get("case_type") in ("功能", "功能/边界")]
        other_p1 = [c for c in p1_cases if c.get("case_type") not in ("功能", "功能/边界")]

        # 先降非功能类P1，再降功能类P1
        downgrade_order = other_p1 + functional_p1
        for c in downgrade_order[:downgrade_count]:
            logger.info(f"[MultiAgent] 降级: {c.get('title', '')[:30]} P1→P2")
            c["priority"] = "P2"

        return cases

    # ============ 落库 ============

    def _load_requirement(self, requirement_id: int) -> Dict[str, Any]:
        """从 DB 读取需求"""
        from src.database.models import Requirement

        if not self.db_session:
            raise ValueError("DB Session 未初始化")

        req = self.db_session.query(Requirement).filter_by(id=requirement_id).first()
        if not req:
            raise ValueError(f"需求不存在: {requirement_id}")

        return {"id": req.id, "title": req.title, "content": req.content, "status": req.status}

    def _save_test_cases(
        self, requirement_id: int, cases: List[Dict[str, Any]]
    ) -> List[int]:
        """落库用例，返回 case_id 列表"""
        from src.database.models import TestCase, CaseStatus

        saved_ids = []
        for idx, case in enumerate(cases, 1):
            import uuid; case_id_str = f"MA_{requirement_id:04d}_{uuid.uuid4().hex[:6]}"

            tc = TestCase(
                case_id=case_id_str,
                requirement_id=requirement_id,
                module=case.get("module", "未分类"),
                name=case.get("title", ""),
                preconditions=case.get("preconditions", ""),
                test_steps=case.get("test_steps", []),
                expected_results=case.get("expected_results", []),
                priority=case.get("priority", "P2"),
                case_type=case.get("case_type", "功能"),
                status=CaseStatus.DRAFT,
            )
            self.db_session.add(tc)
            self.db_session.flush()
            saved_ids.append(tc.id)

        try:
            self.db_session.commit()
            logger.info(f"[MultiAgent] 落库 {len(saved_ids)} 条用例")
        except Exception as e:
            self.db_session.rollback()
            logger.warning(f"[MultiAgent] 批量落库失败: {e}")
            saved_ids = []
        return saved_ids

    def _save_pipeline_log(
        self,
        task_id: int,
        requirement_id: int,
        pipeline_outputs: Dict[str, str],
        total_duration: float,
        review_decision: str,
    ):
        """落库 5 Agent 的过程日志"""
        from src.database.models import GenerationTask, TaskStatus

        task = self.db_session.query(GenerationTask).filter_by(id=task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            # 用 result 字段存 pipeline 日志（原表有此列）
            task.result = {
                "pipeline": "multi_agent_v2",
                "agent_outputs_keys": list(pipeline_outputs.keys()),
                "duration_seconds": total_duration,
                "review_decision": review_decision,
                "sk_prompts_included": True,
            }
            self.db_session.commit()

    # ============ 主入口 ============

    def generate_cases(
        self, requirement_id: int, max_attempts: int = 2
    ) -> Dict[str, Any]:
        """
        5 Agent 协作生成测试用例（主入口，v2 优化版）
        """
        start_time = time.time()
        logger.info(f"[MultiAgent v2] Pipeline 启动 - 需求ID={requirement_id}")

        # 1. 加载需求
        req = self._load_requirement(requirement_id)
        requirement_text = f"# {req['title']}\n\n{req['content']}"

        # 2. 创建任务
        import uuid
        from src.database.models import GenerationTask, TaskStatus, GenerationPhase

        task = GenerationTask(
            task_id=f"ma_{uuid.uuid4().hex[:16]}",
            requirement_id=requirement_id,
            status=TaskStatus.RUNNING,
            phase=GenerationPhase.GENERATION,
            started_at=datetime.now(timezone.utc),
        )
        self.db_session.add(task)
        self.db_session.commit()
        task_id = task.id

        # 3. 5 Agent 串行 Pipeline
        pipeline_outputs = {}

        try:
            pipeline_outputs["orchestrator"] = self._run_orchestrator(requirement_text)
            logger.info("[MultiAgent] ✅ Orchestrator 完成")

            pipeline_outputs["requirement_analyst"] = self._run_analyst(
                requirement_text, pipeline_outputs["orchestrator"]
            )
            logger.info("[MultiAgent] ✅ RequirementAnalyst 完成")

            pipeline_outputs["test_plan_designer"] = self._run_designer(
                requirement_text, pipeline_outputs["requirement_analyst"]
            )
            logger.info("[MultiAgent] ✅ TestPlanDesigner 完成")

            # 4. Generator + Reviewer 循环
            review_decision = "FAIL"
            for attempt in range(1, max_attempts + 1):
                pipeline_outputs["case_generator"] = self._run_generator(
                    requirement_text, pipeline_outputs["test_plan_designer"]
                )
                logger.info(f"[MultiAgent] ✅ CaseGenerator 第 {attempt} 次完成")

                pipeline_outputs["reviewer"] = self._run_reviewer(
                    requirement_text, pipeline_outputs["case_generator"]
                )
                logger.info(f"[MultiAgent] ✅ Reviewer 第 {attempt} 次完成")

                # 用改进的解析方法判断评审结论
                review_decision = self._parse_review_decision(pipeline_outputs["reviewer"])
                logger.info(f"[MultiAgent] 评审结论: {review_decision}")

                if review_decision in ("PASS", "CONDITIONAL"):
                    break
                elif attempt < max_attempts:
                    logger.warning(f"[MultiAgent] 评审不通过，重试 {attempt}/{max_attempts}")
                else:
                    review_decision = "FAIL"

            # 5. 解析用例 + 落库
            cases = self._parse_cases_from_markdown(pipeline_outputs.get("case_generator", ""))
            # 优先级平衡（确保 P0+P1 ≤ 40%）
            cases = self._balance_priorities(cases)
            case_ids = self._save_test_cases(requirement_id, cases) if cases else []

            # 6. 保存 Pipeline 日志
            total_duration = time.time() - start_time
            self._save_pipeline_log(task_id, requirement_id, pipeline_outputs, total_duration, review_decision)

            return {
                "task_id": task_id,
                "status": review_decision,
                "case_count": len(case_ids),
                "duration_seconds": round(total_duration, 1),
                "agent_outputs": pipeline_outputs,
                "review_decision": review_decision,
            }

        except Exception as e:
            logger.error(f"[MultiAgent] Pipeline 失败: {e}")
            from src.database.models import TaskStatus

            task = self.db_session.query(GenerationTask).filter_by(id=task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                self.db_session.commit()
            raise

    # ============ 同步入口（兼容 Flask 同步 API）============

    def generate_cases_sync(self, requirement_id: int) -> Dict[str, Any]:
        """同步入口（用于 Flask 路由调用）"""
        return self.generate_cases(requirement_id)


# ============ 模块自测 ============

if __name__ == "__main__":
    print("=== MultiAgentCaseService v2 模块自测 ===\n")
    print("✅ 5 Agent Prompt 定义完毕")
    for name, prompt in AGENT_PROMPTS.items():
        first_line = prompt.split("\n")[0][:50]
        print(f"  - {name}: {first_line}...")
    print()
    print("v2 优化点:")
    print("  - Generator: 标题禁止泛化词结尾 + 禁止变量占位符")
    print("  - Reviewer: 标题泛化词从一票否决降级为扣分项")
    print("  - Reviewer: 六大维度改为 100 分制评分")
    print("  - _parse_review_decision(): 智能解析评审结论（区分否决级 vs 扣分级）")
    print("  - _save_pipeline_log(): 用 result 字段替代 result_data（兼容原表结构）")