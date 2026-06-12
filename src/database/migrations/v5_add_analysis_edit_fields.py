#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 v5: 为requirements表添加测试规划、生成参数、RAG参数字段
- test_plan JSON: 测试规划内容（methodology, design_methods, test_types）
- generation_params JSON: 生成参数配置（temperature, max_tokens, prompt_template_id）
- rag_params JSON: RAG检索参数（similarity_threshold, top_k, fusion_strategy）
"""

import sqlite3
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="[Migration] %(message)s")
logger = logging.getLogger(__name__)


def get_db_path():
    return os.environ.get("DB_PATH", "data/testgen.db")


def check_column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def run_migration(db_path=None):
    if db_path is None:
        db_path = get_db_path()

    if not os.path.exists(db_path):
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    logger.info(f"开始迁移数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        added_columns = []

        if not check_column_exists(cursor, "requirements", "test_plan"):
            cursor.execute(
                "ALTER TABLE requirements ADD COLUMN test_plan JSON DEFAULT NULL"
            )
            added_columns.append("test_plan")
            logger.info("已添加字段: test_plan JSON")
        else:
            logger.info("字段已存在，跳过: test_plan")

        if not check_column_exists(cursor, "requirements", "generation_params"):
            cursor.execute(
                "ALTER TABLE requirements ADD COLUMN generation_params JSON DEFAULT NULL"
            )
            added_columns.append("generation_params")
            logger.info("已添加字段: generation_params JSON")
        else:
            logger.info("字段已存在，跳过: generation_params")

        if not check_column_exists(cursor, "requirements", "rag_params"):
            cursor.execute(
                "ALTER TABLE requirements ADD COLUMN rag_params JSON DEFAULT NULL"
            )
            added_columns.append("rag_params")
            logger.info("已添加字段: rag_params JSON")
        else:
            logger.info("字段已存在，跳过: rag_params")

        conn.commit()

        if added_columns:
            logger.info(f"迁移成功，新增字段: {', '.join(added_columns)}")
        else:
            logger.info("迁移完成，无新增字段（均已存在）")

        for col in ["test_plan", "generation_params", "rag_params"]:
            if check_column_exists(cursor, "requirements", col):
                logger.info(f"✅ 验证通过: {col}")
            else:
                logger.error(f"❌ 验证失败: {col} 不存在")
                return False

        return True

    except Exception as e:
        conn.rollback()
        logger.error(f"迁移失败: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_migration(db_path)
    sys.exit(0 if success else 1)