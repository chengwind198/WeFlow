"""审核服务 —— 审核队列查询、审核详情、通过/驳回操作。"""

import os
import threading
from typing import Optional

from engine.db.models import (
    task_review_get,
    task_review_list_queue,
    task_review_update,
    task_get,
)
from engine.logger import get_logger

logger = get_logger(__name__)


def list_queue(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    stage: Optional[int] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """分页查询审核队列。"""
    rows, total = task_review_list_queue(
        page=page, page_size=page_size,
        status=status, task_type=task_type, stage=stage,
        sort_by=sort_by, sort_order=sort_order,
        date_from=date_from, date_to=date_to,
    )
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "task_id": r["task_id"],
            "stage": r["stage"],
            "status": r["status"],
            "reviewer": r.get("reviewer", ""),
            "comment": r.get("comment", ""),
            "topic": r.get("topic", ""),
            "type": r.get("type", ""),
            "account": r.get("account", ""),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_detail(review_id: int) -> dict | None:
    """获取审核详情，包含任务信息。stage=60 时额外返回图片列表。"""
    review = task_review_get(review_id)
    if not review:
        return None

    task = task_get(review["task_id"])
    result = {
        "id": review["id"],
        "task_id": review["task_id"],
        "stage": review["stage"],
        "status": review["status"],
        "reviewer": review.get("reviewer", ""),
        "comment": review.get("comment", ""),
        "topic": task.get("topic", "") if task else "",
        "type": task.get("type", "") if task else "",
        "account": task.get("account", "") if task else "",
        "task_status": task.get("status", 0) if task else 0,
        "task_path": task.get("task_path", "") if task else "",
        "created_at": review["created_at"],
        "updated_at": review["updated_at"],
    }

    # stage=20 + image 类型：返回结构化审核数据（title/short_text/卡片列表=images）
    if review["stage"] == 20 and result.get("type") == "image":
        result["task_title"] = task.get("title", "") if task else ""
        result["short_text"] = task.get("short_text", "") if task else ""
        result["image_style"] = task.get("image_style", "") if task else ""
        try:
            from engine.db.models import image_list_by_task
            imgs = image_list_by_task(review["task_id"])
            result["images"] = imgs  # 复用 ImageReviewCard 组件
            result["cards"] = [
                {"id": img["id"], "seq": img["seq"], "description": img.get("description", ""),
                 "image_style": img.get("image_style", ""), "prompt": img.get("prompt", "")}
                for img in imgs
            ]
        except Exception as e:
            logger.warning("加载卡片列表失败 task_id=%d: %s", review["task_id"], e)
            result["images"] = []
            result["cards"] = []
    # stage=60 或 article 类型 stage=40 时返回配图列表
    elif review["stage"] == 60 or (review["stage"] == 40 and result.get("type") == "article"):
        try:
            from engine.db.models import image_list_by_task
            result["images"] = image_list_by_task(review["task_id"])
        except Exception as e:
            logger.warning("加载配图列表失败 task_id=%d: %s", review["task_id"], e)
            result["images"] = []

    return result


def _record_review_in_history(task_id: int, stage: int, action: str,
                              reviewer: str = "", comment: str = "") -> None:
    """在 task_status_history 中记录审核事件。

    审核不会改变 task.status，但通过 status_history_insert 直接写入一条
    同状态的记录，注明审核阶段、审核人和备注信息。
    """
    try:
        from engine.db.models import task_get, status_history_insert

        task = task_get(task_id)
        if not task:
            return

        current_status = task.get("status", 0)

        stage_labels = {20: "选题简报", 40: "文章草稿", 60: "配图审核"}
        stage_label = stage_labels.get(stage, f"阶段{stage}")

        action_label = "通过" if action == "approved" else "驳回"
        reviewer_info = f" · 审核人: {reviewer}" if reviewer else ""

        to_info = f"「{stage_label}」审核{action_label}{reviewer_info}"

        status_history_insert(
            task_id=task_id,
            to_status=current_status,
            to_info=to_info,
            remark=comment or "",
            operator=reviewer or "system",
        )
        logger.info("审核记录已写入 status_history: task_id=%d stage=%d action=%s",
                    task_id, stage, action)
    except Exception as e:
        logger.warning("写入审核记录到 status_history 失败: %s", e)


def approve(review_id: int, reviewer: str = "", comment: str = "") -> dict:
    """通过审核。

    1. 更新审核记录为 approved
    2. 在后台线程继续执行 pipeline（从当前阶段继续）
    """
    review = task_review_get(review_id)
    if not review:
        raise ValueError(f"审核记录 {review_id} 不存在")

    if review["status"] != "pending":
        raise ValueError(f"审核记录状态为 '{review['status']}'，无法通过")

    task_id = review["task_id"]
    stage = review["stage"]

    # 更新审核记录
    task_review_update(review_id, status="approved", reviewer=reviewer, comment=comment)
    logger.info("审核通过: review_id=%d task_id=%d stage=%d reviewer=%s",
                review_id, task_id, stage, reviewer)

    # 在 task_status_history 中留下审核记录（状态不变，但记录审核事件）
    _record_review_in_history(task_id, stage, "approved", reviewer, comment)

    # 后台继续执行 pipeline
    _continue_pipeline(task_id, stage)

    return {
        "review_id": review_id,
        "task_id": task_id,
        "action": "approved",
        "message": f"审核已通过，任务继续执行（从阶段 {stage} 开始）",
    }


def reject(review_id: int, reviewer: str = "", comment: str = "") -> dict:
    """驳回审核。

    更新审核记录为 rejected，任务保持当前状态等待人工修复。
    """
    review = task_review_get(review_id)
    if not review:
        raise ValueError(f"审核记录 {review_id} 不存在")

    if review["status"] != "pending":
        raise ValueError(f"审核记录状态为 '{review['status']}'，无法驳回")

    task_id = review["task_id"]

    task_review_update(review_id, status="rejected", reviewer=reviewer, comment=comment)
    logger.info("审核驳回: review_id=%d task_id=%d reviewer=%s comment=%s",
                review_id, task_id, reviewer, comment[:100])

    # 在 task_status_history 中留下审核记录
    _record_review_in_history(task_id, review["stage"], "rejected", reviewer, comment)

    return {
        "review_id": review_id,
        "task_id": task_id,
        "action": "rejected",
        "message": "审核已驳回",
    }


def _continue_pipeline(task_id: int, from_stage: int) -> None:
    """在后台线程中继续执行 pipeline（审核通过后调用）。

    防御性检查：如果任务状态已经推进到比审核阶段更后面，
    说明 pipeline 已在审核批准前跑过了（例如配置变更、手动触发等），
    此时跳过重复执行，避免重复生图、重复创建审核记录。
    """
    from engine.constants import Status

    task = task_get(task_id)
    if not task:
        logger.error("审核通过后继续 pipeline 失败: task_id=%d 不存在", task_id)
        return

    current_status = task.get("status", 0)
    # stage=20 → status=20, stage=40 → status=40, stage=60 → status=60
    # 如果任务已推进到更后面的状态，说明这个审核阶段的工作已经完成，无需重新执行
    if current_status > from_stage:
        logger.info(
            "审核通过后跳过 pipeline: task_id=%d 当前状态=%d > from_stage=%d，"
            "任务已推进到更后面的阶段，无需重复执行",
            task_id, current_status, from_stage,
        )
        return

    task_type = task.get("type", "article")
    task_path = task.get("task_path", "")
    if task_path and not os.path.isabs(task_path):
        from engine.config import get_project_root
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    def _run():
        try:
            from engine.pipeline import retry_run as pipeline_retry_run
            pipeline_retry_run(
                task_id=task_id,
                task_type=task_type,
                topic=task.get("topic", ""),
                account=task.get("account", "main"),
                task_path=task_path,
                retry_from=from_stage,
                theme=task.get("theme"),
                image_style=task.get("image_style"),
                article_structure=task.get("article_structure"),
                opening_hook=task.get("opening_hook"),
                voice=task.get("voice"),
                genre=task.get("genre"),
                no_images=(task.get("need_images", 1) == 0),
                user_details=task.get("user_details", ""),
            )
        except Exception as e:
            import traceback
            logger.error(
                "审核后继续 pipeline 失败 task_id=%d: %s\n%s",
                task_id, e, traceback.format_exc(),
            )
            try:
                from engine.db.models import task_get, status_transition
                from engine.constants import Status
                current = task_get(task_id)
                last_status = current.get("status", 10) if current else 10
                # 若流程内已落具体失败状态（88 发布失败 / 85 检测未过），
                # 不再覆盖为 ABANDONED，任务可走对应重试路径
                if last_status in (Status.PUBLISH_FAILED, Status.AI_SCORE_FAILED):
                    logger.info("任务 %d 已在状态 %d 记录失败原因，跳过 ABANDONED",
                                task_id, last_status)
                else:
                    status_transition(
                        task_id, Status.ABANDONED,
                        to_info=f"审核通过后继续执行异常 (from_stage={from_stage}): {str(e)[:200]}",
                        remark=traceback.format_exc()[:1000],
                        operator="system",
                    )
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()
    logger.info("审核通过，已启动后台 pipeline: task_id=%d from_stage=%d", task_id, from_stage)
