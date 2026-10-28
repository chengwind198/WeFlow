"""微信公众号永久素材管理相关 schema。"""

from pydantic import BaseModel, Field


class MaterialItem(BaseModel):
    """素材列表中的一条记录。"""
    media_id: str = ""
    name: str = ""
    url: str = ""
    update_time: int = 0


class MaterialListResponse(BaseModel):
    """素材列表响应。"""
    items: list[MaterialItem] = []
    total_count: int = 0
    item_count: int = 0
    material_type: str = ""
    offset: int = 0
    count: int = 20


class MaterialDetailResponse(BaseModel):
    """素材详情响应。"""
    media_id: str = ""
    name: str = ""
    url: str = ""
    data: str = ""  # base64 编码的二进制内容（图片/语音）
    content_type: str = ""
    material_type: str = ""  # image / video / voice / news
    down_url: str = ""  # 视频下载地址（仅视频素材）
    description: str = ""  # 视频描述（仅视频素材）
    update_time: int = 0


class DeleteMaterialRequest(BaseModel):
    """删除素材请求。"""
    media_id: str = Field(..., description="素材 media_id")
