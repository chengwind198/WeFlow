"""多平台同步相关 Pydantic schema。"""
from pydantic import BaseModel, Field


class SyncCreateRequest(BaseModel):
    """创建/覆盖同步记录请求体。"""
    id: int | None = Field(default=None, description="同步记录 ID（编辑已有记录时传入）")
    task_id: int | None = Field(default=None, description="任务 ID（task 来源时必填）")
    sync_from: str = Field(default="task", description="来源: task / local / url")
    url: str | None = Field(default=None, description="目标网址（url 来源时记录）")
    file_path: str | None = Field(default=None, description=".md 文件全路径")
    markdown_content: str = Field(default="", description="Markdown 内容")
    platforms: list[str] = Field(..., min_length=1, description="目标平台列表")


class URLFetchRequest(BaseModel):
    """网址获取请求。"""
    url: str = Field(..., description="要获取的网址")


class URLFetchResponse(BaseModel):
    """网址获取响应。"""
    markdown_content: str
    title: str = ""
    file_path: str
    images: list[str] = []


class LocalFileUploadResponse(BaseModel):
    """本地文件上传响应。"""
    markdown_content: str
    file_path: str
    file_name: str


class SyncListItem(BaseModel):
    """同步记录列表项。"""
    id: int
    task_id: int = 0
    topic: str = ""
    title: str = ""
    sync_from: str = "task"
    url: str | None = None
    file_path: str | None = None
    status: str
    platforms: str  # JSON string from DB
    platform_count: int = 0
    result_count: int = 0
    created_at: int
    updated_at: int


class SyncResultItem(BaseModel):
    """单个平台同步结果。"""
    id: int
    task_sync_id: int
    platform: str
    platform_label: str = ""
    status: str  # success / failed
    error_msg: str = ""
    created_at: int


class SyncDetail(BaseModel):
    """同步详情（含各平台结果）。"""
    id: int
    task_id: int = 0
    topic: str = ""
    title: str = ""
    sync_from: str = "task"
    url: str | None = None
    file_path: str | None = None
    markdown_content: str = ""
    platforms: str
    status: str
    results: list[SyncResultItem] = []
    created_at: int
    updated_at: int
