"""微信公众号草稿管理路由 —— 列表 / 详情 / 新增 / 更新 / 删除。"""

from fastapi import APIRouter, Query
from app.schemas.common import ApiResponse
from app.schemas.wechat import (
    DraftListItem,
    DraftDetailResponse,
    DraftListResponse,
    DraftAddRequest,
    DraftUpdateRequest,
    DeleteDraftRequest,
)

router = APIRouter(prefix="/wechat", tags=["公众号管理"])


@router.get("/drafts", response_model=ApiResponse[DraftListResponse])
async def get_drafts(
    offset: int = Query(default=0, ge=0, description="偏移量"),
    count: int = Query(default=20, ge=1, le=20, description="拉取数量"),
):
    """获取微信公众号草稿列表（draft/batchget）。"""
    try:
        import asyncio
        from engine.api import get_draft_list

        result = await asyncio.to_thread(
            get_draft_list, offset=offset, count=count,
        )

        items: list[DraftListItem] = []
        for entry in (result.get("item") or []):
            media_id = entry.get("media_id", "")
            news_item = {}
            content = entry.get("content", {})
            if content and content.get("news_item"):
                news_item = content["news_item"][0]

            items.append(DraftListItem(
                media_id=media_id,
                title=news_item.get("title", ""),
                author=news_item.get("author", ""),
                digest=news_item.get("digest", ""),
                url=news_item.get("url", ""),
                thumb_url=news_item.get("thumb_url", ""),
                update_time=entry.get("update_time", 0),
            ))

        return ApiResponse(data=DraftListResponse(
            items=items,
            total_count=result.get("total_count", 0),
            item_count=result.get("item_count", len(items)),
            offset=offset,
            count=count,
        ))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.get("/drafts/{media_id}", response_model=ApiResponse[DraftDetailResponse])
async def get_draft_detail(media_id: str):
    """获取草稿详情（draft/get）。"""
    try:
        import asyncio
        from engine.api import get_draft

        result = await asyncio.to_thread(get_draft, media_id)

        return ApiResponse(data=DraftDetailResponse(
            media_id=media_id,
            title=result.get("title", ""),
            author=result.get("author", ""),
            digest=result.get("digest", ""),
            content=result.get("raw", {}).get("content", ""),
            content_source_url=result.get("content_source_url", ""),
            thumb_media_id=result.get("raw", {}).get("thumb_media_id", ""),
            show_cover_pic=result.get("raw", {}).get("show_cover_pic", 0),
            need_open_comment=result.get("raw", {}).get("need_open_comment", 0),
            only_fans_can_comment=result.get("raw", {}).get("only_fans_can_comment", 0),
            url=result.get("url", ""),
            thumb_url=result.get("thumb_url", ""),
        ))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/drafts/add", response_model=ApiResponse[dict])
async def add_draft(body: DraftAddRequest):
    """新增草稿（draft/add）。"""
    try:
        import asyncio
        from engine.api import add_draft as create_draft

        if not body.thumb_media_id:
            return ApiResponse(code=400, message="缺少封面图：请先上传封面图获取 media_id 后再创建草稿")

        article = {
            "title": body.title,
            "content": body.content,
            "thumb_media_id": body.thumb_media_id,
            "author": body.author,
            "digest": body.digest,
            "content_source_url": body.content_source_url,
            "need_open_comment": body.need_open_comment,
            "only_fans_can_comment": body.only_fans_can_comment,
        }

        media_id = await asyncio.to_thread(create_draft, article)
        return ApiResponse(data={"media_id": media_id}, message="草稿创建成功")
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/drafts/update", response_model=ApiResponse[dict])
async def update_draft(body: DraftUpdateRequest):
    """更新草稿（draft/update）。"""
    try:
        import asyncio
        from engine.api import update_draft as do_update

        articles = {
            "title": body.title,
            "content": body.content,
            "author": body.author,
            "digest": body.digest,
            "content_source_url": body.content_source_url,
            "need_open_comment": body.need_open_comment,
            "only_fans_can_comment": body.only_fans_can_comment,
        }
        if body.thumb_media_id:
            articles["thumb_media_id"] = body.thumb_media_id

        result = await asyncio.to_thread(
            do_update, media_id=body.media_id, index=body.index, articles=articles,
        )
        return ApiResponse(data=result, message="草稿更新成功")
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/drafts/delete", response_model=ApiResponse[dict])
async def delete_draft(body: DeleteDraftRequest):
    """删除草稿（draft/delete）。"""
    try:
        import asyncio
        from engine.api import delete_draft as do_delete

        result = await asyncio.to_thread(do_delete, media_id=body.media_id)
        return ApiResponse(data=result, message="删除成功")
    except Exception as e:
        return ApiResponse(code=500, message=str(e))
