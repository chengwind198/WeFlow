"""多平台同步管理路由 —— 同步记录的创建、列表、详情。"""

from fastapi import APIRouter, Query, UploadFile, File
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.sync import (
    SyncCreateRequest, SyncListItem, SyncDetail,
    URLFetchRequest, URLFetchResponse, LocalFileUploadResponse,
)
from app.services import sync_service

router = APIRouter(prefix="/sync", tags=["多平台同步"])


@router.get("/tasks", response_model=ApiResponse[PaginatedResponse[SyncListItem]])
async def list_sync_tasks(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(default=None, description="按状态筛选: pending/syncing/success/partial/failed"),
    sort_by: str = Query(default="created_at", description="排序字段"),
    sort_order: str = Query(default="desc", description="排序方向: asc/desc"),
):
    """分页查询同步任务列表（关联 task 表获取 topic/title）。"""
    result = await sync_service.list_sync_tasks(
        page=page, page_size=page_size, status=status,
        sort_by=sort_by, sort_order=sort_order,
    )
    return ApiResponse(data=result)


@router.get("/tasks/{sync_id}", response_model=ApiResponse[SyncDetail])
async def get_sync_task(sync_id: int):
    """获取同步详情（含各平台同步结果）。"""
    detail = await sync_service.get_sync_task(sync_id)
    if not detail:
        return ApiResponse(code=404, message="同步记录不存在")
    return ApiResponse(data=detail)


@router.post("/tasks/save", response_model=ApiResponse[SyncDetail])
async def save_sync_task(req: SyncCreateRequest):
    """仅保存同步内容到 task_sync，不执行同步。

    前端编辑器修改后调用此接口保存草稿，后续"开始同步"时使用已保存的内容。
    """
    try:
        detail = await sync_service.save_only(
            sync_id=req.id,
            task_id=req.task_id,
            platforms=req.platforms,
            markdown_content=req.markdown_content,
            sync_from=req.sync_from,
            url=req.url,
            file_path=req.file_path,
        )
        return ApiResponse(data=detail)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"保存失败: {e}")


@router.post("/tasks", response_model=ApiResponse[SyncDetail])
async def create_sync_task(req: SyncCreateRequest):
    """创建/覆盖同步记录并执行同步。

    支持三种来源：task（任务）/ local（本地文件）/ url（网址获取）。
    markdown_content 为要同步的内容；如不传则从对应来源读取 .md 文件。
    """
    try:
        detail = await sync_service.create_or_update_sync(
            sync_id=req.id,
            task_id=req.task_id,
            platforms=req.platforms,
            markdown_content=req.markdown_content,
            sync_from=req.sync_from,
            url=req.url,
            file_path=req.file_path,
        )
        return ApiResponse(data=detail)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except FileNotFoundError as e:
        return ApiResponse(code=404, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"同步失败: {e}")


@router.post("/tasks/{sync_id}/retry", response_model=ApiResponse[SyncDetail])
async def retry_sync_task(
    sync_id: int,
    platforms: str | None = Query(default=None, description="要重试的平台列表，逗号分隔。不传则重试所有失败平台"),
):
    """重试同步：对失败的平台重新执行同步。

    不传 platforms 参数时，自动重试所有 status=failed 的平台。
    传 platforms=zhihu,csdn 时，仅重试指定平台。
    """
    platform_list = None
    if platforms:
        platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    try:
        detail = await sync_service.retry_sync(sync_id, platform_list)
        return ApiResponse(data=detail)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"重试失败: {e}")


@router.post("/fetch-url", response_model=ApiResponse[dict])
async def fetch_url(req: URLFetchRequest):
    """从网址获取内容，转为 Markdown 保存到本地同步目录。"""
    try:
        result = await sync_service.fetch_url_and_save(req.url)
        return ApiResponse(data=result)
    except ImportError as e:
        return ApiResponse(code=500, message=str(e))
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取失败: {e}")


@router.post("/upload-local-file", response_model=ApiResponse[dict])
async def upload_local_file(file: UploadFile = File(...)):
    """上传本地 .md 文件，保存到同步目录。"""
    if not file.filename or not file.filename.endswith('.md'):
        return ApiResponse(code=400, message="仅支持 .md 文件")
    try:
        content = await file.read()
        result = await sync_service.save_uploaded_file(content, file.filename or "untitled.md")
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(code=500, message=f"上传失败: {e}")
