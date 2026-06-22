#!/usr/bin/env python3
"""
TestGen AutoGen GroupChat 集成模块
===================================
基于前半周源码阅读结论，将串行 Pipeline 升级为 AutoGen SelectorGroupChat。

核心设计决策：
1. 使用 SelectorGroupChat（非 Swarm/GraphFlow）—— Pipeline 是确定性的
2. selector_func 精确控制调度—— 零 Token 开销
3. 分 Phase 1/Phase 2 两个 Team—— 人机回路在中间
4. 终止条件组合：TextMentionTermination | FunctionalTermination | MaxMessageTermination | TimeoutTermination

与现有 generation_service.py 的关系：
- 本模块是替代方案，通过 Flask 路由切换
- 保留 generation_service.py 作为 fallback
"""

import asyncio
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import (
    FunctionalTermination,
    MaxMessageTermination,
    SourceMatchTermination,
    TextMentionTermination,
    TimeoutTermination,
)
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.database.models import TestCase
from src.utils import get_logger

logger = get_logger(__name__)

# ==================== 提供商 model_info 映射 ====================

PROVIDER_MODEL_INFO = {
    "openai": {"vision": True, "function_calling": True, "json_output": True, "structured_output": True, "family": "openai"},
    "qwen": {"vision": True, "function_calling": True, "json_output": True, "structured_output": False, "family": "qwen"},
    "deepseek": {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "deepseek"},
    "kimi": {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "moonshot"},
    "zhipu": {"vision": True, "function_calling": True, "json_output": True, "structured_output": False, "family": "zhipu"},
    "minimax": {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "minimax"},
    "iflow": {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "unknown"},
    "uniaix": {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "unknown"},
}

DEFAULT_MODEL_INFO = {"vision": False, "function_calling": True, "json_output": True, "structured_output": False, "family": "unknown"}

# ==================== Agent Prompts ====================

ANALYST_SYSTEM = """你是一位资深需求分析师。你的任务是分析软件需求文档，提取测试点和业务规则。

输出格式（严格 JSON）：
{
  "modules": [
    {"name": "模块名", "description": "模块描述", "test_points": ["测试点1", "测试点2"]}
  ],
  "business_rules": [
    {"content": "规则内容", "type": "规则类型"}
  ],
  "risks": [
    {"content": "风险内容", "severity": "High/Medium/Low"}
  ]
}

要求：
1. 每个模块 3-8 个测试点
2. 标注风险等级
3. 只输出 JSON，不要其他内容"""

PLAN_DESIGNER_SYSTEM = """你是一位测试策略设计师。基于需求分析结果，设计测试策略。

输出格式（严格 JSON）：
{
  "strategy": "测试策略概述",
  "items": [
    {
      "title": "测试项名称",
      "module": "所属模块",
      "priority": "P0/P1/P2",
      "points": ["测试点1", "测试点2"],
      "approach": "测试方法（等价类/边界值/错误推测等）"
    }
  ],
  "priority_balance": "P0≤20%, P1≤20%, P2+P3≥60%"
}

要求：
1. P0 必须包含正向主流程
2. 每个 item 2-5 个测试点
3. 只输出 JSON"""

GENERATOR_SYSTEM = """你是一位测试用例生成专家。根据测试策略逐项生成测试用例。

输出格式（每条用例）：
## TC-{id} [{priority}] {type} - {title}
- 模块: {module}
- 前置条件: {preconditions}
- 测试步骤:
  1. {step1}
  2. {step2}
  ...
- 预期结果:
  1. {expected1}
  2. {expected2}
  ...

要求：
1. 步骤可执行，预期可验证
2. type 标注正向/异常/边界
3. 步骤和预期一一对应
4. 不使用占位符（如XXX、待确认）
5. 每个测试项生成 3-8 条用例
6. 说 APPROVE 表示生成完成"""

REVIEWER_SYSTEM = """你是一位测试用例评审专家。评审生成的测试用例。

评审维度（每项 0-10 分）：
1. 完整性：步骤和预期是否完整
2. 准确性：是否正确反映需求
3. 可执行性：步骤是否可操作
4. 可验证性：预期是否可判断通过/失败

输出格式：
## 评审结论: APPROVE / NEEDS_REVIEW / REJECT

### 评分
- 完整性: {score}/10
- 准确性: {score}/10
- 可执行性: {score}/10
- 可验证性: {score}/10
- 总分: {total}/40

### 问题列表
1. {问题描述}

### 建议
1. {改进建议}

规则：
- 总分 ≥ 30 且无严重问题 → APPROVE
- 总分 20-29 → NEEDS_REVIEW
- 总分 < 20 或有严重问题 → REJECT
- 评审时不要过度要求，合格即可通过"""


# ==================== selector_func ====================

def phase1_selector(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> str | None:
    """Phase 1: Analyst → PlanDesigner，然后暂停"""
    if len(messages) <= 1:
        return "Analyst"
    last = messages[-1]
    if last.source == "Analyst":
        return "PlanDesigner"
    # PlanDesigner 说完 → 返回 None（由 SourceMatchTermination 触发暂停）
    return None


def phase2_selector(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> str | None:
    """Phase 2: Generator → Reviewer，REJECT 回到 Generator"""
    if len(messages) <= 1:
        return "Generator"
    last = messages[-1]
    if last.source == "Generator":
        return "Reviewer"
    if last.source == "Reviewer":
        # 检查评审结论
        text = last.to_model_text() if hasattr(last, 'to_model_text') else str(last)
        if "REJECT" in text.upper():
            return "Generator"  # 回去重生成
        # APPROVE 或 NEEDS_REVIEW → 结束（由 TextMatchTermination 触发）
        return None
    return None


# ==================== 自定义终止条件 ====================

class MaxRejectionTermination:
    """REJECT 次数上限终止条件"""

    def __init__(self, max_rejections: int = 2):
        self._max = max_rejections
        self._count = 0

    def check(self, messages: Sequence) -> bool:
        for msg in reversed(messages):
            if hasattr(msg, 'source') and msg.source == "Reviewer":
                text = msg.to_model_text() if hasattr(msg, 'to_model_text') else str(msg)
                if "REJECT" in text.upper():
                    self._count += 1
                    if self._count >= self._max:
                        return True
                break
        return False


# ==================== 核心服务 ====================

@dataclass
class AutogenTask:
    """AutoGen 生成任务"""
    task_id: str
    requirement_id: int
    requirement_title: str = ""
    status: int = 0  # 0=待运行, 1=运行中, 2=完成, 3=失败
    progress: float = 0.0
    message: str = ""
    phase: str = ""  # "phase1" / "phase2" / "complete"
    cases: List[Dict] = field(default_factory=list)
    analysis_data: Optional[Dict] = None
    plan_data: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration: float = 0.0
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutogenGroupChatService:
    """AutoGen GroupChat 集成服务"""

    def __init__(self, db_session=None, socketio=None, llm_manager=None):
        self.db_session = db_session
        self.socketio = socketio  # Flask-SocketIO 实例，用于流式推送
        self.llm_manager = llm_manager  # LLMManager 实例，用于动态获取 LLM 配置
        self._tasks: Dict[str, AutogenTask] = {}
        self._lock = threading.Lock()
        self._rejection_counts: Dict[str, int] = {}

    def _create_model_client(self) -> OpenAIChatCompletionClient:
        """从 LLMManager 动态获取默认配置创建 AutoGen 模型客户端"""
        if not self.llm_manager:
            raise RuntimeError("LLMManager 未初始化，无法创建模型客户端")

        config_info = self.llm_manager.get_config_info()
        if not config_info:
            raise RuntimeError("无可用 LLM 配置，请先在 AI 配置中添加模型")

        provider = config_info.get("provider", "").lower()
        model_id = config_info.get("model_id", "")
        base_url = config_info.get("base_url", "")

        # 从适配器获取 api_key（config_info 中未包含，需从 adapter 实例读取）
        adapter = self.llm_manager.get_adapter()
        api_key = getattr(adapter, "api_key", "")

        # 根据提供商动态构建 model_info
        model_info = PROVIDER_MODEL_INFO.get(provider, DEFAULT_MODEL_INFO)

        logger.info(f"[AutoGen] 动态获取 LLM 配置: provider={provider}, model={model_id}, base_url={base_url}")

        return OpenAIChatCompletionClient(
            model=model_id,
            base_url=base_url,
            api_key=api_key,
            model_info=model_info,
        )

    def _get_requirement(self, requirement_id: int) -> Optional[Any]:
        if not self.db_session:
            return None
        from src.database.models import Requirement
        return self.db_session.query(Requirement).get(requirement_id)

    def _emit(self, task_id: str, event_name: str, data: Dict):
        """推送 SocketIO 事件到前端"""
        if self.socketio:
            try:
                self.socketio.emit(event_name, {"task_id": task_id, **data}, namespace="/progress")
            except Exception as e:
                logger.info(f"[SocketIO] emit 失败: {e}")

    def create_task(self, requirement_id: int) -> str:
        import uuid
        task_id = f"ag_{uuid.uuid4().hex[:12]}"
        from datetime import datetime
        task = AutogenTask(
            task_id=task_id,
            requirement_id=requirement_id,
            created_at=datetime.utcnow().isoformat(),
            status=0,
            message="任务已创建",
        )
        with self._lock:
            self._tasks[task_id] = task
        return task_id

    def get_task(self, task_id: str) -> Optional[AutogenTask]:
        return self._tasks.get(task_id)

    async def run_generation(self, task_id: str, requirement_id: int):
        """完整的两阶段生成流程"""
        from datetime import datetime
        task = self._tasks.get(task_id)
        if not task:
            return

        start_time = time.time()
        task.status = 1
        task.started_at = datetime.utcnow().isoformat()

        try:
            requirement = self._get_requirement(requirement_id)
            if not requirement:
                task.status = 3
                task.error_message = "需求不存在"
                return

            task.requirement_title = requirement.title
            requirement_text = requirement.content

            # ========== Phase 1: 分析 + 策略 ==========
            task.phase = "phase1"
            task.progress = 10.0
            task.message = "📋 Phase 1: 需求分析 + 策略设计"
            task.updated_at = datetime.utcnow().isoformat()
            self._emit(task_id, "progress", {"phase": task.phase, "progress": task.progress, "message": task.message})

            phase1_result = await self._run_phase1(requirement_text)
            if not phase1_result:
                task.status = 3
                task.error_message = "Phase 1 失败"
                return

            task.analysis_data = phase1_result.get("analysis")
            task.plan_data = phase1_result.get("plan")
            task.progress = 40.0
            task.message = "✅ Phase 1 完成，进入 Phase 2"
            task.updated_at = datetime.utcnow().isoformat()
            self._emit(task_id, "progress", {"phase": task.phase, "progress": task.progress, "message": task.message})

            # ========== Phase 2: 生成 + 评审 ==========
            task.phase = "phase2"
            plan_text = json.dumps(phase1_result.get("plan", {}), ensure_ascii=False)
            combined_task = f"需求内容：\n{requirement_text}\n\n测试策略：\n{plan_text}\n\n请根据以上策略逐项生成测试用例。"

            phase2_result = await self._run_phase2(combined_task)
            if not phase2_result:
                task.status = 3
                task.error_message = "Phase 2 失败"
                return

            # 解析用例
            cases = self._parse_cases(phase2_result)
            task.cases = cases
            task.case_count = len(cases) if hasattr(task, 'case_count') else len(cases)

            # 入库
            if self.db_session and cases:
                saved = self._save_cases(requirement_id, cases)
                task.message = f"✅ 生成完成！{len(cases)} 条用例，{saved} 条入库"
            else:
                task.message = f"✅ 生成完成！{len(cases)} 条用例"

            task.progress = 100.0
            self._emit(task_id, "complete", {"phase": "complete", "progress": 100, "cases": len(task.cases), "message": task.message})
            task.status = 2
            task.phase = "complete"
            task.completed_at = datetime.utcnow().isoformat()
            task.duration = time.time() - start_time

        except Exception as e:
            task.status = 3
            task.error_message = str(e)[:500]
            self._emit(task_id, "error", {"error": task.error_message[:200]})
            logger.info(f"[AutogenGroupChat] 任务失败: {e}")

    async def _run_phase1(self, requirement_text: str) -> Optional[Dict]:
        """Phase 1: Analyst → PlanDesigner"""
        model_client = self._create_model_client()

        analyst = AssistantAgent(
            name="Analyst",
            model_client=model_client,
            system_message=ANALYST_SYSTEM,
        )
        plan_designer = AssistantAgent(
            name="PlanDesigner",
            model_client=model_client,
            system_message=PLAN_DESIGNER_SYSTEM,
        )

        termination = SourceMatchTermination(sources=["PlanDesigner"]) | MaxMessageTermination(6)

        team = SelectorGroupChat(
            participants=[analyst, plan_designer],
            model_client=model_client,
            selector_func=phase1_selector,
            termination_condition=termination,
        )

        try:
            result = await team.run(task=f"请分析以下需求：\n\n{requirement_text}")
            # 提取结果
            analysis_text = ""
            plan_text = ""
            for msg in result.messages:
                if hasattr(msg, 'source'):
                    if msg.source == "Analyst":
                        analysis_text = msg.to_model_text() if hasattr(msg, 'to_model_text') else str(msg)
                    elif msg.source == "PlanDesigner":
                        plan_text = msg.to_model_text() if hasattr(msg, 'to_model_text') else str(msg)

            # 解析 JSON
            analysis = self._extract_json(analysis_text)
            plan = self._extract_json(plan_text)

            return {"analysis": analysis or {"raw": analysis_text}, "plan": plan or {"raw": plan_text}}

        except Exception as e:
            logger.info(f"[Phase1] 失败: {e}")
            return None

    async def _run_phase2(self, combined_task: str) -> Optional[str]:
        """Phase 2: Generator → Reviewer（可能循环）"""
        model_client = self._create_model_client()

        generator = AssistantAgent(
            name="Generator",
            model_client=model_client,
            system_message=GENERATOR_SYSTEM,
        )
        reviewer = AssistantAgent(
            name="Reviewer",
            model_client=model_client,
            system_message=REVIEWER_SYSTEM,
        )

        termination = (
            TextMentionTermination("APPROVE", sources=["Reviewer"])
            | MaxMessageTermination(10)
            | TimeoutTermination(600)
        )

        team = SelectorGroupChat(
            participants=[generator, reviewer],
            model_client=model_client,
            selector_func=phase2_selector,
            termination_condition=termination,
        )

        try:
            result = await team.run(task=combined_task)
            # 提取 Generator 的输出
            for msg in reversed(result.messages):
                if hasattr(msg, 'source') and msg.source == "Generator":
                    return msg.to_model_text() if hasattr(msg, 'to_model_text') else str(msg)
            return None
        except Exception as e:
            logger.info(f"[Phase2] 失败: {e}")
            return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 块
        import re
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试找第一个 { 到最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        return None

    def _parse_cases(self, markdown_text: str) -> List[Dict]:
        """从 Markdown 解析测试用例（增强版）"""
        import re
        cases = []

        # 策略1: 匹配 TC-{id} 或 ## TC-{id} 格式
        # 每个用例块以 TC- 开头，到下一个 TC- 或文档结尾
        tc_blocks = re.split(r'(?:^|\n)(?:##\s*)?TC-\d+', markdown_text)
        tc_headers = re.findall(r'(?:^|\n)(?:##\s*)?(TC-\d+[^\n]*)', markdown_text)

        if len(tc_headers) > 0 and len(tc_blocks) > 1:
            for i, (header, block) in enumerate(zip(tc_headers, tc_blocks[1:])):
                case = self._parse_single_case_block(header, block, i + 1)
                if case:
                    cases.append(case)

        # 策略2: 如果没有 TC- 格式，尝试按 ## 标题拆分
        if not cases:
            sections = re.split(r'\n##\s+', markdown_text)
            for sec in sections[1:]:
                lines = sec.strip().split('\n')
                title = lines[0].strip() if lines else ""
                body = '\n'.join(lines[1:]) if len(lines) > 1 else ""
                case = self._parse_freeform_case(title, body)
                if case:
                    cases.append(case)

        # 策略3: 如果仍然没有，尝试按编号列表拆分
        if not cases:
            # 找所有包含步骤/预期的段落
            step_blocks = re.findall(
                r'((?:测试步骤|步骤|Steps)[^:]*:[\s\S]*?)(?:\n\n(?:测试步骤|步骤|Steps|预期|Expected|##|TC-)|\Z)',
                markdown_text, re.MULTILINE
            )
            for i, block in enumerate(step_blocks):
                cases.append({
                    "name": f"TC-{i+1}",
                    "raw": block.strip()[:800],
                    "priority": "P1",
                    "module": "未分类",
                })

        # 策略4: 最终兜底——整段作为一个粗略结果
        if not cases and markdown_text.strip():
            cases.append({
                "name": "TC-1",
                "raw": markdown_text.strip()[:2000],
                "priority": "P1",
                "module": "未分类",
            })

        logger.info(f"[用例解析] 解析出 {len(cases)} 条用例")
        return cases

    def _parse_single_case_block(self, header: str, block: str, idx: int) -> Optional[Dict]:
        """解析单个 TC-xxx 格式的用例块"""
        import re

        # 从标题提取优先级和类型
        priority_match = re.search(r'\[([P0P1P2P3]+)\]', header)
        priority = priority_match.group(1) if priority_match else "P1"

        type_match = re.search(r'\[([正向异常边界安全性能]+)\]', header)
        case_type = type_match.group(1) if type_match else ""

        # 从标题提取名称（去掉 TC-id 和方括号内容）
        name = re.sub(r'TC-\d+', '', header)
        name = re.sub(r'\[[^\]]+\]', '', name).strip()
        if not name:
            name = f"TC-{idx}"

        # 从内容提取各字段
        module = self._extract_field(block, '模块')
        preconditions = self._extract_field(block, '前置条件')

        # 提取步骤
        steps = self._extract_list(block, '测试步骤|步骤|Steps')

        # 提取预期结果
        expected = self._extract_list(block, '预期结果|预期|Expected')

        return {
            "name": name,
            "priority": priority,
            "case_type": case_type,
            "module": module or "未分类",
            "preconditions": preconditions,
            "test_steps": steps,
            "expected_results": expected,
            "raw": block.strip()[:800],
        }

    def _extract_field(self, text: str, field_name: str) -> str:
        """从文本提取单个字段值"""
        import re
        pattern = f'{field_name}[^:]*:\s*(.+?)(?:\n|$)'
        match = re.search(pattern, text)
        return match.group(1).strip() if match else ""

    def _extract_list(self, text: str, field_pattern: str) -> List[str]:
        """从文本提取编号列表"""
        import re
        # 找字段开始位置
        pattern = f'({field_pattern})[^:]*:\s*'
        match = re.search(pattern, text)
        if not match:
            return []

        # 从字段位置开始，提取编号列表
        start = match.end()
        remaining = text[start:]

        # 提取编号条目
        items = re.findall(r'\d+[.、]\s*(.+?)(?:\n|\r|$)', remaining)
        if items:
            return [item.strip() for item in items]

        # 如果没有编号，尝试按换行拆分
        lines = remaining.strip().split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith(('测试', '预期', '模块', '前置', 'TC-', '##')):
                line = re.sub(r'^[-*]\s*', '', line)
                if line:
                    result.append(line)
            if line.startswith(('预期', 'Expected')) and result:
                break

        return result

    def _parse_freeform_case(self, title: str, body: str) -> Optional[Dict]:
        """解析自由格式的用例"""
        import re

        # 从标题提取优先级
        priority = "P1"
        for p in ['P0', 'P1', 'P2', 'P3']:
            if p in title:
                priority = p
                break

        module = self._extract_field(body, '模块')
        steps = self._extract_list(body, '测试步骤|步骤')
        expected = self._extract_list(body, '预期结果|预期')

        return {
            "name": title.strip()[:100],
            "priority": priority,
            "module": module or "未分类",
            "test_steps": steps,
            "expected_results": expected,
            "raw": body.strip()[:800],
        }

    def _save_cases(self, requirement_id: int, cases: List[Dict]) -> int:
        """保存用例到数据库（独立 session，线程安全）"""
        import uuid
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'testgen.db')
        logger.info(f"[AutogenGroupChat] DB path: {db_path}")
        engine = create_engine(f'sqlite:///{db_path}')
        Session = sessionmaker(bind=engine)
        bg_session = Session()

        saved = 0
        try:
            for idx, case_data in enumerate(cases, 1):
                try:
                    case = TestCase(
                        case_id=f"TC_AG_{uuid.uuid4().hex[:8]}",
                        requirement_id=requirement_id,
                        module=case_data.get("module", "未分类"),
                        name=case_data.get("name", case_data.get("raw", "")[:100]),
                        test_point=case_data.get("name", ""),
                        priority=case_data.get("priority", "P1"),
                        test_steps=case_data.get("test_steps", []),
                        expected_results=case_data.get("expected_results", []),
                        preconditions=case_data.get("preconditions", ""),
                        status=0,
                    )
                    bg_session.add(case)
                    saved += 1
                except Exception as e:
                    logger.info(f"[AutogenGroupChat] 保存用例失败: {e}")

            if saved > 0:
                bg_session.commit()
                logger.info(f"[AutogenGroupChat] 入库成功: {saved} 条")
            else:
                bg_session.rollback()

        except Exception as e:
            logger.info(f"[AutogenGroupChat] 入库异常: {e}")
            bg_session.rollback()

        finally:
            bg_session.close()

        return saved

    def run_async(self, task_id: str, requirement_id: int):
        """在新线程中运行异步生成"""
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run_generation(task_id, requirement_id))
            finally:
                loop.close()

        thread = threading.Thread(target=_run, name=f"autogen-{task_id}", daemon=True)
        thread.start()



    def run_async_phase1(self, task_id: str, requirement_id: int):
        """只运行 Phase 1，完成后暂停等人工评审"""
        async def _phase1():
            from datetime import datetime
            task = self._tasks.get(task_id)
            if not task:
                return

            task.status = 1
            requirement = self._get_requirement(requirement_id)
            if not requirement:
                task.status = 3
                task.error_message = "需求不存在"
                return

            task.requirement_title = requirement.title
            task.phase = "phase1"
            task.progress = 10.0
            task.message = "Phase 1: 需求分析 + 策略设计"
            task.updated_at = datetime.utcnow().isoformat()
            self._emit(task_id, "progress", {"phase": "phase1", "progress": 10})

            phase1_result = await self._run_phase1(requirement.content)
            if not phase1_result:
                task.status = 3
                task.error_message = "Phase 1 失败"
                self._emit(task_id, "error", {"error": "Phase 1 失败"})
                return

            task.analysis_data = phase1_result.get("analysis")
            task.plan_data = phase1_result.get("plan")
            task.phase = "phase1_done"
            task.progress = 40.0
            task.message = "Phase 1 完成，等待人工评审"
            task.updated_at = datetime.utcnow().isoformat()
            self._emit(task_id, "phase1_done", {"phase": "phase1_done", "progress": 40, "plan_data": task.plan_data})

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_phase1())
            finally:
                loop.close()

        thread = threading.Thread(target=_run, name=f"autogen-phase1-{task_id}", daemon=True)
        thread.start()

    def run_async_phase2(self, task_id: str, edited_plan: Optional[Dict] = None):
        """人工评审后继续 Phase 2"""
        async def _phase2():
            from datetime import datetime
            task = self._tasks.get(task_id)
            if not task or task.phase != "phase1_done":
                return

            task.phase = "phase2"
            task.progress = 40.0
            task.message = "Phase 2: 用例生成 + 评审"
            task.updated_at = datetime.utcnow().isoformat()
            self._emit(task_id, "progress", {"phase": "phase2", "progress": 40})

            requirement = self._get_requirement(task.requirement_id)
            if not requirement:
                task.status = 3
                task.error_message = "需求不存在"
                return

            plan_data = edited_plan or task.plan_data or {}
            plan_text = json.dumps(plan_data, ensure_ascii=False)
            combined_task = f"需求内容：\n{requirement.content}\n\n测试策略：\n{plan_text}\n\n请根据以上策略逐项生成测试用例。"

            phase2_result = await self._run_phase2(combined_task)
            if not phase2_result:
                task.status = 3
                task.error_message = "Phase 2 失败"
                self._emit(task_id, "error", {"error": "Phase 2 失败"})
                return

            cases = self._parse_cases(phase2_result)
            task.cases = cases
            task.progress = 80.0
            task.message = f"生成完成：{len(cases)} 条用例"
            task.updated_at = datetime.utcnow().isoformat()

            saved = self._save_cases(task.requirement_id, cases)
            if saved > 0:
                task.message = f"生成完成！{len(cases)} 条用例，{saved} 条入库"
            task.progress = 100.0
            task.status = 2
            task.phase = "complete"
            task.completed_at = datetime.utcnow().isoformat()
            task.duration = time.time() - time.mktime(datetime.fromisoformat(task.created_at).timetuple())
            self._emit(task_id, "complete", {"phase": "complete", "progress": 100, "cases": len(cases)})

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_phase2())
            finally:
                loop.close()

        thread = threading.Thread(target=_run, name=f"autogen-phase2-{task_id}", daemon=True)
        thread.start()

# ==================== 单例 ====================

_instance: Optional[AutogenGroupChatService] = None


def get_autogen_service(db_session=None, socketio=None, llm_manager=None) -> AutogenGroupChatService:
    """获取全局单例"""
    global _instance
    if _instance is None:
        _instance = AutogenGroupChatService(db_session=db_session, socketio=socketio, llm_manager=llm_manager)
    else:
        if socketio and not _instance.socketio:
            _instance.socketio = socketio
        if llm_manager and not _instance.llm_manager:
            _instance.llm_manager = llm_manager
    return _instance


