"""草稿路由 —— 文章预览、编辑、配置查询。"""

from fastapi import APIRouter, Query
from app.schemas.common import ApiResponse
from app.schemas.draft import DraftUpdateRequest, DraftPreviewResponse
from app.services import draft_service
from app.services import generation as gen_service

router = APIRouter(prefix="/drafts", tags=["草稿管理"])


@router.get("/{task_id}/preview", response_model=ApiResponse[DraftPreviewResponse])
async def preview_draft(task_id: int, theme: str | None = Query(default=None)):
    """获取文章的微信样式 HTML 预览。"""
    try:
        result = await draft_service.preview_html(task_id, theme)
        return ApiResponse(data=result)
    except FileNotFoundError as e:
        return ApiResponse(code=404, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.get("/config", response_model=ApiResponse[dict])
async def get_config_options():
    """获取所有可用的配置选项（账号、主题、风格、文章结构、开篇钩子）。"""
    import asyncio
    accounts, themes, styles, structures, hooks = await asyncio.gather(
        gen_service.get_accounts(),
        gen_service.get_themes(),
        gen_service.get_image_styles(),
        gen_service.get_article_structures(),
        gen_service.get_opening_hooks(),
    )
    return ApiResponse(data={
        "accounts": accounts,
        "themes": themes,
        "image_styles": styles,
        "article_structures": structures,
        "opening_hooks": hooks,
    })
