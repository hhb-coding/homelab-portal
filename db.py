"""
SQLite database helpers for HomeLab Portal.
HomeLab Portal 的 SQLite 数据库辅助模块。
"""

import sqlite3

from config import BASE_DIR, DATABASE_PATH


def get_connection():
    """
    Create and return a SQLite connection.
    创建并返回 SQLite 数据库连接。
    """

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    # Enforce SQLite foreign-key relationships.
    # 启用 SQLite 外键约束。
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def init_db():
    """
    Initialize the database using schema.sql.
    使用 schema.sql 初始化数据库。
    """

    schema_path = BASE_DIR / "schema.sql"

    with get_connection() as connection:
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            connection.executescript(schema_file.read())


def database_is_ready():
    """
    Verify that the devices table exists.
    检查 devices 数据表是否已经存在。
    """

    try:
        with get_connection() as connection:
            result = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name='devices'
                """
            ).fetchone()

        return result is not None

    except sqlite3.Error:
        return False
