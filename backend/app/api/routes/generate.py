"""文章生成与编排路由 —— Pipeline 阶段执行、HTML 转换、AI 检测、发布。"""

from fastapi import APIRouter
from app.schemas.common import ApiResponse
from app.schemas.article import ArticleCreateRequest, PublishRequest
from app.services import generation as gen_service
from app.services import draft_service

router = APIRouter(prefix="/generate", tags=["文章生成"])


@router.post("/run", response_model=ApiResponse[dict])
async def run_pipeline(req: ArticleCreateRequest):
    """一键执行全流程 Pipeline（与 POST /tasks 等价）。"""
    try:
        result = await gen_service.run_pipeline(
            topic=req.topic,
            account=req.account,
            task_type=req.task_type,
            theme=req.theme,
            image_style=req.image_style,
            provider=req.provider,
            no_images=req.no_images,
            user_details=req.user_details,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"Pipeline 失败: {e}")


@router.post("/convert-html", response_model=ApiResponse[dict])
async def convert_to_html(task_id: int, theme: str | None = None):
    """阶段五：将 article.md 转换为微信兼容 HTML。"""
    try:
        from engine.pipeline import convert_to_html as _convert
        import asyncio
        html_path = await asyncio.to_thread(
            _convert, article_path="", task_id=task_id, theme=theme,
        )
        return ApiResponse(data={"html_path": html_path})
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/check-ai-score", response_model=ApiResponse[dict])
async def check_ai_score(task_id: int, threshold: float = 45.0):
    """阶段 5.5：AI 味检测。"""
    try:
        result = await draft_service.check_ai_score(task_id, threshold)
        return ApiResponse(data=result)
    except FileNotFoundError as e:
        return ApiResponse(code=404, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/publish", response_model=ApiResponse[dict])
async def publish_article(req: PublishRequest):
    """阶段六：发布到微信草稿箱。"""
    try:
        from engine.pipeline import publish_to_wechat as _publish
        import asyncio
        result = await asyncio.to_thread(
            _publish,
            article_path="", task_id=req.task_id,
            sync_platforms=req.sync_platforms,
        )
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(code=500, message=str(e))
