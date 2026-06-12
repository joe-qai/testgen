import os
import sys
import pytest
import tempfile
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.models import (
    init_database,
    get_session,
    Requirement,
    RequirementStatus,
    TestCase,
    CaseStatus,
    Priority,
    GenerationTask,
    TaskStatus,
)
from sqlalchemy.orm.attributes import flag_modified


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_analysis_edit.db")
    engine = init_database(db_path)
    session = get_session(engine)
    yield session
    session.close()
    engine.dispose()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_requirement(db):
    req = Requirement(
        title="登录模块需求",
        content="用户登录功能，账号长度6-10字符，密码长度8-16字符",
        status=RequirementStatus.ANALYZED,
        analysis_data={
            "modules": ["登录入口", "输入校验", "身份验证"],
            "test_points": ["账号长度校验", "密码长度校验", "登录成功", "登录失败"],
        },
    )
    db.add(req)
    db.commit()
    return req


@pytest.fixture
def sample_pending_cases(db, sample_requirement):
    cases = []
    for i in range(5):
        case = TestCase(
            case_id=f"TC_{i+1:03d}",
            requirement_id=sample_requirement.id,
            module="登录模块",
            name=f"测试用例{i+1}",
            priority=Priority.P1,
            status=CaseStatus.PENDING_REVIEW,
        )
        db.add(case)
        cases.append(case)
    db.commit()
    return cases


class TestGetAnalysisDetail:
    def test_get_analysis_detail_success(self, db, sample_requirement):
        req = db.query(Requirement).get(sample_requirement.id)
        assert req is not None
        assert req.analysis_data is not None
        assert "modules" in req.analysis_data
        assert len(req.analysis_data["modules"]) == 3

    def test_get_analysis_detail_not_found(self, db):
        req = db.query(Requirement).get(9999)
        assert req is None

    def test_get_analysis_detail_no_analysis_data(self, db):
        req = Requirement(
            title="未分析需求",
            content="内容",
            status=RequirementStatus.PENDING_ANALYSIS,
        )
        db.add(req)
        db.commit()
        assert req.analysis_data is None


class TestUpdateAnalysisContent:
    def test_update_modules_success(self, db, sample_requirement):
        new_modules = ["登录入口", "输入校验", "身份验证", "错误处理"]
        sample_requirement.analysis_data["modules"] = new_modules
        flag_modified(sample_requirement, "analysis_data")
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.analysis_data["modules"] == new_modules

    def test_update_test_points_success(self, db, sample_requirement):
        new_test_points = ["账号长度校验", "密码长度校验", "登录成功"]
        sample_requirement.analysis_data["test_points"] = new_test_points
        flag_modified(sample_requirement, "analysis_data")
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.analysis_data["test_points"] == new_test_points

    def test_update_business_rules_success(self, db, sample_requirement):
        new_business_rules = ["账号长度6-10字符", "密码长度8-16字符"]
        sample_requirement.analysis_data["business_rules"] = new_business_rules
        flag_modified(sample_requirement, "analysis_data")
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.analysis_data["business_rules"] == new_business_rules


class TestUpdateTestPlan:
    def test_update_test_plan_success(self, db, sample_requirement):
        test_plan = {
            "methodology": "ISO/IEC 29119标准结合20926 FPA",
            "design_methods": ["等价类划分", "边界值分析"],
            "test_types": ["功能测试", "接口测试", "安全测试"],
        }
        sample_requirement.test_plan = test_plan
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.test_plan == test_plan

    def test_update_test_plan_empty(self, db, sample_requirement):
        test_plan = {}
        sample_requirement.test_plan = test_plan
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.test_plan == {}


class TestUpdateGenerationParams:
    def test_update_generation_params_success(self, db, sample_requirement):
        generation_params = {
            "temperature": 0.7,
            "max_tokens": 4096,
            "prompt_template_id": 1,
        }
        sample_requirement.generation_params = generation_params
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.generation_params == generation_params

    def test_update_generation_params_default(self, db, sample_requirement):
        generation_params = {
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        sample_requirement.generation_params = generation_params
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.generation_params["temperature"] == 0.3


class TestUpdateRAGParams:
    def test_update_rag_params_success(self, db, sample_requirement):
        rag_params = {
            "similarity_threshold": 0.7,
            "top_k": 10,
            "fusion_strategy": "rrf",
        }
        sample_requirement.rag_params = rag_params
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert req.rag_params == rag_params

    def test_update_rag_params_threshold_range(self, db, sample_requirement):
        rag_params = {
            "similarity_threshold": 0.5,
            "top_k": 5,
        }
        sample_requirement.rag_params = rag_params
        db.commit()
        req = db.query(Requirement).get(sample_requirement.id)
        assert 0.0 <= req.rag_params["similarity_threshold"] <= 1.0


class TestGetPendingCases:
    def test_get_pending_cases_success(self, db, sample_pending_cases):
        pending_cases = (
            db.query(TestCase)
            .filter(TestCase.status == CaseStatus.PENDING_REVIEW)
            .all()
        )
        assert len(pending_cases) == 5

    def test_get_pending_cases_by_requirement(self, db, sample_pending_cases):
        requirement_id = sample_pending_cases[0].requirement_id
        pending_cases = (
            db.query(TestCase)
            .filter(
                TestCase.status == CaseStatus.PENDING_REVIEW,
                TestCase.requirement_id == requirement_id,
            )
            .all()
        )
        assert len(pending_cases) == 5

    def test_get_pending_cases_empty(self, db):
        pending_cases = (
            db.query(TestCase)
            .filter(TestCase.status == CaseStatus.PENDING_REVIEW)
            .all()
        )
        assert len(pending_cases) == 0


class TestBatchConfirmCases:
    def test_batch_confirm_approve_success(self, db, sample_pending_cases):
        case_ids = [case.id for case in sample_pending_cases[:3]]
        for case_id in case_ids:
            case = db.query(TestCase).get(case_id)
            case.status = CaseStatus.APPROVED
        db.commit()
        approved_cases = (
            db.query(TestCase)
            .filter(TestCase.status == CaseStatus.APPROVED)
            .all()
        )
        assert len(approved_cases) == 3

    def test_batch_confirm_reject_success(self, db, sample_pending_cases):
        case_ids = [case.id for case in sample_pending_cases[3:]]
        for case_id in case_ids:
            case = db.query(TestCase).get(case_id)
            case.status = CaseStatus.REJECTED
        db.commit()
        rejected_cases = (
            db.query(TestCase)
            .filter(TestCase.status == CaseStatus.REJECTED)
            .all()
        )
        assert len(rejected_cases) == 2

    def test_batch_confirm_invalid_case_id(self, db):
        case = db.query(TestCase).get(9999)
        assert case is None


class TestBatchEditCases:
    def test_batch_edit_priority_success(self, db, sample_pending_cases):
        case_ids = [case.id for case in sample_pending_cases]
        for case_id in case_ids:
            case = db.query(TestCase).get(case_id)
            case.priority = Priority.P0
        db.commit()
        edited_cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
        for case in edited_cases:
            assert case.priority == Priority.P0

    def test_batch_edit_module_success(self, db, sample_pending_cases):
        case_ids = [case.id for case in sample_pending_cases]
        new_module = "登录模块-编辑后"
        for case_id in case_ids:
            case = db.query(TestCase).get(case_id)
            case.module = new_module
        db.commit()
        edited_cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
        for case in edited_cases:
            assert case.module == new_module

    def test_batch_edit_multiple_fields(self, db, sample_pending_cases):
        case_ids = [case.id for case in sample_pending_cases[:2]]
        for case_id in case_ids:
            case = db.query(TestCase).get(case_id)
            case.priority = Priority.P0
            case.module = "高优先级模块"
        db.commit()
        edited_cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
        for case in edited_cases:
            assert case.priority == Priority.P0
            assert case.module == "高优先级模块"


class TestRAGWarehouse:
    def test_rag_search_success(self):
        pass

    def test_rag_upsert_success(self):
        pass

    def test_rag_delete_success(self):
        pass

    def test_rag_stats_success(self):
        pass