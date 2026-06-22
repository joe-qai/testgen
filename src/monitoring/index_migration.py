from src.utils import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


class IndexMigration:
    def __init__(self, engine, index_whitelist):
        self.engine = engine
        self.index_whitelist = index_whitelist

    def migrate(self):
        with self.engine.connect() as conn:
            for index_def in self.index_whitelist:
                try:
                    self._create_index_if_not_exists(conn, index_def)
                    logger.info(f"Index {index_def['name']} created or already exists")
                except Exception as e:
                    logger.error(f"Failed to create index {index_def['name']}: {str(e)}")
            conn.commit()

    def _create_index_if_not_exists(self, conn, index_def):
        table = index_def['table']
        columns = index_def['columns']
        name = index_def['name']

        columns_str = ', '.join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns_str})"
        conn.execute(text(sql))