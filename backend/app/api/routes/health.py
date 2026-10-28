"""健康检查路由。"""

import sys
from pathlib import Path
from fastapi import APIRouter
from app.schemas.common import ApiResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=ApiResponse[dict])
async def health_check():
    """服务健康检查 + engine 目录连通性。"""
    engine_ok = False
    try:
        from engine.config import get_project_root
        _engine = Path(get_project_root()) / "backend" / "engine"
        engine_ok = _engine.exists() and _engine.is_dir()
    except Exception:
        pass

    return ApiResponse(
        data={
            "status": "healthy",
            "engine_accessible": engine_ok,
        }
    )
