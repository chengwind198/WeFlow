"""草稿相关 Pydantic schema。"""

from pydantic import BaseModel, Field
from typing import Optional


class DraftUpdateRequest(BaseModel):
    """更新草稿请求体。"""
    title: Optional[str] = Field(default=None, min_length=1, description="文章标题")
    markdown: Optional[str] = Field(default=None, description="Markdown 正文")
    theme: Optional[str] = Field(default=None, description="排版主题")
    ai_score: Optional[float] = Field(default=None, description="AI 味评分")


class DraftPreviewResponse(BaseModel):
    """草稿预览响应。"""
    title: str
    html: str
    ai_score: Optional[float] = None
    ai_verdict: Optional[str] = None
    word_count: int
    theme: str
