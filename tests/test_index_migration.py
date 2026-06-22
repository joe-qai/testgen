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


def test_index_migration_preserves_data():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.execute(text("INSERT INTO test_table VALUES (1, 'data1', 'data2')"))
            conn.execute(text("INSERT INTO test_table VALUES (2, 'data3', 'data4')"))
            conn.commit()

        migration = IndexMigration(engine, INDEX_WHITELIST)
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM test_table ORDER BY id"))
            rows = result.fetchall()
            assert len(rows) == 2
            assert rows[0] == (1, 'data1', 'data2')
            assert rows[1] == (2, 'data3', 'data4')
    finally:
        engine.dispose()


def test_index_migration_upgrades_existing_database():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}")

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
            conn.execute(text("INSERT INTO test_table VALUES (1, 'old1', 'old2')"))
            conn.commit()

        new_whitelist = [
            {
                "table": "test_table",
                "columns": ["col1"],
                "name": "idx_test_col1"
            }
        ]

        migration = IndexMigration(engine, new_whitelist)
        migration.migrate()

        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_col1'"
            ))
            indexes = result.fetchall()
            assert len(indexes) == 1

            result = conn.execute(text("SELECT * FROM test_table"))
            rows = result.fetchall()
            assert len(rows) == 1
            assert rows[0] == (1, 'old1', 'old2')
    finally:
        engine.dispose()


def test_index_does_not_change_query_results():
    tmpdir = tempfile.mkdtemp()
    db_path_no_index = os.path.join(tmpdir, "test_no_index.db")
    db_path_with_index = os.path.join(tmpdir, "test_with_index.db")

    engine_no_index = create_engine(f"sqlite:///{db_path_no_index}")
    engine_with_index = create_engine(f"sqlite:///{db_path_with_index}")

    try:
        test_data = [
            (1, 'apple', 'fruit'),
            (2, 'banana', 'fruit'),
            (3, 'carrot', 'vegetable'),
            (4, 'date', 'fruit'),
            (5, 'eggplant', 'vegetable')
        ]

        for engine in [engine_no_index, engine_with_index]:
            with engine.connect() as conn:
                conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
                for row in test_data:
                    conn.execute(text(f"INSERT INTO test_table VALUES ({row[0]}, '{row[1]}', '{row[2]}')"))
                conn.commit()

        index_whitelist = [
            {"table": "test_table", "columns": ["col1"], "name": "idx_test_col1"},
            {"table": "test_table", "columns": ["col2"], "name": "idx_test_col2"}
        ]

        migration = IndexMigration(engine_with_index, index_whitelist)
        migration.migrate()

        queries = [
            "SELECT * FROM test_table WHERE col2 = 'fruit'",
            "SELECT * FROM test_table WHERE col1 LIKE 'a%'",
            "SELECT id, col1 FROM test_table WHERE id > 2",
            "SELECT COUNT(*) FROM test_table",
        ]

        for query in queries:
            with engine_no_index.connect() as conn:
                result_no_index = conn.execute(text(query)).fetchall()

            with engine_with_index.connect() as conn:
                result_with_index = conn.execute(text(query)).fetchall()

            assert result_no_index == result_with_index, f"Query results differ: {query}"
    finally:
        engine_no_index.dispose()
        engine_with_index.dispose()


def test_index_does_not_change_query_order():
    tmpdir = tempfile.mkdtemp()
    db_path_no_index = os.path.join(tmpdir, "test_no_index.db")
    db_path_with_index = os.path.join(tmpdir, "test_with_index.db")

    engine_no_index = create_engine(f"sqlite:///{db_path_no_index}")
    engine_with_index = create_engine(f"sqlite:///{db_path_with_index}")

    try:
        test_data = [
            (1, 'zebra', 'animal'),
            (2, 'apple', 'fruit'),
            (3, 'banana', 'fruit'),
            (4, 'cat', 'animal'),
            (5, 'dog', 'animal')
        ]

        for engine in [engine_no_index, engine_with_index]:
            with engine.connect() as conn:
                conn.execute(text("CREATE TABLE test_table (id INTEGER, col1 TEXT, col2 TEXT)"))
                for row in test_data:
                    conn.execute(text(f"INSERT INTO test_table VALUES ({row[0]}, '{row[1]}', '{row[2]}')"))
                conn.commit()

        index_whitelist = [
            {"table": "test_table", "columns": ["col1"], "name": "idx_test_col1"},
            {"table": "test_table", "columns": ["col2"], "name": "idx_test_col2"}
        ]

        migration = IndexMigration(engine_with_index, index_whitelist)
        migration.migrate()

        queries_with_order = [
            "SELECT * FROM test_table ORDER BY id",
            "SELECT * FROM test_table ORDER BY col1, id",
            "SELECT * FROM test_table ORDER BY col2 DESC, id",
            "SELECT col1 FROM test_table ORDER BY col1 ASC, id",
        ]

        for query in queries_with_order:
            with engine_no_index.connect() as conn:
                result_no_index = conn.execute(text(query)).fetchall()

            with engine_with_index.connect() as conn:
                result_with_index = conn.execute(text(query)).fetchall()

            assert result_no_index == result_with_index, f"Query order differs: {query}"
    finally:
        engine_no_index.dispose()
        engine_with_index.dispose()