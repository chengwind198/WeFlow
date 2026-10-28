"""贴图(图片消息 / newspic)工具函数 —— 解析 brief.md、切分卡片文字。

自动化流程入口: `flows/newspic_flow.py`（pipeline.py run --type newspic），全程走 task_image。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engine.logger import get_logger

sys.path.insert(0, str(Path(__file__).parent))

logger = get_logger(__name__)

try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "缺少 pyyaml 依赖。请执行: pip install pyyaml --break-system-packages"
    ) from exc


# ============================================================
# brief.md 解析
# ============================================================

FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _repair_yaml_quotes(fm_text: str) -> str:
    """修复 YAML frontmatter 中引号导致的解析失败。

    LLM 可能输出 topic: \"再军事化\"的日本... 或 topic: \"标题\"
    内层引号（ASCII \" 或中文 \"\"）会被 YAML 误认为字符串定界符。

    策略：对每行 key: value，直接去掉 value 部分的所有双引号。
    这不会影响内容理解，且避免了复杂的嵌套引号转义。
    """
    lines = fm_text.splitlines()
    repaired: list[str] = []
    for line in lines:
        if ':' in line:
            key, _, val = line.partition(':')
            # 去掉所有类型的双引号：ASCII " 和中文 ""
            stripped = val.replace('"', '').replace('“', '').replace('”', '')
            if stripped != val:
                line = f'{key}:{stripped}'
                logger.debug("YAML 引号修复: %s", line.strip()[:80])
        repaired.append(line)
    return '\n'.join(repaired)


def parse_brief(md_text: str) -> Dict[str, Any]:
    """
    把 brief.md 拆成:
        {
          "frontmatter": dict,
          "sections": {"要点": [str, ...], "短文本": str, ...}
        }
    """
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        logger.error("brief.md 缺少 YAML frontmatter")
        raise ValueError(
            "brief.md 必须以 YAML frontmatter 开头(--- ... --- 包围),请补上"
        )
    fm_text = m.group(1)
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        # 容错：LLM 输出的 YAML 值可能包含未转义的双引号
        # 如 topic: "再军事化"的日本... → 内层引号破坏 YAML 结构
        # 尝试将双引号包裹的值改为单引号包裹，或去掉外层的双引号
        logger.warning("brief.md frontmatter YAML 解析失败，尝试修复引号: %s", str(e)[:120])
        try:
            fm_text = _repair_yaml_quotes(fm_text)
            frontmatter = yaml.safe_load(fm_text) or {}
            logger.info("brief.md frontmatter 引号修复后解析成功")
        except Exception as e2:
            logger.error("brief.md frontmatter 修复后仍解析失败: %s", e2)
            raise ValueError(f"brief.md frontmatter 解析失败: {e}") from e

    body = md_text[m.end():]

    # 按一级标题切分 body,收集每个 section 的文字
    sections: Dict[str, str] = {}
    current_name: Optional[str] = None
    buf: List[str] = []
    for line in body.splitlines():
        h1 = re.match(r"^#\s+(.+?)\s*$", line)
        if h1:
            if current_name is not None:
                sections[current_name] = "\n".join(buf).strip()
            else:
                # 第一个标题前有未归属的内容 → 自动识别为「要点」
                orphan = "\n".join(buf).strip()
                if orphan:
                    sections["要点"] = orphan
            current_name = h1.group(1).strip()
            buf = []
        else:
            if current_name is not None:
                buf.append(line)
            else:
                # 尚未遇到任何标题，暂存为孤块
                buf.append(line)
    if current_name is not None:
        sections[current_name] = "\n".join(buf).strip()
    elif buf:
        # 整个 body 没有标题，全部归为「要点」
        orphan = "\n".join(buf).strip()
        if orphan:
            sections["要点"] = orphan

    return {"frontmatter": frontmatter, "sections": sections}


def extract_bullet_points(section_text: str) -> List[str]:
    """从一个 section 里提取列表项。支持 `1.` / `-` / `*` / `+` 三种。"""
    points: List[str] = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:\d+[.、)]|[-*+])\s+(.+)$", line)
        if m:
            points.append(m.group(1).strip())
    return points


# ============================================================
# 拆卡
# ============================================================

_VERSION_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-\.][A-Za-z0-9]+)+"
)


def _protect_version_tokens(text: str) -> Tuple[str, Dict[str, str]]:
    """把 GPT-5.5 / V4-Pro / 2026-04-25 / API价$5/M 这样的 token 用占位符替换,
    避免被英文句点/连字符误切。返回 (替换后文本, 占位符到原文 map)。"""
    mapping: Dict[str, str] = {}

    def repl(m: re.Match) -> str:
        key = f"\x01TOK{len(mapping):03d}\x01"
        mapping[key] = m.group(0)
        return key

    return _VERSION_TOKEN_RE.sub(repl, text), mapping


def _restore_tokens(text: str, mapping: Dict[str, str]) -> str:
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def _split_card_text(point: str, max_main: int = 30) -> Tuple[str, str]:
    """
    把一条"要点"拆成卡片主文字 + 副文字。

    策略:
      - 短于 max_main 直接当主文字,副文字空
      - **先保护版本号 token** ("GPT-5.5" / "V4-Pro" / "2026-04-25") 不被切开
      - 找中文句号/逗号/分号/冒号/破折号,在合理位置切
      - 实在没自然断点才硬切
    """
    point = point.strip()
    if len(point) <= max_main:
        return point, ""

    protected, tokens = _protect_version_tokens(point)
    # 占位符长度不同,简单用字符级 index 工作即可

    # pattern 1: 中文/英文断句标点
    safe_splits = re.compile(r"——|[,。;：:,；！？!?]")
    for m in safe_splits.finditer(protected):
        if 3 <= m.start() <= max_main + 8:
            main = _restore_tokens(protected[: m.start()], tokens).strip()
            sub = _restore_tokens(protected[m.end():], tokens).strip()
            if main and sub and len(main) >= 3:
                return main, sub

    # pattern 2: 单独的 `-`(保护过版本号后的安全连字符),两侧至少一侧是中文才切
    for m in re.finditer(r"-", protected):
        i = m.start()
        if not (3 <= i <= max_main + 8):
            continue
        left = protected[i - 1] if i > 0 else ""
        right = protected[i + 1] if i + 1 < len(protected) else ""
        if re.match(r"[一-鿿]", left) or re.match(r"[一-鿿]", right):
            main = _restore_tokens(protected[:i], tokens).strip()
            sub = _restore_tokens(protected[i + 1:], tokens).strip()
            if main and sub:
                return main, sub

    # 硬切(在原始 point 上,但避开占位符)
    restored = _restore_tokens(protected, tokens)
    return restored[:max_main].strip(), restored[max_main:].strip()
