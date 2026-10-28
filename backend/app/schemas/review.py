"""审核相关 Pydantic schema。"""

from pydantic import BaseModel, Field


# ============================================================
# 审核队列
# ============================================================

class ReviewQueueParams(BaseModel):
    """审核队列查询参数。"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    status: str | None = Field(default=None, description="按状态筛选: pending/approved/rejected")
    task_type: str | None = Field(default=None, description="按任务类型筛选: news/newspic")
    stage: int | None = Field(default=None, description="按审核节点筛选: 20/40")
    sort_by: str = Field(default="created_at", description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向: asc/desc")


class ReviewListItem(BaseModel):
    """审核队列列表项。"""
    id: int
    task_id: int
    stage: int
    status: str
    reviewer: str = ""
    comment: str = ""
    topic: str = ""
    type: str = ""
    account: str = ""
    created_at: int = 0
    updated_at: int = 0


# ============================================================
# 审核详情
# ============================================================

class ReviewDetail(BaseModel):
    """审核详情（含任务信息用于预览）。"""
    id: int
    task_id: int
    stage: int
    status: str
    reviewer: str = ""
    comment: str = ""
    topic: str = ""
    type: str = ""
    account: str = ""
    task_status: int = 0
    task_path: str = ""
    images: list = Field(default_factory=list, description="配图列表（stage=60 时返回）")
    task_title: str = Field(default="", description="newspic stage 20 标题")
    short_text: str = Field(default="", description="newspic stage 20 短文本")
    image_style: str = Field(default="", description="newspic 配图风格")
    cards: list = Field(default_factory=list, description="newspic stage 20 卡片列表")
    created_at: int = 0
    updated_at: int = 0


# ============================================================
# 审核操作
# ============================================================

class ReviewActionRequest(BaseModel):
    """审核操作请求（通过/驳回）。"""
    reviewer: str = Field(default="", description="审核人标识")
    comment: str = Field(default="", description="审核意见/备注")


class ReviewActionResponse(BaseModel):
    """审核操作响应。"""
    review_id: int
    task_id: int
    action: str  # "approved" / "rejected"
    message: str = ""
