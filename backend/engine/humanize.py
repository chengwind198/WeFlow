#!/usr/bin/env python3
"""去AI味人味化改写 —— 对用户已有成稿做保守改写（只改 1 轮）。

区别于 draft.py 的创作式写作：本模块不新增内容、不重排结构，
只按「反 AI 检测强制清单」改写 AI 味重的句子，且**必须原样保留
所有图片锚点**（`![说明](images/xx.png)` 的 url 与 alt 均不得改动）。

流程: 保守改写 1 轮 → 锚点一致性校验（破坏则 LLM 重试，最多 2 次）
      → 返回改写稿。AI 味检测由 Flow 统一执行（落 80/85）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

from engine.constants import LLMDefaults, Role, Stage
from engine.logger import get_logger
from engine.llm_client import LLMClient
from engine.utils import get_anti_ai_md

logger = get_logger(__name__)

# 锚点正则：![alt](url)，与 image_handler.extract_images_from_markdown 保持一致
_ANCHOR_PATTERN = r'!\[([^\]]*)\]\(([^)]+)\)'

# LLM 破坏锚点后的最大重试次数（含首次共 3 次尝试）
_MAX_ANCHOR_RETRIES = 2


SYSTEM_PROMPT = """你是一个资深的公众号编辑，负责对一篇**已经成稿**的文章做「去 AI 味」人味化改写。

---

## 一、核心原则：保守改写

1. 这是用户的成品文章，你的任务是**消除 AI 味**，不是重写文章。
2. **忠实保留**：全部事实、数据、观点、结构、段落顺序、标题层级一律不动。
3. 只改写 AI 味重的句子：套话、空泛表达、工整排比、机械的"首先/其次/综上所述"、
   高频 AI 黑话（赋能/打造/闭环/方法论/底层逻辑等）。
4. 不新增任何事实，不删减原有信息，不写新的段落，不重排小节。

## 二、硬性约束（违反将导致整篇作废）

1. **图片锚点行原样保留**：形如 `![描述](images/xx.png)` 的每一行，
   **url 与 alt 文本都不得改动**，不得新增图片、不得删除图片、不得调整位置。
2. 只输出改写后的 Markdown 正文，**禁止输出 YAML frontmatter**（--- 开头的内容）、
   禁止输出任何解释说明文字、禁止用代码块包裹全文。

## 三、按「反 AI 检测强制清单」逐条改写

用户消息中会附带完整的反 AI 检测强制清单（9 条），逐条对照改写，重点：
- 句长抖动：插入 5-12 字短句，避免连续 4 句标准长句
- 替换禁用词与 AI 高频词（清单中列出）
- 第一段禁止宏观背景式开头
- 全文 ≥3 处第一人称"我"的主观表达（个人经历/判断/困惑）
- 每 500 字 ≥1 个具体数字或专有名词
- 标点多样：破折号 ≥1、问号 ≥2、括号 ≥1（省略号 ≤3）
- 允许结构"不完美"：小节长短不一、一句"扯远了"式的真人痕迹
- 按账号 voice 过滤整体语气（见用户消息）

## 四、输出格式

只输出改写后的 Markdown 正文（不含 frontmatter、不含代码围栏、不含任何说明）。"""


def _extract_anchor_basenames(md: str) -> Dict[str, int]:
    """提取全文图片锚点的 basename 计数（顺序无关），用于一致性校验。

    仅比较 basename：`images/xx.png`、`./images/xx.png`、`xx.png` 视为同一图片，
    容错用户目录结构差异。
    """
    counts: Dict[str, int] = {}
    for _, url in re.findall(_ANCHOR_PATTERN, md):
        name = Path(url.strip()).name
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 偶尔用 ```markdown 包裹全文的情况。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        # 去掉首行围栏（``` / ```markdown / ```md）
        body = lines[1:]
        # 去掉末尾围栏
        if body and body[-1].strip().startswith("```"):
            body = body[:-1]
        t = "\n".join(body).strip()
    return t


def humanize_article(
    md_content: str,
    task_id: int = 0,
    account_cfg: Optional[dict] = None,
    provider: Optional[str] = None,
) -> Dict[str, object]:
    """对已有成稿做保守人味化改写（1 轮，锚点破坏时 LLM 重试 ≤2 次）。

    Args:
        md_content: 完整 article.md 内容（可含 YAML frontmatter）
        task_id: 关联任务 ID（LLMClient 记录 llm_call_log / task_message 用）
        account_cfg: 账号配置（voice 等）
        provider: 指定 LLM provider（None 用默认）

    Returns:
        {"content": 改写后的完整 md（frontmatter 原样保留）, "rounds": 实际 LLM 调用轮数}

    Raises:
        RuntimeError: LLM 连续 3 次破坏图片锚点，改写作废
    """
    cfg = account_cfg or {}

    # 剥离 frontmatter，只改写正文；改写后原样拼回
    frontmatter = ""
    body = md_content
    stripped = md_content.lstrip("﻿").lstrip()
    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end != -1:
            frontmatter = stripped[: end + 4]
            body = stripped[end + 4:].lstrip("\n")

    original_anchors = _extract_anchor_basenames(body)
    checklist_path = get_anti_ai_md()
    try:
        checklist = checklist_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("[humanize] 读取反 AI 清单失败: %s", e)
        checklist = ""

    voice = cfg.get("voice", "")

    client = LLMClient(provider=provider, stage=Stage.HUMANIZE)
    client.task_id = task_id

    current = body
    anchor_warning = ""
    rounds = 0
    for attempt in range(_MAX_ANCHOR_RETRIES + 1):
        rounds += 1
        user_msg = (
            f"## 原文\n\n{current}\n\n"
            f"## 反AI检测强制清单\n\n{checklist}\n\n"
            f"## 账号 voice\n{voice or '（未配置，按通用真人语气改写）'}\n\n"
            f"{anchor_warning}"
            f"请输出保守改写后的 Markdown 正文。"
        )
        reply = client.chat(
            [{"role": Role.SYSTEM, "content": SYSTEM_PROMPT},
             {"role": Role.USER, "content": user_msg}],
            temperature=LLMDefaults.DRAFT_TEMPERATURE,
            max_tokens=LLMDefaults.DRAFT_MAX_TOKENS,
        )
        reply = _strip_code_fence(reply)

        # 锚点一致性校验：basename 集合 + 计数必须与原文完全一致
        if _extract_anchor_basenames(reply) != original_anchors:
            missing = sorted(set(original_anchors) - set(_extract_anchor_basenames(reply)))
            logger.warning(
                "[humanize] 第 %d 轮改写破坏图片锚点，缺失/变化: %s，重试",
                attempt + 1, missing or "计数不一致",
            )
            anchor_warning = (
                "## ⚠️ 上一轮改写出错\n"
                "你破坏了图片锚点（删除/修改了图片引用）。本轮必须逐行原样保留以下图片锚点"
                "（url 与 alt 均不得改动、不得新增/删除/移动）：\n"
                + "\n".join(f"- `![{alt}]({url})`" for alt, url in
                            re.findall(_ANCHOR_PATTERN, body))
                + "\n\n"
            )
            continue

        break
    else:
        raise RuntimeError(
            f"LLM 改写连续 {_MAX_ANCHOR_RETRIES + 1} 次破坏图片锚点，改写作废。"
            "请检查文章 md 中的图片引用格式（应形如 ![说明](images/xx.png)）。"
        )

    # 拼回 frontmatter，返回完整 md
    content = (frontmatter + "\n" if frontmatter else "") + reply.strip() + "\n"
    logger.info("[humanize] 人味化改写完成 task=%d rounds=%d 字符=%d -> %d",
                task_id, rounds, len(body), len(reply))
    return {"content": content, "rounds": rounds}
