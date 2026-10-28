#!/usr/bin/env python3
"""Pipeline DB 辅助函数 —— 所有操作以 task_id 为参数。"""

from __future__ import annotations

import json

from engine.constants import Status, Operator
from engine.logger import get_logger

logger = get_logger(__name__)


def db_task_create(account: str, topic: str, account_cfg: dict = None,
                   task_path: str = "", task_type: str = "article",
                   need_images: int = 1, user_details: str = "") -> int:
    """根据用户输入的 topic 和 config.yaml 账号配置创建任务记录。返回 task_id。"""
    try:
        from engine.db.models import task_insert

        cfg = account_cfg or {}
        sync_platforms = cfg.get("sync_platforms")
        if isinstance(sync_platforms, list):
            sync_platforms_str = json.dumps(sync_platforms, ensure_ascii=False)
        elif sync_platforms:
            sync_platforms_str = str(sync_platforms)
        else:
            sync_platforms_str = ""

        tid = task_insert(
            account=account,
            topic=topic,
            task_path=task_path,
            app_id=cfg.get("app_id", ""),
            author=cfg.get("author", ""),
            theme=cfg.get("theme", ""),
            image_style=cfg.get("image_style", ""),
            newspic_image_style=cfg.get("newspic_image_style", ""),
            article_structure=cfg.get("article_structure", ""),
            opening_hook=cfg.get("opening_hook", ""),
            voice=cfg.get("voice", ""),
            task_type=task_type,
            sync_platforms=sync_platforms_str,
            need_images=need_images,
            user_details=user_details,
        )
        logger.info("DB: task=%d 已创建 topic=%s path=%s", tid, topic, task_path)
        return tid
    except Exception as e:
        logger.error("DB: 创建任务失败 topic=%s account=%s: %s", topic, account, e)
        return 0


def db_transition(tid: int, status: int, info: str, remark: str = "", **fields) -> None:
    """更新任务字段并记录状态变更。tid=0 时静默跳过。"""
    if not tid:
        return
    try:
        from engine.db.models import task_update, status_transition

        if fields:
            task_update(tid, **fields)
        status_transition(tid, status, to_info=info, remark=remark, operator=Operator.PIPELINE)
    except Exception as e:
        logger.error("DB: db_transition 失败 task=%d status=%d: %s", tid, status, e)


def db_image_record(tid: int, seq: int, prompt: str, provider: str,
                    model: str, local_path: str, image_bytes: bytes,
                    img_size: str = "1200*900", message_id: int = 0) -> int:
    """记录生图日志到 task_image 表，返回 image_id。tid=0 时返回 0。"""
    if not tid:
        return 0
    try:
        from engine.db.models import image_insert

        from engine.utils import get_png_dimensions
        w, h = get_png_dimensions(image_bytes)
        est_in = max(1, len(prompt) // 3)
        est_out = max(1, len(image_bytes) // 200)
        img_id = image_insert(task_id=tid, message_id=message_id, seq=seq,
                              prompt=prompt, provider=provider, model=model,
                              size=img_size, local_path=local_path,
                              local_size=len(image_bytes), width=w, height=h, fmt="png",
                              tokens_in=est_in, tokens_out=est_out)
        return img_id
    except Exception as e:
        logger.error("DB: 写入 task_image 失败 task=%d seq=%d: %s", tid, seq, e)
        return 0
