"""草稿服务 —— 文章编辑、预览、AI 检测等。"""

import sys
import asyncio
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from engine.config import ARTICLE_FILE


async def preview_html(task_id: int, theme: Optional[str] = None) -> dict:
    """生成文章 HTML 预览。"""
    return await asyncio.to_thread(_preview_html_sync, task_id, theme)


def _preview_html_sync(task_id: int, theme: Optional[str]) -> dict:
    from engine.db.models import task_get
    from engine.html_converter import convert_markdown_to_wechat_html, load_theme
    from engine.article_images import parse_frontmatter

    task = task_get(task_id)
    if not task:
        raise FileNotFoundError(f"任务不存在: {task_id}")

    task_path = task.get("task_path", "")
    article_md = Path(task_path) / ARTICLE_FILE
    if not article_md.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_md}")

    raw = article_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)

    resolved_theme = theme or task.get("theme") or "refined-blue"
    styles, highlights, divider_text, list_style = load_theme(theme_name=resolved_theme)
    html = convert_markdown_to_wechat_html(body, styles, highlights, divider_text, list_style)

    return {
        "title": fm.get("title") or task.get("title", ""),
        "html": html,
        "ai_score": task.get("ai_score"),
        "ai_verdict": task.get("ai_verdict"),
        "word_count": len(body),
        "theme": resolved_theme,
    }


async def check_ai_score(task_id: int, threshold: float = 45.0) -> dict:
    """对文章进行 AI 味检测。"""
    return await asyncio.to_thread(_check_ai_score_sync, task_id, threshold)


def _check_ai_score_sync(task_id: int, threshold: float) -> dict:
    from engine.db.models import task_get
    from engine.ai_score import check_ai_score as _check

    task = task_get(task_id)
    if not task:
        raise FileNotFoundError(f"任务不存在: {task_id}")

    task_path = task.get("task_path", "")
    article_md = Path(task_path) / ARTICLE_FILE
    if not article_md.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_md}")

    content = article_md.read_text(encoding="utf-8")
    passed, report = _check(content, threshold, mode="article")

    return {
        "passed": passed,
        "score": report.get("total_score", 0),
        "threshold": threshold,
        "dimensions": report.get("dimensions", {}),
        "hit_phrases": report.get("hit_phrases", [])[:20],
        "hit_vocab": report.get("hit_vocab", [])[:20],
    }
