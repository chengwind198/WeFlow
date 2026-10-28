#!/usr/bin/env python3
"""通用辅助函数。"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
# engine 位于 backend/engine/，项目根目录在 engine/ 上级的上级
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_REFS_DIR = _PROJECT_ROOT / "references"
_STRUCTURES_MD = _REFS_DIR / "article-structures.md"
_ANTI_AI_MD = _REFS_DIR / "anti-ai-checklist.md"


def create_task_dir(account: str, output_dir: Optional[str] = None) -> Path:
    """创建任务产物目录（含时间戳+随机后缀防冲突），返回 Path。"""
    from engine.config import get_generated_task_dir

    task_dir = get_generated_task_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    millis = int((time.time() % 1) * 1000)
    rand_suffix = f"{random.randint(0, 999):03d}"
    out_dir = Path(output_dir) if output_dir else Path(
        f"{task_dir}/{timestamp}{millis:03d}_{rand_suffix}_{account}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_ref(path: Path) -> str:
    """读取参考文档，文件不存在时返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def extract_hooks_from_structures(text: str) -> str:
    """从 article-structures.md 中提取「开头钩子库」章节（约 2000 字符）。"""
    if "开头钩子库" in text:
        start = text.index("开头钩子库")
        return text[start:start + 2000]
    return text


def get_structures_md() -> Path:
    return _STRUCTURES_MD


def get_anti_ai_md() -> Path:
    return _ANTI_AI_MD


# ============================================================
# 图片工具
# ============================================================

def get_png_dimensions(image_bytes: bytes) -> tuple:
    """从 PNG 文件头解析宽高，返回 (width, height)；非 PNG 返回 (0, 0)。"""
    if len(image_bytes) >= 24 and image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        import struct
        return struct.unpack('>II', image_bytes[16:24])
    return 0, 0


# ============================================================
# Markdown / 文本处理工具
# ============================================================

# 行内标记对：(开始标记, 结束标记)，用于清除 Markdown 格式字符
INLINE_MARKER_PAIRS = [
    ("**", "**"), ("__", "__"), ("*", "*"), ("_", "_"),
    ("~~", "~~"), ("`", "`"), ("==", "=="),
]


def strip_inline_markers(text: str) -> str:
    """清除文本中的 Markdown 行内标记（粗体、斜体、删除线、代码、高亮）。"""
    import re
    result = text
    for start, end in INLINE_MARKER_PAIRS:
        esc_start = re.escape(start)
        esc_end = re.escape(end)
        result = re.sub(f'{esc_start}(.+?){esc_end}', r'\1', result)
    return result


def remove_anchor_placeholders(body: str) -> str:
    """移除正文中未替换的 anchor:// 占位符。"""
    import re
    return re.sub(r'!\[([^\]]*)\]\(anchor://[^)]+\)', '', body)
