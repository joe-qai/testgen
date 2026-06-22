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