"""审核管理路由 —— 审核队列、详情、通过/驳回。"""

from fastapi import APIRouter, Query, HTTPException
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.review import (
    ReviewListItem, ReviewDetail,
    ReviewActionRequest, ReviewActionResponse,
)
from app.services import review_service

router = APIRouter(prefix="/review", tags=["审核管理"])


@router.get("/queue", response_model=ApiResponse[PaginatedResponse[ReviewListItem]])
async def list_queue(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(default=None, description="按状态筛选: pending/approved/rejected"),
    task_type: str | None = Query(default=None, description="按任务类型筛选: article/image"),
    stage: int | None = Query(default=None, description="按审核节点筛选: 20/40"),
    sort_by: str = Query(default="created_at", description="排序字段"),
    sort_order: str = Query(default="desc", description="排序方向: asc/desc"),
    date_from: str | None = Query(default=None, description="提交时间起始（Unix 时间戳）"),
    date_to: str | None = Query(default=None, description="提交时间截止（Unix 时间戳）"),
):
    """分页查询审核队列。"""
    result = review_service.list_queue(
        page=page, page_size=page_size,
        status=status, task_type=task_type, stage=stage,
        sort_by=sort_by, sort_order=sort_order,
        date_from=date_from, date_to=date_to,
    )
    return ApiResponse(data=result)


@router.get("/{review_id}", response_model=ApiResponse[ReviewDetail])
async def get_detail(review_id: int):
    """获取审核详情（含任务信息，用于预览 brief.md/article.md 等产物）。"""
    detail = review_service.get_detail(review_id)
    if not detail:
        return ApiResponse(code=404, message="审核记录不存在")
    return ApiResponse(data=detail)


@router.post("/{review_id}/approve", response_model=ApiResponse[ReviewActionResponse])
async def approve(review_id: int, req: ReviewActionRequest):
    """通过审核，后台继续执行 pipeline。"""
    try:
        result = review_service.approve(
            review_id,
            reviewer=req.reviewer,
            comment=req.comment,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))


@router.post("/{review_id}/reject", response_model=ApiResponse[ReviewActionResponse])
async def reject(review_id: int, req: ReviewActionRequest):
    """驳回审核。"""
    try:
        result = review_service.reject(
            review_id,
            reviewer=req.reviewer,
            comment=req.comment,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
