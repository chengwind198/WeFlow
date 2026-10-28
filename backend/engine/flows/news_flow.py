"""NewsFlow —— 标准公众号图文全流程（当前唯一的完整流程实现）。

支持 --no-images 模式：跳过阶段四配图生成，文章不含配图锚点，
封面图在发布时按需自动生成。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from engine.constants import Status, DirPath
from .base import FlowRunner

logger = logging.getLogger(__name__)


class NewsFlow(FlowRunner):
    """news 类型：标准图文 7 阶段流程。

    阶段: understand → draft → generate_images → convert_to_html
          → check_ai_score → publish → sync
    """

    @staticmethod
    def flow_type() -> str:
        return "article"

    def execute(self) -> Dict[str, Any]:
        self._setup_environment()

        # 前端可覆盖的配置项：合并到 _account_cfg，优先级高于 config.yaml
        for key in ("article_structure", "opening_hook", "voice", "theme", "image_style", "genre"):
            if self.kwargs.get(key):
                self._account_cfg[key] = self.kwargs[key]

        provider = self.kwargs.get("provider")
        theme = self._account_cfg.get("theme") or self.kwargs.get("theme")
        skip_ai_score = self.kwargs.get("skip_ai_score", False)
        sync = self.kwargs.get("sync")
        no_images = self.kwargs.get("no_images", False)
        # need_images: type=news 且 --no-images 时为 0，否则为 1
        self.kwargs["need_images"] = 0 if no_images else 1

        # 断点重试：获取已有任务路径
        retry_from = getattr(self, 'retry_from', 0)
        existing_tid = self.kwargs.get("existing_task_id", 0)
        existing_path = self.kwargs.get("existing_task_path", "")
        _task_dir = Path(existing_path) if existing_path else None

        logger.info("weflow Pipeline [news]: %s  账号: %s  %s%s",
                     self.topic, self.account,
                     "无配图模式 " if no_images else "",
                     f"(断点重试 retry_from={retry_from})" if retry_from else "标准模式")

        # ── 阶段一：理解需求 → brief.md + 创建 task ──
        if retry_from >= Status.BRIEF_READY:
            logger.info("[NewsFlow] 跳过阶段一（brief 已就绪），task_id=%d", existing_tid)
            self.task_id = existing_tid
            from engine.config import BRIEF_FILE
            brief = str(_task_dir / BRIEF_FILE) if _task_dir else ""
            if not brief or not Path(brief).exists():
                logger.warning("[NewsFlow] %s 不存在，回退执行阶段一", BRIEF_FILE)
                brief, _ = self._create_task_and_brief()
        else:
            brief, _ = self._create_task_and_brief()

        # ── 审核检查：阶段一完成（选题简报已就绪，status=20）──
        if self._check_review(20):
            return {"task_id": str(self.task_id), "brief": brief,
                    "status": "reviewing", "review_stage": 20}

        # 阶段二：调研（暂时关闭）
        research = ""

        # ── 阶段三：撰写骨架稿 → article.md ──
        if retry_from >= Status.DRAFT_READY:
            from engine.config import ARTICLE_FILE
            article = str(_task_dir / ARTICLE_FILE) if _task_dir else ""
            if article and Path(article).exists():
                logger.info("[NewsFlow] 跳过阶段三（草稿已存在）: %s", article)
            else:
                logger.warning("[NewsFlow] %s 不存在，回退执行阶段三", ARTICLE_FILE)
                from engine.draft import write_draft
                article = write_draft(brief, research, self.task_id, self._account_cfg,
                                      no_images=no_images)
        else:
            from engine.draft import write_draft
            article = write_draft(brief, research, self.task_id, self._account_cfg,
                                  no_images=no_images)

        # ── 审核检查：阶段三完成（文章已就绪，status=40）──
        if self._check_review(40):
            return {"task_id": str(self.task_id), "brief": brief, "article": article,
                    "status": "reviewing", "review_stage": 40}

        # ── 阶段四：生成配图（无配图模式跳过）──
        # 始终调用 generate_images()，其内部逐张检查文件是否已存在，
        # 已生成的文件自动跳过，失败的文件（upload_status=generate_failed）重新生成。
        images = []
        if no_images:
            logger.info("[NewsFlow] 无配图模式，跳过阶段四（配图生成）")
            # 生成封面图（从 _stage_publish 拆出，使封面也可审核）
            from engine.article_images import generate_cover
            from engine.pipeline_db import db_transition
            cover_result = generate_cover(
                str(Path(article).parent / "article.md") if article else "",
                self.task_id, provider=provider,
                image_style=self._account_cfg.get("image_style"),
            )
            if cover_result:
                images = [cover_result]
                if retry_from < Status.IMAGES_GENERATED:
                    db_transition(self.task_id, Status.IMAGES_GENERATED,
                                  f"封面图已生成 ({provider or '默认'})")
        else:
            from engine.article_images import generate_images
            # 重试时跳过状态推进（避免 88→60 回退），仅补齐缺失图片
            skip_transition = retry_from >= Status.IMAGES_GENERATED
            images = generate_images(article, self.task_id, provider=provider,
                                     skip_status_transition=skip_transition)

        # ── 审核检查：阶段四完成（配图已生成，status=60）──
        if self._check_review(60):
            return {"task_id": str(self.task_id), "brief": brief, "article": article,
                    "images": str(len(images)),
                    "status": "reviewing", "review_stage": 60}

        # ── 阶段五：转换 HTML ──
        if retry_from >= Status.HTML_CONVERTED:
            from engine.config import ARTICLE_HTML_FILE
            html_path = _task_dir / ARTICLE_HTML_FILE if _task_dir else None
            if html_path and html_path.exists():
                html = str(html_path)
                logger.info("[NewsFlow] 跳过阶段五（HTML 已存在）: %s", html)
            else:
                logger.warning("[NewsFlow] %s 不存在，回退执行阶段五", ARTICLE_HTML_FILE)
                html = self._stage_convert_to_html(article, theme)
        else:
            html = self._stage_convert_to_html(article, theme)

        # ── 阶段 5.5：AI 味检测 ──
        if retry_from >= Status.AI_SCORE_PASSED:
            ai_result = {"passed": True, "score": 0, "report": {}}
            logger.info("[NewsFlow] 跳过阶段 5.5（AI 检测已通过）")
        else:
            ai_result = self._stage_check_ai_score(article)

        if not ai_result["passed"] and not skip_ai_score:
            logger.warning("AI味检测未通过！手动改写后重新发布，或 --skip-ai-score")
            return {"task_id": str(self.task_id), "brief": brief, "article": article,
                    "ai_score": str(ai_result["score"]), "status": "ai_failed"}

        # 阶段六：发布（重试时 AI 已通过则跳过 publish 内置的预检）
        pub_result = self._stage_publish(
            article,
            no_images=no_images,
            provider=provider,
        )

        # 阶段七：多平台同步
        if sync:
            platforms = [p.strip() for p in sync.split(",") if p.strip()]
            if platforms:
                self._stage_sync(article, platforms)

        result = {
            "task_id": str(self.task_id), "brief": brief, "article": article,
            "images": str(len(images)), "html": html,
            "ai_score": str(ai_result["score"]),
            "media_id": pub_result.get("media_id", ""),
            "status": "published",
        }
        self._log_completion(result)
        return result

    # ── 阶段私有方法 ──

    def _stage_convert_to_html(self, article_path: str, theme: str = None) -> str:
        """阶段五：article.md → article.html。"""
        from pathlib import Path
        from engine.html_converter import convert_markdown_to_wechat_html, load_theme as _load_theme
        from engine.pipeline_db import db_transition
        from engine.article_images import parse_frontmatter

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
                logger.debug("[NewsFlow] 从 DB 读取 theme 失败: %s", e)
        if not resolved_theme:
            try:
                from engine.config import get_config
                resolved_theme = get_config().get("theme", "") or "refined-blue"
            except Exception:
                resolved_theme = "refined-blue"

        # 清理未替换的 anchor:// 锚点
        from engine.utils import remove_anchor_placeholders
        body = remove_anchor_placeholders(body)

        styles, highlights, divider_text, list_style = _load_theme(theme_name=resolved_theme)
        logger.info("[NewsFlow] 阶段五 转换 HTML: theme=%s task=%d", resolved_theme, self.task_id)
        html = convert_markdown_to_wechat_html(body, styles, highlights, divider_text, list_style)

        html_path = ap.parent / "article.html"
        html_path.write_text(html, encoding="utf-8")
        db_transition(self.task_id, Status.HTML_CONVERTED,
                      f"HTML ({len(html)}字符, theme={resolved_theme})")
        return str(html_path)

    def _stage_check_ai_score(self, article_path: str, threshold: float = 45.0) -> dict:
        """阶段 5.5：AI 味检测。"""
        from pathlib import Path
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
                logger.debug("[NewsFlow] AI 评分 DB 更新失败: %s", e)

        return {"passed": passed, "score": score, "report": report}

    def _stage_publish(self, article_path: str,
                        no_images: bool = False, provider: str = None) -> dict:
        """阶段六：发布到微信草稿箱（纯发布，AI 检测已前置到 _stage_check_ai_score）。

        封面图优先取 images/ 下第一张图片；若无则从 task_image 表查找 is_cover=1 的记录。
        （封面生成已在阶段四完成，此处不再内联生成。）
        """
        from pathlib import Path
        from engine.publish import publish_from_markdown

        ap = Path(article_path)
        images_dir = ap.parent / DirPath.IMAGES
        cover = None
        if images_dir.exists():
            imgs = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
            if imgs:
                cover = str(imgs[0])

        # 获取 draft message_id（用于定位封面图）
        draft_msg_id = 0
        try:
            from engine.db.models import task_message_get_last_assistant
            draft_msg_id = task_message_get_last_assistant(self.task_id, "write_draft")
        except Exception as e:
            logger.debug("[NewsFlow] 获取 draft_msg_id 失败: %s", e)

        # 如果 images/ 下无图片，尝试从 task_image 表查找封面记录
        if not cover:
            try:
                from engine.db.models import image_find_cover
                img = image_find_cover(self.task_id, draft_msg_id)
                if img and img.get("local_path"):
                    lp = img["local_path"]
                    if "/" not in lp and "\\" not in lp:
                        lp = f"images/{lp}"
                    cover_full = ap.parent / lp
                    if cover_full.exists():
                        cover = str(cover_full)
                        logger.info("[NewsFlow] 从 task_image 加载封面: %s", cover)
            except Exception as e:
                logger.debug("[NewsFlow] 查询 task_image 封面失败: %s", e)

        # 传递 theme 给 publish，确保 HTML 排版风格一致
        theme = self.kwargs.get("theme")

        logger.info("[NewsFlow] 阶段六 发布: article=%s task=%d theme=%s cover=%s",
                     article_path, self.task_id, theme or '默认',
                     cover or '(无封面)')
        result = publish_from_markdown(
            md_path=article_path, title=None, cover_path=cover or "",
            theme=theme, account_name=self.account,
            task_id=self.task_id, draft_msg_id=draft_msg_id,
        )
        return result

    def _stage_sync(self, article_path: str, platforms: List[str]) -> dict:
        """阶段七：同步到多平台。"""
        from engine.multi_publish import run as _sync_run

        logger.info("[NewsFlow] 阶段七 多平台同步: %s", platforms)
        result = _sync_run(md_path=article_path, platforms=platforms, strict=False)
        logger.info("[NewsFlow] 阶段七完成: %s", 'OK' if result.get('success') else 'FAIL')
        return result
