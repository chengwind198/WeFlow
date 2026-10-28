"""NewspicFlow —— 贴图（图片消息）全流程实现。

阶段: 创建任务 → 生成newspic格式brief → 拆卡入task_image → 生图 → AI检测 → 发布
全程以 task_image 表为数据中枢，不依赖 card_plan.json。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# scripts/ 不是 Python 包，手动加到 sys.path 以支持同级模块导入
_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from engine.constants import Status, Stage, Role, LLMDefaults, Operator, DirPath
from .base import FlowRunner

logger = logging.getLogger(__name__)

# ============================================================
# Newspic brief 生成的 System Prompt
# ============================================================

_NEWSPIC_BRIEF_PROMPT = """你是一个资深的公众号贴图（图片消息）策划助手。

贴图是一种特殊的微信内容形式：由 5-10 张图片卡片 + 一段 100-300 字的短文本描述组成。
每张卡片承载一个独立的要点，图片上可以有少量文字（关键词、数字等）。

根据 `选题简报` 和 `研究素材` 的内容，自主选择 1 个图片风格（image_styles）和 1 个文章体裁（genre）。


# 文章体裁选配

- 新闻资讯、热点速递 → 记叙文（narrative）：讲述事件过程，传递信息与体验
- 教程、科普、技术解读 → 说明文（expository）：清晰解释事物，客观准确，术语规范
- 观点评论、行业分析 → 议论文（argumentative）：提出并论证观点，逻辑严密，说服读者
- 生活方式、情感共鸣、体验分享 → 抒情文（lyrical）：抒发感受，富于感染力，引发共鸣
- 工具推荐、清单盘点、实用指南 → 应用文（practical）：规范简洁，针对性强，便于实用

优先级：用户指定 > 题材匹配 > AI 自主选择。用户指定体裁时直接使用，不要自行更改。

# 图片风格选配

- AI、产品深挖、功能拆解：首选 infographic-warm，备选 infographic-blue、hand-drawn-blue
- 技术、架构、SDK、协议：首选 infographic-blue，备选 blue、hand-drawn-blue
- 步骤教程、工具对比：首选 flat-editorial，备选 warm-handdrawn、knowledge-card
- 数据、报告、趋势：首选 data-chart，备选 infographic-blue
- 热点、标题党、短句：首选 marker-lime，备选其他 marker 系列
- 生活方式、清单、盘点：首选 warm-handdrawn，备选 xiaohongshu-colorful、mint
- 观点、人文、深度评论：首选 morandi，备选 magazine-editorial
- 体验分享、有人物叙事：首选 illustrated-warm，备选 slice-of-life

你的任务是根据用户输入的话题，输出一份贴图策划简报，严格按以下格式：

---
topic: 话题名称（不要加引号）
title: 文章标题，吸引眼球，15字以内（不要加引号）
image_style: 图片风格代码
card_count: 3-8的数字
genre: 文件体裁代码
---

**YAML 约束：**
- Frontmatter 值**禁止使用双引号或单引号包裹**，直接写纯文本
- 如果话题名称本身包含引号（如书名号《》、中文引号「」），直接保留，不要额外加英文引号
- 这是为了确保 YAML 解析不会因引号嵌套而失败

**务必先写 "# 要点" 作为一级标题（三个字符：# 空格 要点），再列出编号列表，否则解析会失败。**

# 要点

1. [要点1，一句话，15-25字，信息密度高]
2. [要点2]
3. [要点3]
...

# 短文本

[100-300字的短文，概括这批卡片的核心信息，语气自然、有个人观点，避免AI套话]

**格式约束：**
- Frontmatter 必须是标准 YAML（`---` 开头和结尾），第一行即 `---`
- Frontmatter 值不要用引号包裹，直接写纯文本
- `card_count` 与要点数量一致
- 要点每条一句话，适合做成信息图卡片
- 短文本 100-300 字，自然口语化
- 不要输出任何 Frontmatter 之外的解释性文字
"""


def _persist_brief_to_task(tid: int, brief_content: str) -> None:
    """从 image 模式 brief.md 解析 title/image_style/short_text 并持久化到 task 表。

    后续 publish 流程优先使用 task 表字段，brief.md 解析仅作为 fallback。
    失败不影响主流程（仅日志记录）。
    """
    try:
        from engine.newspic_build import parse_brief
        from engine.db.models import task_update

        parsed = parse_brief(brief_content)
        fm = parsed.get("frontmatter", {})
        sections = parsed.get("sections", {})

        task_updates = {}
        if fm.get("title"):
            task_updates["title"] = fm["title"]
        if fm.get("image_style"):
            task_updates["image_style"] = fm["image_style"]
        if fm.get("genre"):
            task_updates["genre"] = fm["genre"]
        short_text = (sections.get("短文本") or sections.get("短描述") or "").strip()
        if short_text:
            task_updates["short_text"] = short_text

        if task_updates:
            task_update(tid, **task_updates)
            logger.info("[NewspicFlow] 已持久化字段到 task 表: %s", list(task_updates.keys()))
    except Exception as e:
        logger.warning("[NewspicFlow] 持久化 brief 字段到 task 表失败（不影响主流程）: %s", e)


def _persist_bullet_points_to_task_image(tid: int, brief_content: str) -> None:
    """从 brief.md 解析「要点」列表，每条写入 task_image（seq + description 原文，prompt 留空）。

    mode 35 将从此表读取卡片描述并套用风格模板生成 prompt。
    失败不影响主流程（仅日志记录）。
    """
    try:
        from engine.newspic_build import parse_brief, extract_bullet_points
        from engine.db.models import image_delete_by_task, image_insert

        parsed = parse_brief(brief_content)
        fm = parsed.get("frontmatter", {})
        style = fm.get("image_style", "") or ""
        section_text = parsed.get("sections", {}).get("要点", "")
        points = extract_bullet_points(section_text)
        if not points:
            logger.info("[NewspicFlow] brief.md 中「要点」无可解析的列表项，跳过 task_image 写入")
            return

        # 预填 provider / model / size（与阶段三 _generate_cards 一致）
        from engine.image_gen_core import detect_provider, get_default_model
        provider = detect_provider()
        model = get_default_model(provider)

        # 先清理旧记录，防止重试时积累
        image_delete_by_task(tid)

        for idx, point in enumerate(points, start=1):
            image_insert(
                task_id=tid, seq=idx, anchor="",
                description=point, prompt=point,
                provider=provider, model=model,
                image_style=style, size="",
            )
        logger.info("[NewspicFlow] 已写入 %d 条卡片要点到 task_image", len(points))
    except Exception as e:
        logger.warning("[NewspicFlow] 写入卡片要点到 task_image 失败（不影响主流程）: %s", e)


class NewspicFlow(FlowRunner):
    """newspic 类型：贴图/图片消息流程。

    完整流程：创建任务 → 生成newspic格式brief(20) → 拆卡入task_image(35)
             → 生图(60) → AI味检测(80) → 发布(90)
    全程以 task_image 表为数据中枢。
    """

    @staticmethod
    def flow_type() -> str:
        return "image"

    def execute(self) -> Dict[str, Any]:
        self._setup_environment()

        # 前端可覆盖的配置项：合并到 _account_cfg
        # image_style 映射为 newspic_image_style（前端统一用 image_style 传参）
        frontend_image_style = self.kwargs.get("image_style")
        if frontend_image_style:
            self._account_cfg["newspic_image_style"] = frontend_image_style
        for key in ("voice", "newspic_image_style", "genre"):
            if self.kwargs.get(key):
                self._account_cfg[key] = self.kwargs[key]

        provider = self.kwargs.get("provider")
        skip_ai_score = self.kwargs.get("skip_ai_score", False)

        # 断点重试：获取已有任务路径
        retry_from = getattr(self, 'retry_from', 0)
        existing_tid = self.kwargs.get("existing_task_id", 0)
        existing_path = self.kwargs.get("existing_task_path", "")
        _task_dir = Path(existing_path) if existing_path else None

        logger.info("weflow Pipeline [newspic]: %s  账号: %s%s",
                     self.topic, self.account,
                     f" (断点重试 retry_from={retry_from})" if retry_from else "")

        # ── 阶段一：创建任务 + 生成 newspic 格式 brief.md ──
        if retry_from >= Status.BRIEF_READY:
            logger.info("[NewspicFlow] 跳过阶段一（brief 已就绪），task_id=%d", existing_tid)
            self.task_id = existing_tid
            from engine.config import BRIEF_FILE
            brief = str(_task_dir / BRIEF_FILE) if _task_dir else ""
            if not brief or not Path(brief).exists():
                logger.warning("[NewspicFlow] %s 不存在，回退执行阶段一", BRIEF_FILE)
                brief = self._create_newspic_brief()
        else:
            brief = self._create_newspic_brief()

        # ── 审核检查：阶段一完成（选题简报已就绪，status=20）──
        if self._check_review(20):
            return {"task_id": str(self.task_id), "brief": brief,
                    "status": "reviewing", "review_stage": 20}

        # ── 阶段二：拆卡 → 存入 task_image ──
        if retry_from >= Status.CARDS_PLANNED:
            logger.info("[NewspicFlow] 跳过阶段二（卡片已规划），从 DB 读取")
            try:
                from engine.db.models import image_list_by_task
                db_imgs = image_list_by_task(self.task_id)
                card_count = len(db_imgs)
            except Exception:
                card_count = self._plan_cards(brief)
        else:
            card_count = self._plan_cards(brief)

        # ── 阶段三：从 task_image 读取 → 逐卡生图 ──
        # 始终调用 _generate_cards()，其内部逐张检查 target.exists()，
        # 已生成的文件自动跳过，失败的会重新生成，实现断点续传。
        # 重试时不会重复生成已有图片。
        images = self._generate_cards(provider)

        # ── 审核检查：阶段三完成（贴图已生成，status=60）──
        if self._check_review(60):
            return {"task_id": str(self.task_id), "brief": brief,
                    "cards": str(card_count), "images": str(len(images)),
                    "status": "reviewing", "review_stage": 60}

        # ── 阶段四：AI 味检测（对短文本）──
        if retry_from >= Status.AI_SCORE_PASSED:
            ai_result = {"passed": True, "score": 0, "report": {}}
            logger.info("[NewspicFlow] 跳过阶段四（AI 检测已通过）")
        else:
            ai_result = self._check_ai_score(brief, skip_ai_score)

        if not ai_result["passed"] and not skip_ai_score:
            logger.warning("AI味检测未通过！手动改写后重新发布，或 --skip-ai-score")
            return {"task_id": str(self.task_id), "brief": brief,
                    "cards": str(card_count),
                    "ai_score": str(ai_result["score"]), "status": "ai_failed"}

        # 阶段五：发布（重试时 AI 已通过则跳过预检，直接发布）
        if retry_from >= Status.AI_SCORE_PASSED:
            logger.info("[NewspicFlow] 跳过发布前 AI 预检，直接发布")
            pub_result = self._publish_upload(brief)
        else:
            pub_result = self._publish(brief)

        result = {
            "task_id": str(self.task_id), "brief": brief,
            "cards": str(card_count),
            "images": str(len(images)),
            "ai_score": str(ai_result["score"]),
            "media_id": pub_result.get("media_id", ""),
            "status": "published",
        }
        self._log_completion(result)
        return result

    # ── 阶段方法 ──

    def _create_newspic_brief(self) -> str:
        """阶段一：创建 task + 生成 newspic 格式的 brief.md。返回 brief_path。"""
        from engine.utils import create_task_dir
        from engine.pipeline_db import db_task_create, db_transition

        user_details = self._resolve_user_details()

        existing_tid = self.kwargs.get("existing_task_id", 0)
        existing_path = self.kwargs.get("existing_task_path", "")

        if existing_tid > 0:
            out_dir = Path(existing_path) if existing_path else create_task_dir(self.account, self.output_dir)
            tid = existing_tid
            logger.info("[NewspicFlow] 使用已有任务 task_id=%d path=%s", tid, out_dir)
        else:
            out_dir = create_task_dir(self.account, self.output_dir)
            tid = db_task_create(
                self.account, self.topic, self._account_cfg,
                task_path=str(out_dir), task_type="image",
            )
            if not tid:
                raise RuntimeError("阶段一失败：无法创建任务记录")
        self.task_id = tid

        from engine.llm_client import LLMClient
        client = LLMClient(stage=Stage.UNDERSTAND)
        client.task_id = tid

        # 用户指定了配图风格则传入，约定用户指定优先；未指定则由 AI 自主选择
        frontend_image_style = self.kwargs.get("image_style")
        if frontend_image_style:
            image_style_hint = (
                f"配图风格：{frontend_image_style}（用户已指定，请直接使用此风格，不要自行更改）\n"
            )
        else:
            image_style_hint = "配图风格：未指定，请根据话题内容自主选择合适的风格。\n"

        user_genre = self._account_cfg.get("genre", "") or ""
        genre_hint = (
            f"文章体裁：{user_genre}（用户已指定，请按此体裁策划内容）\n"
            if user_genre
            else "文章体裁：未指定，请根据话题内容自主选择合适的体裁。\n"
        )

        user_msg = (
            f"话题：{self.topic}\n"
            f"账号：{self.account}\n"
            f"账号配置 voice：{self._account_cfg.get('voice', '')}\n"
            f"{image_style_hint}"
            f"{genre_hint}"
            f"参考素材：{user_details}\n"
            "请按格式输出贴图策划简报。"
        )

        logger.info("[NewspicFlow] 阶段一 生成 newspic brief: topic=%s", self.topic)
        content = client.chat([
            {"role": Role.SYSTEM, "content": _NEWSPIC_BRIEF_PROMPT},
            {"role": Role.USER, "content": user_msg},
        ], temperature=LLMDefaults.DRAFT_TEMPERATURE, max_tokens=LLMDefaults.DRAFT_MAX_TOKENS)

        if not content or not content.strip():
            raise RuntimeError("阶段一失败：LLM 返回空内容")

        from engine.config import BRIEF_FILE
        brief_path = out_dir / BRIEF_FILE
        brief_path.write_text(content, encoding="utf-8")

        db_transition(tid, Status.BRIEF_READY, str(out_dir), operator=Operator.UNDERSTAND)
        logger.info("[NewspicFlow] brief.md 已生成: %s", brief_path)

        # 持久化 title、image_style、short_text 到 task 表（后续 publish 以 task 表为准）
        _persist_brief_to_task(tid, content)
        # 解析要点写入 task_image（seq + description 原文），mode 35 从 DB 读取
        _persist_bullet_points_to_task_image(tid, content)

        return str(brief_path)

    def _plan_cards(self, brief_path: str) -> int:
        """阶段二：从 task_image 读取卡片描述 → 套模板生成 prompt，状态 20→35。

        优先从 DB 读取（mode 20 已写入要点原文），若 task_image 为空则回退到文件解析。
        """
        from engine.pipeline_db import db_transition
        from engine.db.models import image_list_by_task, image_update, task_get

        db_images = image_list_by_task(self.task_id)

        # 向后兼容：task_image 为空时回退到 brief.md 文件解析
        if not db_images:
            logger.info("[NewspicFlow] task_image 为空，回退到 brief.md 文件解析")
            return self._plan_cards_from_file(brief_path)

        # 解析图片风格
        task = task_get(self.task_id)
        task_image_style = (task.get("image_style", "") if task else "")
        resolved_style = (
            self.kwargs.get("image_style")
            or task_image_style
            or self._account_cfg.get("newspic_image_style", "")
            or "infographic-warm"
        )
        style_cfg = self._load_style_config(resolved_style)
        topic = (task.get("topic", "") if task else "") or self.topic

        logger.info("[NewspicFlow] 阶段二 从 DB 拆卡: %d 张 style=%s", len(db_images), resolved_style)

        for img in db_images:
            seq = img["seq"]
            point = img.get("description", "")
            if not point:
                logger.warning("[NewspicFlow] seq=%d 无 description，跳过", seq)
                continue

            main_text, sub_text = self._split_card_text(point)
            prompt = self._build_card_prompt(
                style_cfg, topic=topic, card_main=main_text, card_sub=sub_text,
                point_full=point, card_index=seq, card_total=len(db_images),
            )
            aspect = self._get_card_aspect(style_cfg)
            size = self._get_card_size(style_cfg)

            image_update(
                img["id"],
                description=main_text,
                prompt=prompt,
                image_style=resolved_style,
                size=size,
            )

        db_transition(self.task_id, Status.CARDS_PLANNED,
                      f"拆卡 {len(db_images)} 张, style={resolved_style} (DB)")
        logger.info("[NewspicFlow] task_image 已更新 %d 条（prompt/风格/尺寸）", len(db_images))
        return len(db_images)

    def _plan_cards_from_file(self, brief_path: str) -> int:
        """文件解析 fallback：从 brief.md 解析要点 → 套模板 → 写入 task_image（向后兼容旧任务）。"""
        from newspic_build import parse_brief, extract_bullet_points
        from engine.pipeline_db import db_transition
        from engine.db.models import image_delete_by_task

        brief_text = Path(brief_path).read_text(encoding="utf-8")
        parsed = parse_brief(brief_text)
        fm = parsed.get("frontmatter", {})
        topic = fm.get("topic", self.topic)
        section_text = parsed.get("sections", {}).get("要点", "")
        points = extract_bullet_points(section_text)
        if not points:
            raise RuntimeError("阶段二失败：brief.md 中「要点」无可解析的列表项")

        resolved_style = self._resolve_newspic_style(fm)
        style_cfg = self._load_style_config(resolved_style)

        logger.info("[NewspicFlow] 阶段二 从文件拆卡: %d 要点 style=%s", len(points), resolved_style)

        # 先清理旧记录
        deleted = image_delete_by_task(self.task_id)
        if deleted > 0:
            logger.info("[NewspicFlow] 已清理 %d 条旧 task_image 记录", deleted)

        for idx, point in enumerate(points, start=1):
            main_text, sub_text = self._split_card_text(point)
            prompt = self._build_card_prompt(
                style_cfg, topic=topic, card_main=main_text, card_sub=sub_text,
                point_full=point, card_index=idx, card_total=len(points),
            )
            aspect = self._get_card_aspect(style_cfg)
            size = self._get_card_size(style_cfg)

            self._ensure_card_placeholder(
                seq=idx, main_text=main_text, prompt=prompt,
                image_style=resolved_style, aspect=aspect, size=size,
            )

        db_transition(self.task_id, Status.CARDS_PLANNED,
                      f"拆卡 {len(points)} 张, style={resolved_style} (file)")
        logger.info("[NewspicFlow] task_image 已创建 %d 条（从文件）", len(points))
        return len(points)

    def _generate_cards(self, provider: str = None) -> List[str]:
        """阶段三：从 task_image 读取卡片 → 逐张生图，状态 35→60。"""
        from engine.image_gen_core import generate_image, detect_provider, get_default_model
        from engine.pipeline_db import db_transition
        from engine.db.models import image_list_by_task

        db_images = image_list_by_task(self.task_id)
        if not db_images:
            raise RuntimeError("阶段三失败：task_image 中无卡片记录")

        used_provider = provider or detect_provider()
        model = get_default_model(used_provider)
        results: List[str] = []

        # 从 task_path 获取输出目录
        out_dir = self._get_task_dir()
        images_dir = out_dir / DirPath.IMAGES
        images_dir.mkdir(parents=True, exist_ok=True)

        logger.info("[NewspicFlow] 阶段三 生图: %d 张 provider=%s model=%s",
                     len(db_images), used_provider, model)

        for img in db_images:
            seq = img["seq"]
            target = images_dir / f"{seq:02d}.png"
            prompt = img.get("prompt", "")
            if not prompt:
                logger.warning("[NewspicFlow] seq=%d 无 prompt，跳过", seq)
                continue

            if target.exists() and target.stat().st_size > 0:
                logger.info("[NewspicFlow] 跳过已存在: %s", target)
                results.append(str(target))
                self._update_card_image(seq, target, target.read_bytes(),
                                        used_provider, model, prompt,
                                        img.get("size", ""), img.get("image_style", ""))
                continue
            elif img.get("upload_status") == "generated":
                # DB 标记已生成但文件不存在（路径迁移/CWD变化导致），重新生成
                logger.warning("[NewspicFlow] seq=%d DB状态=generated 但文件缺失，重新生成", seq)

            logger.info("[NewspicFlow] [%d/%d] %s", seq, len(db_images), target.name)
            t0 = time.time()

            try:
                image_bytes = generate_image(
                    provider=used_provider, model=model,
                    prompt=prompt,
                    size=img.get("size"),
                    aspect_ratio=img.get("aspect"),
                    quality="normal",
                )
            except Exception as e:
                logger.error("[NewspicFlow] 生图失败 seq=%d: %s", seq, str(e)[:200])
                self._update_card_failed(seq, str(e)[:200])
                continue

            target.write_bytes(image_bytes)
            # 确认文件实际写入成功，再标记 generated
            if target.exists() and target.stat().st_size > 0:
                results.append(str(target))
                self._update_card_image(seq, target, image_bytes,
                                        used_provider, model, prompt,
                                        img.get("size", ""), img.get("image_style", ""))
            else:
                logger.error("[NewspicFlow] 文件写入异常 seq=%d: %s", seq, target)
                self._update_card_failed(seq, f"文件写入后缺失: {target}")

            duration = int((time.time() - t0) * 1000)
            logger.info("  [%d/%d] %s (%dKB, %dms)",
                         seq, len(db_images), target.name,
                         int(len(image_bytes) / 1024), duration)

            if seq < len(db_images):
                time.sleep(2)

        total = len(db_images)
        success = len(results)
        failed = total - success
        if failed > 0:
            logger.warning("[NewspicFlow] 阶段三: %d/%d 张成功, %d 张失败（已标记 generate_failed，重试时会续传）",
                           success, total, failed)
        # 仅在非重试场景（首次执行）时推进状态，避免重试时状态回退
        if getattr(self, 'retry_from', 0) < Status.IMAGES_GENERATED:
            db_transition(self.task_id, Status.IMAGES_GENERATED,
                          f"配图 {success}/{total} 张: {used_provider}")
        logger.info("[NewspicFlow] 阶段三完成: %d/%d 张", success, total)
        return results

    def _check_ai_score(self, brief_path: str, skip_ai_score: bool = False) -> dict:
        """阶段四：对短文本做 AI 味检测。状态 60→80 或 60→85。"""
        from engine.pipeline_db import db_transition
        from engine.ai_score import check_ai_score as _check, DEFAULT_THRESHOLD as _DEFAULT
        from engine.db.models import task_get

        # 优先从 task 表读取 short_text，为空时 fallback 到 brief.md
        short_text = ""
        if self.task_id:
            task = task_get(self.task_id)
            if task:
                short_text = (task.get("short_text") or "").strip()

        if not short_text:
            brief_text = Path(brief_path).read_text(encoding="utf-8")
            short_text = self._extract_short_text(brief_text)

        if not short_text:
            logger.warning("[NewspicFlow] 未找到短文本，跳过 AI 味检测")
            return {"passed": True, "score": 0, "report": {}}

        threshold = _DEFAULT
        logger.info("[NewspicFlow] 阶段四 AI味检测: %d字 threshold=%.0f mode=newspic",
                     len(short_text), threshold)

        passed, report = _check(short_text, threshold, mode="image")
        score = report.get("total_score", 0)

        if self.task_id:
            try:
                from engine.db.models import task_update, status_transition
                from engine.constants import AIVerdict
                import json
                report_json = json.dumps(report, ensure_ascii=False)
                if passed:
                    db_transition(self.task_id, Status.AI_SCORE_PASSED,
                                  f"AI 味检测通过 ({score}/100, newspic)",
                                  ai_score=score, remark=report_json)
                else:
                    task_update(self.task_id, ai_score=score, ai_verdict=AIVerdict.FAIL)
                    status_transition(self.task_id, Status.AI_SCORE_FAILED,
                                      to_info=f"AI 评分 {score}/100 >= 阈值 {threshold} (newspic)",
                                      operator=Operator.AI_SCORE,
                                      remark=report_json)
            except Exception as e:
                logger.debug("[NewspicFlow] AI 评分 DB 更新失败: %s", e)

        return {"passed": passed, "score": score, "report": report}

    def _publish_ai_gate(self, brief_path: str) -> dict:
        """阶段五-A：发布前的 AI 味预检（可独立调用）。

        publish_from_brief 内置的 AI 预检与 Flow 的阶段四 _check_ai_score
        是同一件事。拆出来以便重试时跳过 AI 检测直接发布。
        """
        from engine.publish import _run_newspic_ai_gate
        from engine.newspic_build import parse_brief
        from engine.db.models import task_get

        # 优先从 task 表读取 short_text，为空时 fallback 到 brief.md
        short_text = ""
        if self.task_id:
            task = task_get(self.task_id)
            if task:
                short_text = (task.get("short_text") or "").strip()

        if not short_text:
            brief_text = Path(brief_path).read_text(encoding="utf-8")
            parsed = parse_brief(brief_text)
            short_text = (parsed.get("sections", {}).get("短文本")
                          or parsed.get("sections", {}).get("短描述") or "").strip()

        if not short_text:
            logger.info("[NewspicFlow] 无短文本，跳过 AI 预检")
            return {"passed": True, "score": 0}

        logger.info("[NewspicFlow] 发布前 AI 预检: %d字", len(short_text))
        return _run_newspic_ai_gate(short_text, task_id=self.task_id)

    def _publish_upload(self, brief_path: str) -> dict:
        """阶段五-B：纯发布 —— 上传图片 + 创建微信草稿（不含 AI 预检）。

        重试场景（retry_from>=80）直接调用此方法，跳过 AI 检测。
        """
        from engine.publish import do_publish_newspic
        from engine.config import get_config, ConfigError
        from engine.config import resolve_image_style
        from engine.newspic_build import parse_brief
        from engine.db.models import task_get

        final_account = self.account

        # 优先从 task 表读取持久化字段，为空时 fallback 到 brief.md 解析
        task = task_get(self.task_id) if self.task_id else None
        final_title = (task.get("title", "") if task else "") or ""
        short_text = (task.get("short_text", "") if task else "") or ""
        task_image_style = (task.get("image_style", "") if task else "") or ""

        # fallback: task 表字段为空时解析 brief.md
        if not final_title or not short_text or not task_image_style:
            brief_path_obj = Path(brief_path)
            brief_text = brief_path_obj.read_text(encoding="utf-8")
            parsed = parse_brief(brief_text)
            fm = parsed.get("frontmatter", {})
            sections = parsed.get("sections", {})
            if not final_title:
                final_title = fm.get("title", "") or ""
            if not short_text:
                short_text = (sections.get("短文本") or sections.get("短描述") or "").strip()
            if not task_image_style:
                task_image_style = fm.get("image_style")

        style = resolve_image_style(
            frontmatter_value=task_image_style,
            account_name=final_account,
            mode="image",
        )

        # 收集图片
        images_dir = Path(brief_path).parent / DirPath.IMAGES
        exts = (".png", ".jpg", ".jpeg", ".webp")
        image_paths = sorted(
            [p for p in images_dir.iterdir() if p.suffix.lower() in exts],
            key=lambda p: p.name,
        )
        if not image_paths:
            raise FileNotFoundError(f"{images_dir} 下没有图片")

        # ══ 卡片完整性校验：所有计划的卡片都必须已生成 ══
        if self.task_id:
            try:
                from engine.db.models import image_list_by_task
                db_images = image_list_by_task(self.task_id)
                planned = [img for img in db_images if img.get("prompt")]
                if planned:
                    existing_names = {p.name for p in image_paths}
                    missing: list[str] = []
                    failed: list[str] = []
                    for img in planned:
                        seq = img["seq"]
                        expected_name = f"{seq:02d}.png"
                        status = img.get("upload_status", "")
                        if expected_name not in existing_names:
                            # 检查是否有其他扩展名的同名文件
                            found = any(
                                p.stem == f"{seq:02d}" for p in image_paths
                            )
                            if not found:
                                if status == "generate_failed":
                                    failed.append(f"#{seq} (生图失败)")
                                else:
                                    missing.append(f"#{seq} (未找到文件 {expected_name})")
                    if missing or failed:
                        all_missing = failed + missing
                        msg = (
                            f"卡片图片未全部生成，共 {len(planned)} 张计划，"
                            f"{len(all_missing)} 张缺失，无法发布。\n"
                            f"缺失卡片: {', '.join(all_missing)}\n"
                            f"请先完成阶段三（生图），或检查失败原因后重试。"
                        )
                        logger.error("[NewspicFlow] %s", msg)
                        raise RuntimeError(msg)
                    logger.info(
                        "[NewspicFlow] 卡片完整性校验通过: %d/%d 张已就绪",
                        len(image_paths), len(planned),
                    )
            except RuntimeError:
                raise
            except Exception as e:
                logger.warning("[NewspicFlow] 卡片完整性校验异常（跳过）: %s", e)

        # 作者兜底
        author = None
        try:
            cfg = get_config(final_account)
            author = cfg.get("author", "") or ""
        except ConfigError:
            author = ""

        logger.info("[NewspicFlow] 纯发布: brief=%s 标题=%s 图片=%d张",
                     brief_path, final_title, len(image_paths))
        return do_publish_newspic(
            brief_path=brief_path,
            image_paths=image_paths,
            final_title=final_title,
            short_text=short_text,
            author=author,
            final_account=final_account,
            style=style,
            task_id=self.task_id,
        )

    def _publish(self, brief_path: str) -> dict:
        """阶段五：发布贴图到微信草稿箱（完整流程：AI 预检 + 上传发布）。"""
        self._publish_ai_gate(brief_path)
        return self._publish_upload(brief_path)

        # ── 上传状态回写 task_image ──
        if self.task_id:
            try:
                from engine.db.models import image_list_by_task, image_update_upload
                db_images = image_list_by_task(self.task_id)
                media_ids = result.get("image_media_ids", [])
                for img in db_images:
                    if img.get("local_path"):
                        seq = img.get("seq", 0)
                        media_id = media_ids[seq - 1] if 0 < seq <= len(media_ids) else ""
                        image_update_upload(img["id"], "uploaded", media_id=media_id)
                logger.info("[NewspicFlow] task_image 上传状态已更新 %d 条", len(db_images))
            except Exception as e:
                logger.warning("[NewspicFlow] task_image 上传状态更新失败: %s", e)

        logger.info("[NewspicFlow] 阶段五完成 → media_id: %s", result.get("media_id", "?"))
        return result

    # ── 卡片辅助方法 ──

    def _resolve_newspic_style(self, fm: dict) -> str:
        """解析图片风格：用户指定(前端/CLI) > Frontmatter(LLM选择) > 账号配置 > 默认。"""
        # 用户通过前端/CLI 明确指定的风格，优先级最高
        frontend_style = self.kwargs.get("image_style")
        if frontend_style:
            return frontend_style
        style = fm.get("image_style", "") or self._account_cfg.get("newspic_image_style", "")
        return style or "infographic-warm"

    @staticmethod
    def _load_style_config(style_name: str) -> dict:
        """加载图片风格配置文件。"""
        from engine.config import get_image_style
        try:
            return get_image_style(style_name) or {}
        except Exception:
            return {}

    @staticmethod
    def _get_card_aspect(style_cfg: dict) -> str:
        """从风格配置获取卡片宽高比。"""
        canvas = style_cfg.get("canvas", {}) if style_cfg else {}
        return canvas.get("newspic_aspect", "1:1")

    @staticmethod
    def _get_card_size(style_cfg: dict) -> str:
        """从风格配置获取卡片尺寸。"""
        canvas = style_cfg.get("canvas", {}) if style_cfg else {}
        return canvas.get("newspic_size", "")

    @staticmethod
    def _build_card_prompt(style_cfg: dict, **kwargs) -> str:
        """用风格模板 + 变量替换构建生图 prompt。"""
        pt = (style_cfg or {}).get("prompt_template", {})
        template = pt.get("newspic_card") or pt.get("article_inline", "")
        if not template:
            raise RuntimeError("风格配置缺少 prompt_template.newspic_card")

        topic = kwargs.get("topic", "")
        card_main = kwargs.get("card_main", "")
        card_sub = kwargs.get("card_sub", "") or card_main
        point_full = kwargs.get("point_full", "")
        card_index = f"{kwargs.get('card_index', 1):02d}"
        card_total = f"{kwargs.get('card_total', 1):02d}"
        image_subject = f"{topic} - {card_main}"

        return template.format(
            topic=topic, card_main=card_main, card_sub=card_sub,
            point_full=point_full, card_index=card_index, card_total=card_total,
            image_subject=image_subject,
        )

    @staticmethod
    def _split_card_text(point: str, max_main: int = 30) -> tuple:
        """拆分要点为卡片主/副文字（复用 newspic_build 的切分逻辑）。"""
        from newspic_build import _split_card_text as _split
        return _split(point, max_main)

    def _ensure_card_placeholder(self, seq: int, main_text: str, prompt: str,
                                 image_style: str, aspect: str, size: str) -> None:
        """创建或更新 task_image 占位记录（upsert by task_id + seq）。"""
        try:
            from engine.db.models import image_insert, image_update, image_find_by_seq

            existing = image_find_by_seq(self.task_id, seq)
            if existing:
                image_update(
                    existing["id"],
                    description=main_text, prompt=prompt,
                    image_style=image_style, size=size,
                )
            else:
                image_insert(
                    task_id=self.task_id, seq=seq, anchor="",
                    description=main_text, prompt=prompt,
                    provider="", model="",
                    image_style=image_style, size=size,
                )
        except Exception as e:
            logger.warning("[NewspicFlow] 写入卡占位失败 seq=%d: %s", seq, e)

    def _update_card_image(self, seq: int, target: Path, image_bytes: bytes,
                           provider: str, model: str, prompt: str,
                           size: str, image_style: str) -> None:
        """生图后回填 task_image（provider / model / local_path / 尺寸）。"""
        try:
            from engine.db.models import image_update, image_find_by_seq
            from engine.utils import get_png_dimensions

            existing = image_find_by_seq(self.task_id, seq)
            if not existing:
                return

            w, h = get_png_dimensions(image_bytes)
            est_in = max(1, len(prompt) // 3)
            est_out = max(1, len(image_bytes) // 200)

            image_update(
                existing["id"],
                provider=provider, model=model, size=size,
                local_path=target.name, local_size=len(image_bytes),
                width=w, height=h, format="png",
                prompt=prompt, description=existing.get("description", ""),
                image_style=image_style,
                upload_status="generated",
                tokens_in=est_in, tokens_out=est_out,
            )
        except Exception as e:
            logger.debug("[NewspicFlow] 更新 task_image 失败 seq=%d: %s", seq, e)

    def _update_card_failed(self, seq: int, error_msg: str = "") -> None:
        """标记单张卡片生图失败，记录错误原因。"""
        try:
            from engine.db.models import image_update, image_find_by_seq
            existing = image_find_by_seq(self.task_id, seq)
            if not existing:
                return
            image_update(
                existing["id"],
                upload_status="generate_failed",
                prompt=existing.get("prompt", ""),
                description=(existing.get("description") or "") + f" [失败: {error_msg[:100]}]",
            )
        except Exception as e:
            logger.debug("[NewspicFlow] 标记失败 seq=%d 出错: %s", seq, e)

    # ── 通用辅助方法 ──

    def _get_task_dir(self) -> Path:
        """获取任务产物目录（始终返回绝对路径）。"""
        try:
            from engine.db.models import task_get
            from engine.config import get_project_root
            t = task_get(self.task_id)
            if t and t.get("task_path"):
                p = Path(t["task_path"])
                if not p.is_absolute():
                    p = Path(get_project_root()) / p
                return p
        except Exception:
            pass
        return Path(".")

    def _resolve_user_details(self) -> str:
        """解析 user_details：支持 @文件路径 语法。"""
        raw = self.kwargs.get("user_details") or self._account_cfg.get("user_details", "")
        if not raw:
            return "暂无"
        raw = raw.strip()
        if raw.startswith("@") and len(raw) > 1:
            ref_path = Path(raw[1:])
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8")
        return raw

    @staticmethod
    def _extract_short_text(brief_text: str) -> str:
        """从 brief.md 中提取 '# 短文本' 段落内容。"""
        import re
        m = re.search(r'#\s*短文本\s*\n(.*?)$', brief_text, re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r'#\s*短描述\s*\n(.*?)$', brief_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""
