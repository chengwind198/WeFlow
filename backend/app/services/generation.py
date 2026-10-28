"""业务服务层 —— 封装 engine/ 下的现有功能，以异步方式暴露给 API 层。

所有耗时操作（LLM 调用、图片生成、发布）在线程池中运行，避免阻塞事件循环。
"""

import os
import sys
import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 确保 backend/ 目录在 sys.path 中，使 engine 包可导入
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ============================================================
# 任务管理（直接操作 DB）
# ============================================================

async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    account: Optional[str] = None,
    keyword: Optional[str] = None,
    created_after: Optional[int] = None,
    created_before: Optional[int] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    """分页查询任务列表。"""
    return await asyncio.to_thread(
        _list_tasks_sync, page, page_size, status, task_type, account,
        keyword, created_after, created_before, sort_by, sort_order,
    )


def _list_tasks_sync(
    page: int, page_size: int, status: Optional[str],
    task_type: Optional[str], account: Optional[str], keyword: Optional[str],
    created_after: Optional[int] = None, created_before: Optional[int] = None,
    sort_by: str = "created_at", sort_order: str = "desc",
) -> dict:
    from engine.db.models import task_list
    from engine.constants import Status

    items, total = task_list(
        page=page, page_size=page_size,
        status=status, account=account, task_type=task_type,
        keyword=keyword, created_after=created_after, created_before=created_before,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {
        "items": [
            {**item, "status_label": Status.label(item.get("status", 0))}
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_task(task_id: int) -> dict | None:
    """获取任务详情（含文章内容、图片、对话记录）。"""
    return await asyncio.to_thread(_get_task_sync, task_id)


def _get_task_sync(task_id: int) -> dict | None:
    from engine.db.models import task_get, image_list_by_task, status_history_list, publish_record_list_by_task
    from engine.constants import Status

    task = task_get(task_id)
    if not task:
        return None

    task["status_label"] = Status.label(task.get("status", 0))

    # 补充账号名称（task 表只存 account key）
    try:
        from engine.config import get_config as _get_account_cfg
        acc_cfg = _get_account_cfg(task.get("account", "main"))
        task["account_name"] = acc_cfg.get("account_name", task.get("account", ""))
    except Exception:
        task["account_name"] = task.get("account", "")

    # 文章内容 & 简报
    brief = ""
    markdown = ""
    html = ""
    task_path = task.get("task_path", "")
    if task_path:
        # 将相对路径转为绝对路径（相对于项目根目录）
        if not os.path.isabs(task_path):
            from engine.config import get_project_root
            task_path = os.path.normpath(os.path.join(get_project_root(), task_path))
        from engine.config import get_brief_path, get_article_path, get_article_html_path
        brief_md = get_brief_path(task_path)
        article_md = get_article_path(task_path)
        article_html = get_article_html_path(task_path)
        if os.path.exists(brief_md):
            with open(brief_md, encoding="utf-8") as f:
                brief = f.read()
        if os.path.exists(article_md):
            with open(article_md, encoding="utf-8") as f:
                markdown = f.read()
        if os.path.exists(article_html):
            with open(article_html, encoding="utf-8") as f:
                html = f.read()
            # 将本地图片路径替换为后端绝对 URL
            from app.core.config import settings
            base = f"http://{settings.host}:{settings.port}{settings.api_v1_prefix}/tasks/{task_id}/files/"
            import re
            html = re.sub(r'src="(images/[^"]+)"', rf'src="{base}\1"', html)
            html = re.sub(r"src='(images/[^']+)'", rf"src='{base}\1'", html)
            html = re.sub(r'src="(images\\[^"]+)"', rf'src="{base}\1"', html)
            html = html.replace('\\', '/')

    task["brief"] = brief
    task["markdown"] = markdown
    task["html"] = html
    task["images"] = image_list_by_task(task_id)
    task["messages"] = _get_task_messages(task_id)
    task["status_history"] = status_history_list(task_id)
    task["publish_records"] = publish_record_list_by_task(task_id)
    task["review_records"] = _get_review_records(task_id)
    return task


def _get_review_records(task_id: int) -> list[dict]:
    """获取任务的审核记录。"""
    try:
        from engine.db.models import task_review_list_by_task
        return task_review_list_by_task(task_id)
    except Exception:
        return []


def _get_task_messages(task_id: int) -> list[dict]:
    """获取任务的对话历史。"""
    try:
        from engine.db.models import task_message_list
        return task_message_list(task_id)
    except Exception:
        return []


async def delete_task(task_id: int) -> bool:
    """软删除任务。"""
    return await asyncio.to_thread(_delete_task_sync, task_id)


def _delete_task_sync(task_id: int) -> bool:
    import shutil
    from engine.db.models import task_delete_hard
    from engine.config import get_project_root
    try:
        result = task_delete_hard(task_id)
        if not result:
            return False
        # 删除任务产物目录
        task_path = result.get("task_path", "")
        if task_path:
            if not os.path.isabs(task_path):
                task_path = os.path.normpath(os.path.join(get_project_root(), task_path))
            if os.path.isdir(task_path):
                shutil.rmtree(task_path)
        return True
    except Exception:
        return False


def _extract_frontmatter(file_path: str) -> str | None:
    """从文件中提取 YAML frontmatter（--- ... ---）。若文件不存在或无 frontmatter 则返回 None。"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            old = f.read()
        trimmed = old.strip()
        if trimmed.startswith("---"):
            end = trimmed.find("---", 3)
            if end != -1:
                return trimmed[:end + 3]  # 含首尾 ---
    except Exception:
        pass
    return None


def _preserve_frontmatter(file_path: str, new_content: str) -> str:
    """如果新内容不以 --- 开头，尝试从旧文件中提取 frontmatter 拼接到前面。"""
    stripped = new_content.strip()
    if stripped.startswith("---"):
        return new_content  # 已有 frontmatter，不处理
    fm = _extract_frontmatter(file_path)
    if fm:
        return fm + "\n" + stripped
    return new_content


def update_brief(task_id: int, content: str) -> dict:
    """更新选题简报内容。

    允许以下两种场景：
    1. 任务状态为 0 且从 20 转入（原有逻辑：简报阶段出错后修改）
    2. 任务状态为 20 且存在待审核的 stage=20 审核记录（审核页编辑简报）
    """
    from engine.db.models import task_get, status_history_list, task_review_list_by_task
    from engine.config import get_project_root, get_brief_path

    # 1. 获取任务
    task = task_get(task_id)
    if not task:
        raise ValueError("任务不存在")

    status = task.get("status")

    # 2. 校验权限：优先检查是否存在待审核的 stage=20 记录（审核页编辑）
    reviews = task_review_list_by_task(task_id)
    has_pending_stage20 = any(
        r.get("status") == "pending" and r.get("stage") == 20
        for r in reviews
    )
    if has_pending_stage20:
        pass  # 有待审核记录，允许编辑
    elif status == 0:
        # 兼容旧逻辑：状态 0 + 流转 20→0（简报阶段出错后修改）
        history = status_history_list(task_id)
        transition_20_to_0 = False
        for i in range(1, len(history)):
            if history[i].get("to_status") == 0 and history[i - 1].get("to_status") == 20:
                transition_20_to_0 = True
                break
        if not transition_20_to_0:
            raise ValueError("仅从'简报已就绪'阶段终止的任务可修改简报")
    else:
        raise ValueError("当前任务没有待审核的选题简报，无法编辑")

    # 4. 获取简报文件路径
    task_path = task.get("task_path", "")
    if not task_path:
        raise ValueError("任务无产物目录")

    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    brief_path = get_brief_path(task_path)

    # 5. 写入新内容（保留原有 YAML frontmatter）
    os.makedirs(os.path.dirname(brief_path), exist_ok=True)
    preserved = _preserve_frontmatter(brief_path, content)
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(preserved)

    return {"task_id": task_id, "message": "简报已保存"}


def update_article(task_id: int, content: str) -> dict:
    """更新文章草稿内容（article.md）。

    允许以下两种场景：
    1. 任务状态为 0 且从 40 转入（文章阶段出错后修改）
    2. 任务状态为 40 且存在待审核的 stage=40 审核记录（审核页编辑文章）
    """
    from engine.db.models import task_get, status_history_list, task_review_list_by_task
    from engine.config import get_project_root, get_article_path

    # 1. 获取任务
    task = task_get(task_id)
    if not task:
        raise ValueError("任务不存在")

    status = task.get("status")

    # 2. 校验权限：优先检查是否存在待审核的 stage=40 记录（审核页编辑）
    from engine.constants import TaskType, Status as S
    task_type = task.get("type", "article")
    reviews = task_review_list_by_task(task_id)
    has_pending_stage40 = any(
        r.get("status") == "pending" and r.get("stage") == 40
        for r in reviews
    )
    if has_pending_stage40:
        pass  # 有待审核记录，允许编辑
    elif status == 0:
        # 兼容旧逻辑：状态 0 + 流转 40→0（文章阶段出错后修改）
        history = status_history_list(task_id)
        transition_40_to_0 = False
        for i in range(1, len(history)):
            if history[i].get("to_status") == 0 and history[i - 1].get("to_status") == 40:
                transition_40_to_0 = True
                break
        if not transition_40_to_0:
            raise ValueError("仅从'文章已就绪'阶段终止的任务可修改文章")
    elif task_type == TaskType.MD and status == S.AI_SCORE_FAILED:
        # md 去味发布：AI 味未过（85）允许人工改稿，改后重试将重新人味化
        pass
    else:
        raise ValueError("当前任务没有待审核的文章草稿，无法编辑")

    # 3. 获取文章文件路径
    task_path = task.get("task_path", "")
    if not task_path:
        raise ValueError("任务无产物目录")

    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    article_path = get_article_path(task_path)

    # 4. 写入新内容（保留原有 YAML frontmatter）
    os.makedirs(os.path.dirname(article_path), exist_ok=True)
    preserved = _preserve_frontmatter(article_path, content)
    with open(article_path, "w", encoding="utf-8") as f:
        f.write(preserved)

    return {"task_id": task_id, "message": "文章已保存"}


# ============================================================
# 图片管理（审核阶段操作）
# ============================================================

def _check_image_ops_allowed(task_id: int) -> dict:
    """检查是否允许图片操作（删除/替换/重新生成/更新）。

    允许条件：任务未发布（status < 90）即可。具体的图片记录存在性由各函数自行校验。
    即使任务处于出错/终止等中间状态，只要图片记录存在就允许操作。
    返回 task 字典供后续使用。
    """
    from engine.db.models import task_get

    task = task_get(task_id)
    if not task:
        raise ValueError("任务不存在")

    status = task.get("status", 0)

    if status >= 90:
        raise ValueError("任务已发布，无法操作图片")

    return task


def delete_task_image(task_id: int, image_id: int) -> dict:
    """删除任务图片。"""
    from engine.db.models import image_get, image_delete

    # 权限校验
    try:
        _check_image_ops_allowed(task_id)
    except ValueError as e:
        logger.warning("删除图片被拒: task_id=%d image_id=%d: %s", task_id, image_id, e)
        raise

    img = image_get(image_id)
    if not img:
        logger.warning("删除图片被拒: task_id=%d image_id=%d 原因=记录不存在", task_id, image_id)
        raise ValueError("图片记录不存在")
    if img["task_id"] != task_id:
        logger.warning("删除图片被拒: task_id=%d image_id=%d 原因=不属于该任务(属于task_id=%d)", task_id, image_id, img["task_id"])
        raise ValueError("图片不属于该任务")

    # 删除本地文件
    local_path = img.get("local_path", "")
    if local_path:
        # 获取任务产物目录
        from engine.db.models import task_get
        from engine.config import get_project_root
        task = task_get(task_id)
        task_path = task.get("task_path", "") if task else ""
        if task_path:
            if not os.path.isabs(task_path):
                task_path = os.path.normpath(os.path.join(get_project_root(), task_path))
            file_path = os.path.join(task_path, "images", os.path.basename(local_path))
            if os.path.isfile(file_path):
                os.remove(file_path)

    image_delete(image_id)
    logger.info("图片已删除: task_id=%d image_id=%d local_path=%s", task_id, image_id, local_path)
    return {"task_id": task_id, "image_id": image_id, "action": "deleted"}


def replace_task_image(task_id: int, image_id: int, file_data: bytes, filename: str) -> dict:
    """用本地上传文件替换任务图片。"""
    from engine.db.models import image_get, image_update
    from engine.utils import get_png_dimensions

    # 权限校验
    try:
        _check_image_ops_allowed(task_id)
    except ValueError as e:
        logger.warning("替换图片被拒: task_id=%d image_id=%d: %s", task_id, image_id, e)
        raise

    img = image_get(image_id)
    if not img:
        logger.warning("替换图片被拒: task_id=%d image_id=%d 原因=记录不存在", task_id, image_id)
        raise ValueError("图片记录不存在")
    if img["task_id"] != task_id:
        logger.warning("替换图片被拒: task_id=%d image_id=%d 原因=不属于该任务(属于task_id=%d)", task_id, image_id, img["task_id"])
        raise ValueError("图片不属于该任务")

    # 获取目标路径
    local_path = img.get("local_path", "")
    if not local_path:
        # 生图失败时无 local_path，基于 seq 自动生成文件名
        ext = os.path.splitext(filename)[1].lstrip(".") or "png"
        local_path = f"{img['seq']:02d}-local.{ext}"
        logger.info("替换图片: task_id=%d image_id=%d 原无本地文件，新建 %s", task_id, image_id, local_path)

    from engine.db.models import task_get
    from engine.config import get_project_root
    task = task_get(task_id)
    task_path = task.get("task_path", "") if task else ""
    if not task_path:
        raise ValueError("任务无产物目录")
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    target_file = os.path.join(task_path, "images", os.path.basename(local_path))
    os.makedirs(os.path.dirname(target_file), exist_ok=True)

    # 覆盖写入文件
    with open(target_file, "wb") as f:
        f.write(file_data)

    # 更新 DB 记录
    w, h = 0, 0
    try:
        w, h = get_png_dimensions(file_data)
    except Exception:
        pass

    image_update(
        image_id,
        local_path=os.path.basename(target_file),
        local_size=len(file_data),
        width=w, height=h,
        format=os.path.splitext(filename)[1].lstrip(".") or "png",
        upload_status="generated",  # 手动替换视为已就绪，待上传
    )

    logger.info("图片已替换: task_id=%d image_id=%d file=%s size=%d",
                task_id, image_id, target_file, len(file_data))
    return {"task_id": task_id, "image_id": image_id, "action": "replaced",
            "size": len(file_data), "width": w, "height": h}


def regenerate_task_image(task_id: int, image_id: int, new_prompt: str) -> dict:
    """用新 prompt 重新 AI 生成图片。

    复用原 provider / model / style / size，覆盖同一文件。
    """
    from engine.db.models import image_get, image_update
    from engine.image_gen_core import generate_image, detect_provider, get_default_model

    # 确保 API Key 等环境变量已加载（API 进程独立于 pipeline 进程，必须先加载再 detect）
    from engine.config import load_env
    load_env()

    # 权限校验
    try:
        _check_image_ops_allowed(task_id)
    except ValueError as e:
        logger.warning("重新生图被拒: task_id=%d image_id=%d: %s", task_id, image_id, e)
        raise

    img = image_get(image_id)
    if not img:
        logger.warning("重新生图被拒: task_id=%d image_id=%d 原因=记录不存在", task_id, image_id)
        raise ValueError("图片记录不存在")
    if img["task_id"] != task_id:
        logger.warning("重新生图被拒: task_id=%d image_id=%d 原因=不属于该任务(属于task_id=%d)", task_id, image_id, img["task_id"])
        raise ValueError("图片不属于该任务")

    if not new_prompt or not new_prompt.strip():
        logger.warning("重新生图被拒: task_id=%d image_id=%d 原因=prompt为空", task_id, image_id)
        raise ValueError("prompt 不能为空")

    # 获取原图片的 provider / model / size
    provider = img.get("provider") or detect_provider()
    model = img.get("model") or get_default_model(provider)
    size = img.get("size", "")
    image_style = img.get("image_style", "")

    # 确定目标文件路径
    local_path = img.get("local_path", "")
    from engine.db.models import task_get
    from engine.config import get_project_root
    task = task_get(task_id)
    task_path = task.get("task_path", "") if task else ""
    if not task_path:
        logger.warning("重新生图被拒: task_id=%d image_id=%d 原因=任务无产物目录", task_id, image_id)
        raise ValueError("任务无产物目录")
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    if not local_path:
        # 生图失败时无 local_path，基于 seq 自动生成文件名
        ext = img.get("format", "png") or "png"
        local_path = f"{img['seq']:02d}-regen.{ext}"
        logger.info("重新生图: task_id=%d image_id=%d 原无本地文件，新建 %s", task_id, image_id, local_path)

    target_file = os.path.join(task_path, "images", os.path.basename(local_path))
    os.makedirs(os.path.dirname(target_file), exist_ok=True)

    # 调用生图 API
    import time
    from engine.utils import get_png_dimensions

    t0 = time.time()
    try:
        image_bytes = generate_image(
            provider=provider, model=model,
            prompt=new_prompt.strip(),
            size=size, quality="normal",
        )
    except Exception as e:
        logger.error("重新生图失败: task_id=%d image_id=%d: %s", task_id, image_id, str(e)[:200])
        raise ValueError(f"AI 生图失败: {str(e)[:200]}") from e

    # 覆盖文件
    with open(target_file, "wb") as f:
        f.write(image_bytes)

    duration = int((time.time() - t0) * 1000)
    w, h = 0, 0
    try:
        w, h = get_png_dimensions(image_bytes)
    except Exception:
        pass

    # 更新 DB
    est_in = max(1, len(new_prompt) // 3)
    est_out = max(1, len(image_bytes) // 200)
    new_local_path = os.path.basename(target_file)
    image_update(
        image_id,
        prompt=new_prompt.strip(),
        local_path=new_local_path,
        local_size=len(image_bytes),
        width=w, height=h,
        format="png",
        provider=provider, model=model,
        size=size, image_style=image_style,
        upload_status="generated",
        tokens_in=est_in, tokens_out=est_out,
    )

    logger.info("图片已重新生成: task_id=%d image_id=%d size=%dKB duration=%dms",
                task_id, image_id, len(image_bytes) // 1024, duration)
    return {
        "task_id": task_id, "image_id": image_id,
        "action": "regenerated",
        "size": len(image_bytes), "width": w, "height": h,
        "provider": provider, "model": model,
        "duration_ms": duration,
    }


def update_task_image(task_id: int, image_id: int,
                      description: Optional[str] = None,
                      prompt: Optional[str] = None,
                      image_style: Optional[str] = None) -> dict:
    """更新图片元数据（描述、提示词、风格）。"""
    from engine.db.models import image_get, image_update

    # 权限校验
    try:
        _check_image_ops_allowed(task_id)
    except ValueError as e:
        logger.warning("更新图片被拒: task_id=%d image_id=%d: %s", task_id, image_id, e)
        raise

    img = image_get(image_id)
    if not img:
        logger.warning("更新图片被拒: task_id=%d image_id=%d 原因=记录不存在", task_id, image_id)
        raise ValueError("图片记录不存在")
    if img["task_id"] != task_id:
        logger.warning("更新图片被拒: task_id=%d image_id=%d 原因=不属于该任务(属于task_id=%d)", task_id, image_id, img["task_id"])
        raise ValueError("图片不属于该任务")

    kwargs = {}
    if description is not None:
        kwargs["description"] = description
    if prompt is not None:
        kwargs["prompt"] = prompt
    if image_style is not None:
        kwargs["image_style"] = image_style

    if not kwargs:
        logger.warning("更新图片被拒: task_id=%d image_id=%d 原因=无有效字段", task_id, image_id)
        raise ValueError("至少需要提供一个更新字段")

    image_update(image_id, **kwargs)
    logger.info("图片元数据已更新: task_id=%d image_id=%d fields=%s",
                task_id, image_id, list(kwargs.keys()))
    return {"task_id": task_id, "image_id": image_id, "action": "updated",
            "fields": list(kwargs.keys())}


def append_task_images(task_id: int, files: list) -> dict:
    """新增图片（审核阶段）：上传到任务 images/ 目录并建 task_image 记录。

    - article 模式：锚点 `![alt](images/xx.png)` 追加到 article.md 末尾，
      发布时随文章正文一起上传（与「AI去味发布」新增图片行为一致）
    - image(newspic) 模式：无正文 markdown，图片落盘即成为末尾新卡片
      （发布时收集 images/ 目录全部文件作为卡片）

    files: [(文件字节, 原始文件名), ...]
    """
    from engine.db.models import task_get, image_list_by_task, image_insert
    from engine.utils import get_png_dimensions
    from engine.config import get_project_root, get_article_path

    # 权限校验（返回 task 供后续使用）
    try:
        task = _check_image_ops_allowed(task_id)
    except ValueError as e:
        logger.warning("新增图片被拒: task_id=%d: %s", task_id, e)
        raise

    if not files:
        logger.warning("新增图片被拒: task_id=%d 原因=未选择图片文件", task_id)
        raise ValueError("未选择图片文件")

    task_path = task.get("task_path", "") or ""
    if not task_path:
        raise ValueError("任务无产物目录")
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    images_dir = os.path.join(task_path, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 已有文件名集合（task_image 记录 + images/ 目录磁盘文件），新文件不与它们重名
    db_images = image_list_by_task(task_id) or []
    existing_names: set = set()
    for img in db_images:
        lp = img.get("local_path") or ""
        if lp:
            existing_names.add(os.path.basename(lp))
    for n in os.listdir(images_dir):
        existing_names.add(n)

    # 现有最大 seq（新增记录在末尾依次递增）
    max_seq = max((img.get("seq") or 0) for img in db_images)

    # article 模式：预读 article.md 准备追加锚点
    task_type = task.get("type", "article")
    article_md = None
    md_content = ""
    if task_type == "article":
        article_md = get_article_path(task_path)
        try:
            with open(article_md, "r", encoding="utf-8") as f:
                md_content = f.read()
        except FileNotFoundError:
            md_content = ""

    added = []
    anchors = []
    seq = max_seq
    for data, filename in files:
        # 文件名去重：重名时加序号（a.png → a-2.png），与 md 流程一致
        name = filename
        base, ext = os.path.splitext(filename)
        i = 2
        while name in existing_names:
            name = f"{base}-{i}{ext}"
            i += 1
        existing_names.add(name)

        target = os.path.join(images_dir, name)
        with open(target, "wb") as f:
            f.write(data)

        w, h = 0, 0
        try:
            w, h = get_png_dimensions(data)
        except Exception:
            pass

        seq += 1
        alt = os.path.splitext(name)[0] or name
        img_id = image_insert(
            task_id=task_id, seq=seq, local_path=name,
            local_size=len(data), width=w, height=h,
            fmt=os.path.splitext(name)[1].lstrip(".") or "png",
            description=alt, upload_status="generated",
        )
        added.append({"image_id": img_id, "seq": seq, "local_path": name,
                      "description": alt, "width": w, "height": h})
        anchors.append(f"\n![{alt}](images/{name})\n")

    # article 模式：锚点追加到 article.md 末尾（保留原有 YAML frontmatter）
    if task_type == "article" and anchors and article_md:
        if md_content and not md_content.endswith("\n"):
            md_content += "\n"
        preserved = _preserve_frontmatter(article_md, md_content + "".join(anchors))
        with open(article_md, "w", encoding="utf-8") as f:
            f.write(preserved)

    logger.info("新增图片完成: task_id=%d type=%s 新增 %d 张",
                task_id, task_type, len(added))
    return {"task_id": task_id, "added": added}


# ============================================================
# 后台异步 Pipeline
# ============================================================

import threading


def _spawn_pipeline_thread(task_id: int, topic: str, account: str,
                           task_type: str, out_dir, **kwargs) -> None:
    """启动后台线程运行 pipeline，异常时标记任务 ABANDONED。

    供 create_task_bg（news/newspic）与 import_md_task_bg（md）共用。
    """
    def _run():
        try:
            from engine.pipeline import run as pipeline_run
            pipeline_run(
                topic=topic, account=account, task_type=task_type,
                existing_task_id=task_id,
                existing_task_path=str(out_dir),
                **kwargs,
            )
        except Exception as e:
            import logging, traceback
            logging.getLogger(__name__).error(
                "后台 pipeline 失败 task_id=%d: %s\n%s",
                task_id, e, traceback.format_exc(),
            )
            # 记录失败阶段和错误信息到 status_history
            try:
                from engine.db.models import task_get, status_transition
                from engine.constants import Status
                current = task_get(task_id)
                last_status = current.get("status", 10) if current else 10
                # 如果已经记录了具体失败状态（如 PUBLISH_FAILED），不再覆盖为 ABANDONED
                if last_status in (Status.PUBLISH_FAILED, Status.AI_SCORE_FAILED):
                    logging.getLogger(__name__).info(
                        "任务 %d 已在状态 %d 记录失败原因，跳过 ABANDONED", task_id, last_status)
                else:
                    last_label = Status.label(last_status)
                    status_transition(
                        task_id, Status.ABANDONED,
                        to_info=f"在「{last_label}」阶段执行异常: {str(e)[:200]}",
                        remark=traceback.format_exc()[:1000],
                        operator="system",
                    )
                    logging.getLogger(__name__).info("任务 %d 已标记为出错了", task_id)
            except Exception as ex2:
                logging.getLogger(__name__).error("标记任务失败状态时出错 task_id=%d: %s", task_id, ex2)

    threading.Thread(target=_run, daemon=True).start()


def import_md_task_init(
    md_bytes: bytes,
    md_filename: str,
    images: list,
    account: str = "main",
    topic: str = "",
) -> int:
    """第一步：导入 md 内容（含配图），创建 md 类型任务并初始化 task / task_image 表。

    用户选中本地 .md 后立即调用：解析文章、创建任务记录（status=10）、
    归置 md 与配图到任务目录、为每个图片锚点插入 task_image 记录：
    锚点图片文件已存在（本次上传或目录中已有）→ 标记 uploaded；
    否则标记 pending（提交时由 import_md_task_run 补图）。

    Args:
        md_bytes: article.md 文件内容（UTF-8，兼容 BOM）
        md_filename: 原始文件名（用于提取话题兜底）
        images: [(原始文件名, 文件内容), ...] 可选配图列表
        account: 发布账号
        topic: 话题/标题（留空自动从文章提取）

    Returns:
        task_id（尚未启动 pipeline）

    Raises:
        ValueError: 校验失败（md 编码错误、内容为空、图片格式不支持等）
    """
    import re
    from pathlib import Path

    from engine.config import get_project_root
    from engine.article_images import parse_frontmatter
    from engine.image_handler import extract_images_from_markdown
    from engine.utils import create_task_dir
    from engine.pipeline_db import db_task_create

    # 1. 解码 md（兼容 BOM）
    try:
        md_text = md_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("md 文件必须为 UTF-8 编码")
    if not md_text.strip():
        raise ValueError("md 文件内容为空")

    # 2. 提取 frontmatter title 与正文本地图片引用
    fm, _ = parse_frontmatter(md_text)
    md_title = (fm.get("title") or "").strip() if fm else ""
    anchors = extract_images_from_markdown(md_text)
    local_refs = [a for a in anchors
                  if not a["url"].strip().startswith(("http://", "https://"))]

    # 3. 话题兜底：表单 topic > 正文首个 # 标题 > frontmatter title > 文件名
    if not topic or not topic.strip():
        m = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
        topic = (m.group(1).strip() if m else "") or md_title or md_filename
    topic = topic.strip()

    # 4. 规范化锚点：本地引用统一为 images/<basename>（保留 alt），
    #    保证 publish_from_markdown(base_dir=task_dir) 可解析
    def _norm(m) -> str:
        alt, url = m.group(1), m.group(2)
        if url.strip().startswith(("http://", "https://")):
            return m.group(0)
        return f"![{alt}](images/{Path(url.strip()).name})"

    norm_md = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _norm, md_text)

    # 5. 创建任务目录 + 写入 article.md
    out_dir = create_task_dir(account)
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)
    (out_dir / "article.md").write_text(norm_md, encoding="utf-8")

    # 5.5 归置本次上传的配图（与 run 同规则：扩展名白名单 + basename 防穿越）
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    for filename, data in images:
        name = Path(filename).name.strip()
        if not name:
            continue
        if Path(name).suffix.lower() not in _IMG_EXTS:
            raise ValueError(f"不支持的图片格式: {name}（仅支持 png/jpg/jpeg/webp/gif）")
        (images_dir / name).write_bytes(data)

    # 6. 加载账号配置并创建任务记录（status=10，pipeline 未启动）
    _project_root = get_project_root()
    _backend = os.path.join(_project_root, "backend")
    if _backend not in sys.path:
        sys.path.insert(0, _backend)
    os.environ.setdefault("GENERATED_TASK_DIR", os.path.join(_project_root, "generated"))

    from engine.config import load_env, set_account, get_config
    load_env()
    set_account(account)
    try:
        account_cfg = get_config(account)
    except Exception:
        account_cfg = {}

    task_path_rel = os.path.relpath(str(out_dir), _project_root).replace("\\", "/")
    task_id = db_task_create(
        account=account, topic=topic, account_cfg=account_cfg,
        task_path=task_path_rel, task_type="md",
        need_images=0, user_details="",
    )
    if not task_id:
        raise RuntimeError("创建任务记录失败")

    # 7. 为每个本地图片锚点插入 task_image 记录：
    #    - 锚点图片文件已在任务目录 images/ 下（本次上传或之前已就位）→ uploaded；否则 pending
    #    - 封面（is_cover）：第一张已存在的图片；全部不存在则第一张
    from engine.db.models import image_insert
    exists_flags = []
    for a in local_refs:
        url = a["url"].strip()
        name = Path(url).name
        exists_flags.append((images_dir / name).exists())
    cover_seq = next((i + 1 for i, ok in enumerate(exists_flags) if ok), 1)

    for seq, (a, exists) in enumerate(zip(local_refs, exists_flags), start=1):
        url = a["url"].strip()
        name = Path(url).name
        image_insert(
            task_id=task_id, seq=seq,
            anchor=url, description=a["alt"] or "",
            local_path=name, fmt=Path(name).suffix.lstrip(".") or "png",
            upload_status="uploaded" if exists else "pending",
            is_cover=(seq == cover_seq),
        )

    logger.info("md 任务已初始化: task_id=%d topic=%s account=%s 锚点=%d (已就位=%d, 封面=seq%d)",
                task_id, topic, account, len(local_refs),
                sum(exists_flags), cover_seq)
    return task_id


def import_md_task_run(
    task_id: int,
    images: list,
    theme: str = "",
    voice: str = "",
    provider: str = "",
    topic: str = "",
    author: str = "",
) -> int:
    """第二步：上传配图并启动「去味发布」pipeline（对应 import_md_task_init）。

    Args:
        task_id: import_md_task_init 返回的任务 ID
        images: [(原始文件名, 文件内容), ...] 配图列表
        theme / voice / provider / author: 前端表单参数
        topic: 话题/标题（非空则覆盖 init 时的值）

    Returns:
        task_id（pipeline 已在后台线程启动）

    Raises:
        ValueError: 校验失败（任务不存在/类型不符、图片格式不支持、锚点缺图等）
    """
    from pathlib import Path

    from engine.config import get_project_root
    from engine.image_handler import extract_images_from_markdown
    from engine.utils import get_png_dimensions

    # 1. 任务校验：md 类型且未开始执行
    from engine.constants import Status
    from engine.db.models import task_get, task_update
    task = task_get(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")
    if task.get("type") != "md":
        raise ValueError(f"任务 {task_id} 不是 md 类型（当前: {task.get('type')}）")
    if task.get("status", 0) not in (10, 40):
        raise ValueError(
            f"任务状态「{Status.label(task.get('status', 0))}」不允许上传配图，请刷新页面")

    task_path = task.get("task_path", "")
    if not task_path:
        raise ValueError("任务无产物目录")
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))
    task_dir = Path(task_path)
    article_md = task_dir / "article.md"
    if not article_md.exists():
        raise ValueError("任务缺少 article.md，请重新导入")

    # 2. 图片扩展名白名单 + 按 basename 归集（防路径穿越）
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    img_files: dict = {}  # basename -> bytes（同名后者覆盖）
    for filename, data in images:
        name = Path(filename).name.strip()
        if not name:
            continue
        if Path(name).suffix.lower() not in _IMG_EXTS:
            raise ValueError(f"不支持的图片格式: {name}（仅支持 png/jpg/jpeg/webp/gif）")
        img_files[name] = data

    # 3. 缺图校验：文章锚点引用的每个文件必须已在任务目录 images/ 下
    #    （init 阶段已就位的图 + 本次上传的图都算已就位）
    images_dir = task_dir / "images"
    md_text = article_md.read_text(encoding="utf-8")
    anchors = extract_images_from_markdown(md_text)
    local_refs = [a for a in anchors
                  if not a["url"].strip().startswith(("http://", "https://"))]
    need_names = {Path(a["url"].strip()).name for a in local_refs if a["url"].strip()}
    if need_names:
        missing = sorted(
            n for n in need_names
            if not (images_dir / n).exists() and n not in img_files)
        if missing:
            raise ValueError(
                "以下配图缺失，请与文章中的图片引用对应上传: " + ", ".join(missing))

    # 4. 归置图片到任务目录 images/
    images_dir.mkdir(exist_ok=True)
    for name, data in img_files.items():
        (images_dir / name).write_bytes(data)

    # 5. 更新 task_image 记录：文件已就位 → 标记 uploaded 并回填尺寸元数据
    #    （初始化时已 uploaded 的记录幂等保留，本次未重传的文件不覆盖元数据）
    #    封面重算：按 seq 顺序第一个已就位的锚点标 is_cover，其余清掉
    from engine.db.models import image_list_by_task, image_update
    imgs = sorted(image_list_by_task(task_id), key=lambda x: x.get("seq") or 0)
    cover_set = False
    for img in imgs:
        local_name = img.get("local_path", "")
        data = img_files.get(Path(local_name).name) if local_name else None
        already_uploaded = img.get("upload_status") == "uploaded"
        if data is None and not already_uploaded:
            continue  # 该锚点仍未就位，跳过
        is_cover = 0 if cover_set else 1  # 按 seq 顺序第一个就位的为封面
        cover_set = True
        kwargs: dict = {}
        if data is not None:
            w, h = 0, 0
            try:
                w, h = get_png_dimensions(data)
            except Exception:
                pass
            kwargs = dict(local_size=len(data), width=w, height=h,
                          upload_status="uploaded")
        kwargs["is_cover"] = is_cover
        image_update(img["id"], **kwargs)

    # 6. 合并主题/语气/作者/话题到 task 表（供重试/审核续跑恢复）
    task_updates = {}
    if theme:
        task_updates["theme"] = theme
    if voice:
        task_updates["voice"] = voice
    if author and author.strip():
        task_updates["author"] = author.strip()
    if topic and topic.strip():
        task_updates["topic"] = topic.strip()
    if task_updates:
        task_update(task_id, **task_updates)

    # 7. 启动后台 pipeline
    account = task.get("account", "main")
    _spawn_pipeline_thread(
        task_id, task.get("topic", ""), account, "md", task_dir,
        theme=theme, voice=voice, provider=provider, author=author,
    )
    logger.info("md 任务已提交并启动: task_id=%d 图片=%d theme=%s",
                task_id, len(img_files), theme or '账号默认')
    return task_id


def create_task_bg(
    topic: str,
    account: str = "main",
    task_type: str = "article",
    theme: Optional[str] = None,
    image_style: Optional[str] = None,
    article_structure: Optional[str] = None,
    opening_hook: Optional[str] = None,
    voice: Optional[str] = None,
    genre: Optional[str] = None,
    provider: Optional[str] = None,
    no_images: bool = False,
    user_details: Optional[str] = None,
) -> int:
    """创建任务记录并立即返回 task_id，pipeline 在后台线程执行。"""
    from pathlib import Path

    # 确保 backend/ 在 sys.path
    from engine.config import get_project_root
    _project_root = get_project_root()
    _backend = os.path.join(_project_root, "backend")
    if _backend not in sys.path:
        sys.path.insert(0, _backend)

    # 强制 generated 目录创建在项目根目录下
    os.environ.setdefault("GENERATED_TASK_DIR", os.path.join(_project_root, "generated"))

    # 加载账号配置
    from engine.config import load_env, set_account, get_config
    load_env()
    set_account(account)
    try:
        account_cfg = get_config(account)
    except Exception:
        account_cfg = {}

    # 应用前端覆盖参数
    if article_structure:
        account_cfg["article_structure"] = article_structure
    if opening_hook:
        account_cfg["opening_hook"] = opening_hook
    if voice:
        account_cfg["voice"] = voice
    if theme:
        account_cfg["theme"] = theme
    if image_style:
        account_cfg["image_style"] = image_style
    if genre:
        account_cfg["genre"] = genre

    # 创建任务目录和记录
    from engine.utils import create_task_dir
    from engine.pipeline_db import db_task_create

    out_dir = create_task_dir(account)
    # 存入 DB 时用相对路径（相对于项目根目录），保持可移植性
    task_path_rel = os.path.relpath(str(out_dir), _project_root).replace("\\", "/")
    task_id = db_task_create(
        account=account, topic=topic, account_cfg=account_cfg,
        task_path=task_path_rel, task_type=task_type,
        need_images=0 if no_images else 1,
        user_details=user_details or "",
    )

    if not task_id:
        raise RuntimeError("创建任务记录失败")

    # 后台线程运行 pipeline
    _spawn_pipeline_thread(
        task_id, topic, account, task_type, out_dir,
        theme=theme, image_style=image_style,
        article_structure=article_structure,
        opening_hook=opening_hook, voice=voice,
        genre=genre,
        provider=provider, no_images=no_images,
        user_details=user_details,
    )
    return task_id


# ============================================================
# Pipeline 操作（调用 pipeline.py）
# ============================================================

async def run_pipeline(
    topic: str,
    account: str = "main",
    task_type: str = "article",
    theme: Optional[str] = None,
    image_style: Optional[str] = None,
    article_structure: Optional[str] = None,
    opening_hook: Optional[str] = None,
    voice: Optional[str] = None,
    provider: Optional[str] = None,
    skip_ai_score: bool = False,
    sync: Optional[str] = None,
    no_images: bool = False,
    user_details: Optional[str] = None,
) -> dict:
    """一键全流程：理解需求 → 撰写 → 配图 → HTML → AI 检测 → 发布。

    返回 pipeline 执行结果 dict。
    """
    return await asyncio.to_thread(
        _run_pipeline_sync, topic, account, task_type, theme,
        image_style, article_structure, opening_hook, voice,
        provider, skip_ai_score, sync, no_images, user_details,
    )


def _run_pipeline_sync(
    topic: str, account: str, task_type: str, theme: Optional[str],
    image_style: Optional[str], article_structure: Optional[str],
    opening_hook: Optional[str], voice: Optional[str],
    provider: Optional[str],
    skip_ai_score: bool, sync: Optional[str], no_images: bool,
    user_details: Optional[str],
) -> dict:
    from engine.pipeline import run
    return run(
        topic=topic, account=account, task_type=task_type,
        theme=theme, image_style=image_style,
        article_structure=article_structure, opening_hook=opening_hook,
        voice=voice,
        provider=provider, skip_ai_score=skip_ai_score,
        sync=sync, no_images=no_images, user_details=user_details,
    )


async def run_stage(
    stage: str,
    task_id: int = 0,
    **kwargs,
) -> dict:
    """执行单个 pipeline 阶段。

    stage 可选值: understand_requirements, write_draft, generate_images,
                 convert_to_html, check_ai_score, publish_to_wechat, sync_to_platforms
    """
    return await asyncio.to_thread(_run_stage_sync, stage, task_id, kwargs)


def _run_stage_sync(stage: str, task_id: int, kwargs: dict) -> dict:
    import engine.pipeline as pl

    stage_map = {
        "convert_to_html": pl.convert_to_html,
        "check_ai_score": pl.check_ai_score,
        "publish_to_wechat": pl.publish_to_wechat,
        "sync_to_platforms": pl.sync_to_platforms,
    }

    fn = stage_map.get(stage)
    if not fn:
        raise ValueError(f"未知阶段: {stage}")

    result = fn(**kwargs)
    return {"stage": stage, "task_id": task_id, "result": result}


def save_newspic_review(task_id: int, data: dict) -> dict:
    """保存 newspic stage 20 审核编辑：更新 task 表字段 + task_image 卡片描述。

    data 可包含:
      - title: str（可选）
      - short_text: str（可选）
      - image_style: str（可选）
      - cards: list[dict]，每项 {id, description}（可选）

    返回更新摘要。
    """
    from engine.db.models import task_get, task_update, image_update

    task = task_get(task_id)
    if not task:
        raise ValueError("任务不存在")
    if task.get("type") != "image":
        raise ValueError("此操作仅支持 image 类型任务")

    task_field_count = 0
    card_count = 0

    # 更新 task 表字段
    task_updates = {}
    for field in ("title", "short_text", "image_style"):
        if field in data and data[field] is not None and data[field] != "":
            task_updates[field] = data[field]
    if task_updates:
        task_update(task_id, **task_updates)
        task_field_count = len(task_updates)

    # 更新卡片描述（task_image）
    cards = data.get("cards") or []
    for card in cards:
        card_id = card.get("id")
        if not card_id:
            continue
        card_updates = {}
        if "description" in card and card["description"] is not None:
            card_updates["description"] = card["description"]
        if card_updates:
            image_update(card_id, **card_updates)
            card_count += 1

    logger.info("Newspic 审核保存: task=%d task_fields=%d cards=%d",
                task_id, task_field_count, card_count)
    return {
        "task_id": task_id,
        "message": f"已保存：{task_field_count} 个任务字段，{card_count} 条卡片描述",
    }


# ============================================================
# 配置相关
# ============================================================

async def get_accounts() -> list[str]:
    """获取所有已配置的公众号账号名。"""
    return await asyncio.to_thread(_get_accounts_sync)


def _get_accounts_sync() -> list[str]:
    try:
        from engine.config import list_accounts
        return list_accounts()
    except Exception:
        return ["main"]


async def get_themes() -> list[dict]:
    """获取所有排版主题。"""
    return await asyncio.to_thread(_get_themes_sync)


def _get_themes_sync() -> list[dict]:
    from engine.constants import Theme
    return [
        {"code": code, "label": Theme.label(code), "description": Theme.description(code)}
        for code in Theme.all_codes()
    ]


async def get_image_styles() -> list[dict]:
    """获取所有配图风格。"""
    return await asyncio.to_thread(_get_image_styles_sync)


def _get_image_styles_sync() -> list[dict]:
    from engine.constants import ImageStyle
    return [
        {
            "code": code,
            "label": ImageStyle.label(code),
            "keywords": ImageStyle.keywords(code),
            "topics": ImageStyle.topics(code),
            "density": ImageStyle.density(code),
        }
        for code in ImageStyle.all_codes()
    ]


async def get_article_structures() -> list[dict]:
    """获取所有文章结构。"""
    from engine.constants import ArticleStructure
    return [
        {"code": code, "label": ArticleStructure.label(code),
         "topics": ArticleStructure.topics(code), "flow": ArticleStructure.flow(code)}
        for code in ArticleStructure.all_codes()
    ]


async def get_opening_hooks() -> list[dict]:
    """获取所有开篇钩子。"""
    from engine.constants import OpeningHook
    return [
        {"code": code, "label": OpeningHook.label(code),
         "tip": OpeningHook.tip(code), "avoid": OpeningHook.avoid(code)}
        for code in OpeningHook.all_codes()
    ]


# ============================================================
# 任务重试
# ============================================================

RETRYABLE_STATUSES = (0, 85, 88)  # ABANDONED, AI_SCORE_FAILED, PUBLISH_FAILED


def get_retry_info(task_id: int) -> dict:
    """查询任务的重试元数据（供前端确认弹窗使用）。

    Returns:
        dict: {retryable, current_status, action, action_label, description,
               cost_hint, retry_from, retry_from_label}
    """
    from engine.constants import Status, RetryResume
    from engine.db.models import task_get, status_history_list

    task = task_get(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")

    current_status = task.get("status", 0)
    if current_status not in RETRYABLE_STATUSES:
        return {
            "retryable": False,
            "current_status": current_status,
            "current_status_label": Status.label(current_status),
        }

    task_type = task.get("type", "article")
    failed_at_status = 0

    if current_status == Status.ABANDONED:
        history = status_history_list(task_id)
        # 找到 ABANDONED 之前最后一个状态作为失败阶段
        prev_status = 0
        for entry in history:
            if entry.get("to_status") == Status.ABANDONED:
                break
            prev_status = entry.get("to_status", 0)
        if not prev_status:
            failed_at_status = Status.CREATED
        else:
            failed_at_status = prev_status

    retry_from = RetryResume.get_resume_status(
        task_type, current_status,
        business_key=str(failed_at_status),
    )

    # 根据状态生成不同的操作描述
    if current_status == Status.PUBLISH_FAILED:
        action = "retry_publish_only"
        action_label = "重新发布"
        if task_type == "md":
            description = "文章、配图、HTML 已就绪，仅重新调用微信发布接口"
        else:
            description = "内容、配图、HTML 已就绪，仅重新调用微信发布接口"
        cost_hint = "零 LLM / 生图成本，仅调用微信 API"
    elif current_status == Status.AI_SCORE_FAILED:
        action = "retry_regenerate"
        action_label = "重新生成"
        if task_type == "image":
            description = "重新生成贴图简报并生成新配图"
            cost_hint = "需要 LLM 调用 + 生图，成本与原任务相当"
        elif task_type == "md":
            description = "重新执行 AI 去味改写（从文章导入阶段恢复）"
            cost_hint = "需要 LLM 调用"
        else:
            description = "重新撰写文章草稿并生成配图"
            cost_hint = "需要 LLM 调用 + 生图，成本与原任务相当"
    elif current_status == Status.ABANDONED and retry_from >= Status.AI_SCORE_PASSED:
        # 任务在 AI 味通过后崩溃（如发布阶段异常），仅需重新发布
        action = "retry_publish_only"
        action_label = "重新发布"
        description = "内容、配图、HTML、AI 味检测已就绪，仅重新调用微信发布接口"
        cost_hint = "零 LLM / 生图成本，仅调用微信 API"
    else:  # ABANDONED（前序阶段崩溃）
        action = "retry_from_breakpoint"
        action_label = "断点重试"
        stage_label = Status.label(retry_from)
        description = f"从「{stage_label}」阶段恢复执行，保留已有产物"
        if task_type == "image":
            cost_hint = f"从阶段「{stage_label}」开始，跳过前序步骤"
        else:
            cost_hint = f"从阶段「{stage_label}」开始，跳过前序步骤"

    return {
        "retryable": True,
        "current_status": current_status,
        "current_status_label": Status.label(current_status),
        "action": action,
        "action_label": action_label,
        "description": description,
        "cost_hint": cost_hint,
        "retry_from": retry_from,
        "retry_from_label": Status.label(retry_from),
    }


def retry_task_bg(task_id: int) -> tuple:
    """对失败任务发起断点重试（后台线程执行）。

    Returns:
        (task_id, retry_from, action)
    """
    from engine.constants import Status, RetryResume
    from engine.db.models import task_get, status_history_list

    task = task_get(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")

    current_status = task.get("status", 0)

    # 校验可重试状态
    if current_status not in RETRYABLE_STATUSES:
        raise ValueError(f"任务状态「{Status.label(current_status)}」不支持重试")

    # 校验不在运行中
    if 10 <= current_status <= 70:
        raise ValueError("任务正在运行中，无需重试")

    task_type = task.get("type", "article")
    failed_at_status = 0  # ABANDONED 时记录崩溃前所处阶段的状态码

    if current_status == Status.ABANDONED:
        history = status_history_list(task_id)
        # 按时间倒序，取第一个非 ABANDONED 的状态作为中断前所处阶段
        prev_status = 0
        for entry in reversed(history):
            if entry.get("to_status") != Status.ABANDONED:
                prev_status = entry.get("to_status", 0)
                break
        if not prev_status:
            # 无前序 history（如 db_task_create 直接设 status=10 后即崩溃），
            # 回退到 CREATED 从头开始
            failed_at_status = Status.CREATED
        else:
            failed_at_status = prev_status

    retry_from = RetryResume.get_resume_status(
        task_type, current_status,
        business_key=str(failed_at_status),
    )

    if current_status == Status.PUBLISH_FAILED:
        action = "retry_publish_only"
    elif current_status == Status.AI_SCORE_FAILED:
        action = "retry_regenerate"
    elif current_status == Status.ABANDONED and retry_from >= Status.AI_SCORE_PASSED:
        # 任务在 AI 味通过后崩溃，仅需重新发布
        action = "retry_publish_only"
    else:
        action = "retry_from_breakpoint"

    task_path = task.get("task_path", "")
    # 相对路径转绝对路径（同 _get_task_sync），避免 CWD 不同时找不到文件
    if task_path and not os.path.isabs(task_path):
        from engine.config import get_project_root
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    # 标记重试开始：静默回退 task.status，不写 history，避免重复记录。
    # 后续 pipeline 阶段从 retry_from 继续执行时，会自然产生新的 history 记录。
    # - PUBLISH_FAILED / retry_from >= 80: 任务在发布阶段失败，不回退状态
    # - 其他情况: 通过 task_update 静默设置状态，不产生重复的 history 条目
    skip_transition = (
        current_status == Status.PUBLISH_FAILED
        or retry_from >= Status.AI_SCORE_PASSED
    )
    if not skip_transition:
        from engine.db.models import task_update
        task_update(task_id, status=retry_from)
        import logging
        logging.getLogger(__name__).info(
            "重试: task=%d 从「%s」回退到「%s」（静默更新状态，不写 history）",
            task_id, Status.label(current_status), Status.label(retry_from),
        )

    def _retry_run():
        try:
            from engine.pipeline import retry_run as pipeline_retry_run
            pipeline_retry_run(
                task_id=task_id,
                task_type=task_type,
                topic=task.get("topic", ""),
                account=task.get("account", "main"),
                task_path=task_path,
                retry_from=retry_from,
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
            import logging, traceback
            logging.getLogger(__name__).error(
                "后台重试 pipeline 失败 task_id=%d: %s\n%s",
                task_id, e, traceback.format_exc(),
            )
            try:
                from engine.db.models import task_get as _get, status_transition
                from engine.constants import Status as S
                current = _get(task_id)
                last_status = current.get("status", 10) if current else 10
                if last_status not in (S.PUBLISH_FAILED, S.AI_SCORE_FAILED):
                    last_label = S.label(last_status)
                    status_transition(
                        task_id, S.ABANDONED,
                        to_info=f"重试时在「{last_label}」阶段执行异常: {str(e)[:200]}",
                        remark=traceback.format_exc()[:1000],
                        operator="system",
                    )
            except Exception:
                pass

    threading.Thread(target=_retry_run, daemon=True).start()
    return task_id, retry_from, action
