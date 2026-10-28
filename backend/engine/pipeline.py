#!/usr/bin/env python3
"""
weflow 文章生成 Pipeline（全阶段 1-7）。
pipeline.py 只负责流程串接，各阶段具体逻辑分布如下：

  阶段一 → understand.py      understand_requirements()
  阶段二 → research.py        search_and_research()
  阶段三 → draft.py           write_draft()
  阶段四 → article_images.py  generate_images()
  阶段五 → html_converter.py  convert_to_html()
  阶段5.5 → ai_score.py       check_ai_score()
  阶段六 → publish.py         publish_to_wechat()
  阶段七 → multi_publish.py   sync_to_platforms()

用法:
  # 一键全流程（必选 --topic，其他可选）
  python engine/pipeline.py run --topic "话题"
  python engine/pipeline.py run --topic "话题" --account main
  python engine/pipeline.py run --topic "话题" --theme refined-blue
  python engine/pipeline.py run --topic "话题" --provider z_image
  python engine/pipeline.py run --topic "话题" --skip-ai-score
  python engine/pipeline.py run --topic "话题" --sync "zhihu,juejin,csdn"
  python engine/pipeline.py run --topic "话题" --user-details "@./details.md"
  python engine/pipeline.py run --topic "话题" --user-details "具体的参考素材文本"
  python engine/pipeline.py run --topic "话题" --no-images

  # 分阶段执行
  python engine/pipeline.py understand_requirements --topic "话题"
  python engine/pipeline.py understand_requirements --topic "话题" --user-details "@./details.md"
  python engine/pipeline.py search_and_research --brief ./brief.md --task-id 1
  python engine/pipeline.py write_draft --brief ./brief.md --research ./research.md --task-id 1
  python engine/pipeline.py generate_images --article ./article.md --task-id 1 --provider z_image
  python engine/pipeline.py convert_to_html --article ./article.md --task-id 1 --theme refined-blue
  python engine/pipeline.py check_ai_score --article ./article.md --task-id 1 --threshold 45.0
  python engine/pipeline.py publish_to_wechat --article ./article.md --task-id 1 --title "标题"
  python engine/pipeline.py sync_to_platforms --article ./article.md --platforms "zhihu,juejin"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 确保 backend 目录在 Python 路径中，支持从项目根目录直接运行
_sys_path = Path(__file__).resolve().parent.parent
if str(_sys_path) not in sys.path:
    sys.path.insert(0, str(_sys_path))

from engine.constants import Status, DirPath
from engine.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 流程串接：run
# ============================================================

def run(topic: str, account: str = "main", output_dir: Optional[str] = None,
        provider: Optional[str] = None, theme: Optional[str] = None,
        skip_ai_score: bool = False, sync: Optional[str] = None,
        user_details: Optional[str] = None,
        task_type: str = "article",
        no_images: bool = False,
        article_structure: Optional[str] = None,
        opening_hook: Optional[str] = None,
        voice: Optional[str] = None,
        image_style: Optional[str] = None,
        genre: Optional[str] = None,
        author: Optional[str] = None,
        existing_task_id: int = 0,
        existing_task_path: str = "",
        retry_from: int = 0) -> Dict[str, str]:
    """分发到对应的 FlowRunner 执行全流程。"""
    from engine.flows import get_flow, list_flow_types

    flow_cls = get_flow(task_type)
    if not flow_cls:
        valid = ", ".join(list_flow_types())
        raise ValueError(f"未知的任务类型 '{task_type}'，有效值: {valid}")

    flow = flow_cls(
        topic=topic,
        account=account,
        output_dir=output_dir,
        retry_from=retry_from,
        provider=provider,
        theme=theme,
        skip_ai_score=skip_ai_score,
        sync=sync,
        user_details=user_details,
        no_images=no_images,
        article_structure=article_structure,
        opening_hook=opening_hook,
        voice=voice,
        image_style=image_style,
        genre=genre,
        author=author,
        existing_task_id=existing_task_id,
        existing_task_path=existing_task_path,
    )
    return flow.execute()


def retry_run(
    task_id: int,
    task_type: str,
    topic: str,
    account: str,
    task_path: str,
    retry_from: int,
    provider: Optional[str] = None,
    theme: Optional[str] = None,
    image_style: Optional[str] = None,
    article_structure: Optional[str] = None,
    opening_hook: Optional[str] = None,
    voice: Optional[str] = None,
    genre: Optional[str] = None,
    no_images: bool = False,
    user_details: Optional[str] = None,
) -> Dict[str, Any]:
    """从指定断点重试失败任务。

    使用 existing_task_id + retry_from 复用已有任务记录和产物，
    FlowRunner 会根据 retry_from 自动跳过已完成的阶段。

    Args:
        task_id: 要重试的任务 ID
        task_type: "article" 或 "image"
        topic: 话题
        account: 账号名
        task_path: 任务产物目录路径
        retry_from: 恢复起点状态码（如 80 表示从发布阶段开始）
        其他参数同 run()
    """
    return run(
        topic=topic,
        account=account,
        task_type=task_type,
        existing_task_id=task_id,
        existing_task_path=task_path,
        retry_from=retry_from,
        provider=provider,
        theme=theme,
        image_style=image_style,
        article_structure=article_structure,
        opening_hook=opening_hook,
        voice=voice,
        genre=genre,
        no_images=no_images,
        user_details=user_details,
    )


# ============================================================
# 阶段五~七：薄封装（委托给已有模块）
# ============================================================

def convert_to_html(article_path: str, task_id: int = 0,
                    theme: Optional[str] = None) -> str:
    """阶段五：article.md → article.html。"""
    from engine.html_converter import convert_markdown_to_wechat_html, load_theme as _load_theme
    from engine.config import get_config
    from engine.pipeline_db import db_transition
    from engine.article_images import parse_frontmatter

    ap = Path(article_path)
    if not ap.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_path}")

    raw = ap.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)

    # 从 task 表读取 theme，回退到配置默认值
    resolved_theme = theme  # 参数优先级最高
    if not resolved_theme and task_id > 0:
        try:
            from engine.db.models import task_get
            t = task_get(task_id)
            if t and t.get("theme"):
                resolved_theme = t["theme"]
        except Exception as e:
            logger.debug("[Pipeline] 从 DB 读取 theme 失败: %s", e)
    if not resolved_theme:
        try:
            resolved_theme = get_config().get("theme", "") or "refined-blue"
        except Exception as e:
            logger.debug("[Pipeline] 读取默认 theme 失败: %s", e)
            resolved_theme = "refined-blue"

    # 清理未替换的 anchor:// 内部锚点（阶段四未运行时的残留）
    from engine.utils import remove_anchor_placeholders
    body = remove_anchor_placeholders(body)

    styles, highlights, divider_text, list_style = _load_theme(theme_name=resolved_theme)

    logger.info("[阶段五] 转换 HTML: theme=%s task=%d", resolved_theme, task_id)
    html = convert_markdown_to_wechat_html(body, styles, highlights, divider_text, list_style)

    from engine.config import ARTICLE_HTML_FILE
    html_path = ap.parent / ARTICLE_HTML_FILE
    html_path.write_text(html, encoding="utf-8")
    db_transition(task_id, Status.HTML_CONVERTED, f"HTML ({len(html)}字符, theme={resolved_theme})")
    logger.info("阶段五完成 → %s (%d 字符)", html_path, len(html))
    return str(html_path)


def check_ai_score(article_path: str, task_id: int = 0,
                   threshold: float = 45.0) -> dict:
    """阶段5.5：AI味检测。"""
    from engine.ai_score import check_ai_score as _check
    from engine.pipeline_db import db_transition

    ap = Path(article_path)
    if not ap.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_path}")

    passed, report = _check(ap.read_text(encoding="utf-8"), threshold, mode="article")
    score = report.get("total_score", 0)
    report_json = json.dumps(report, ensure_ascii=False)

    logger.info("[阶段5.5] AI味检测: score=%.1f task=%d passed=%s", score, task_id, passed)

    if passed:
        db_transition(task_id, Status.AI_SCORE_PASSED, f"AI评分 {score}/100 PASS",
                      remark=report_json, ai_score=score, ai_verdict="PASS")
    else:
        db_transition(task_id, Status.AI_SCORE_FAILED, f"AI评分 {score}/100 FAIL (threshold={threshold})",
                      remark=report_json, ai_score=score, ai_verdict="FAIL")

    verdict = "🟢 PASS" if passed else "🔴 FAIL"
    logger.info("阶段5.5 AI味检测: %s (score=%.1f/100)", verdict, score)
    return {"passed": passed, "score": score, "report": report}


def publish_to_wechat(article_path: str, task_id: int = 0,
                      title: Optional[str] = None,
                      account_name: Optional[str] = None,
                      skip_ai_score: bool = False,
                      ai_score_threshold: float = None,
                      draft_msg_id: int = 0) -> dict:
    """阶段六：发布到微信草稿箱。"""
    from engine.publish import publish_from_markdown, run_news_ai_gate
    ap = Path(article_path)
    if not ap.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_path}")

    md_content = ap.read_text(encoding="utf-8")

    # AI 味检测（已从 publish_from_markdown 中拆出，在此前置执行）
    if not skip_ai_score:
        try:
            run_news_ai_gate(md_content, task_id=task_id, ai_score_threshold=ai_score_threshold)
        except Exception as e:
            logger.error("[阶段六] AI 味检测未通过: %s", e)
            raise

    # 从 task 表读取 theme
    theme = None
    if task_id > 0:
        try:
            from engine.db.models import task_get
            t = task_get(task_id)
            if t:
                theme = t.get("theme") or None
        except Exception as e:
            logger.debug("[Pipeline] 从 DB 读取 theme 失败: %s", e)

        # 获取 draft message_id（用于定位封面图）
        if not draft_msg_id:
            try:
                from engine.db.models import task_message_get_last_assistant
                draft_msg_id = task_message_get_last_assistant(task_id, "write_draft")
            except Exception as e:
                logger.debug("[Pipeline] 获取 draft_msg_id 失败: %s", e)

    images_dir = ap.parent / DirPath.IMAGES
    cover = None
    if images_dir.exists():
        imgs = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
        if imgs:
            cover = str(imgs[0])

    logger.info("[阶段六] 发布: article=%s task=%d theme=%s draft_msg_id=%d",
                article_path, task_id, theme or '默认', draft_msg_id)
    result = publish_from_markdown(
        md_path=article_path, title=title, cover_path=cover or "",
        theme=theme, account_name=account_name,
        task_id=task_id, draft_msg_id=draft_msg_id)
    logger.info("阶段六完成 → media_id: %s", result.get('media_id', '?'))
    return result


def sync_to_platforms(article_path: str, platforms: List[str],
                      title: Optional[str] = None) -> dict:
    """阶段七：同步到知乎/掘金/CSDN 等平台。"""
    from engine.multi_publish import run as _sync_run

    logger.info("[阶段七] 多平台同步: %s", platforms)
    result = _sync_run(md_path=article_path, platforms=platforms, title=title, strict=False)
    logger.info("阶段七完成: %s", '✅' if result.get('success') else '⚠')
    return result


# ============================================================
# CLI
# ============================================================

def _add_topic(p): p.add_argument("--topic", required=True)
def _add_account(p): p.add_argument("--account", default="main")
def _add_tid(p): p.add_argument("--task-id", type=int, default=0)
def _add_brief(p): p.add_argument("--brief", required=True, help="brief.md 路径")
def _add_article(p): p.add_argument("--article", required=True, help="article.md 路径")


def main():
    parser = argparse.ArgumentParser(description="weflow Pipeline")
    sub = parser.add_subparsers(dest="command")

    # run
    p = sub.add_parser("run", help="一键全流程")
    _add_topic(p); _add_account(p)
    p.add_argument("--output-dir"); p.add_argument("--provider")
    p.add_argument("--theme"); p.add_argument("--skip-ai-score", action="store_true")
    p.add_argument("--sync")
    p.add_argument("--no-images", action="store_true",
                   help="跳过配图生成，文章不包含图片锚点。封面图在发布时按需自动生成。")
    p.add_argument("--user-details", help="覆盖 config.yml 中的 user_details，支持 @文件路径 语法")
    p.add_argument("--type", default="article", dest="task_type",
                   help="任务类型 (article / image)，默认 article")
    p.set_defaults(func=lambda a: run(a.topic, a.account, a.output_dir, a.provider, a.theme,
                                       a.skip_ai_score, a.sync, a.user_details, a.task_type,
                                       a.no_images))

    # stage 1
    p = sub.add_parser("understand_requirements", help="阶段一→brief.md")
    _add_topic(p); _add_account(p); p.add_argument("--output-dir")
    p.add_argument("--user-details", help="覆盖 config.yml 中的 user_details，支持 @文件路径 语法")
    p.set_defaults(func=lambda a: _run_stage1(a.topic, a.account, a.output_dir, a.user_details))

    # stage 2
    p = sub.add_parser("search_and_research", help="阶段二→research.md")
    _add_brief(p); _add_tid(p)
    p.set_defaults(func=lambda a: _run_stage2(a.brief, a.task_id))

    # stage 3
    p = sub.add_parser("write_draft", help="阶段三→article.md")
    _add_brief(p); p.add_argument("--research"); _add_tid(p)
    p.add_argument("--no-images", action="store_true",
                   help="无配图模式：不生成 image_prompts，文章不包含图片锚点")
    p.set_defaults(func=lambda a: _run_stage3(a.brief, a.research, a.task_id, a.no_images))

    # stage 4
    p = sub.add_parser("generate_images", help="阶段四→配图")
    _add_article(p); _add_tid(p); p.add_argument("--provider")
    p.set_defaults(func=lambda a: _run_stage4(a.article, a.task_id, a.provider))

    # stage 5
    p = sub.add_parser("convert_to_html", help="阶段五→HTML")
    _add_article(p); _add_tid(p); p.add_argument("--theme")
    p.set_defaults(func=lambda a: convert_to_html(a.article, a.task_id, a.theme))

    # stage 5.5
    p = sub.add_parser("check_ai_score", help="阶段5.5→AI检测")
    _add_article(p); _add_tid(p); p.add_argument("--threshold", type=float, default=45.0)
    p.set_defaults(func=lambda a: check_ai_score(a.article, a.task_id, a.threshold))

    # stage 6
    p = sub.add_parser("publish_to_wechat", help="阶段六→发布")
    _add_article(p); _add_tid(p)
    p.add_argument("--title"); p.add_argument("--account-name"); p.add_argument("--skip-ai-score", action="store_true")
    p.set_defaults(func=lambda a: publish_to_wechat(a.article, a.task_id, a.title, a.account_name, a.skip_ai_score))

    # stage 7
    p = sub.add_parser("sync_to_platforms", help="阶段七→多平台同步")
    _add_article(p)
    p.add_argument("--platforms", required=True, help="逗号分隔"); p.add_argument("--title")
    p.set_defaults(func=lambda a: sync_to_platforms(a.article, [x.strip() for x in a.platforms.split(",")], a.title))

    args = parser.parse_args()
    if not args.command:
        parser.print_help(); sys.exit(1)
    try:
        args.func(args)
    except Exception as e:
        # 发布失败等异常：打印错误并退出（CLI 场景）；后台线程场景由 generation.py 处理
        logger.error("%s: %s", type(e).__name__, e)
        sys.exit(1)


# CLI 子命令的延迟 import helper（避免启动时加载全部依赖）
def _run_stage1(topic, account, output_dir, user_details=None):
    from engine.config import get_config, load_env, set_account
    load_env(); set_account(account)
    try:
        cfg = get_config(account)
    except Exception as e:
        logger.debug("[Pipeline] 加载账号配置失败 (stage1 CLI): %s", e)
        cfg = {}
    from engine.understand import understand_requirements
    understand_requirements(topic, account, output_dir, cfg, user_details)

def _run_stage2(brief, task_id):
    from engine.research import search_and_research
    search_and_research(brief, task_id)

def _run_stage3(brief, research, task_id, no_images=False):
    from engine.draft import write_draft
    write_draft(brief, research, task_id, account_cfg=None, no_images=no_images)

def _run_stage4(article, task_id, provider):
    from engine.article_images import generate_images
    generate_images(article, task_id, provider)


if __name__ == "__main__":
    main()
