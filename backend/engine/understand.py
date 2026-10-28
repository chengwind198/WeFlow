#!/usr/bin/env python3
"""阶段一：理解需求 → brief.md。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Tuple

from engine.logger import get_logger
from engine.constants import Stage, Status, Operator, FileName, LLMDefaults, Role
from engine.pipeline_db import db_task_create

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是一个资深的公众号选题策划助手。你的任务是根据用户提供的输入信息，**一次性**产出完整、高质量的选题简报，作为后续正式内容写作的输入。

## 核心工作流

1. **解析用户输入**，提取话题、指定要求、参考细节。
2. **基于题材和规则**，自主决策文章结构和开篇钩子（遵循：用户指定 > 题材匹配 > 随机选择）。
3. **补齐关键信息**：哪怕用户信息不足，也要合理推断/虚构具体的“真人味原料”和“核心论点”。
4. **重要** **文章体裁/表达方式，文章结构，开头钩子，文章主题theme**：优先级:用户指定 > AI自动
5. **输出结构化的 Markdown 简报**，严格遵循指定的输出格式。
6. **重要**： 输出的字数要尽可能小于3900字。

---

## 决策规则（必须严格遵守）

### 1. 文章结构（article_structure）选择

- **如果用户在输入中指定了文章结构**：直接使用该值。
- **否则**：根据话题题材，从以下结构库中**自动匹配最合适的**。
- **若题材不明显或存在多个候选**：**随机选择一个**。

以下为结构库，左侧为代码（用于输出），右侧为题材和说明：

| 结构代码 | 适合题材 |
| :--- | :--- | 
| `data-first` | 榜单 / benchmark / 融资 / 财报 / 模型能力 |
| `question-led` | 争议 / 真假难辨 / 产品变化 / 用户困惑 |
| `contrarian` | 舆论一边倒但事实更复杂 | 
| `teardown` | 新框架 / 新协议 / Agent架构 / SDK |
| `field-notes` | 工具体验 / 教程 / 踩坑 / 本机实验 |
| `timeline-news` | 热点新闻 / 公司动作 / 政策 / 安全事故 |
| `playbook` | 方法论 / 技巧合集 / 入门指南 / 生产力 |
| `case-file` | 翻车 / 处罚 / 安全事件 / 商业事故 |

---

### 2. 开篇钩子（opening_hook）选择

- **如果用户在输入中指定了开篇钩子**：直接使用该值。
- **否则**：从以下钩子库中，**匹配最契合所选文章结构的钩子**。
- **若多个都合适**：**随机选一个**。

以下为钩子库：

| 钩子代码 | 写法要点 | 避免 |
| :--- | :--- | :--- |
| `hard-number` | 第一屏出现具体数字、金额、比例、版本号 | 数字后面空泛感慨 |
| `sharp-question` | 用一个读者真会问的问题开场 | 连续自问自答三四句 |
| `contradiction` | 把两个冲突事实并排放出来 | 为反转而反转 |
| `quote-first` | 用当事人原话 / issue / commit message 开场 | 编造无法溯源的“有人说” |
| `artifact-first` | 用命令输出、日志、截图描述、排行榜条目开场 | 贴一大段无解释的技术细节 |
| `timeline-first` | 用具体日期 / 小时时间线开场 | 宏观时代背景 |
| `scene-first` | 用个人经历或具体场景开场 | 每篇都这样写；故事必须短，不要铺陈 |

---

### 3. 主题(theme)选配

- AI、产品、深度分析：refined-blue、business-navy、sage-premium
- 技术、SDK、工程：minimal-mono、minimal-bw、academic-paper
- 新闻、热点、速读：news-bold、warm-editorial
- 人文、随笔、文化：ink-wash、elegant-ink、magazine-grid
- 生活、美食、旅行：warm-orange、mint-fresh、sunset-coral
- 时尚、美妆、情感：girly-pink、sunset-coral

---
### 4. 文章体裁/表达方式

| 名称 | 核心写作目的 | 语言特征 |
| :--- | :--- | :--- |
| **记叙文** | 讲述人物经历或事件过程，传递情感与体验，让读者“感同身受” | 生动形象，时态明确，常用第一或第三人称，多细节描写和对话 |
| **说明文** | 清晰解释事物或事理，传授知识，让读者“明白理解” | 平实准确，客观冷静，术语规范，避免主观抒情，多用定义、分类等方法 |
| **议论文** | 提出并论证观点，说服读者接受主张，让读者“信服并行动” | 严谨慎重，逻辑性强，多用关联词和判断句，论证层次分明 |
| **抒情文** | 抒发内心主观感受，引发读者共鸣，让读者“受到感染” | 富于感染力，多用修饰语、感叹句、排比、比喻，节奏感强 |
| **应用文** | 处理具体事务、传递实用信息，让读者“依此办事” | 规范得体，简洁明了，针对性强，忌空泛抒情，常用固定套语和格式化表达 |
---
### 5. 真人味原料处理

- **用户提供了具体细节**：直接写入输出中的“用户提供的真实细节”部分。
- **用户未提供或信息不足**：根据话题**合理推断/虚构 1-3 个逼真的个人亲历场景**，包含具体的人名、时间、金额、产品版本、踩过的坑。这些是后续写作“反 AI 检测”的核心素材。

---

## 输出格式（必须严格遵守）

**禁止输出任何除以下指定格式外的内容**（包括“好的”“以下是简报”等前缀或后缀）。

请输出以下 Markdown 结构：

# 需求摘要

## 话题
[填入话题标题]

## 文章主题
[用一句话说清楚：这篇文章到底要说明/记叙/议论/抒情什么。这是文章的“灵魂句”。]

## 文章体裁/表达方式
`[名称]`—— [核心写作目的] [语言特征]

## 备选标题（3-5个）
- 标题1：[用具体数字/痛点/悬念]
- 标题2：[用对比/冲突]
- 标题3：[用场景/故事感]

## 关键词
[3-5 个关键词，逗号分隔]

## 目标读者
[一句话描述目标读者的核心特征和痛点]

## 内容调性
[语气风格要求，如：第一人称亲历、口语化、短句子、敢自黑、专业术语必带白话解释]

## 文章结构
`[结构代码]`—— [结构中文名]：1. [步骤1] -> 2. [步骤2] -> 3. [步骤3] -> 4. [步骤4] -> 5. [步骤5]

## 开头钩子
`[钩子代码]` —— [钩子策略描述，一两句话说明打算怎么用这个钩子] [写法要点] [避免]

## 文章主题theme
`[theme]`—— [theme说明]

## 结尾策略
[文章结尾要达成什么目的？例如：总结升华（让读者收藏转发）、灵魂拷问（引导评论区互动）、行动号召（引导添加好友/入群）、或虎头豹尾留个悬念]

## 用户的要求或细节
[用户直接给出的具体要求或细节，如无则写“暂无”]

## 硬核素材清单
[本文必须出现的具体数据、版本号、人名、项目名、网址等，若无则写“暂无”]
```"""
USER_PROMPT = """
话题：{topic}
指定文章体裁：{genre}
指定文章结构：{article_structure}
指定开篇钩子：{opening_hook}
指定文章主题：{theme}
用户的要求或细节：{user_details}
voice：{voice}
```"""
def understand_requirements(
        topic: str,
        account: str = "main",
        output_dir: Optional[str] = None,
        account_cfg: Optional[dict] = None,
        user_details: Optional[str] = None,
        task_type: str = "article",
        need_images: int = 1,
        existing_task_id: int = 0,
        existing_task_path: str = "",
) -> Tuple[str, int]:
    """阶段一：理解需求 → brief.md。返回 (brief_path, task_id)。

    account_cfg: 由调用方（pipeline.run）从 config.yaml 一次性加载传入。
                 字段: article_structure / opening_hook / voice
    user_details: 用户提供的具体细节/参考素材，仅通过 CLI --user-details 传入。
                  支持 @文件路径 语法读取文件内容。
    existing_task_id: 若非零，跳过任务创建，使用已有 task（异步模式）。
    existing_task_path: 与 existing_task_id 配套的任务产物目录。
    """
    from engine.llm_client import LLMClient

    cfg = account_cfg or {}
    user_genre = cfg.get("genre", "") or "auto"
    user_article_structure = cfg.get("article_structure", "") or "auto"
    user_opening_hook = cfg.get("opening_hook", "") or "auto"
    user_theme = cfg.get("theme", "") or "auto"
    voice = cfg.get("voice", "") or ""

    # 解析 user_details：仅来自 CLI 参数，支持 @文件路径 语法
    details = user_details or "暂无"
    if details.startswith("@"):
        file_path = details[1:].strip()  # 去掉 @ 前缀
        path = Path(file_path)
        if not path.exists():
            logger.error("[阶段一] user_details 文件不存在: %s", path.resolve())
            raise FileNotFoundError(f"user_details 文件不存在: {path.resolve()}")
        details = path.read_text(encoding="utf-8")
        logger.info("[阶段一] user_details 从文件加载: %s (%d 字符)", file_path, len(details))

    # 确定产物目录和任务记录
    if existing_task_id > 0:
        tid = existing_task_id
        out_dir = Path(existing_task_path) if existing_task_path else create_task_dir(account, output_dir)
        logger.info("[阶段一] 使用已有任务 task_id=%d path=%s", tid, out_dir)
    else:
        from engine.utils import create_task_dir as _create_task_dir
        out_dir = _create_task_dir(account, output_dir)
        tid = db_task_create(account, topic, account_cfg, task_path=str(out_dir), task_type=task_type, need_images=need_images)
        if not tid:
            logger.error("[阶段一] 无法创建任务记录，db_task_create 返回 0（详见上方错误日志）")
            raise RuntimeError("阶段一失败：无法创建任务记录。请检查数据库及上方错误日志。")

    client = LLMClient(stage=Stage.UNDERSTAND)
    client.task_id = tid

    # SYSTEM_PROMPT 不再需要 format，结构库和钩子库已内嵌在 prompt 中
    user_msg = USER_PROMPT.format(
        topic=topic,
        genre=user_genre,
        article_structure=user_article_structure,
        opening_hook=user_opening_hook,
        theme=user_theme,
        user_details=details,
        voice=voice,
    )
    logger.info("[阶段一] 理解需求: topic=%s account=%s genre=%s structure=%s hook=%s theme=%s",
                topic, account, user_genre, user_article_structure, user_opening_hook, user_theme)
    content = client.chat([
        {"role": Role.SYSTEM, "content": SYSTEM_PROMPT},
        {"role": Role.USER, "content": user_msg},
    ], temperature=LLMDefaults.UNDERSTAND_TEMPERATURE, max_tokens=LLMDefaults.UNDERSTAND_MAX_TOKENS)

    if not content or not content.strip():
        logger.error("[阶段一] LLM 返回空内容，无法生成 brief.md。请检查 API 或重试。")
        raise RuntimeError("阶段一失败：LLM 返回空内容，brief.md 未生成。请重试。")

    brief_path = out_dir / FileName.BRIEF
    brief_path.write_text(content, encoding="utf-8")

    # 解析 AI 返回的 theme / article_structure / opening_hook，
    # 用户未指定时用 AI 选择的值更新 task 表
    _apply_ai_choices(tid, content, user_article_structure, user_opening_hook, user_theme, user_genre)

    # 推进状态到 brief_ready (20)
    from engine.pipeline_db import db_transition
    db_transition(tid, Status.BRIEF_READY, f"{out_dir}", operator=Operator.UNDERSTAND)
    logger.info("阶段一完成 → %s  task_id=%d", brief_path, tid)
    return str(brief_path), tid


def _apply_ai_choices(tid: int, brief_content: str,
                      user_structure: str, user_hook: str, user_theme: str,
                      user_genre: str) -> None:
    """从 brief.md 中解析 AI 选择的 theme / article_structure / opening_hook，
    用户未指定（auto/空）时回写 task 表。"""
    import re
    from engine.db.models import task_update

    # 解析「文章主题theme」: `[theme]`—— [说明]
    m = re.search(r'文章主题theme.*?\n`([^`]+)`', brief_content)
    ai_theme = m.group(1).strip() if m else ""

    # 解析「文章结构」: `[结构代码]`—— [说明]
    m = re.search(r'文章结构.*?\n`([^`]+)`', brief_content)
    ai_structure = m.group(1).strip() if m else ""

    # 解析「开头钩子」: `[钩子代码]` —— [说明]
    m = re.search(r'开头钩子.*?\n`([^`]+)`', brief_content)
    ai_hook = m.group(1).strip() if m else ""

    # 解析「文章体裁/表达方式」: `[genre]`—— [说明]
    m = re.search(r'文章体裁.*?\n`([^`]+)`', brief_content)
    ai_genre = m.group(1).strip() if m else ""

    updates = {}
    if _should_apply(user_theme, ai_theme):
        updates["theme"] = ai_theme
        logger.info("[阶段一] AI 选择 theme=%s → 更新 task", ai_theme)
    if _should_apply(user_structure, ai_structure):
        updates["article_structure"] = ai_structure
        logger.info("[阶段一] AI 选择 article_structure=%s → 更新 task", ai_structure)
    if _should_apply(user_hook, ai_hook):
        updates["opening_hook"] = ai_hook
        logger.info("[阶段一] AI 选择 opening_hook=%s → 更新 task", ai_hook)
    # genre：用户可指定，未指定时应用 AI 选择
    if _should_apply(user_genre, ai_genre):
        updates["genre"] = ai_genre
        logger.info("[阶段一] AI 选择 genre=%s → 更新 task", ai_genre)

    if updates:
        try:
            task_update(tid, **updates)
        except Exception as e:
            logger.debug("[阶段一] 更新 task 字段失败: %s", e)


def _should_apply(user_value: str, ai_value: str) -> bool:
    """用户未指定（auto/空）且 AI 有返回值时，才用 AI 的选择。"""
    return (not user_value or user_value == "auto") and bool(ai_value)
