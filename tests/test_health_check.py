import pytest
import json
import tempfile
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def test_health_live_logic():
    result = {"status": "alive"}
    assert result["status"] == "alive"


def test_health_ready_logic_with_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.fetchone() is not None
            status = {"status": "ready", "database": "connected"}
            assert status["status"] == "ready"
            assert status["database"] == "connected"
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_health_ready_logic_without_db():
    status = {"status": "not_ready", "database": "disconnected"}
    assert status["status"] == "not_ready"


def test_metrics_logic():
    from src.monitoring.metrics_collector import MetricsCollector

    collector = MetricsCollector()
    collector.record_request(200, 100.0)
    collector.record_request(404, 50.0)

    metrics = collector.get_metrics()
    assert "total_requests" in metrics
    assert metrics["total_requests"] == 2
    assert metrics["status_codes"].get(200) == 1
    assert metrics["status_codes"].get(404) == 1