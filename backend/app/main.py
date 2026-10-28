"""WeFlow公众号AI写作助手 — FastAPI 应用入口。

将 scripts/ 下的现有 Python 功能封装为 RESTful API，
供 React 前端通过 HTTP 调用。

启动方式:
    cd backend
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import health, tasks, generate, drafts, config, wechat, materials, sync, review


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时将 backend/ 加入 sys.path，使 engine 包可导入。"""
    import sys
    from pathlib import Path

    backend_dir = Path(settings.backend_dir)
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    engine_dir = Path(settings.engine_dir)
    if engine_dir.exists():
        print(f"[启动] engine 包已就绪: {engine_dir}")
    else:
        print(f"[警告] engine 目录不存在: {engine_dir}")

    # 启动时扫描僵尸任务（进程崩溃后状态残留在 10~80 的任务）
    import time
    from engine.constants import Status
    from engine.db.models import task_list_stuck, status_transition

    STALE_TIMEOUT = 5 * 60  # 5分钟无心跳视为僵尸
    stale_ts = int(time.time()) - STALE_TIMEOUT
    stuck = task_list_stuck(stale_ts)
    if stuck:
        print(f"[启动] 发现 {len(stuck)} 个疑似僵尸任务，正在标记为中断...")
        for t in stuck:
            label = Status.label(t["status"])
            status_transition(
                t["id"], Status.ABANDONED,
                to_info=f"进程中断，任务在「{label}」阶段未完成（自动恢复）",
                operator="system",
            )
            print(f"  - task #{t['id']} 「{t.get('topic','')[:30]}」状态={label} → 已标记为出错了")
    else:
        print("[启动] 无僵尸任务")

    yield


app = FastAPI(
    title=settings.project_name,
    description="微信公众号 AI 写作工具 — 后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(tasks.router, prefix=settings.api_v1_prefix)
app.include_router(generate.router, prefix=settings.api_v1_prefix)
app.include_router(drafts.router, prefix=settings.api_v1_prefix)
app.include_router(config.router, prefix=settings.api_v1_prefix)
app.include_router(wechat.router, prefix=settings.api_v1_prefix)
app.include_router(materials.router, prefix=settings.api_v1_prefix)
app.include_router(sync.router, prefix=settings.api_v1_prefix)
app.include_router(review.router, prefix=settings.api_v1_prefix)


# ── 根路径 ──
@app.get("/")
async def root():
    return {
        "name": settings.project_name,
        "version": "0.1.0",
        "docs": f"http://{settings.host}:{settings.port}/docs",
    }
