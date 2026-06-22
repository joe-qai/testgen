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