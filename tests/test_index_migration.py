import pytest
import tempfile
import os
from sqlalchemy import create_engine, text
from src.monitoring.index_migration import IndexMigration


INDEX_WHITELIST = [
    {
        "table": "test_table",
        "columns": ["col1", "col2"],
        "name": "idx_test_col1_col2"
    }
]


def test_index_migration_creates_index():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.commit()

        migration = IndexMigration(engine, INDEX_WHITELIST)
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_col1_col2'"
            ))
            indexes = result.fetchall()
            assert len(indexes) == 1
    finally:
        engine.dispose()


def test_index_migration_idempotent():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.commit()

        migration = IndexMigration(engine, INDEX_WHITELIST)

        migration.migrate()
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_col1_col2'"
            ))
            indexes = result.fetchall()
            assert len(indexes) == 1
    finally:
        engine.dispose()


def test_index_migration_handles_failure():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        invalid_whitelist = [
            {
                "table": "nonexistent_table",
                "columns": ["col1"],
                "name": "idx_invalid"
            }
        ]

        migration = IndexMigration(engine, invalid_whitelist)

        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            indexes = result.fetchall()
            assert len(indexes) == 0
    finally:
        engine.dispose()