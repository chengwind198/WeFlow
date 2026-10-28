"""通用 Pydantic schema。"""

from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """通用 API 响应包装。"""
    code: int = 0
    message: str = "ok"
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页列表响应。"""
    items: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorResponse(BaseModel):
    """错误响应。"""
    code: int
    message: str
    detail: str | None = None
