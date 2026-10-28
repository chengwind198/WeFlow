"""微信公众号草稿管理相关 schema。"""

from pydantic import BaseModel, Field


class DraftNewsItem(BaseModel):
    """草稿中的图文条目（详情用）。"""
    title: str = ""
    author: str = ""
    digest: str = ""
    content: str = ""
    content_source_url: str = ""
    thumb_media_id: str = ""
    show_cover_pic: int = 0
    need_open_comment: int = 0
    only_fans_can_comment: int = 0
    url: str = ""
    thumb_url: str = ""


class DraftListItem(BaseModel):
    """草稿列表中的一条记录。"""
    media_id: str = ""
    title: str = ""
    author: str = ""
    digest: str = ""
    url: str = ""
    thumb_url: str = ""
    update_time: int = 0


class DraftDetailResponse(BaseModel):
    """草稿详情响应。"""
    media_id: str = ""
    title: str = ""
    author: str = ""
    digest: str = ""
    content: str = ""
    content_source_url: str = ""
    thumb_media_id: str = ""
    show_cover_pic: int = 0
    need_open_comment: int = 0
    only_fans_can_comment: int = 0
    url: str = ""
    thumb_url: str = ""


class DraftListResponse(BaseModel):
    """草稿列表响应。"""
    items: list[DraftListItem] = []
    total_count: int = 0
    item_count: int = 0
    offset: int = 0
    count: int = 20


class DraftAddRequest(BaseModel):
    """新增草稿请求。"""
    title: str = Field(..., description="文章标题")
    content: str = Field(..., description="HTML 正文内容")
    author: str = Field(default="", description="作者名")
    digest: str = Field(default="", description="摘要")
    content_source_url: str = Field(default="", description="原文链接")
    thumb_media_id: str = Field(default="", description="封面图 media_id")
    need_open_comment: int = Field(default=0, ge=0, le=1, description="是否开启留言")
    only_fans_can_comment: int = Field(default=0, ge=0, le=1, description="是否仅粉丝可留言")


class DraftUpdateRequest(BaseModel):
    """更新草稿请求。"""
    media_id: str = Field(..., description="草稿 media_id")
    index: int = Field(default=0, ge=0, description="要更新的文章位置（0=第一篇）")
    title: str = Field(..., description="文章标题")
    content: str = Field(..., description="HTML 正文内容")
    author: str = Field(default="", description="作者名")
    digest: str = Field(default="", description="摘要")
    content_source_url: str = Field(default="", description="原文链接")
    thumb_media_id: str = Field(default="", description="封面图 media_id")
    need_open_comment: int = Field(default=0, ge=0, le=1)
    only_fans_can_comment: int = Field(default=0, ge=0, le=1)


class DeleteDraftRequest(BaseModel):
    """删除草稿请求。"""
    media_id: str = Field(..., description="草稿 media_id")
