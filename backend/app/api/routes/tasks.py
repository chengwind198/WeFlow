"""任务管理路由 —— 任务的 CRUD 与状态查询。"""

import os
import logging
import asyncio

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Query, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.article import (
    ArticleCreateRequest, ArticleListItem, ArticleDetail,
    BriefUpdateRequest,
)
from app.services import generation as gen_service

router = APIRouter(prefix="/tasks", tags=["任务管理"])


@router.get("", response_model=ApiResponse[PaginatedResponse[ArticleListItem]])
async def list_tasks(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(default=None, description="按状态筛选（多选用逗号分隔，如 10,20,40）"),
    type: str | None = Query(default=None, description="按类型筛选: article / image"),
    account: str | None = Query(default=None, description="按账号筛选"),
    keyword: str | None = Query(default=None, description="按关键词搜索"),
    created_after: int | None = Query(default=None, description="创建时间起始 (Unix timestamp)"),
    created_before: int | None = Query(default=None, description="创建时间截止 (Unix timestamp)"),
    sort_by: str = Query(default="created_at", description="排序字段: id/topic/type/account/status/created_at/updated_at"),
    sort_order: str = Query(default="desc", description="排序方向: asc/desc"),
):
    """分页查询任务列表。"""
    result = await gen_service.list_tasks(
        page=page, page_size=page_size, status=status,
        task_type=type, account=account, keyword=keyword,
        created_after=created_after, created_before=created_before,
        sort_by=sort_by, sort_order=sort_order,
    )
    return ApiResponse(data=result)


@router.get("/{task_id}", response_model=ApiResponse[ArticleDetail])
async def get_task(task_id: int):
    """获取任务详情（含文章内容、图片、对话历史）。"""
    task = await gen_service.get_task(task_id)
    if not task:
        return ApiResponse(code=404, message="任务不存在")
    return ApiResponse(data=task)


@router.post("", response_model=ApiResponse[dict])
async def create_and_run_task(req: ArticleCreateRequest):
    """创建任务并启动后台全流程 Pipeline。

    任务立即创建并返回 task_id，Pipeline 在后台线程中异步执行。
    """
    try:
        task_id = gen_service.create_task_bg(
            topic=req.topic,
            account=req.account,
            task_type=req.task_type,
            theme=req.theme,
            image_style=req.image_style,
            article_structure=req.article_structure,
            opening_hook=req.opening_hook,
            voice=req.voice,
            genre=req.genre,
            provider=req.provider,
            no_images=req.no_images,
            user_details=req.user_details,
        )
        return ApiResponse(data={"task_id": task_id})
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"创建任务失败: {e}")


@router.post("/import", response_model=ApiResponse[dict])
async def import_md_task_init(
    file: UploadFile = File(..., description="已有文章 Markdown 文件"),
    images: list[UploadFile] = File(default=[], description="配图文件（可选，与 md 中图片引用对应）"),
    account: str = Form("main", description="公众号账号"),
    topic: str = Form("", description="话题/标题（留空自动从文章提取）"),
):
    """第一步：导入 md 内容（含可选配图），初始化 task / task_image 表。

    用户选中本地 .md 后立即调用：创建任务记录（status=10），
    归置 md 与配图到任务目录；锚点图片文件已就位 → 标记 uploaded，
    否则标记 pending（提交时由 POST /import/{task_id}/run 补齐配图并启动流程）。
    """
    try:
        # 校验 md 扩展名与大小
        if not file.filename or not file.filename.lower().endswith(".md"):
            return ApiResponse(code=400, message="请上传 .md 格式的 Markdown 文件")
        md_bytes = await file.read()
        if len(md_bytes) > 5 * 1024 * 1024:
            return ApiResponse(code=400, message="md 文件不能超过 5MB")

        img_list = []
        for img in images:
            if not img.filename:
                continue
            data = await img.read()
            if not data:
                continue
            img_list.append((img.filename, data))

        task_id = await asyncio.to_thread(
            gen_service.import_md_task_init,
            md_bytes, file.filename, img_list,
            account=account, topic=topic,
        )
        return ApiResponse(data={"task_id": task_id})
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("初始化 md 任务失败: %s", e, exc_info=True)
        return ApiResponse(code=500, message=f"初始化失败: {e}")


@router.post("/import/{task_id}/run", response_model=ApiResponse[dict])
async def import_md_task_run(
    task_id: int,
    images: list[UploadFile] = File(default=[], description="配图文件（可多个，与 md 中图片引用对应）"),
    theme: str = Form("", description="排版主题"),
    voice: str = Form("", description="语气风格"),
    provider: str = Form("", description="LLM provider（留空用默认）"),
    topic: str = Form("", description="话题/标题（非空则覆盖 init 时的值）"),
    author: str = Form("", description="发布署名作者（留空用账号默认）"),
):
    """第二步：上传配图并启动「AI去味发布」流程。

    流程: 导入确认 → LLM 保守去味改写 → 转 HTML → AI 味检测
          → 未过则进审核队列（审核通过后自动发布）/ 通过则发布草稿箱
    """
    try:
        img_list = []
        for img in images:
            if not img.filename:
                continue
            data = await img.read()
            if not data:
                continue
            img_list.append((img.filename, data))

        await asyncio.to_thread(
            gen_service.import_md_task_run,
            task_id, img_list,
            theme=theme, voice=voice, provider=provider, topic=topic,
            author=author,
        )
        return ApiResponse(data={"task_id": task_id})
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("提交 md 任务失败: %s", e, exc_info=True)
        return ApiResponse(code=500, message=f"提交失败: {e}")


@router.delete("/{task_id}", response_model=ApiResponse[dict])
async def delete_task(task_id: int):
    """软删除任务。"""
    ok = await gen_service.delete_task(task_id)
    if not ok:
        return ApiResponse(code=404, message="任务不存在或删除失败")
    return ApiResponse(data={"deleted": task_id})


@router.get("/{task_id}/retry-info", response_model=ApiResponse[dict])
async def get_retry_info(task_id: int):
    """查询任务的重试信息（可重试状态、重试动作、成本提示等），
    供前端确认弹窗使用，不实际发起重试。"""
    try:
        info = await asyncio.to_thread(gen_service.get_retry_info, task_id)
        return ApiResponse(data=info)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))


@router.post("/{task_id}/retry", response_model=ApiResponse[dict])
async def retry_task(task_id: int):
    """对失败任务发起断点重试。

    支持的状态:
      - 88 (发布失败): 仅重试发布阶段，零 LLM/生图成本
      - 85 (AI 味未过): 从适当前序阶段重新生成
      - 0 (异常终止): 从 business_key 记录的失败阶段恢复

    重试在后台线程执行，立即返回 task_id。
    """
    try:
        tid, retry_from, action = await asyncio.to_thread(
            gen_service.retry_task_bg, task_id)
        return ApiResponse(data={
            "task_id": tid,
            "retry_from": retry_from,
            "action": action,
            "message": "重试已启动",
        })
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"重试启动失败: {e}")


@router.put("/{task_id}/brief", response_model=ApiResponse[dict])
async def update_brief(task_id: int, req: BriefUpdateRequest):
    """更新选题简报内容（仅状态为 0 且从 20 转入时可用，或审核中 stage=20）。"""
    try:
        result = await asyncio.to_thread(gen_service.update_brief, task_id, req.content)
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"更新简报失败: {e}")


@router.put("/{task_id}/article", response_model=ApiResponse[dict])
async def update_article(task_id: int, req: BriefUpdateRequest):
    """更新文章草稿内容（仅状态为 0 且从 40 转入时可用，或审核中 stage=40）。"""
    try:
        result = await asyncio.to_thread(gen_service.update_article, task_id, req.content)
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"更新文章失败: {e}")


# ── 图片管理（审核阶段 stage=60）──

from fastapi import UploadFile, File, Form


@router.delete("/{task_id}/images/{image_id}", response_model=ApiResponse[dict])
async def delete_image(task_id: int, image_id: int):
    """删除任务图片（仅审核阶段 stage=60 可用）。"""
    try:
        result = await asyncio.to_thread(gen_service.delete_task_image, task_id, image_id)
        return ApiResponse(data=result)
    except ValueError as e:
        logger.warning("删除图片失败: task_id=%d image_id=%d: %s", task_id, image_id, e)
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("删除图片异常: task_id=%d image_id=%d: %s", task_id, image_id, e, exc_info=True)
        return ApiResponse(code=500, message=f"删除图片失败: {e}")


@router.post("/{task_id}/images/{image_id}/replace", response_model=ApiResponse[dict])
async def replace_image(
    task_id: int,
    image_id: int,
    file: UploadFile = File(..., description="替换的图片文件"),
):
    """用本地上传文件替换任务图片（仅审核阶段 stage=60 可用）。"""
    try:
        if not file.filename:
            return ApiResponse(code=400, message="未选择文件")
        file_data = await file.read()
        result = await asyncio.to_thread(
            gen_service.replace_task_image, task_id, image_id,
            file_data, file.filename,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        logger.warning("替换图片失败: task_id=%d image_id=%d file=%s: %s", task_id, image_id, file.filename or '(无)', e)
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("替换图片异常: task_id=%d image_id=%d: %s", task_id, image_id, e, exc_info=True)
        return ApiResponse(code=500, message=f"替换图片失败: {e}")


@router.post("/{task_id}/images/append", response_model=ApiResponse[dict])
async def append_images(
    task_id: int,
    files: list[UploadFile] = File(..., description="新增的图片文件（可多个）"),
):
    """新增图片（审核阶段）：上传到任务 images/ 目录并建 task_image 记录。
    article 模式锚点追加到文章末尾；image(newspic) 模式作为末尾新卡片。"""
    try:
        if not files:
            return ApiResponse(code=400, message="未选择图片文件")
        file_items = []
        for f in files:
            if not f.filename:
                continue
            data = await f.read()
            if not data:
                continue
            file_items.append((data, f.filename))
        if not file_items:
            return ApiResponse(code=400, message="未选择有效的图片文件")
        result = await asyncio.to_thread(
            gen_service.append_task_images, task_id, file_items,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        logger.warning("新增图片失败: task_id=%d: %s", task_id, e)
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("新增图片异常: task_id=%d: %s", task_id, e, exc_info=True)
        return ApiResponse(code=500, message=f"新增图片失败: {e}")


@router.post("/{task_id}/images/{image_id}/regenerate", response_model=ApiResponse[dict])
async def regenerate_image(
    task_id: int,
    image_id: int,
    prompt: str = Form(..., description="新的生图提示词"),
):
    """用新 prompt 重新 AI 生成图片（仅审核阶段 stage=60 可用）。"""
    try:
        if not prompt or not prompt.strip():
            return ApiResponse(code=400, message="prompt 不能为空")
        result = await asyncio.to_thread(
            gen_service.regenerate_task_image, task_id, image_id, prompt,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        logger.warning("重新生图失败: task_id=%d image_id=%d: %s", task_id, image_id, e)
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("重新生图异常: task_id=%d image_id=%d: %s", task_id, image_id, e, exc_info=True)
        return ApiResponse(code=500, message=f"重新生成图片失败: {e}")


from pydantic import BaseModel as PydanticBaseModel

class ImageUpdateRequest(PydanticBaseModel):
    """更新图片元数据请求体，所有字段可选。"""
    description: str | None = None
    prompt: str | None = None
    image_style: str | None = None


@router.put("/{task_id}/images/{image_id}", response_model=ApiResponse[dict])
async def update_image(
    task_id: int,
    image_id: int,
    req: ImageUpdateRequest,
):
    """更新图片元数据（描述、提示词、风格），仅审核阶段 stage=60 可用。"""
    try:
        result = await asyncio.to_thread(
            gen_service.update_task_image, task_id, image_id,
            description=req.description,
            prompt=req.prompt,
            image_style=req.image_style,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        logger.warning("更新图片失败: task_id=%d image_id=%d: %s", task_id, image_id, e)
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("更新图片异常: task_id=%d image_id=%d: %s", task_id, image_id, e, exc_info=True)
        return ApiResponse(code=500, message=f"更新图片失败: {e}")


class NewspicReviewSaveRequest(PydanticBaseModel):
    """newspic stage 20 审核保存请求体。"""
    title: str | None = None
    short_text: str | None = None
    image_style: str | None = None
    cards: list[dict] | None = None


@router.put("/{task_id}/newspic-review", response_model=ApiResponse[dict])
async def save_newspic_review(task_id: int, req: NewspicReviewSaveRequest):
    """保存 newspic stage 20 审核编辑（task 字段 + 卡片描述）。"""
    try:
        result = await asyncio.to_thread(
            gen_service.save_newspic_review, task_id,
            {"title": req.title, "short_text": req.short_text,
             "image_style": req.image_style, "cards": req.cards},
        )
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"保存审核编辑失败: {e}")


@router.get("/{task_id}/files/{filename:path}")
async def serve_task_file(task_id: int, filename: str):
    """提供任务产物文件（图片、HTML 等）。"""
    task = await gen_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_path = task.get("task_path", "")
    if not task_path:
        raise HTTPException(status_code=404, detail="任务无产物目录")

    # 将相对路径转为绝对路径（相对于项目根目录）
    from engine.config import get_project_root
    original_path = task_path
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))

    # 安全检查：防止路径穿越
    safe_path = os.path.realpath(os.path.join(task_path, filename))
    real_task_path = os.path.realpath(task_path)
    if not safe_path.startswith(real_task_path + os.sep) and safe_path != real_task_path:
        raise HTTPException(status_code=403, detail="禁止访问")

    if not os.path.isfile(safe_path):
        print(f"[文件服务] 404: task_path={original_path} filename={filename} resolved={safe_path} exists={os.path.exists(safe_path)} isfile={os.path.isfile(safe_path)}")
        raise HTTPException(status_code=404, detail=f"文件不存在: resolved={safe_path}")

    print(f"[文件服务] 200: {safe_path}")
    return FileResponse(safe_path)
