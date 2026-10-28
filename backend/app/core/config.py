"""应用配置 —— 从 .env 加载，通过 pydantic-settings 校验。"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """FastAPI 应用配置。"""

    # ── 路径（通过 engine.config 统一获取）──
    from engine.config import get_project_root as _get_root
    _root = _get_root()
    project_root: str = _root
    backend_dir: str = str(Path(_root) / "backend")
    engine_dir: str = str(Path(_root) / "backend" / "engine")

    # ── 服务器 ──
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    # ── CORS ──
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── API ──
    api_v1_prefix: str = "/api/v1"
    project_name: str = "WeFlow公众号AI写作助手"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
