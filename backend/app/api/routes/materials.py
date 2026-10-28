"""微信公众号永久素材管理路由 —— 列表 / 详情 / 上传 / 删除 / 图片代理。"""

from fastapi import APIRouter, Query, UploadFile, File, Form
from fastapi.responses import Response
from app.schemas.common import ApiResponse
from app.schemas.material import (
    MaterialItem,
    MaterialListResponse,
    MaterialDetailResponse,
    DeleteMaterialRequest,
)

router = APIRouter(prefix="/wechat", tags=["公众号管理"])


def _https_url(raw: str) -> str:
    """将 http:// 转为 https://，避免浏览器混合内容拦截。"""
    if raw.startswith("http://"):
        return "https://" + raw[len("http://"):]
    return raw


@router.get("/materials", response_model=ApiResponse[MaterialListResponse])
async def get_materials(
    material_type: str = Query(default="image", description="素材类型: image/video/voice/news"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    count: int = Query(default=20, ge=1, le=20, description="拉取数量"),
):
    """获取永久素材列表（material/batchget_material）。"""
    try:
        import asyncio
        from engine.api import get_material_list

        result = await asyncio.to_thread(
            get_material_list, material_type=material_type, offset=offset, count=count,
        )

        def _extract_url(item: dict) -> str:
            """提取素材封面/图片 URL，优先取顶层 url，视频素材尝试从 content 中取。"""
            top_url = item.get("url", "")
            if top_url:
                return _https_url(top_url)
            # 视频素材：url 可能在 content 嵌套中
            content = item.get("content", {})
            if content:
                for key in ("url", "thumb_url", "cover_url", "thumb_media_url"):
                    if content.get(key):
                        return _https_url(content[key])
            return ""

        items = [
            MaterialItem(
                media_id=item.get("media_id", ""),
                name=item.get("name", ""),
                url=_extract_url(item),
                update_time=item.get("update_time", 0),
            )
            for item in (result.get("item") or [])
        ]

        return ApiResponse(data=MaterialListResponse(
            items=items,
            total_count=result.get("total_count", 0),
            item_count=result.get("item_count", len(items)),
            material_type=material_type,
            offset=offset,
            count=count,
        ))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.get("/materials/{media_id}", response_model=ApiResponse[MaterialDetailResponse])
async def get_material_detail(media_id: str):
    """获取永久素材详情/内容（material/get_material）。"""
    try:
        import asyncio
        from engine.api import get_material

        print(f"[素材详情] 请求 media_id={media_id}")
        result = await asyncio.to_thread(get_material, media_id)
        print(f"[素材详情] 类型={result.get('type')} name={result.get('name')} has_data={bool(result.get('data'))} has_down_url={bool(result.get('down_url'))}")

        return ApiResponse(data=MaterialDetailResponse(
            media_id=result.get("media_id", ""),
            name=result.get("name", ""),
            url=result.get("url", ""),
            data=result.get("data", ""),
            content_type=result.get("content_type", ""),
            material_type=result.get("type", ""),
            down_url=result.get("down_url", ""),
            description=result.get("description", ""),
            update_time=result.get("update_time", 0),
        ))
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/materials/upload", response_model=ApiResponse[dict])
async def upload_material(
    file: UploadFile = File(...),
    material_type: str = Form(default="image", description="素材类型: image/video/voice/thumb"),
):
    """上传永久素材（material/add_material）。"""
    try:
        import asyncio
        import tempfile
        import os
        from engine.api import upload_material as do_upload

        # 将上传的文件保存到临时目录
        suffix = os.path.splitext(file.filename or "upload")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            result = await asyncio.to_thread(do_upload, file_path=tmp_path, material_type=material_type)
            return ApiResponse(data=result, message="上传成功")
        finally:
            # 清理临时文件
            os.unlink(tmp_path)
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.post("/materials/delete", response_model=ApiResponse[dict])
async def delete_material(body: DeleteMaterialRequest):
    """删除永久素材（material/del_material）。"""
    try:
        import asyncio
        from engine.api import delete_material as do_delete

        result = await asyncio.to_thread(do_delete, media_id=body.media_id)
        return ApiResponse(data=result, message="删除成功")
    except Exception as e:
        return ApiResponse(code=500, message=str(e))


@router.get("/materials/{media_id}/image")
async def get_material_image(media_id: str):
    """获取素材图片/视频封面（代理，解决微信 http 图片无法加载的问题）。
    视频素材无封面图时返回 404，由前端显示占位图标。"""
    try:
        import asyncio
        import base64
        from engine.api import get_material as do_get

        result = await asyncio.to_thread(do_get, media_id)
        data_b64 = result.get("data", "")
        content_type = result.get("content_type", "image/jpeg")
        material_type = result.get("type", "image")

        # 视频素材：无二进制封面数据，返回 404 让前端用视频图标占位
        if material_type == "video" or not data_b64:
            return Response(status_code=404)

        return Response(
            content=base64.b64decode(data_b64),
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception:
        return Response(status_code=500)


@router.post("/materials/upload-content-image", response_model=ApiResponse[dict])
async def upload_content_image(file: UploadFile = File(...)):
    """上传发表内容中的图片（media/uploadimg），返回 CDN URL，不占永久素材配额。"""
    try:
        import asyncio
        import tempfile
        import os
        from engine.api import upload_content_image as do_upload

        suffix = os.path.splitext(file.filename or "upload")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            cdn_url = await asyncio.to_thread(do_upload, file_path=tmp_path)
            return ApiResponse(data={"url": _https_url(cdn_url)}, message="上传成功")
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        return ApiResponse(code=500, message=str(e))
