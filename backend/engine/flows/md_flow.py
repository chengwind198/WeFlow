"""MdFlow —— 「AI去味发布」流程：用户已有 article.md + 配图，去味后发布。

与 NewsFlow 的差异：
- 跳过 理解需求 / 调研 / 撰写 / 配图生成（文章与图片由用户导入）
- 阶段: 导入确认(40) → 人味化改写(50) → 转换HTML(70)
       → AI味检测(80/85) → 发布(90)
- AI 味未过(85)时自动创建 stage=85 审核记录进入审核队列，
  审核通过后 _continue_pipeline 以 retry_from=85 续跑（跳过检测直接发布）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict

from engine.constants import Status, DirPath
from .base import FlowRunner

logger = logging.getLogger(__name__)

# 图片锚点正则（与 image_handler.extract_images_from_markdown 一致）
_ANCHOR_PATTERN = r'!\[([^\]]*)\]\(([^)]+)\)'


class MdFlow(FlowRunner):
    """md 类型：已有文章 + 配图，LLM 去味改写后发布到微信草稿箱。"""

    @staticmethod
    def flow_type() -> str:
        return "md"

    def execute(self) -> Dict[str, Any]:
        self._setup_environment()

        # 前端可覆盖的配置项：合并到 _account_cfg，优先级高于 config.yaml
        for key in ("theme", "voice", "provider", "author"):
            if self.kwargs.get(key):
                self._account_cfg[key] = self.kwargs[key]

        theme = self._account_cfg.get("theme") or self.kwargs.get("theme")
        provider = self.kwargs.get("provider")
        skip_ai_score = self.kwargs.get("skip_ai_score", False)

        # 断点重试：获取已有任务路径
        retry_from = getattr(self, 'retry_from', 0)
        existing_tid = self.kwargs.get("existing_task_id", 0)
        existing_path = self.kwargs.get("existing_task_path", "")
        _task_dir = Path(existing_path) if existing_path else None
        if not _task_dir:
            raise ValueError("md 流程必须提供 existing_task_path（文章由 import 接口导入）")

        from engine.config import ARTICLE_FILE
        article_path = _task_dir / ARTICLE_FILE
        if not article_path.exists():
            raise FileNotFoundError(f"{ARTICLE_FILE} 不存在: {article_path}")

        self.task_id = existing_tid
        logger.info("weflow Pipeline [md]: %s  账号: %s  %s",
                     self.topic, self.account,
                     f"(断点重试 retry_from={retry_from})" if retry_from else "标准模式")

        # ── 阶段一：文章导入确认（import 接口已落盘 article.md）──
        if retry_from >= Status.DRAFT_READY:
            logger.info("[MdFlow] 跳过阶段一（文章已就绪），task_id=%d", self.task_id)
        else:
            from engine.pipeline_db import db_transition
            n_chars = len(article_path.read_text(encoding="utf-8"))
            db_transition(self.task_id, Status.DRAFT_READY,
                          f"文章已导入 ({n_chars}字符)")

        # ── 审核检查：文章导入完成（status=40，默认不参与审核）──
        if self._check_review(40):
            return {"task_id": str(self.task_id), "article": str(article_path),
                    "status": "reviewing", "review_stage": 40}

        # ── 阶段二：人味化改写（保守 1 轮）→ 50 ──
        if retry_from >= Status.HUMANIZED:
            logger.info("[MdFlow] 跳过阶段二（人味化已完成）")
        else:
            from engine.humanize import humanize_article
            from engine.pipeline_db import db_transition

            raw = article_path.read_text(encoding="utf-8")
            result = humanize_article(raw, task_id=self.task_id,
                                       account_cfg=self._account_cfg,
                                       provider=provider)
            article_path.write_text(result["content"], encoding="utf-8")
            db_transition(self.task_id, Status.HUMANIZED,
                          f"人味化完成 ({result['rounds']}轮)")

        # ── 阶段三：转换 HTML → 70 ──
        if retry_from >= Status.HTML_CONVERTED:
            from engine.config import ARTICLE_HTML_FILE
            html_path = _task_dir / ARTICLE_HTML_FILE
            if html_path.exists():
                html = str(html_path)
                logger.info("[MdFlow] 跳过阶段三（HTML 已存在）: %s", html)
            else:
                logger.warning("[MdFlow] %s 不存在，回退执行阶段三", ARTICLE_HTML_FILE)
                html = self._stage_convert_to_html(str(article_path), theme)
        else:
            html = self._stage_convert_to_html(str(article_path), theme)

        # ── 阶段四：AI 味检测 → 80/85 ──
        # 85 审核通过后 retry_from=85 续跑：人工已确认可发布，跳过检测直接发布
        if retry_from >= Status.AI_SCORE_PASSED:
            ai_result = {"passed": True, "score": 0, "report": {}}
            logger.info("[MdFlow] 跳过阶段四（AI 检测已通过/人工审核已确认）")
        else:
            ai_result = self._stage_check_ai_score(str(article_path))

        if not ai_result["passed"] and not skip_ai_score:
            # AI 味未过 → 创建 stage=85 审核记录，进入审核队列等待人工确认
            self._create_review_on_ai_failed(ai_result["score"])
            return {"task_id": str(self.task_id), "article": str(article_path),
                    "html": html, "ai_score": str(ai_result["score"]),
                    "status": "reviewing", "review_stage": Status.AI_SCORE_FAILED}

        # ── 阶段五：发布 → 90 ──
        pub_result = self._stage_publish(str(article_path), theme=theme)

        result = {
            "task_id": str(self.task_id), "article": str(article_path),
            "html": html, "ai_score": str(ai_result["score"]),
            "media_id": pub_result.get("media_id", ""),
            "status": "published",
        }
        self._log_completion(result)
        return result

    # ── 阶段私有方法 ──

    def _stage_convert_to_html(self, article_path: str, theme: str = None) -> str:
        """阶段三：article.md → article.html（与 NewsFlow 同逻辑）。"""
        from engine.html_converter import convert_markdown_to_wechat_html, load_theme as _load_theme
        from engine.pipeline_db import db_transition
        from engine.article_images import parse_frontmatter
        from engine.utils import remove_anchor_placeholders

        ap = Path(article_path)
        raw = ap.read_text(encoding="utf-8")
        _, body = parse_frontmatter(raw)

        # 主题优先级: 参数 > DB task.theme > 配置 > 兜底
        resolved_theme = theme
        if not resolved_theme and self.task_id:
            try:
                from engine.db.models import task_get
                t = task_get(self.task_id)
                if t and t.get("theme"):
                    resolved_theme = t["theme"]
            except Exception as e:
                logger.debug("[MdFlow] 从 DB 读取 theme 失败: %s", e)
        if not resolved_theme:
            try:
                from engine.config import get_config
                resolved_theme = get_config().get("theme", "") or "refined-blue"
            except Exception:
                resolved_theme = "refined-blue"

        # 清理未替换的 anchor:// 锚点
        body = remove_anchor_placeholders(body)

        styles, highlights, divider_text, list_style = _load_theme(theme_name=resolved_theme)
        logger.info("[MdFlow] 阶段三 转换 HTML: theme=%s task=%d", resolved_theme, self.task_id)
        html = convert_markdown_to_wechat_html(body, styles, highlights, divider_text, list_style)

        html_path = ap.parent / "article.html"
        html_path.write_text(html, encoding="utf-8")
        db_transition(self.task_id, Status.HTML_CONVERTED,
                      f"HTML ({len(html)}字符, theme={resolved_theme})")
        return str(html_path)

    def _stage_check_ai_score(self, article_path: str, threshold: float = 45.0) -> dict:
        """阶段四：AI 味检测（对 article.md 内容检测，与 NewsFlow 同逻辑）。"""
        from engine.ai_score import check_ai_score as _check, DEFAULT_THRESHOLD as _DEFAULT
        from engine.pipeline_db import db_transition

        th = threshold if threshold is not None else _DEFAULT
        content = Path(article_path).read_text(encoding="utf-8")
        passed, report = _check(content, th, mode="article")
        score = report.get("total_score", 0)

        if self.task_id:
            try:
                from engine.db.models import task_update, status_transition
                from engine.constants import Operator, AIVerdict
                import json
                report_json = json.dumps(report, ensure_ascii=False)
                if passed:
                    db_transition(self.task_id, Status.AI_SCORE_PASSED,
                                  f"AI 味检测通过 ({score}/100)", ai_score=score,
                                  remark=report_json)
                else:
                    task_update(self.task_id, ai_score=score, ai_verdict=AIVerdict.FAIL)
                    status_transition(self.task_id, Status.AI_SCORE_FAILED,
                                      to_info=f"AI 评分 {score}/100 >= 阈值 {th}",
                                      operator=Operator.AI_SCORE,
                                      remark=report_json)
            except Exception as e:
                logger.debug("[MdFlow] AI 评分 DB 更新失败: %s", e)

        return {"passed": passed, "score": score, "report": report}

    def _create_review_on_ai_failed(self, score: float) -> None:
        """AI 味未过 → 创建 stage=85 审核记录（防重），进入审核队列。"""
        try:
            from engine.db.models import task_review_get_pending, task_review_insert
            existing = task_review_get_pending(self.task_id, Status.AI_SCORE_FAILED)
            if existing:
                logger.info("[MdFlow] stage=%d 已有待审核记录 review_id=%d，跳过",
                            Status.AI_SCORE_FAILED, existing["id"])
                return
            review_id = task_review_insert(
                task_id=self.task_id, stage=Status.AI_SCORE_FAILED, status="pending",
            )
            logger.info("[MdFlow] AI 味未过 (score=%.1f)，已创建审核 review_id=%d，等待人工确认",
                        score, review_id)
        except Exception as e:
            logger.error("[MdFlow] 创建 AI 味审核记录失败: %s", e)

    def _stage_publish(self, article_path: str, theme: str = None) -> dict:
        """阶段五：发布到微信草稿箱。

        封面优先取 md 正文中第一个图片锚点对应的图片（更符合用户直觉）；
        无图片时传空，由 publish 内部自动生成封面。
        """
        from engine.publish import publish_from_markdown

        ap = Path(article_path)
        raw = ap.read_text(encoding="utf-8")

        # 封面：md 中第一个「文件已就位」的锚点图 → images/ 下对应文件
        # （与 import 接口的 is_cover 标记规则一致；全部缺失则回退自动生成）
        cover = ""
        for _, url in re.findall(_ANCHOR_PATTERN, raw):
            name = Path(url.strip()).name
            if name:
                cand = ap.parent / DirPath.IMAGES / name
                if cand.exists():
                    cover = str(cand)
                    break

        logger.info("[MdFlow] 阶段五 发布: article=%s task=%d theme=%s cover=%s",
                    article_path, self.task_id, theme or '默认',
                    cover or '(无封面，将自动生成)')
        try:
            result = publish_from_markdown(
                md_path=article_path, title=None, cover_path=cover,
                theme=theme, account_name=self.account,
                author=self._account_cfg.get("author") or None,
                task_id=self.task_id, draft_msg_id=0,
            )
        except Exception as e:
            # 微信接口返回错误（如封面裁剪失败）→ 落 88（发布失败），
            # 由 generation._run 检测到 88 后跳过 ABANDONED，任务可重试
            from engine.publish import _record_publish_failure
            _record_publish_failure(self.task_id, f"微信发布失败: {e}")
            logger.error("[MdFlow] 阶段五 发布失败 task=%d: %s", self.task_id, e)
            raise
        return result
