#!/usr/bin/env python3
"""阶段三：撰写骨架稿 → article.md。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from engine.logger import get_logger
from engine.constants import Stage, Status, FileName, LLMDefaults, Role
from engine.pipeline_db import db_transition
from engine.utils import get_anti_ai_md, load_ref

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是一个资深的公众号文章撰稿助手。你的任务是根据用户提供的**选题简报**和**研究素材**，撰写一篇完整的公众号文章骨架稿（初稿），并同时完成视觉风格决策与配图提示词生成。

---

## 一、核心目标

1. 严格按照 `选题简报` 中已指定的文章结构和开篇钩子组织全文，不重新选择或更改。
2. 重要：选题简报 中的'用户的要求或细节'部分需优先满足。
3. 在正文中插入配图锚点，并为每张配图生成高质量的图像生成提示词。

---

## 二、输入说明

用户会提供以下信息：

- `选题简报`：第一阶段产出的完整选题简报，包含话题、核心论点、文章结构、开篇钩子、内容调性、真人味原料等。
- `研究素材*`：网络搜索或用户提供的参考资料、数据、案例等。

---

## 三、写作约束

### 3.1 文章规模

- 小节数量：3-6 个，不强行凑对称。有的小节 1000 字，有的 200 字均可。
- 配图数量：1-2 张，按内容需要插入，不必每节都有。

### 3.2 排版增强标记

整篇只用一种加粗是最典型的 AI 公众号指纹。整篇最多混用 3 种不同标记类型，颜色考虑一致性：

- 加粗（双星号）：最重要结论，一段最多 1 次。
- 双等号：黄色高亮，用于关键数据、核心论点、名言。
- 双加号：蓝色高亮，用于概念定义、工具名、平台名。
- 双百分号：粉色高亮，用于警示、陷阱、反面案例。
- 双与符号：绿色高亮，用于正面结果、推荐做法。
- 双叹号：红色强调，用于警告、关键负面数字。
- 双 at 符号：蓝色强调，用于术语、专有名词。
- 双 caret 符号：橙色强调，用于温暖点缀。
- 大于号加空格：引用块，用于金句、关键数据。
- 三个等号单独一行：分节符，用于大段之间的呼吸。

### 3.3 要避免的写法

- 不用"首先...其次...最后..."、"值得一提的是"、"不可否认"、"综上所述"、"总而言之"。
- 不用"一方面...另一方面..."、"不仅...而且..."。
- 不用"在...的背景下"、"随着...的发展"。
- 不用过于工整的排比句。
- 文末不做全面的"总结回顾"。

---

## 四、视觉风格决策

根据 `选题简报` 和 `研究素材` 的内容，自主选择 1 个图片风格（image_styles）。


### 4.1 图片风格选配

- AI、产品深挖、功能拆解：首选 infographic-warm，备选 infographic-blue、hand-drawn-blue
- 技术、架构、SDK、协议：首选 infographic-blue，备选 blue、hand-drawn-blue
- 步骤教程、工具对比：首选 flat-editorial，备选 warm-handdrawn、knowledge-card
- 数据、报告、趋势：首选 data-chart，备选 infographic-blue
- 热点、标题党、短句：首选 marker-lime，备选其他 marker 系列
- 生活方式、清单、盘点：首选 warm-handdrawn，备选 xiaohongshu-colorful、mint
- 观点、人文、深度评论：首选 morandi，备选 magazine-editorial
- 体验分享、有人物叙事：首选 illustrated-warm，备选 slice-of-life

---

## 五、默认 Markdown 骨架

请按以下骨架组织文章：

# 标题（抓眼球，15-25 字）

> 摘要引言（1-2 句话，会显示在分享卡片中）

## { 序号 } {开篇说明}
（按 brief 中指定的 opening_hook 切入）
可以是具体数字 / 尖锐问题 / 反常识判断 / 原话 / 命令输出 / 时间线 / 具体场景。
禁止"随着 XX 的飞速发展"这类宏观铺垫。

## { 序号 } {小节x}

## { 序号 } {小节x}

## { 序号 } {小节x}

## { 序号 } { 写在最后 }

配图按实际需要在正文中插入 `![配图描述](anchor://image-XXX)` 锚点，全文共 1-2 张（inline 配图，不含封面图）。
封面图（anchor://cover）为文章封面，**不需要**在正文中插入锚点。


## 六、输出格式

禁止输出任何除以下指定格式外的内容。输出分两部分：

### 6.1 Frontmatter（YAML 元数据块）

**格式强制要求（违反将导致解析失败）：**
- 第一行必须是 `---`（行首，三个减号，独占一行，不要加任何字母如 yaml）
- 最后一行必须是 `---`（行首，三个减号，独占一行）
- 禁止使用 `---yaml`、`---yml`、`---YAML` 等任何变体
- 禁止在 `---` 前输出任何文字、空行或解释

**不要输出 author / date**（这些由系统自动注入）：

---
title: [文章标题]
abstract_introduction: [摘要引言]
image_style: [选中的图片风格标识，**禁忌**混用风格，一篇文章所有配图统一一种风格]
image_prompts:
  - anchor: anchor://cover
    prompt: |
      [封面图提示词，英文，文章核心主题概括，10-70词，注意：不要要求图片中出现具体文字，可出现少量的中文，除非是英文专用名词，术语等。宽银幕构图，画面比例 2.35:1。]
    description: cover
  - anchor: anchor://image-001
    prompt: |
      [配图提示词，英文，10-70词，不要包含风格/色调/样式信息，注意：不要要求图片中出现具体文字，可出现少量的中文，除非是英文专用名词，术语等。]
    description: [配图描述，中文，10-50字]
---

**再次强调：** 你的输出第一个字符必须是 `-`（即第一行是 `---`），最后一个 Frontmatter 行也是 `---`。不要在此之前输出任何其他内容。

**重要：** prompt 字段必须使用 YAML 字面量块标量（`|`）语法，值缩进 2 个空格。

### 6.2 正文（Markdown）

Frontmatter 之后输出正文。**正文中必须插入 inline 配图锚点**（封面图 anchor://cover **不插入正文**），inline 配图数量 1-2 张，锚点格式如下：

```
![描述文字](anchor://image-001)
```

- XXX 为 3 位数字编号，`anchor://image-001`、`anchor://image-002`……
- 描述：中文，10-50 字，简要说明画面内容
- **必须**在正文需要配图的位置插入锚点，不要漏插

示例输出结构：

```
---
# ... Frontmatter ...
---

# 标题

正文内容... ![配表描述](anchor://image-001) 正文继续...
```
"""

# ── 无配图模式的 SYSTEM_PROMPT ──
# 当 no_images=True 时使用此提示词，不要求 AI 生成配图相关信息

SYSTEM_PROMPT_NO_IMAGES = """你是一个资深的公众号文章撰稿助手。你的任务是根据用户提供的**选题简报**和**研究素材**，撰写一篇完整的公众号文章骨架稿（初稿）。

---

## 一、核心目标

严格按照 `选题简报` 中已指定的文章结构和开篇钩子组织全文，不重新选择或更改。
重要：选题简报 中的'用户的要求或细节'部分需优先满足。


---

## 二、输入说明

用户会提供以下信息：

- `选题简报`：第一阶段产出的完整选题简报，包含话题、核心论点、文章结构、开篇钩子、内容调性、真人味原料等。
- `研究素材*`：网络搜索或用户提供的参考资料、数据、案例等。

---

## 三、写作约束

### 3.1 文章规模

- 小节数量：3-6 个，不强行凑对称。有的小节 1000 字，有的 200 字均可。
- 重要：总字数 2000-5000 字。

### 3.2 排版增强标记

整篇只用一种加粗是最典型的 AI 公众号指纹。整篇最多混用 3 种不同标记类型，颜色考虑一致性：

- 加粗（双星号）：最重要结论，一段最多 1 次。
- 双等号：黄色高亮，用于关键数据、核心论点、名言。
- 双加号：蓝色高亮，用于概念定义、工具名、平台名。
- 双百分号：粉色高亮，用于警示、陷阱、反面案例。
- 双与符号：绿色高亮，用于正面结果、推荐做法。
- 双叹号：红色强调，用于警告、关键负面数字。
- 双 at 符号：蓝色强调，用于术语、专有名词。
- 双 caret 符号：橙色强调，用于温暖点缀。
- 大于号加空格：引用块，用于金句、关键数据。
- 三个等号单独一行：分节符，用于大段之间的呼吸。

### 3.3 要避免的写法

- 不用"首先...其次...最后..."、"值得一提的是"、"不可否认"、"综上所述"、"总而言之"。
- 不用"一方面...另一方面..."、"不仅...而且..."。
- 不用"在...的背景下"、"随着...的发展"。
- 不用过于工整的排比句。
- 文末不做全面的"总结回顾"。

---

## 四、默认 Markdown 骨架

请按以下骨架组织文章：

# 标题（抓眼球，15-25 字）

> 摘要引言（1-2 句话，会显示在分享卡片中）

## { 序号 } {开篇说明}
（按 brief 中指定的 opening_hook 切入）
可以是具体数字 / 尖锐问题 / 反常识判断 / 原话 / 命令输出 / 时间线 / 具体场景。
禁止"随着 XX 的飞速发展"这类宏观铺垫。

## { 序号 } {小节x}

## { 序号 } {小节x}

## { 序号 } {小节x}

## { 序号 } { 写在最后 }


## 五、输出格式

禁止输出任何除以下指定格式外的内容。输出分两部分：

### 5.1 Frontmatter（YAML 元数据块）

**格式强制要求（违反将导致解析失败）：**
- 第一行必须是 `---`（行首，三个减号，独占一行，不要加任何字母如 yaml）
- 最后一行必须是 `---`（行首，三个减号，独占一行）
- 禁止使用 `---yaml`、`---yml`、`---YAML` 等任何变体
- 禁止在 `---` 前输出任何文字、空行或解释

**不要输出 author / date**（这些由系统自动注入）。**本模式下不需要输出 image_style / image_prompts 字段**：

---
title: [文章标题]
abstract_introduction: [摘要引言]
---

**再次强调：** 你的输出第一个字符必须是 `-`（即第一行是 `---`），最后一个 Frontmatter 行也是 `---`。不要在此之前输出任何其他内容。

### 5.2 正文（Markdown）

Frontmatter 之后直接输出正文。本模式为纯文本模式，**不需要**插入任何图片锚点（`anchor://`），正文专注于文字内容本身。

示例输出结构：

```
---
title: xxx
abstract_introduction: xxx
---

# 标题

正文内容...
```
"""

def write_draft(brief_path: str, research_path: Optional[str] = None,
                task_id: int = 0, account_cfg: Optional[Dict] = None,
                no_images: bool = False) -> str:
    """阶段三：撰写骨架稿 → article.md。返回 article_path。

    Args:
        brief_path: brief.md 路径
        research_path: research.md 路径（可选）
        task_id: 任务 ID
        account_cfg: 账号配置 dict
        no_images: True 时跳过配图相关提示词，不生成 image_prompts / image_style，
                   文章不包含图片锚点。封面图在发布时按需自动生成。

    article.md: 仅有正文，无 Frontmatter
    配图信息（image_prompts / image_style）写入 task_image 表；
    title / theme 写入 task 表。
    """
    from engine.llm_client import LLMClient

    brief = Path(brief_path)
    if not brief.exists():
        raise FileNotFoundError(f"brief.md 不存在: {brief_path}")

    research_content = ""
    if research_path:
        rp = Path(research_path)
        if rp.exists():
            research_content = rp.read_text(encoding="utf-8")

    cfg = account_cfg or {}
    user_image_style = cfg.get("image_style", "") or "auto"

    client = LLMClient(stage=Stage.DRAFT)
    client.task_id = task_id

    if no_images:
        # 无配图模式：使用精简提示词，不要求配图信息
        system_prompt = SYSTEM_PROMPT_NO_IMAGES
        user = (
            f"## 选题简报\n\n{brief.read_text(encoding='utf-8')}\n\n"
            f"## 研究素材\n\n{research_content or '(无)'}\n\n"
            f"请按格式输出文章内容。"
        )
        logger.info("[阶段三] 撰写骨架稿（无配图模式）: brief=%s task=%d", brief_path, task_id)
    else:
        # 标准模式：包含配图风格选择 + 配图提示词生成
        system_prompt = SYSTEM_PROMPT
        user = (
            f"## 选题简报\n\n{brief.read_text(encoding='utf-8')}\n\n"
            f"## 研究素材\n\n{research_content or '(无)'}\n\n"
            f"## 指定配图风格\n\n{user_image_style}\n\n"
            f"请按格式输出文章内容和配图信息。"
        )
        logger.info("[阶段三] 撰写骨架稿: brief=%s task=%d", brief_path, task_id)

    content = client.chat([
        {"role": Role.SYSTEM, "content": system_prompt},
        {"role": Role.USER, "content": user},
    ], temperature=LLMDefaults.DRAFT_TEMPERATURE, max_tokens=LLMDefaults.DRAFT_MAX_TOKENS)

    # 解析单 Frontmatter，拆分文章和配图信息
    text = content

    _IMAGE_KEYS = {"image_style", "image_styles", "image_prompts"}
    fm, body = _parse_frontmatter(text)

    if no_images:
        # 无配图模式：只更新 title，不处理 image_style / image_prompts
        try:
            task_updates = {}
            ai_title = fm.get("title", "")
            if ai_title:
                task_updates["title"] = ai_title
            if task_updates:
                from engine.db.models import task_update
                task_update(task_id, **task_updates)
                logger.info("[阶段三] task 表元信息已更新（无配图）: %s", list(task_updates.keys()))
        except Exception as e:
            logger.warning("[阶段三] 更新 task 元信息失败: task=%d: %s", task_id, e)
    else:
        # 标准模式：处理配图信息
        # 用户未指定 image_style 时，用 AI 选择的 image_style 更新 task 表
        ai_image_style = fm.get("image_style") or fm.get("image_styles") or ""
        if (not user_image_style or user_image_style == "auto") and ai_image_style:
            try:
                from engine.db.models import task_update
                task_update(task_id, image_style=ai_image_style)
                logger.info("[阶段三] AI 选择 image_style=%s → 更新 task", ai_image_style)
            except Exception as e:
                logger.warning("[阶段三] 更新 task.image_style 失败: task=%d: %s", task_id, e)

        # 配图信息存入 task_image 表
        image_meta = {k: v for k, v in fm.items() if k in _IMAGE_KEYS}
        has_images = image_meta.get("image_prompts")
        if has_images:
            # 更新 task 表的 theme 和 title
            try:
                task_updates = {}
                ai_theme = fm.get("theme", "")
                ai_title = fm.get("title", "")
                if ai_theme:
                    task_updates["theme"] = ai_theme
                if ai_title:
                    task_updates["title"] = ai_title
                if task_updates:
                    from engine.db.models import task_update
                    task_update(task_id, **task_updates)
                    logger.info("[阶段三] task 表元信息已更新: %s", list(task_updates.keys()))
            except Exception as e:
                logger.warning("[阶段三] 更新 task 元信息失败: task=%d: %s", task_id, e)

            # 为每张配图创建 task_image 占位记录（后续生图/上传阶段更新）
            if task_id:
                _create_image_placeholders(task_id, image_meta["image_prompts"],
                                           ai_image_style, client.last_assistant_msg_id)
        elif image_meta:
            logger.warning("[阶段三] image_meta 不含 image_prompts (keys: %s)",
                           list(image_meta.keys()))
        else:
            logger.warning("[阶段三] 未提取到配图信息（AI 返回的 Frontmatter 可能使用了非标准格式如 ---yaml）")

    # article.md: 仅有正文，无 Frontmatter
    article_path = brief.parent / FileName.ARTICLE
    article_path.write_text(body, encoding="utf-8")

    db_transition(task_id, Status.DRAFT_READY, f"article.md ({len(body)}字)",
                  word_count=len(body))
    logger.info("阶段三完成 → %s", article_path)
    return str(article_path)


def _parse_frontmatter(text: str) -> tuple:
    """解析 YAML Frontmatter，返回 (frontmatter_dict, body_text)。

    委托给 article_images.parse_frontmatter，保持单点维护。
    """
    from engine.article_images import parse_frontmatter
    return parse_frontmatter(text)



def _create_image_placeholders(task_id: int, image_prompts: list,
                               image_style: str, draft_msg_id: int = 0) -> None:
    """为每张配图创建 task_image 占位记录，后续生图/上传阶段更新。

    占位记录包含 draft 阶段已知的所有信息（anchor / description / prompt / image_style），
    provider / model / local_path 等字段留空，由 generate_images 阶段回填。
    """
    try:
        from engine.db.models import image_insert, image_delete_by_task

        # 先清理旧记录，防止重试/重新生成时积累
        deleted = image_delete_by_task(task_id)
        if deleted > 0:
            logger.info("[阶段三] 已清理 %d 条旧 task_image 记录", deleted)

        if draft_msg_id:
            logger.info("[阶段三] 关联 draft assistant message_id=%d", draft_msg_id)
        else:
            logger.warning("[阶段三] draft assistant message_id=0")

        for seq, item in enumerate(image_prompts, start=1):
            anchor = item.get("anchor", f"anchor://image-{seq:03d}")
            prompt = item.get("prompt", "")
            description = item.get("description", "")

            img_id = image_insert(
                task_id=task_id,
                message_id=draft_msg_id,
                seq=seq,
                anchor=str(anchor),
                description=str(description),
                prompt=str(prompt),
                provider="",
                model="",
                image_style=image_style or "",
                size="",
                is_cover=(str(description).strip().lower() == "cover"),
            )
            logger.debug("[阶段三] task_image 占位记录: id=%d anchor=%s", img_id, anchor)

        logger.info("[阶段三] 已创建 %d 条 task_image 占位记录", len(image_prompts))
    except Exception as e:
        logger.warning("[阶段三] 创建 task_image 占位记录失败: %s", e)
