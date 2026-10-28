"""文章相关 Pydantic schema。"""

from pydantic import BaseModel, Field
from typing import Optional


class ArticleCreateRequest(BaseModel):
    """创建文章（启动 AI 写作流程）请求体。"""
    topic: str = Field(..., min_length=1, max_length=500, description="文章话题/关键词")
    account: str = Field(default="main", description="公众号账号标识")
    task_type: str = Field(default="article", description="任务类型：article / image")
    theme: Optional[str] = Field(default=None, description="排版主题标识")
    image_style: Optional[str] = Field(default=None, description="配图风格标识")
    article_structure: Optional[str] = Field(default=None, description="文章结构")
    opening_hook: Optional[str] = Field(default=None, description="开篇钩子")
    voice: Optional[str] = Field(default=None, description="语气风格")
    genre: Optional[str] = Field(default=None, description="文章体裁")
    provider: Optional[str] = Field(default=None, description="AI大模型提供商")
    no_images: bool = Field(default=False, description="跳过配图生成")
    user_details: Optional[str] = Field(default=None, description="补充要求或素材")


class ArticleUpdateRequest(BaseModel):
    """更新文章请求体。"""
    title: Optional[str] = Field(default=None, min_length=1, description="文章标题")
    markdown: Optional[str] = Field(default=None, description="Markdown 正文")
    theme: Optional[str] = Field(default=None, description="排版主题")
    image_style: Optional[str] = Field(default=None, description="配图风格")


class ArticleListItem(BaseModel):
    """文章列表项。"""
    id: int
    topic: str
    title: str
    account: str
    type: str
    status: int
    status_label: str
    ai_score: Optional[float] = None
    ai_verdict: Optional[str] = None
    theme: str
    image_style: str
    genre: str = ""
    short_text: str = ""
    word_count: int
    author: str
    user_details: str = ""
    need_images: int = 1
    created_at: int
    updated_at: int


class ArticleDetail(BaseModel):
    """文章详情。"""
    id: int
    topic: str
    title: str
    account: str
    account_name: str = ""
    author: str = ""
    type: str
    status: int
    status_label: str
    theme: str
    image_style: str
    article_structure: str
    opening_hook: str
    voice: str
    genre: str = ""
    short_text: str = ""
    user_details: str = ""
    need_images: int = 1
    word_count: int
    ai_score: Optional[float] = None
    ai_verdict: Optional[str] = None
    brief: str = ""
    markdown: str
    html: str
    images: list[dict] = []
    messages: list[dict] = []
    status_history: list[dict] = []
    publish_records: list[dict] = []
    review_records: list[dict] = []
    sync_platforms: str = ""
    created_at: int
    updated_at: int


class BriefUpdateRequest(BaseModel):
    """更新选题简报请求体。"""
    content: str = Field(..., min_length=1, description="简报 Markdown 内容")


class PublishRequest(BaseModel):
    """发布请求。"""
    task_id: int = Field(..., description="任务 ID")
    sync_platforms: Optional[str] = Field(default=None, description="同步平台，逗号分隔")
