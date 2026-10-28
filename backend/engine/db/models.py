#!/usr/bin/env python3
"""
各表 CRUD 操作。
所有函数遵循: get_connection() → 执行 → commit/close。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.constants import Role, Operator

from . import get_connection

# ============================================================
# task 表 — 任务主表
# ============================================================

def task_insert(
    account: str = "main",
    task_type: str = "article",
    topic: str = "",
    title: str = "",
    image_style: str = "",
    theme: str = "",
    status: int = 10,
    app_id: str = "",
    author: str = "",
    newspic_image_style: str = "",
    article_structure: str = "",
    opening_hook: str = "",
    voice: str = "",
    sync_platforms: str = "",
    genre: str = "",
    short_text: str = "",
    user_details: str = "",
    task_path: str = "",
    need_images: int = 1,
) -> int:
    """创建新任务，返回 task.id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task (topic, title, account, type, need_images, status, task_path,
           app_id, author, theme, image_style, newspic_image_style,
           article_structure, opening_hook, voice, genre, short_text, sync_platforms, user_details,
           created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (topic, title, account, task_type, need_images, status, task_path,
         app_id, author, theme, image_style, newspic_image_style,
         article_structure, opening_hook, voice, genre, short_text, sync_platforms, user_details,
         now, now),
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def task_update(task_id: int, **kwargs) -> None:
    """
    更新任务字段。自动更新 updated_at。
    支持的字段: status, topic, title, task_path, app_id, author,
               image_style, theme, newspic_image_style, article_structure,
               opening_hook, voice, sync_platforms,
               word_count, ai_score, ai_verdict
    """
    allowed = {
        "status", "topic", "title", "task_path", "app_id", "author",
        "image_style", "theme", "newspic_image_style", "article_structure",
        "opening_hook", "voice", "genre", "short_text", "sync_platforms",
        "word_count", "ai_score", "ai_verdict", "need_images", "user_details",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return

    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]

    conn = get_connection()
    conn.execute(f"UPDATE task SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def task_get(task_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查询任务。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def task_list(
    page: int = 1, page_size: int = 20,
    status: Optional[str] = None,
    account: Optional[str] = None,
    task_type: Optional[str] = None,
    keyword: Optional[str] = None,
    created_after: Optional[int] = None,
    created_before: Optional[int] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple:
    """分页查询任务列表，返回 (items, total)。"""
    # 安全校验排序字段，防止 SQL 注入
    _allowed_sort = {"id", "topic", "type", "account", "status", "created_at", "updated_at"}
    if sort_by not in _allowed_sort:
        sort_by = "created_at"
    sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

    conn = get_connection()
    where = ["t.is_deleted = 0"]
    params: list = []

    # 状态多选：逗号分隔，如 "10,20,40"
    if status:
        status_list = [s.strip() for s in status.split(",") if s.strip().isdigit()]
        if status_list:
            placeholders = ",".join(["?" for _ in status_list])
            where.append(f"t.status IN ({placeholders})")
            params.extend(int(s) for s in status_list)

    if account:
        where.append("t.account = ?")
        params.append(account)
    if task_type:
        where.append("t.type = ?")
        params.append(task_type)
    if keyword:
        where.append("(t.topic LIKE ? OR t.title LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    if created_after:
        where.append("t.created_at >= ?")
        params.append(created_after)
    if created_before:
        where.append("t.created_at <= ?")
        params.append(created_before)

    where_clause = " AND ".join(where)

    # 总数
    count_sql = f"SELECT COUNT(*) FROM task t WHERE {where_clause}"
    total = conn.execute(count_sql, params).fetchone()[0]

    # 分页
    offset = (page - 1) * page_size
    data_sql = f"SELECT t.* FROM task t WHERE {where_clause} ORDER BY t.{sort_by} {sort_order} LIMIT ? OFFSET ?"
    rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def task_list_stuck(stale_before_ts: int) -> list:
    """查询长时间无心跳的非终态任务（进程崩溃后残留的僵尸任务）。

    只扫描中间状态（10~80），不包含已是失败状态（85/88）或终态（0/90）的任务。
    排除有待审记录（task_review.status='pending'）的任务——这些是正常等待人工审核。
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM task
           WHERE status >= 10 AND status <= 80
             AND status NOT IN (85, 88)
             AND updated_at < ?
             AND is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM task_review r
               WHERE r.task_id = task.id AND r.status = 'pending'
             )
           ORDER BY updated_at ASC""",
        (stale_before_ts,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# task_status_history 表 — 状态变更审计
# ============================================================

def status_history_insert(
    task_id: int,
    to_status: int,
    to_info: str = "",
    business_key: str = "",
    remark: str = "",
    operator: str = "system",
    duration_s: int = 0,
) -> int:
    """插入一条状态变更记录，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_status_history
           (task_id, to_status, business_key, to_info, remark, operator, duration_s, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, to_status, business_key, to_info, remark, operator, duration_s, now),
    )
    conn.commit()
    hist_id = cur.lastrowid
    conn.close()
    return hist_id


def status_transition(
    task_id: int,
    to_status: int,
    to_info: str = "",
    business_key: str = "",
    remark: str = "",
    operator: str = "system",
) -> int:
    """
    便捷方法：自动读取当前状态，写入新状态，
    同时更新 task.status。返回 history.id。

    这是日常使用最频繁的方法。
    """
    task = task_get(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")
    from_status = task["status"]
    if from_status == to_status:
        return 0  # 状态未变，不记录

    # 计算上一状态持续秒数
    duration_s = int(time.time()) - task["updated_at"]

    # 写入历史
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_status_history
           (task_id, to_status, business_key, to_info, remark, operator, duration_s, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, to_status, business_key, to_info, remark, operator, duration_s, now),
    )
    # 同时更新 task.status + updated_at
    conn.execute("UPDATE task SET status = ?, updated_at = ? WHERE id = ?",
                 (to_status, now, task_id))
    conn.commit()
    hist_id = cur.lastrowid
    conn.close()
    return hist_id


def status_history_list(task_id: int) -> List[Dict[str, Any]]:
    """查询某任务的所有状态变更记录。"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT h.*, ts.label AS to_label
           FROM task_status_history h
           LEFT JOIN task_status ts ON ts.code = h.to_status
           WHERE h.task_id = ? ORDER BY h.created_at""",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# task_image 表 — 生图记录
# ============================================================

def image_insert(
    task_id: int,
    seq: int = 1,
    prompt: str = "",
    provider: str = "",
    model: str = "",
    size: str = "",
    local_path: str = "",
    local_size: int = 0,
    width: int = 0,
    height: int = 0,
    fmt: str = "png",
    is_cover: bool = False,
    tokens_in: int = 0,
    tokens_out: int = 0,
    anchor: str = "",
    description: str = "",
    image_style: str = "",
    message_id: int = 0,
    upload_status: str = "pending",
    upload_error: str = "",
) -> int:
    """插入一条生图记录，返回 id。

    初始化时若未提供 prompt（如 md 流程导入的锚点图），
    用 description（锚点说明文字）兜底填充，保证记录不缺 prompt。
    """
    if not prompt and description:
        prompt = description
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_image
           (task_id, message_id, seq, anchor, description, prompt, provider, model, image_style, size,
            local_path, local_size, width, height, format,
            upload_status, upload_error, is_cover, tokens_in, tokens_out, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, message_id, seq, anchor, description, prompt, provider, model, image_style, size,
         local_path, local_size, width, height, fmt,
         upload_status, upload_error, 1 if is_cover else 0, tokens_in, tokens_out, now),
    )
    conn.commit()
    img_id = cur.lastrowid
    conn.close()
    return img_id


def image_update(image_id: int, **kwargs) -> None:
    """更新图片记录字段（生图结果 / 上传状态等）。"""
    allowed = {
        "local_path", "local_size", "width", "height", "format",
        "provider", "model", "size", "tokens_in", "tokens_out",
        "upload_status", "upload_cdn_url", "upload_media_id", "upload_error",
        "prompt", "description", "image_style", "message_id", "seq", "is_cover",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [image_id]
    conn = get_connection()
    conn.execute(f"UPDATE task_image SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def image_find_by_anchor(task_id: int, anchor: str) -> Optional[Dict[str, Any]]:
    """按 task_id + anchor 查找图片记录，无则返回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_image WHERE task_id = ? AND anchor = ? LIMIT 1",
        (task_id, anchor),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def image_find_by_seq(task_id: int, seq: int) -> Optional[Dict[str, Any]]:
    """按 task_id + seq 查找图片记录，无则返回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_image WHERE task_id = ? AND seq = ? LIMIT 1",
        (task_id, seq),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def image_find_cover(task_id: int, message_id: int = 0) -> Optional[Dict[str, Any]]:
    """按 task_id + is_cover=1 查找封面图记录。

    message_id > 0 时精确匹配某次 draft；= 0 时返回最新一条（ORDER BY message_id DESC）。
    无则返回 None。
    """
    conn = get_connection()
    if message_id > 0:
        row = conn.execute(
            "SELECT * FROM task_image WHERE task_id = ? AND is_cover = 1 AND message_id = ? LIMIT 1",
            (task_id, message_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM task_image WHERE task_id = ? AND is_cover = 1 ORDER BY message_id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def image_update_upload(
    image_id: int,
    upload_status: str,
    cdn_url: str = "",
    media_id: str = "",
    error: str = "",
) -> None:
    """更新图片上传状态。"""
    conn = get_connection()
    conn.execute(
        """UPDATE task_image
           SET upload_status = ?, upload_cdn_url = ?, upload_media_id = ?, upload_error = ?
           WHERE id = ?""",
        (upload_status, cdn_url, media_id, error, image_id),
    )
    conn.commit()
    conn.close()


def image_get(image_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查询单条图片记录。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_image WHERE id = ?", (image_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def image_delete(image_id: int) -> bool:
    """硬删除一条 task_image 记录，返回是否成功。"""
    conn = get_connection()
    cur = conn.execute("DELETE FROM task_image WHERE id = ?", (image_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def image_delete_by_task(task_id: int) -> int:
    """删除某任务的所有 task_image 记录，返回删除条数。"""
    conn = get_connection()
    cur = conn.execute("DELETE FROM task_image WHERE task_id = ?", (task_id,))
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def image_list_by_task(task_id: int) -> List[Dict[str, Any]]:
    """查询某任务的所有生图记录。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task_image WHERE task_id = ? ORDER BY seq",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# task_message 表 — 任务与大模型对话记录
# ============================================================

def task_message_insert(
    task_id: int,
    stage: str,
    provider: str,
    model: str,
    role: str,
    message: str = "",
    image_id: int = 0,
) -> int:
    """插入一条对话记录，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_message
           (task_id, image_id, stage, provider, model, role, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, image_id, stage, provider, model, role, message, now),
    )
    conn.commit()
    msg_id = cur.lastrowid
    conn.close()
    return msg_id


def task_message_exists(task_id: int, stage: str = "", image_id: int = 0) -> bool:
    """检查指定 task_id + stage（或 task_id + image_id）是否已有对话记录。"""
    conn = get_connection()
    if image_id > 0:
        row = conn.execute(
            "SELECT 1 FROM task_message WHERE task_id = ? AND image_id = ? LIMIT 1",
            (task_id, image_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM task_message WHERE task_id = ? AND stage = ? LIMIT 1",
            (task_id, stage),
        ).fetchone()
    conn.close()
    return row is not None


def task_message_append(
    task_id: int,
    stage: str,
    provider: str,
    model: str,
    role: str,
    message: str = "",
    image_id: int = 0,
) -> bool:
    """
    智能追加对话记录。
    - 该 task_id + stage（或 image_id）首次写入时，允许任意 role。
    - 已有记录时，仅允许 role=user 或 role=tool 写入（拒绝 system/assistant 重复）。
    返回 True 表示已写入，False 表示被跳过。
    """
    exists = task_message_exists(task_id, stage, image_id)
    if exists and role not in (Role.USER, Role.TOOL):
        return False
    task_message_insert(task_id, stage, provider, model, role, message, image_id)
    return True


def task_message_list(task_id: int, stage: str = "",
                      image_id: int = 0) -> List[Dict[str, Any]]:
    """查询对话记录。可按 stage 或 image_id 过滤。"""
    conn = get_connection()
    if image_id > 0:
        rows = conn.execute(
            "SELECT * FROM task_message WHERE task_id = ? AND image_id = ? ORDER BY id",
            (task_id, image_id),
        ).fetchall()
    elif stage:
        rows = conn.execute(
            "SELECT * FROM task_message WHERE task_id = ? AND stage = ? ORDER BY id",
            (task_id, stage),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM task_message WHERE task_id = ? ORDER BY stage, id",
            (task_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def task_message_get_last_assistant(task_id: int, stage: str) -> int:
    """获取指定 task_id + stage 最后一条 assistant 消息的 id，无则返回 0。"""
    conn = get_connection()
    row = conn.execute(
        """SELECT id FROM task_message
           WHERE task_id = ? AND stage = ? AND role = 'assistant'
           ORDER BY id DESC LIMIT 1""",
        (task_id, stage),
    ).fetchone()
    conn.close()
    return row["id"] if row else 0


# ============================================================
# llm_call_log 表 — 大模型调用日志
# ============================================================

def llm_log_insert(
    task_id: int = 0,
    call_type: str = "text",       # "text" | "image"
    stage: str = "",
    provider: str = "",
    model: str = "",
    prompt: str = "",
    prompt_chars: int = 0,
    response: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    image_count: int = 0,
    image_size: str = "",
    duration_ms: int = 0,
    status: str = "success",
    finish_msg: str = "",
    retry_count: int = 0,
    cost_est: float = 0.0,
) -> int:
    """插入一条 LLM 调用日志，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO llm_call_log
           (task_id, call_type, stage, provider, model,
            prompt, prompt_chars, response,
            tokens_in, tokens_out, image_count, image_size,
            duration_ms, status, finish_msg, retry_count, cost_est, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, call_type, stage, provider, model,
         prompt, prompt_chars, response,
         tokens_in, tokens_out, image_count, image_size,
         duration_ms, status, finish_msg, retry_count, cost_est, now),
    )
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id


def llm_log_update(log_id: int, **kwargs) -> None:
    """更新 LLM 调用日志（如补写 response / tokens / duration）。"""
    allowed = {"response", "tokens_in", "tokens_out", "duration_ms",
               "status", "finish_msg", "cost_est"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [log_id]
    conn = get_connection()
    conn.execute(f"UPDATE llm_call_log SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


# ============================================================
# publish_record 表 — 发布记录
# ============================================================

def publish_record_insert(
    task_id: int,
    platform: str = "wechat",
    publish_type: str = "draft",
    media_id: str = "",
    title: str = "",
    digest: str = "",
    url: str = "",
    image_count: int = 0,
    word_count: int = 0,
    ai_score_at_pub: float = 0.0,
    status: str = "success",
    error_msg: str = "",
    published_at: Optional[int] = None,
) -> int:
    """插入一条发布记录，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO publish_record
           (task_id, platform, publish_type, media_id, title, digest, url,
            image_count, word_count, ai_score_at_pub, status, error_msg,
            published_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, platform, publish_type, media_id, title, digest, url,
         image_count, word_count, ai_score_at_pub, status, error_msg,
         published_at, now),
    )
    conn.commit()
    rec_id = cur.lastrowid
    conn.close()
    return rec_id


def publish_record_update(pub_id: int, **kwargs) -> None:
    """更新发布记录。"""
    allowed = {"media_id", "url", "status", "error_msg", "published_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [pub_id]
    conn = get_connection()
    conn.execute(f"UPDATE publish_record SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def publish_record_list_by_task(task_id: int) -> list[dict]:
    """获取某个任务的所有发布记录（含发布 URL）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM publish_record WHERE task_id = ? ORDER BY id ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# task_review 表 — 审核记录
# ============================================================

def task_review_insert(
    task_id: int,
    stage: int,
    status: str = "pending",
    reviewer: str = "",
    comment: str = "",
) -> int:
    """创建审核记录，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_review (task_id, stage, status, reviewer, comment, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, stage, status, reviewer, comment, now, now),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def task_review_update(review_id: int, **kwargs) -> None:
    """更新审核记录。"""
    allowed = {"status", "reviewer", "comment"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [review_id]
    conn = get_connection()
    conn.execute(f"UPDATE task_review SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def task_review_get(review_id: int) -> dict | None:
    """获取单条审核记录。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM task_review WHERE id = ?", (review_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def task_review_get_pending(task_id: int, stage: int) -> dict | None:
    """获取某任务某节点的待审核记录（同一节点不应有多个 pending）。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_review WHERE task_id = ? AND stage = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (task_id, stage),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def task_review_list_by_task(task_id: int) -> list[dict]:
    """获取某个任务的所有审核记录。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task_review WHERE task_id = ? ORDER BY id ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def task_review_list_queue(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    task_type: str | None = None,
    stage: int | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple:
    """分页查询审核队列（关联 task 表获取 topic/type/account）。"""
    # tr.* 列 + task 表关联列
    _allowed_sort = {"id", "task_id", "stage", "status", "created_at", "updated_at", "topic", "type"}
    if sort_by not in _allowed_sort:
        sort_by = "created_at"
    sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

    # 确定排序前缀：topic/type 来自 task 表，其余来自 task_review 表
    if sort_by in ("topic", "type"):
        order_col = f"t.{sort_by}"
    else:
        order_col = f"tr.{sort_by}"

    conn = get_connection()
    where = ["1=1"]
    params: list = []

    if status:
        where.append("tr.status = ?")
        params.append(status)
    if stage:
        where.append("tr.stage = ?")
        params.append(stage)
    if task_type:
        where.append("t.type = ?")
        params.append(task_type)
    if date_from:
        where.append("tr.created_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("tr.created_at <= ?")
        params.append(date_to)

    where_clause = " AND ".join(where)

    count_sql = f"""SELECT COUNT(*) FROM task_review tr
        LEFT JOIN task t ON t.id = tr.task_id
        WHERE {where_clause}"""
    total = conn.execute(count_sql, params).fetchone()[0]

    offset = (page - 1) * page_size
    data_sql = f"""SELECT tr.*, t.topic, t.type, t.account
        FROM task_review tr
        LEFT JOIN task t ON t.id = tr.task_id
        WHERE {where_clause}
        ORDER BY {order_col} {sort_order}
        LIMIT ? OFFSET ?"""
    rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


# ============================================================
# 硬删除 —— 删除任务及其所有关联数据
# ============================================================

# ============================================================
# task_sync 表 — 多平台同步记录
# ============================================================

def task_sync_upsert(
    task_id: Optional[int] = None,
    markdown_content: str = "",
    platforms: str = "[]",
    sync_from: str = "task",
    url: Optional[str] = None,
    file_path: Optional[str] = None,
    status: str = "pending",
) -> int:
    """创建或覆盖同步记录，返回 id。
     - sync_from='task' + task_id 非空 → 按 task_id 查重，存在则 UPDATE
     - sync_from='local'/'url' → 直接 INSERT（不查重）
    """
    conn = get_connection()
    now = int(time.time())

    if sync_from == "task" and task_id is not None:
        existing = conn.execute(
            "SELECT id FROM task_sync WHERE task_id = ? AND sync_from = 'task'",
            (task_id,),
        ).fetchone()
        if existing:
            sync_id = existing["id"]
            conn.execute(
                """UPDATE task_sync SET markdown_content = ?, platforms = ?,
                   sync_from = ?, url = ?, file_path = ?,
                   status = ?, updated_at = ? WHERE id = ?""",
                (markdown_content, platforms, sync_from, url, file_path, status, now, sync_id),
            )
            conn.commit()
            conn.close()
            return sync_id

    cur = conn.execute(
        """INSERT INTO task_sync
           (task_id, markdown_content, platforms, sync_from, url, file_path, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, markdown_content, platforms, sync_from, url, file_path, status, now, now),
    )
    sync_id = cur.lastrowid
    conn.commit()
    conn.close()
    return sync_id


def task_sync_update(sync_id: int, **kwargs) -> None:
    """更新同步记录字段。supported: markdown_content, platforms, status, sync_from, url, file_path"""
    allowed = {"markdown_content", "platforms", "status", "sync_from", "url", "file_path"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [sync_id]
    conn = get_connection()
    conn.execute(f"UPDATE task_sync SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def task_sync_get(sync_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查询同步记录。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM task_sync WHERE id = ?", (sync_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def task_sync_get_by_task_id(task_id: int) -> Optional[Dict[str, Any]]:
    """按 task_id 查询同步记录。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_sync WHERE task_id = ?", (task_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def task_sync_list(
    page: int = 1, page_size: int = 20,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple:
    """分页查询同步记录列表（JOIN task 表获取 topic/title），返回 (items, total)。"""
    _allowed_sort = {"id", "task_id", "status", "created_at", "updated_at", "sync_from", "topic", "title"}
    if sort_by not in _allowed_sort:
        sort_by = "created_at"
    sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

    # 映射排序字段到正确的表前缀
    _sort_map = {
        "sync_from": "ts.sync_from",
        "topic": "t.topic",
        "title": "t.title",
    }
    sort_col = _sort_map.get(sort_by, f"ts.{sort_by}")

    conn = get_connection()
    where = ["1=1"]
    params: list = []

    if status:
        where.append("ts.status = ?")
        params.append(status)

    where_clause = " AND ".join(where)

    count_sql = f"SELECT COUNT(*) FROM task_sync ts WHERE {where_clause}"
    total = conn.execute(count_sql, params).fetchone()[0]

    offset = (page - 1) * page_size
    data_sql = f"""SELECT ts.*, t.topic, t.title,
            (SELECT COUNT(*) FROM task_sync_result WHERE task_sync_id = ts.id) AS result_count
        FROM task_sync ts
        LEFT JOIN task t ON t.id = ts.task_id
        WHERE {where_clause}
        ORDER BY {sort_col} {sort_order}
        LIMIT ? OFFSET ?"""
    rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


# ============================================================
# task_sync_result 表 — 同步各平台结果
# ============================================================

def task_sync_result_insert(
    task_sync_id: int,
    platform: str,
    status: str = "pending",
    error_msg: str = "",
) -> int:
    """插入一条平台同步结果，返回 id。"""
    conn = get_connection()
    now = int(time.time())
    cur = conn.execute(
        """INSERT INTO task_sync_result (task_sync_id, platform, status, error_msg, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (task_sync_id, platform, status, error_msg, now),
    )
    conn.commit()
    result_id = cur.lastrowid
    conn.close()
    return result_id


def task_sync_result_list_by_sync_id(task_sync_id: int) -> List[Dict[str, Any]]:
    """查询某个同步记录的所有平台结果。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task_sync_result WHERE task_sync_id = ? ORDER BY id",
        (task_sync_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def task_sync_result_delete_by_sync_id(task_sync_id: int) -> None:
    """删除某个同步记录的所有平台结果（覆盖更新时先删旧数据）。"""
    conn = get_connection()
    conn.execute("DELETE FROM task_sync_result WHERE task_sync_id = ?", (task_sync_id,))
    conn.commit()
    conn.close()


def task_delete_hard(task_id: int) -> dict:
    """硬删除任务：删除 task 及所有关联表记录，返回被删除的 task_path 等信息。"""
    conn = get_connection()
    task = dict(conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone() or {})

    if not task:
        conn.close()
        return {}

    task_path = task.get("task_path", "")

    # 按外键依赖顺序删除
    conn.execute("DELETE FROM task_message WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM task_image WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM task_status_history WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM llm_call_log WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM publish_record WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    return {"task_id": task_id, "task_path": task_path, "topic": task.get("topic", "")}
