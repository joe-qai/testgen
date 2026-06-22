import pytest
import json
import uuid
import time
from src.monitoring.error_response import ErrorResponse
from src.monitoring.metrics_collector import MetricsCollector


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


def test_error_response_json_format():
    result = ErrorResponse.create("服务器内部错误", "INTERNAL_ERROR", "req-456")
    assert json.dumps(result) is not None


def test_metrics_collector_integration():
    collector = MetricsCollector()
    collector.record_request(200, 100.5)
    collector.record_request(404, 50.2)
    collector.record_request(500, 200.8)

    metrics = collector.get_metrics()
    assert metrics["total_requests"] == 3
    assert metrics["error_count"] == 2
    assert metrics["status_codes"].get(200) == 1
    assert metrics["status_codes"].get(404) == 1
    assert metrics["status_codes"].get(500) == 1