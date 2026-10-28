#!/usr/bin/env python3
"""阶段四：解析 article.md 的 Frontmatter 中 image_prompts，逐张生成配图。"""

from __future__ import annotations

import json as _json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engine.config import load_env
from engine.logger import get_logger
from engine.constants import Stage, Status, Role, DirPath
from engine.pipeline_db import db_image_record, db_transition

logger = get_logger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
# engine 位于 backend/engine/，项目根目录在 engine/ 上级的上级
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent

# 终极兜底风格
_FALLBACK_STYLE = "hand-drawn-blue"


# ============================================================
# Frontmatter 解析
# ============================================================

def parse_frontmatter(text: str) -> tuple[Dict, str]:
    """解析 article.md：提取 YAML Frontmatter 和正文。

    支持两种格式：
      - 标准 YAML Frontmatter：以 `---` 开头和结尾
      - 非标准 `---yaml` 标记：某些 AI 模型会输出这种格式
    如果有多个 Frontmatter 块，优先解析包含 image_prompts / title
    等核心字段的那个块。

    返回 (frontmatter_dict, body_text)。
    """
    import yaml

    _CORE_KEYS = {"image_prompts", "title", "theme", "image_style"}

    # 优先检测「无头 Frontmatter」：AI 忘记写开头 ---，直接以 YAML 键开头，
    # 后面紧跟一个独立的 --- 作为结束标记
    headless_fm = _try_parse_headless_frontmatter(text, yaml, _CORE_KEYS)
    if headless_fm:
        return headless_fm

    # 快速失败：标准 `---` / 非标准 `---yaml` Frontmatter 必须位于文件开头
    # （允许前导空行）。文首不是 fence 时，正文中的 `---` 只是 Markdown 分割线，
    # 不应触发扫描 —— 否则正文会被误当 frontmatter 截断（例如「AI去味发布」
    # 导入的用户 md 正文里常含 `---`）。此检查不影响标准 frontmatter 文章
    # （AI 生成的 article.md 均以 `---` 开头），行为与之前完全一致。
    if not re.match(r'^(?:\s*)(?:---yaml|---)\s*\n', text):
        return {}, text

    # 手动扫描：逐个查找 --- 或 ---yaml 开头的 YAML 块，避免正则贪婪问题
    all_blocks = []  # [(fm_dict, body_start_pos)]
    pos = 0
    while pos < len(text):
        # 跳过前导空白行，找到下一个 --- 或 ---yaml 开头
        remaining = text[pos:]
        m = re.search(r'(?:^|\n)(---yaml|---)\n', remaining, re.MULTILINE)
        if not m:
            break
        fence_start = pos + m.start(1)  # --- 或 ---yaml 的绝对位置
        content_start = fence_start + len(m.group(1)) + 1  # 跳过 "---\n" 或 "---yaml\n"
        # 查找对应的结束 ---（独立一行）
        end_m = re.search(r'\n---\n', text[content_start:])
        if not end_m:
            # 可能到文件末尾
            end_m2 = re.search(r'\n---$', text[content_start:])
            if end_m2:
                content = text[content_start:content_start + end_m2.start()]
                body_start = content_start + end_m2.end()
            else:
                break
        else:
            content = text[content_start:content_start + end_m.start()]
            body_start = content_start + end_m.end()
        try:
            fm = yaml.safe_load(content) or {}
        except Exception as e:
            logger.warning("[阶段四] YAML 解析 Frontmatter 块失败: %s", e)
            fm = {}
        all_blocks.append((fm, body_start))
        pos = body_start

    if not all_blocks:
        return {}, text

    # 优先选包含核心字段最多的块
    best_fm, best_body_start = all_blocks[0]
    best_score = len(_CORE_KEYS & set(best_fm.keys()))
    for fm, bs in all_blocks[1:]:
        score = len(_CORE_KEYS & set(fm.keys()))
        if score > best_score:
            best_score = score
            best_fm = fm
            best_body_start = bs

    body = text[best_body_start:].strip()
    return best_fm, body


def _try_parse_headless_frontmatter(text: str, yaml_module, core_keys: set) -> Optional[tuple]:
    """检测「无头 Frontmatter」：文本以 YAML 键值对开头，没有 --- 作为起始标记，
    只有后面的独立 --- 作为结束标记。例如 AI 输出直接以 `title: xxx` 开头。

    检测条件：
      1. 文本开头不含 --- 或 ---yaml 标记
      2. 有一个独立的 \\n---\\n 作为结束标记
      3. --- 之前的内容包含典型 Frontmatter 键（title / theme / image_prompts 等）
      4. --- 之前的内容能成功解析为 YAML 且包含至少一个核心键

    如检测成功，返回 (fm_dict, body_text)；否则返回 None。
    """
    # 条件1：文首不能已经是 --- 或 ---yaml（那应该走正常扫描流程）
    if re.match(r'^(?:---yaml|---)\s*\n', text):
        return None

    # 条件2：找到第一个独立的 ---
    m = re.search(r'\n---\s*\n', text)
    if not m:
        return None

    # --- 之前的内容
    candidate = text[:m.start()].strip()
    if not candidate:
        return None

    # 条件3：必须包含典型的 Frontmatter 键
    if not re.search(r'^(?:title|theme|image_style|image_prompts|abstract_introduction):',
                     candidate, re.MULTILINE):
        return None

    # 条件4：能成功解析为 YAML 且包含至少一个核心键
    try:
        fm = yaml_module.safe_load(candidate) or {}
    except Exception as e:
        logger.debug("[阶段四] 无头 Frontmatter YAML 解析失败: %s", e)
        return None
    if not fm or not (core_keys & set(fm.keys())):
        return None

    body = text[m.end():].strip()
    return fm, body


def replace_anchors(body: str, url_map: Dict[str, str]) -> str:
    """将正文中的 anchor://image-XXX 替换为真实 URL 或本地路径。"""
    # 归一化全角 Markdown 符号（LLM 有时会输出全角 ！、（）等）
    body = body.replace("！[", "![").replace("）", ")").replace("（", "(")

    def replacer(match):
        alt_text = match.group(1)
        anchor = match.group(2)
        real = url_map.get(anchor, anchor)
        return f'![{alt_text}]({real})'

    pattern = r'!\[([^\]]*)\]\((anchor://[^)]+)\)'
    return re.sub(pattern, replacer, body)


def _strip_text_requirements(prompt: str) -> str:
    """清洗 prompt 中的文字渲染要求，避免生图模型产生文字幻觉。

    当前生图模型对中文文字渲染不可靠，会生成乱码/错字。
    此函数移除明确要求文字出现的内容。
    """
    import re

    # 1. 移除 "小字" / "文字" / "标注" / "写着" + 引号内容
    prompt = re.sub(
        r'[,，、：:]*[小文底][字本部][^，。]*?(["“「])(.*?)\1',
        '', prompt, flags=re.DOTALL)
    # 2. 移除 "（如XXX）" 数值示例
    prompt = re.sub(r'[（(]如[^）)]*[）)]', '', prompt)
    # 3. 移除括号中包含 "写着"、"标注"、"显示" 的内容
    prompt = re.sub(r'[（(][^）)]*?(写着|标注|显示|出现|列出|写入)[^）)]*[）)]', '', prompt)
    # 4. 移除括号中的分数/数字系列（如 "(20分)" "(20分、18分)"）
    prompt = re.sub(r'[（(]\d+分[、，, ]*\d*分*[）)]', '', prompt)
    prompt = re.sub(r'[（(][^）)]*?差\d+分[^）)]*[）)]', '', prompt)
    # 5. 移除 "写着XXX"、"标注XXX"（无括号形式）
    prompt = re.sub(r'[，,]\s*(?:写着|标注|标明|列出|出现)\s*["“「]?[^，。\s]+["」」]?', '', prompt)
    # 6. 清理 "底部有。" "说明。" 这类残缺句子
    prompt = re.sub(r'[，,。\s]*底部[^，。]*有[。，,。\s]', '。', prompt)
    prompt = re.sub(r'[，,]\s*说明[。，,。\s]', '。', prompt)
    # 7. 清理多重标点和多余空格
    prompt = re.sub(r'[。，,]{2,}', '。', prompt)
    prompt = re.sub(r'\s{2,}', ' ', prompt)
    prompt = prompt.strip().strip('，,、。')

    return prompt


# ============================================================
# 风格解析
# ============================================================

def _resolve_style_name(frontmatter: Dict) -> str:
    """解析配图风格标识。

    优先级:
      1. article.md frontmatter 的 image_style / image_styles
      2. config.yaml 默认账号的 image_style
      3. _FALLBACK_STYLE (hand-drawn-blue)
    """
    # 1. 从 frontmatter 读取
    fm_style = frontmatter.get("image_style") or ""
    if not fm_style:
        image_styles = frontmatter.get("image_styles") or []
        if isinstance(image_styles, list) and image_styles:
            fm_style = image_styles[0]
        elif isinstance(image_styles, str) and image_styles:
            fm_style = image_styles
    if fm_style:
        return str(fm_style)

    # 2. 从 config.yaml 默认账号读取
    try:
        from engine.config import get_config
        cfg = get_config()
        account_style = cfg.get("image_style") or ""
        if account_style:
            return str(account_style)
    except Exception as e:
        logger.debug("[阶段四] 读取 config.yaml image_style 失败: %s", e)

    # 3. 兜底
    return _FALLBACK_STYLE


def _load_style_json(style_name: str) -> Optional[Dict]:
    """加载风格 JSON 文件，返回完整 dict；文件不存在或损坏返回 None。"""
    sp = _PROJECT_ROOT / "assets" / "image-styles" / f"{style_name}.json"
    if not sp.exists():
        logger.warning("风格 JSON 不存在: %s", sp)
        return None
    try:
        return _json.loads(sp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("风格 JSON 解析失败 (%s): %s", sp, e)
        return None


def _build_article_prompt(style_name: str, image_subject: str) -> str:
    """用风格模板包裹原始 prompt。

    Args:
        style_name: 风格标识（如 data-chart）
        image_subject: LLM 生成的原始图片主题（item.prompt），替换模板中的 {image_subject}

    Returns:
        拼接后的完整生图 prompt。若模板缺失则原样返回 image_subject。
    """
    style = _load_style_json(style_name)
    if not style:
        return image_subject

    tmpl = style.get("prompt_template", {})
    template = tmpl.get("article_inline") or ""
    if not template:
        logger.warning("风格 '%s' 缺少 prompt_template.article_inline，回退到原始 prompt", style_name)
        return image_subject

    text = template.replace("{image_subject}", image_subject)
    # 追加文字屏蔽指令：当前生图模型对中文文字渲染不可靠
    # text += " 图片中不要包含任何文字、数字或符号，所有文字信息将通过HTML渲染。"
    return text


def _get_canvas_size(style_name: str) -> str:
    """从风格 JSON 读取 article_size，兜底 1200*900。"""
    style = _load_style_json(style_name)
    if style:
        return style.get("canvas", {}).get("article_size", "1200*900")
    return "1200*900"


# ============================================================
# 主入口
# ============================================================

def generate_images(article_path: str, task_id: int = 0,
                    provider: Optional[str] = None,
                    skip_status_transition: bool = False) -> List[str]:
    """阶段四：从 task_image 表读取配图信息，逐张生成配图。

    1. 从 task_image 表读取 image_prompts
    2. 根据 image_style / image_styles 确定配图风格
    3. 从 assets/image-styles/{style}.json 读取 prompt_template.article_inline
    4. 用模板包裹每张图的 prompt，替换 {image_subject} 占位符
    5. 调用 image_gen_core.generate_image 生图
    6. 回填 anchor 到 article.md 正文

    返回图片路径列表。
    """
    from engine.image_gen_core import detect_provider, generate_image, get_default_model, get_platform_for_provider

    ap = Path(article_path)
    if not ap.exists():
        raise FileNotFoundError(f"article.md 不存在: {article_path}")

    # 从 task_image 表读取配图信息
    image_prompts = []
    image_fm = {}
    style_from_db = ""

    if not task_id:
        raise ValueError("[阶段四] task_id 为空，无法从 task_image 表读取配图信息")

    from engine.db.models import image_list_by_task, task_get
    db_images = image_list_by_task(task_id)
    if db_images:
        image_prompts = [
            {
                "anchor": img["anchor"],
                "prompt": img["prompt"],
                "description": img.get("description", ""),
            }
            for img in db_images
        ]
        # 从 task 表读取 image_style
        task = task_get(task_id)
        if task:
            style_from_db = task.get("image_style", "")
        logger.info("[阶段四] 从 task_image 表读取 %d 条配图信息", len(image_prompts))

    if not image_prompts:
        raise RuntimeError(
            f"[阶段四] task_image 表中无配图记录 (task={task_id})，"
            "请确认 draft 阶段已正常完成并创建了占位记录"
        )

    load_env()
    used_provider = provider or detect_provider()
    model = get_default_model(used_provider)
    images_dir = ap.parent / DirPath.IMAGES
    images_dir.mkdir(parents=True, exist_ok=True)

    # 读取 article.md 用于回填 anchor
    article_text = ap.read_text(encoding="utf-8")
    article_fm, body = parse_frontmatter(article_text)

    # 风格优先级: DB (task.image_style) > frontmatter > config > 兜底
    if task_id > 0 and style_from_db:
        style_name = style_from_db
    else:
        style_name = _resolve_style_name(image_fm)
    img_size = _get_canvas_size(style_name)

    logger.info("[阶段四] 开始生图: %d 张 provider=%s model=%s size=%s style=%s task=%d",
                len(image_prompts), used_provider, model, img_size, style_name, task_id)

    # 获取 draft 阶段 assistant 消息的 id，关联到 task_image
    draft_msg_id = 0
    if task_id:
        try:
            from engine.db.models import task_message_get_last_assistant
            draft_msg_id = task_message_get_last_assistant(task_id, "write_draft")
            if draft_msg_id:
                logger.info("[阶段四] 关联 draft assistant message_id=%d", draft_msg_id)
        except Exception as e:
            logger.debug("[阶段四] 获取 draft assistant message_id 失败: %s", e)

    results = []
    url_map: Dict[str, str] = {}

    for seq, item in enumerate(image_prompts, start=1):
        anchor = item.get("anchor", f"anchor://image-{seq:03d}")
        image_subject = item.get("prompt", "")
        if not image_subject:
            logger.error("[阶段四] [%d/%d] anchor=%s 无 prompt，跳过",
                         seq, len(image_prompts), anchor)
            continue

        # 清洗文字渲染要求，避免生图模型产生文字幻觉
        image_subject = _strip_text_requirements(image_subject)

        # 用风格模板包裹原始 prompt
        full_prompt = _build_article_prompt(style_name, image_subject)

        filename = _anchor_to_filename(anchor, draft_msg_id)
        out = images_dir / filename

        if out.exists():
            logger.info("[阶段四] 跳过已存在: %s", out)
            results.append(str(out))
            url_map[anchor] = out.relative_to(ap.parent).as_posix()
            continue

        logger.info("[阶段四] [%d/%d] anchor=%s style=%s",
                    seq, len(image_prompts), anchor, style_name)

        # 查找已有占位记录（用于后续更新或失败标记）
        existing = None
        if task_id:
            try:
                from engine.db.models import image_find_by_anchor
                existing = image_find_by_anchor(task_id, anchor)
            except Exception:
                pass

        t0 = time.time()
        try:
            image_bytes = generate_image(
                provider=used_provider, model=model, prompt=full_prompt,
                size=img_size, quality="normal",
                platform=get_platform_for_provider(used_provider))
        except Exception as e:
            logger.error("[阶段四] [%d/%d] 生图失败: anchor=%s error=%s",
                         seq, len(image_prompts), anchor, str(e)[:200])
            # 标记占位记录为生成失败
            if existing and task_id:
                try:
                    from engine.db.models import image_update
                    image_update(existing["id"], upload_status="generate_failed")
                except Exception as ue:
                    logger.debug("[阶段四] 更新失败状态出错: %s", ue)
            continue

        out.write_bytes(image_bytes)
        results.append(str(out))
        url_map[anchor] = out.relative_to(ap.parent).as_posix()

        # 解析图片尺寸
        from engine.utils import get_png_dimensions
        w, h = get_png_dimensions(image_bytes)
        est_in = max(1, len(full_prompt) // 3)
        est_out = max(1, len(image_bytes) // 200)

        # 更新已有占位记录或新建（向后兼容）
        img_id = 0
        if task_id:
            try:
                from engine.db.models import image_update
                if existing:
                    image_update(
                        existing["id"],
                        provider=used_provider, model=model, size=img_size,
                        local_path=filename, local_size=len(image_bytes),
                        width=w, height=h, format="png",
                        tokens_in=est_in, tokens_out=est_out,
                        upload_status="generated",
                    )
                    img_id = existing["id"]
                    logger.debug("[阶段四] 更新 task_image id=%d anchor=%s", img_id, anchor)
            except Exception as e:
                logger.warning("[阶段四] 查找/更新 task_image 失败: task=%d anchor=%s: %s",
                               task_id, anchor, e)

        if not existing:
            img_id = db_image_record(task_id, seq, image_subject, used_provider, model,
                                     filename, image_bytes, img_size, message_id=draft_msg_id)

        # 记录文生图对话到 task_message
        if img_id:
            try:
                from engine.db.models import task_message_append
                task_message_append(
                    task_id=task_id, stage=Stage.GENERATE,
                    provider=used_provider, model=model,
                    role=Role.USER, message=full_prompt, image_id=img_id,
                )
                task_message_append(
                    task_id=task_id, stage=Stage.GENERATE,
                    provider=used_provider, model=model,
                    role=Role.ASSISTANT,
                    message=f"图片已生成: {out} ({len(image_bytes)}字节)",
                    image_id=img_id,
                )
            except Exception as e:
                logger.warning("[阶段四] 写入生图 task_message 失败: task=%d img_id=%d: %s",
                               task_id, img_id, e)
        logger.info("  [%d/%d] %s (%dKB, %dms)",
                    seq, len(image_prompts), filename,
                    int(len(image_bytes) / 1024), int((time.time() - t0) * 1000))
        if seq < len(image_prompts):
            time.sleep(2)

    # 回填：将 article.md 正文中的 anchor 替换为本地图片路径
    if url_map:
        new_body = replace_anchors(body, url_map)
        fm_yaml = _dump_frontmatter(article_fm)
        if fm_yaml and fm_yaml != "{}":
            new_text = f"---\n{fm_yaml}\n---\n\n{new_body}"
        else:
            new_text = new_body  # article.md 无 Frontmatter，仅正文
        ap.write_text(new_text, encoding="utf-8")
    if results and not skip_status_transition:
        db_transition(task_id, Status.IMAGES_GENERATED, f"配图 {len(results)} 张: {used_provider} ({style_name})")

    logger.info("阶段四完成 → %d 张配图 (风格=%s), 已回填 %d 个 anchor",
                len(results), style_name, len(url_map))
    return results


# ============================================================
# 辅助函数
# ============================================================

def _anchor_to_filename(anchor: str, prefix: int = 0) -> str:
    """anchor://image-001 → image-42-001.png / anchor://cover → cover-42.png（prefix 为 draft message_id）"""
    name = anchor.split("/")[-1]
    if prefix:
        if name.startswith("image-"):
            tail = name[len("image-"):]
            name = f"image-{prefix}-{tail}"
        elif name == "cover":
            name = f"cover-{prefix}"
    return f"{name}.png" if not name.endswith(".png") else name


def _dump_frontmatter(fm: Dict) -> str:
    """将 Frontmatter dict 序列化为 YAML 字符串。"""
    try:
        import yaml
        return yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    except Exception as e:
        logger.warning("[阶段四] Frontmatter YAML 序列化失败: %s", e)
        return ""


# ============================================================
# 封面图自动生成（用于 no_images 模式下的发布阶段）
# ============================================================

def generate_cover(article_path: str, task_id: int = 0,
                   provider: Optional[str] = None,
                   image_style: Optional[str] = None) -> Optional[str]:
    """为无配图模式的文章自动生成封面图。

    在 no_images 模式下，文章没有配图，但发布时仍需要封面图。
    此函数根据文章标题/话题自动生成一张封面图，存入 task_image 表（is_cover=1）。

    Args:
        article_path: article.md 路径
        task_id: 任务 ID（用于读取 topic/title 并写入 task_image）
        provider: 生图 provider（None 时自动检测）
        image_style: 配图风格标识（None 时使用账号默认或兜底）

    Returns:
        封面图本地路径，失败返回 None
    """
    from engine.image_gen_core import detect_provider, generate_image, get_default_model, get_platform_for_provider
    from engine.config import load_env

    ap = Path(article_path)
    if not ap.exists():
        logger.error("[封面生成] article.md 不存在: %s", article_path)
        return None

    load_env()
    used_provider = provider or detect_provider()
    model = get_default_model(used_provider)

    # 获取文章话题/标题，生成封面提示词
    topic = ""
    title = ""
    if task_id:
        try:
            from engine.db.models import task_get
            t = task_get(task_id)
            if t:
                topic = t.get("topic", "")
                title = t.get("title", "")
        except Exception as e:
            logger.warning("[封面生成] 读取 task 信息失败: task=%d: %s", task_id, e)

    # 如果 DB 没有，尝试从 article.md frontmatter 读取
    if not topic and not title:
        try:
            raw = ap.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(raw)
            title = fm.get("title", "")
            topic = fm.get("topic", "")
        except Exception as e:
            logger.debug("[封面生成] 从 article.md 读取元信息失败: %s", e)

    # 兜底：用文件名或路径中的 slug 作为话题
    if not topic:
        topic = ap.parent.name or "技术文章"
    if not title:
        title = topic

    # 构建封面提示词
    cover_prompt = (
        f"a conceptual illustration representing the topic '{topic}', "
        f"article titled '{title}', editorial illustration style, "
        f"clean composition, wide cinematic aspect ratio 2.35:1, "
        f"no text in the image, abstract visual metaphor"
    )

    # 解析风格名
    if not image_style:
        image_style = _resolve_style_name({})
    cover_size = _get_canvas_size(image_style)

    # 确定保存路径
    images_dir = ap.parent / DirPath.IMAGES
    images_dir.mkdir(parents=True, exist_ok=True)

    # 获取 draft message_id 用于文件命名
    draft_msg_id = 0
    if task_id:
        try:
            from engine.db.models import task_message_get_last_assistant
            draft_msg_id = task_message_get_last_assistant(task_id, "write_draft")
        except Exception as e:
            logger.debug("[封面生成] 获取 draft_msg_id 失败: %s", e)

    filename = _anchor_to_filename("anchor://cover", draft_msg_id)
    out = images_dir / filename

    # 如果已存在，直接返回
    if out.exists():
        logger.info("[封面生成] 封面图已存在: %s", out)
    else:
        logger.info("[封面生成] 开始生成封面: provider=%s model=%s style=%s topic=%s",
                    used_provider, model, image_style, topic[:50])

        try:
            image_bytes = generate_image(
                provider=used_provider, model=model, prompt=cover_prompt,
                size=cover_size, quality="normal",
                platform=get_platform_for_provider(used_provider))
        except Exception as e:
            logger.error("[封面生成] 生图失败: %s", str(e)[:200])
            # 标记失败状态
            if task_id:
                try:
                    from engine.db.models import image_find_cover, image_update, image_insert
                    existing = image_find_cover(task_id, draft_msg_id)
                    if existing:
                        image_update(existing["id"], upload_status="generate_failed",
                                     upload_error=str(e)[:500])
                    else:
                        image_insert(
                            task_id=task_id, message_id=draft_msg_id, seq=0,
                            anchor="anchor://cover", description=topic,
                            prompt=cover_prompt, provider=used_provider, model=model,
                            image_style=image_style or "", size=cover_size,
                            is_cover=True, upload_status="generate_failed",
                            upload_error=str(e)[:500],
                        )
                except Exception as ue:
                    logger.debug("[封面生成] 写入失败状态出错: %s", ue)
            return None

        out.write_bytes(image_bytes)
        logger.info("[封面生成] 封面已保存: %s (%d KB)", out, len(image_bytes) // 1024)

    # 写入 task_image 表
    if task_id:
        try:
            from engine.db.models import image_insert, image_find_cover, image_update

            # 估算 token 消耗
            est_tokens_in = max(1, len(cover_prompt) // 3)
            est_tokens_out = max(1, (out.stat().st_size if out.exists() else 0) // 200)

            # 检查是否已有封面记录
            existing = image_find_cover(task_id, draft_msg_id)
            if existing:
                logger.info("[封面生成] task_image 已有封面记录 id=%d，更新状态", existing["id"])
                if out.exists():
                    image_update(existing["id"], upload_status="generated",
                                 description=topic,
                                 local_path=filename,
                                 local_size=out.stat().st_size,
                                 tokens_in=est_tokens_in,
                                 tokens_out=est_tokens_out)
            else:
                # 解析图片尺寸（如果文件存在）
                w, h = 0, 0
                if out.exists():
                    try:
                        from engine.utils import get_png_dimensions
                        w, h = get_png_dimensions(out.read_bytes())
                    except Exception:
                        pass

                cover_id = image_insert(
                    task_id=task_id,
                    message_id=draft_msg_id,
                    seq=0,  # 封面 seq=0，排在配图之前
                    anchor="anchor://cover",
                    description=topic,
                    prompt=cover_prompt,
                    provider=used_provider,
                    model=model,
                    image_style=image_style or "",
                    size=cover_size,
                    local_path=filename,
                    local_size=out.stat().st_size if out.exists() else 0,
                    width=w, height=h, fmt="png",
                    is_cover=True,
                    upload_status="generated",
                    tokens_in=est_tokens_in,
                    tokens_out=est_tokens_out,
                )
                logger.info("[封面生成] task_image 封面记录已创建 id=%d", cover_id)
        except Exception as e:
            logger.warning("[封面生成] 写入 task_image 失败: task=%d: %s", task_id, e)

    return str(out)
