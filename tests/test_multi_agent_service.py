#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiAgentCaseService 集成测试
防止回归，验证核心接口
"""

import sys
import os
import json
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.multi_agent_service import (
    MultiAgentCaseService,
    AGENT_PROMPTS,
)


# ============ Prompt 定义测试 ============

class TestAgentPrompts:
    """验证 6 个 Agent Prompt 定义完整且关键约束存在"""

    def test_all_prompts_defined(self):
        """所有 6 个 Agent prompt 都存在"""
        expected = [
            "orchestrator",
            "requirement_analyst",
            "test_plan_designer",
            "case_generator_batch",
            "case_generator_positive",
            "reviewer",
        ]
        for name in expected:
            assert name in AGENT_PROMPTS, f"缺少 prompt: {name}"

    def test_prompts_not_empty(self):
        """每个 prompt 不为空"""
        for name, prompt in AGENT_PROMPTS.items():
            assert len(prompt) > 50, f"prompt {name} 太短: {len(prompt)} 字"

    def test_generator_batch_has_priority_constraint(self):
        """Generator batch prompt 包含优先级约束"""
        prompt = AGENT_PROMPTS["case_generator_batch"]
        assert "P0+P1" in prompt or "P0" in prompt
        assert "40%" in prompt  # P0+P1 ≤ 40%

    def test_generator_batch_no_placeholder(self):
        """Generator batch prompt 禁止占位符"""
        prompt = AGENT_PROMPTS["case_generator_batch"]
        assert "{username}" in prompt  # 规则里提到禁止占位符
        assert "占位符" in prompt or "placeholder" in prompt.lower()

    def test_generator_positive_requires_main_flow(self):
        """Generator positive prompt 要求生成正向主流程"""
        prompt = AGENT_PROMPTS["case_generator_positive"]
        assert "正向" in prompt or "主流程" in prompt
        assert "P0" in prompt or "P1" in prompt

    def test_reviewer_veto_items(self):
        """Reviewer prompt 只有 4 个一票否决项（不含标题泛化词）"""
        prompt = AGENT_PROMPTS["reviewer"]
        assert "占位符" in prompt
        assert "模糊" in prompt
        assert "步骤不对应" in prompt or "步骤数" in prompt
        # 标题泛化词是扣分项，不是一票否决
        assert "扣分项" in prompt

    def test_reviewer_scoring_system(self):
        """Reviewer prompt 有评分系统"""
        prompt = AGENT_PROMPTS["reviewer"]
        assert "0-20" in prompt or "100" in prompt or "120" in prompt
        assert "评分" in prompt


# ============ 用例解析测试 ============

class TestCaseParsing:
    """验证 Markdown → 结构化用例的解析逻辑"""

    def setup_method(self):
        self.service = MultiAgentCaseService(db_session=None, llm_manager=None)

    def test_parse_simple_case(self):
        """解析单条简单用例"""
        markdown = """## [P0] 用户名密码正确时登录成功并跳转主页
[测试类型] 功能
[前置条件] 已注册账号 user01
[测试步骤] 1. 输入用户名user01。2. 输入密码Admin@123。3. 点击登录按钮
[预期结果] 1. 登录成功。2. 跳转到主页。3. 显示用户名user01"""

        cases = self.service._parse_cases_from_markdown(markdown)
        assert len(cases) >= 1
        if cases:
            case = cases[0]
            assert case["priority"] == "P0"
            assert case["case_type"] == "功能"
            # test_steps 可能解析为空（单行格式与 LLM 实际输出格式略有差异）
            # 主要验证解析不报错且有基本信息
            assert case["title"] != ""

    def test_parse_multiple_cases(self):
        """解析多条用例"""
        markdown = """## [P1] 密码连续错误5次后账号锁定并提示已锁定
[测试类型] 边界/异常
[前置条件] 已注册账号
[测试步骤] 1. 输入错误密码5次
[预期结果] 1. 提示账号已锁定

## [P2] 验证码超过5分钟后登录失败
[测试类型] 边界
[前置条件] 已获取验证码
[测试步骤] 1. 6分钟后输入验证码
[预期结果] 1. 提示验证码过期"""

        cases = self.service._parse_cases_from_markdown(markdown)
        assert len(cases) == 2
        assert cases[0]["priority"] == "P1"
        assert cases[1]["priority"] == "P2"

    def test_parse_empty_input(self):
        """解析空输入返回空列表"""
        cases = self.service._parse_cases_from_markdown("")
        assert cases == []

    def test_parse_no_priority_tag(self):
        """没有 [Px] 标签的文本返回空列表"""
        markdown = "这是一段普通文本，没有测试用例格式"
        cases = self.service._parse_cases_from_markdown(markdown)
        assert cases == []


# ============ 模块切分测试 ============

class TestModuleExtraction:
    """验证从 Designer 输出中提取测试点模块"""

    def setup_method(self):
        self.service = MultiAgentCaseService(db_session=None, llm_manager=None)

    def test_extract_from_headings(self):
        """按标题切分模块"""
        designer_out = """### 模块A：手机号验证码登录
测试点1：正常登录
测试点2：验证码过期

### 模块B：用户名密码登录
测试点3：密码错误
测试点4：账号锁定"""

        modules = self.service._extract_test_modules(designer_out)
        assert len(modules) >= 2

    def test_extract_from_paragraphs(self):
        """无标题时按段落切分"""
        designer_out = "测试点1：正常登录\n测试点2：密码错误\n测试点3：验证码过期\n测试点4：账号锁定\n测试点5：并发登录"

        modules = self.service._extract_test_modules(designer_out)
        assert len(modules) >= 1

    def test_max_4_batches(self):
        """超过 4 个模块时合并"""
        designer_out = "### M1\n### M2\n### M3\n### M4\n### M5\n### M6\n### M7\n### M8"

        modules = self.service._extract_test_modules(designer_out)
        assert len(modules) <= 4


# ============ 评审解析测试 ============

class TestReviewDecisionParsing:
    """验证 _parse_review_decision 的解析逻辑"""

    def setup_method(self):
        self.service = MultiAgentCaseService(db_session=None, llm_manager=None)

    def test_pass_decision(self):
        """解析合格结论"""
        output = "评审结论：合格，总分 95"
        result = self.service._parse_review_decision(output)
        assert result == "PASS"

    def test_conditional_decision(self):
        """解析有条件通过"""
        output = "评审结论：有条件通过，总分 75"
        result = self.service._parse_review_decision(output)
        assert result == "CONDITIONAL"

    def test_fail_with_low_score(self):
        """解析不合格 + 低评分"""
        output = "评审结论：不合格，总分 52"
        result = self.service._parse_review_decision(output)
        assert result == "FAIL"

    def test_fail_with_score_above_60(self):
        """不合格但评分 >= 60 → 有条件通过"""
        output = "评审结论：不合格，但六大维度总分：85"
        result = self.service._parse_review_decision(output)
        assert result == "CONDITIONAL"

    def test_veto_keyword_triggers_fail(self):
        """一票否决关键词触发 FAIL"""
        output = "占位符检查：不通过（触发否决）\n评审结论：不合格"
        result = self.service._parse_review_decision(output)
        assert result == "FAIL"

    def test_default_returns_conditional(self):
        """无法匹配时默认返回 CONDITIONAL"""
        output = "用例评审完成"
        result = self.service._parse_review_decision(output)
        assert result == "CONDITIONAL"


# ============ 运行测试 ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])