#!/usr/bin/env python3
"""
统一日志配置模块。

基于 Python 内置 logging，零外部依赖。支持:
  - 控制台输出(INFO 级别，用户可见)
  - 文件输出(DEBUG 级别，按天轮转，完整记录)
  - 通过环境变量 WEFLOW_LOG_LEVEL 控制级别

用法:
    from engine.logger import get_logger
    logger = get_logger(__name__)
    logger.info("操作成功")
    logger.error("操作失败: %s", err, exc_info=True)
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from engine.constants import DirPath

# ============================================================
# 模块级别常量
# ============================================================

# 项目根目录：logger.py 位于 backend/engine/，往上三级即项目根
# 不通过 config.get_project_root() 以避免循环导入
# （config.py 顶层 import logger，logger 不能顶层 import config）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LOG_DIR = _PROJECT_ROOT / DirPath.LOGS
_DEFAULT_LOG_FILE = _LOG_DIR / "weflow.log"
_LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(filename)s:%(lineno)d %(funcName)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志级别映射(环境变量 → logging 常量)
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_initialized: bool = False


# ============================================================
# 初始化
# ============================================================

def setup_logging(
    level: str | int | None = None,
    log_file: str | Path | None = None,
) -> None:
    """
    初始化日志系统（幂等，多次调用不会重复添加 handler）。

    Args:
        level: 日志级别，可以是字符串("DEBUG"/"INFO"/...)或 logging 常量。
               为 None 时按以下优先级取:
                 1. 环境变量 WEFLOW_LOG_LEVEL
                 2. 默认 INFO
        log_file: 日志文件路径，为 None 时用默认路径 ../logs/weflow.log（项目根目录下）
    """
    global _initialized
    if _initialized:
        return

    # 解析日志级别
    if level is None:
        level = os.environ.get("WEFLOW_LOG_LEVEL", "INFO").upper()
    resolved_level: int
    if isinstance(level, str):
        resolved_level = _LEVEL_MAP.get(level, logging.INFO)
    elif isinstance(level, int):
        resolved_level = level
    else:
        resolved_level = logging.INFO

    # 解析日志文件路径
    log_path = Path(log_file) if log_file else _DEFAULT_LOG_FILE

    # 获取根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根 logger 放开，由 handler 各自控制级别

    # 统一 formatter
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # —— 控制台 handler (INFO+) ——
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # —— 文件 handler (DEBUG+，按天轮转，保留 30 天) ——
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_path),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        # 文件 handler 创建失败不应阻断程序，打印警告后继续
        print(f"[logger] 无法创建日志文件 handler ({log_path}): {e}", file=sys.stderr)

    # 抑制第三方库的 DEBUG 日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    _initialized = True
    logging.getLogger(__name__).debug(
        "日志系统已初始化，控制台级别=%s，文件=%s",
        logging.getLevelName(resolved_level), log_path,
    )


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger。

    首次调用时会自动初始化日志系统（使用默认配置），
    后续调用等效于 logging.getLogger(name)。

    Args:
        name: 通常传 __name__，可获得模块级 logger 名称（如 "config" / "api"）
    """
    setup_logging()
    return logging.getLogger(name)


# ============================================================
# 便捷函数：异常转日志
# ============================================================

def log_exception(
    logger: logging.Logger,
    level: str,
    msg: str,
    exc: BaseException | None = None,
    **extra: object,
) -> None:
    """
    统一的异常日志记录。

    Args:
        logger: 目标 logger
        level: 日志级别 ("warn" | "error" | "critical")
        msg: 描述信息
        exc: 异常对象（可选，None 时自动取当前异常）
        **extra: 额外的关键信息，会拼接到消息末尾
    """
    level_map = {
        "warn": logger.warning,
        "error": logger.error,
        "critical": logger.critical,
    }
    log_fn = level_map.get(level)
    if log_fn is None:
        return

    # 拼接额外信息
    if extra:
        extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
        msg = f"{msg} [{extra_str}]"

    if exc is not None:
        log_fn("%s: %s", msg, exc, exc_info=True)
    else:
        log_fn(msg, exc_info=True)
