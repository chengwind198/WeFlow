#!/usr/bin/env python3
"""
weflow 数据库访问层。
连接管理 + 各表 CRUD 便捷函数。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from engine.logger import get_logger

logger = get_logger(__name__)

_db_path: Optional[Path] = None
_initialized: bool = False


def _resolve_db_path() -> Path:
    """返回 weflow.db 的绝对路径。"""
    global _db_path
    if _db_path is not None:
        return _db_path
    # 默认: engine/db/weflow.db（相对于本模块所在目录）
    here = Path(__file__).resolve().parent
    _db_path = here / "weflow.db"
    return _db_path


def set_db_path(path: str | Path) -> None:
    """手动设置数据库路径（用于测试或非标准部署）。"""
    global _db_path
    _db_path = Path(path)


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（WAL 模式，外键开启）。首次连接时自动建表。"""
    global _initialized
    db_path = _resolve_db_path()

    if not _initialized:
        _ensure_db(db_path)
        _initialized = True

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_add_column(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    """安全迁移：如果表中不存在指定列，则添加。"""
    try:
        conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("数据库迁移: 为 %s 表添加 %s 列", table, column)
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        conn.commit()


def _migrate_sync_source_columns(conn: sqlite3.Connection) -> None:
    """迁移：为 task_sync 表添加 sync_from/url/file_path 列，并改为 task_id 可空。"""
    try:
        conn.execute("SELECT sync_from FROM task_sync LIMIT 1")
        return  # 已迁移
    except sqlite3.OperationalError:
        pass

    logger.info("数据库迁移: task_sync 添加 sync_from/url/file_path 列，task_id 改为可空")
    # 1. 添加新列
    try:
        conn.execute("ALTER TABLE task_sync ADD COLUMN sync_from TEXT NOT NULL DEFAULT 'task'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE task_sync ADD COLUMN url TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE task_sync ADD COLUMN file_path TEXT")
    except sqlite3.OperationalError:
        pass

    # 2. 重建表使 task_id 可空（SQLite 不支持 ALTER COLUMN 约束）
    conn.execute("""CREATE TABLE task_sync_new (
        id              INTEGER PRIMARY KEY,
        task_id         INTEGER,
        markdown_content TEXT   NOT NULL DEFAULT '',
        platforms       TEXT    NOT NULL DEFAULT '[]',
        sync_from       TEXT    NOT NULL DEFAULT 'task',
        url             TEXT,
        file_path       TEXT,
        status          TEXT    NOT NULL DEFAULT 'pending',
        created_at      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        updated_at      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )""")
    conn.execute("""INSERT INTO task_sync_new
        (id, task_id, markdown_content, platforms, sync_from, url, file_path, status, created_at, updated_at)
        SELECT id, task_id, markdown_content, platforms,
            'task', NULL, NULL, status, created_at, updated_at
        FROM task_sync""")
    conn.execute("DROP TABLE task_sync")
    conn.execute("ALTER TABLE task_sync_new RENAME TO task_sync")
    conn.execute("CREATE INDEX idx_ts_task_id ON task_sync(task_id)")
    conn.execute("CREATE INDEX idx_ts_status ON task_sync(status)")
    conn.commit()


def _migrate_task_type_rename(conn: sqlite3.Connection) -> None:
    """迁移：将 task.type / task_status.applies_to 从 news/newspic 重命名为 article/image。"""
    # 检查是否已迁移：看 task 表中是否还有 type='news' 的记录
    try:
        row = conn.execute("SELECT 1 FROM task WHERE type = 'news' LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return  # task 表不存在，跳过
    if row is None:
        return  # 已迁移

    logger.info("数据库迁移: task.type news→article / newspic→image")
    conn.execute("UPDATE task SET type = 'article' WHERE type = 'news'")
    conn.execute("UPDATE task SET type = 'image' WHERE type = 'newspic'")
    conn.execute("UPDATE task_status SET applies_to = 'article' WHERE applies_to = 'news'")
    conn.execute("UPDATE task_status SET applies_to = 'image' WHERE applies_to = 'newspic'")
    conn.commit()


def _migrate_task_review(conn: sqlite3.Connection) -> None:
    """安全迁移：如果 task_review 表不存在，则创建。"""
    try:
        conn.execute("SELECT 1 FROM task_review LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("数据库迁移: 创建 task_review 审核记录表")
        conn.execute("""CREATE TABLE task_review (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            stage INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewer TEXT NOT NULL DEFAULT '',
            comment TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )""")
        conn.execute("CREATE INDEX idx_tr_task ON task_review(task_id)")
        conn.execute("CREATE INDEX idx_tr_status ON task_review(status)")
        conn.execute("CREATE INDEX idx_tr_stage ON task_review(stage)")
        conn.commit()


def _migrate_add_sync_tables(conn: sqlite3.Connection) -> None:
    """安全迁移：如果 task_sync 表不存在，则创建同步相关表。"""
    try:
        conn.execute("SELECT 1 FROM task_sync LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("数据库迁移: 创建 task_sync / task_sync_result 表")
        conn.execute("""CREATE TABLE task_sync (
            id INTEGER PRIMARY KEY,
            task_id INTEGER,
            markdown_content TEXT NOT NULL DEFAULT '',
            platforms TEXT NOT NULL DEFAULT '[]',
            sync_from TEXT NOT NULL DEFAULT 'task',
            url TEXT,
            file_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )""")
        conn.execute("CREATE INDEX idx_ts_task_id ON task_sync(task_id)")
        conn.execute("CREATE INDEX idx_ts_status ON task_sync(status)")
        conn.execute("""CREATE TABLE task_sync_result (
            id INTEGER PRIMARY KEY,
            task_sync_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )""")
        conn.execute("CREATE INDEX idx_tsr_sync_id ON task_sync_result(task_sync_id)")
        conn.execute("CREATE INDEX idx_tsr_platform ON task_sync_result(platform)")
        conn.commit()


def _ensure_db(db_path: Path) -> None:
    """确保数据库文件及表结构存在，不存在则从 ddl.sql 创建。"""
    ddl_path = Path(__file__).resolve().parent / "ddl.sql"
    if not ddl_path.exists():
        logger.error("DDL 文件不存在: %s", ddl_path)
        return

    # 检查核心表 task 是否已存在
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1 FROM task LIMIT 1")
            # 迁移：为已有数据库添加 need_images 列
            _migrate_add_column(conn, "task", "need_images", "INTEGER NOT NULL DEFAULT 1")
            # 迁移：为已有数据库添加 user_details 列
            _migrate_add_column(conn, "task", "user_details", "TEXT NOT NULL DEFAULT ''")
            # 迁移：为已有数据库添加 genre 列（文章体裁，article 模式有效）
            _migrate_add_column(conn, "task", "genre", "TEXT NOT NULL DEFAULT ''")
            # 迁移：为已有数据库添加 short_text 列（短文本，image 模式有效）
            _migrate_add_column(conn, "task", "short_text", "TEXT NOT NULL DEFAULT ''")
            # 迁移：检查 task_sync 表是否存在，不存在则创建
            _migrate_add_sync_tables(conn)
            # 迁移：task_sync 添加 sync_from/url/file_path 列，task_id 改为可空
            _migrate_sync_source_columns(conn)
            # 迁移：task.type news→article / newspic→image
            _migrate_task_type_rename(conn)
            # 迁移：创建 task_review 审核记录表
            _migrate_task_review(conn)
            conn.close()
            return  # 表已存在，跳过
        except sqlite3.OperationalError:
            pass  # 表不存在，继续执行 DDL

    logger.info("初始化数据库: %s <- %s", db_path, ddl_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    with open(ddl_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")


def init_db() -> None:
    """强制（重新）初始化数据库。"""
    global _initialized
    db_path = _resolve_db_path()
    ddl_path = Path(__file__).resolve().parent / "ddl.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    with open(ddl_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()
    conn.close()
    _initialized = True
