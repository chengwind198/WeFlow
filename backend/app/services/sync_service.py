"""多平台同步服务层 —— 封装同步记录的 CRUD 与 wechatsync CLI 调用。

核心约定：
  - task_sync.markdown_content 是唯一权威源（用户在前端编辑后点"开始同步"即保存到此）
  - 同步时写入任务目录下的 .sync.md 给 CLI 使用，不生成临时文件，不改源文件
  - 重试时直接从 task_sync.markdown_content 读取，不回读 brief.md
  - 支持三种来源: task（任务）/ local（本地文件）/ url（网址获取）
"""

import asyncio
import json
import os
import re
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ============================================================
# 同步目录管理
# ============================================================

def create_sync_dir(account: str = "main") -> Path:
    """创建同步专用产物目录（含时间戳+随机后缀防冲突），返回 Path。
    命名规范：{generated_dir}/{timestamp}{millis}_{rand3}_{account}_sync/
    """
    from engine.config import get_generated_dir

    generated_dir = get_generated_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    millis = int((time.time() % 1) * 1000)
    rand_suffix = f"{random.randint(0, 999):03d}"
    out_dir = Path(f"{generated_dir}/{timestamp}{millis:03d}_{rand_suffix}_{account}_sync")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ============================================================
# 辅助工具
# ============================================================

_H1_RE = re.compile(r'^#\s+', re.MULTILINE)


def _extract_heading(md_content: str) -> str:
    """从 Markdown 内容提取第一个 # 标题文本，没有则返回空字符串。"""
    m = _H1_RE.search(md_content)
    if not m:
        return ""
    line_start = m.start()
    line_end = md_content.find("\n", line_start)
    if line_end == -1:
        line_end = len(md_content)
    return md_content[line_start + 2:line_end].strip()


def _ensure_markdown_heading(md_content: str, fallback_title: str = "") -> tuple[str, str]:
    """确保 Markdown 内容包含 # 标题。没有则自动补一个，返回 (content, title)。"""
    title = _extract_heading(md_content)
    if title:
        return md_content, title
    # 没有 # 标题 → 自动生成
    heading = fallback_title.strip() if fallback_title.strip() else "未命名文章"
    return f"# {heading}\n\n{md_content}", heading


# ============================================================
# 网址获取
# ============================================================

async def fetch_url_and_save(url: str) -> dict:
    """获取网址内容，转为 Markdown 保存到本地，返回内容及路径。"""
    return await asyncio.to_thread(_fetch_url_and_save_sync, url)


def _fetch_url_and_save_sync(url: str) -> dict:
    try:
        import trafilatura
        import requests
    except ImportError as e:
        raise ImportError(f"请安装依赖: {e}")

    # 1. 使用 requests 获取网页（绕过 trafilatura 内部 zstd 解压问题）
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=30,
        )
        resp.raise_for_status()
        # 尝试检测编码
        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        html = resp.text
    except Exception as e:
        raise ValueError(f"无法访问该网址: {url} — {e}")

    if not html:
        raise ValueError(f"获取到的页面内容为空: {url}")

    # 2. 提取 Markdown
    markdown_content = trafilatura.extract(
        html,
        output_format="markdown",
        include_images=True,
        include_links=True,
    )
    if not markdown_content:
        raise ValueError(f"无法从网址提取内容: {url}")

    # 3. 确保有 # 标题（从内容提取或自动生成）
    markdown_content, extracted_title = _ensure_markdown_heading(markdown_content, fallback_title="")

    # 4. 提取元数据标题（可能覆盖 extracted_title）
    title = extracted_title
    try:
        metadata_json = trafilatura.extract(html, output_format="json")
        if metadata_json:
            meta = json.loads(metadata_json)
            title = meta.get("title", "") if isinstance(meta, dict) else ""
    except Exception:
        pass

    # 5. 创建同步目录，保存 article.md
    sync_dir = create_sync_dir()
    article_path = sync_dir / "article.md"
    article_path.write_text(markdown_content, encoding="utf-8")

    # 6. 下载文章中的图片
    images_dir = sync_dir / "images"
    images_dir.mkdir(exist_ok=True)
    downloaded_images = _download_markdown_images(markdown_content, images_dir)

    return {
        "markdown_content": markdown_content,
        "title": title,
        "file_path": str(article_path),
        "images": downloaded_images,
    }


def _download_markdown_images(md_content: str, output_dir: Path) -> list[str]:
    """查找 Markdown 中的 HTTP(S) 图片链接，下载到 output_dir，返回本地路径列表。"""
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    images: list[str] = []

    for match in re.finditer(pattern, md_content):
        img_url = match.group(2)
        if not img_url.startswith(("http://", "https://")):
            continue
        try:
            url_path = urllib.parse.urlparse(img_url).path
            ext = os.path.splitext(url_path)[1] or ".jpg"
            file_name = f"{len(images) + 1:03d}{ext}"
            file_path = output_dir / file_name
            urllib.request.urlretrieve(img_url, str(file_path))
            images.append(str(file_path))
        except Exception:
            pass  # 图片下载失败不影响整体流程

    return images


# ============================================================
# 本地文件上传
# ============================================================

async def save_uploaded_file(file_content: bytes, file_name: str) -> dict:
    """保存上传的 .md 文件到同步目录，返回内容及路径。"""
    return await asyncio.to_thread(_save_uploaded_file_sync, file_content, file_name)


def _save_uploaded_file_sync(file_content: bytes, file_name: str) -> dict:
    markdown_content = file_content.decode("utf-8")

    # 确保有 # 标题
    markdown_content, _title = _ensure_markdown_heading(markdown_content, fallback_title="")

    sync_dir = create_sync_dir()
    article_path = sync_dir / "article.md"
    article_path.write_text(markdown_content, encoding="utf-8")

    return {
        "markdown_content": markdown_content,
        "file_path": str(article_path),
        "file_name": file_name,
    }


# ============================================================
# 列表查询
# ============================================================

async def list_sync_tasks(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    """分页查询同步任务列表。"""
    return await asyncio.to_thread(
        _list_sync_tasks_sync, page, page_size, status, sort_by, sort_order,
    )


def _list_sync_tasks_sync(
    page: int, page_size: int, status: Optional[str],
    sort_by: str, sort_order: str,
) -> dict:
    from engine.db.models import task_sync_list

    items, total = task_sync_list(
        page=page, page_size=page_size, status=status,
        sort_by=sort_by, sort_order=sort_order,
    )
    for item in items:
        # 处理 NULL 值（local/url 来源无对应 task 行，LEFT JOIN 返回 NULL）
        item["task_id"] = item.get("task_id") or 0
        item["topic"] = item.get("topic") or ""
        item["title"] = item.get("title") or ""
        # 确保新字段存在默认值
        item.setdefault("sync_from", "task")
        item.setdefault("url", None)
        item.setdefault("file_path", None)
        # 非 task 来源：截取 markdown_content 前 20 字符作为预览
        sync_from = item.get("sync_from", "task")
        if sync_from != "task" and not item["topic"]:
            md = item.get("markdown_content", "") or ""
            item["topic"] = md[:50].replace("\n", " ") + ("..." if len(md) > 50 else "")
        item.setdefault("result_count", 0)
        # 解析平台数量
        platforms = item.get("platforms", "[]")
        try:
            pl = json.loads(platforms) if isinstance(platforms, str) else platforms
            item["platform_count"] = len(pl) if isinstance(pl, list) else 0
        except (json.JSONDecodeError, TypeError):
            item["platform_count"] = 0
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ============================================================
# 详情查询
# ============================================================

async def get_sync_task(sync_id: int) -> Optional[dict]:
    """获取同步详情（含各平台结果）。"""
    return await asyncio.to_thread(_get_sync_task_sync, sync_id)


def _get_sync_task_sync(sync_id: int) -> Optional[dict]:
    from engine.db.models import (
        task_sync_get, task_sync_result_list_by_sync_id, task_get,
    )
    from engine.constants import SyncPlatform

    sync = task_sync_get(sync_id)
    if not sync:
        return None
    # 处理 task_id 为 NULL 的情况
    sync["task_id"] = sync.get("task_id") or 0
    # 确保新字段存在
    sync.setdefault("sync_from", "task")
    sync.setdefault("url", None)
    sync.setdefault("file_path", None)
    task = task_get(sync["task_id"]) if sync["task_id"] else None
    if task:
        sync["topic"] = task.get("topic", "")
        sync["title"] = task.get("title", "")
    else:
        sync["topic"] = ""
        sync["title"] = ""
    results = task_sync_result_list_by_sync_id(sync_id)
    for r in results:
        r["platform_label"] = SyncPlatform.label(r.get("platform", ""))
    sync["results"] = results
    return sync


# ============================================================
# 辅助
# ============================================================

def _resolve_task_path(task: dict) -> str:
    """将 task_path 解析为绝对路径。"""
    from engine.config import get_project_root

    task_path = task.get("task_path", "")
    if not task_path:
        raise ValueError("任务缺少 task_path")
    if not os.path.isabs(task_path):
        task_path = os.path.normpath(os.path.join(get_project_root(), task_path))
    return task_path


def _parse_and_insert_results(
    result: dict, sync_id: int, platforms: list[str],
) -> str:
    """解析 CLI 返回结果，逐平台写入 task_sync_result，返回整体状态。"""
    from engine.db.models import task_sync_result_insert

    parsed = result.get("parsed", None)

    if parsed and isinstance(parsed, dict):
        for p in platforms:
            platform_result = parsed.get(p, {})
            if isinstance(platform_result, dict):
                p_status = "success" if platform_result.get("success", False) else "failed"
                p_error = platform_result.get("error", "") or platform_result.get("message", "")
            else:
                p_status = "failed"
                p_error = f"无法解析平台 {p} 的返回结果"
            task_sync_result_insert(sync_id, p, status=p_status, error_msg=p_error)

        all_success = all(
            parsed.get(p, {}).get("success", False)
            if isinstance(parsed.get(p, {}), dict) else False
            for p in platforms
        )
        if all_success:
            return "success"
        elif any(
            isinstance(parsed.get(p, {}), dict) and parsed.get(p, {}).get("success")
            for p in platforms
        ):
            return "partial"
        else:
            return "failed"
    else:
        # 无法解析为 dict，从 CLI 文本输出中逐行解析各平台结果
        # wechatsync 文本格式:
        #   ✓ zhihu (草稿)
        #   ✗ csdn
        #     请先登录 CSDN
        output_text = result.get("stderr", "") + "\n" + result.get("stdout", "")
        lines = output_text.splitlines()

        # 第一遍：找到每个平台的的状态行及其后续错误消息
        platform_results: dict[str, dict] = {}  # {platform: {status, msg}}
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            # 匹配状态行: 成功符号 ✓ ✔  或 失败符号 ✗ ✖ × ✘
            is_status_line = any(
                sym in stripped for sym in ("✓", "✔", "✗", "✖", "×", "✘")
            )
            if not is_status_line:
                continue
            # 找到该行对应的平台
            matched_platform = None
            for p in platforms:
                if p in stripped:
                    matched_platform = p
                    break
            if not matched_platform:
                continue

            is_success = "✓" in stripped or "✔" in stripped
            # 收集错误消息：后续行直到下一个状态行或空行
            error_lines = []
            if not is_success:
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line:
                        break
                    if any(sym in next_line for sym in ("✓", "✔", "✗", "✖", "×", "✘")):
                        break
                    error_lines.append(next_line)
            msg = stripped
            if error_lines:
                msg += "\n" + "\n".join(error_lines)
            platform_results[matched_platform] = {"status": "success" if is_success else "failed", "msg": msg}

        # 第二遍：为所有请求的平台写入结果
        for p in platforms:
            if p in platform_results:
                pr = platform_results[p]
            else:
                # 没找到该平台的明确结果，汇总全部输出
                summary = [
                    l for l in lines
                    if l.strip() and not l.startswith("Active code page")
                ]
                pr = {"status": "failed", "msg": "\n".join(summary[:10])}
            task_sync_result_insert(sync_id, p, status=pr["status"], error_msg=pr["msg"][:500])

    # 从 task_sync_result 重新计算整体状态
    from engine.db.models import task_sync_result_list_by_sync_id
    all_results = task_sync_result_list_by_sync_id(sync_id)
    all_success = all(r.get("status") == "success" for r in all_results)
    any_success = any(r.get("status") == "success" for r in all_results)
    if all_success:
        return "success"
    elif any_success:
        return "partial"
    else:
        return "failed"


# ============================================================
# 创建/覆盖同步记录并执行同步
# ============================================================

# ============================================================
# 仅保存（不执行同步）
# ============================================================

async def save_only(
    sync_id: Optional[int] = None,
    task_id: Optional[int] = None,
    platforms: list[str] | None = None,
    markdown_content: str = "",
    sync_from: str = "task",
    url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    """仅保存 markdown 内容到 task_sync，不触发同步。"""
    if platforms is None:
        platforms = []
    return await asyncio.to_thread(
        _save_only_sync, sync_id, task_id, platforms, markdown_content,
        sync_from, url, file_path,
    )


def _save_only_sync(
    sync_id: Optional[int],
    task_id: Optional[int],
    platforms: list[str],
    markdown_content: str = "",
    sync_from: str = "task",
    url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    from engine.db.models import task_get, task_sync_get, task_sync_upsert, task_sync_update
    from engine.config import get_project_root, get_brief_path

    # —— 已有记录（syncId 编辑模式）：复用 file_path，仅更新内容 ——
    if sync_id:
        existing = task_sync_get(sync_id)
        if not existing:
            raise ValueError(f"同步记录 {sync_id} 不存在")
        # 复用已有 file_path
        if not file_path:
            file_path = existing.get("file_path")
        # 覆盖写入文件
        if markdown_content and file_path:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        task_sync_update(sync_id,
                         markdown_content=markdown_content,
                         platforms=json.dumps(platforms),
                         status="draft")
        return _get_sync_task_sync(sync_id)

    # task 来源：验证任务存在并读取 brief.md
    if sync_from == "task":
        if not task_id:
            raise ValueError("task 来源时 task_id 不能为空")
        task = task_get(task_id)
        if not task:
            raise ValueError(f"任务 {task_id} 不存在")
        task_path = _resolve_task_path(task)
        brief_md = get_brief_path(task_path)
        if not markdown_content:
            if os.path.exists(brief_md):
                with open(brief_md, encoding="utf-8") as f:
                    markdown_content = f.read()
            else:
                raise ValueError(f"简报文件不存在: {brief_md}")
        # task 来源：记录 brief.md 路径作为 file_path
        if not file_path:
            file_path = brief_md
    else:
        # local/url 来源：从 file_path 读取 .md 内容（如果 markdown_content 为空）
        if not markdown_content and file_path:
            if os.path.exists(file_path):
                with open(file_path, encoding="utf-8") as f:
                    markdown_content = f.read()
            else:
                raise ValueError(f"文章文件不存在: {file_path}")
        # 如果 markdown_content 非空且有 file_path，写入文件
        if markdown_content and file_path:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, encoding="utf-8") as f:
                existing = f.read()
            if existing != markdown_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(markdown_content)

    sync_id = task_sync_upsert(
        task_id=task_id,
        markdown_content=markdown_content,
        platforms=json.dumps(platforms),
        sync_from=sync_from,
        url=url,
        file_path=file_path,
        status="draft",
    )

    return _get_sync_task_sync(sync_id)


async def create_or_update_sync(
    sync_id: Optional[int] = None,
    task_id: Optional[int] = None,
    platforms: list[str] | None = None,
    markdown_content: str = "",
    sync_from: str = "task",
    url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    """创建/覆盖同步记录并调用 wechatsync CLI 执行同步。"""
    if platforms is None:
        platforms = []
    return await asyncio.to_thread(
        _create_or_update_sync_sync, sync_id, task_id, platforms, markdown_content,
        sync_from, url, file_path,
    )


def _create_or_update_sync_sync(
    sync_id: Optional[int],
    task_id: Optional[int],
    platforms: list[str],
    markdown_content: str = "",
    sync_from: str = "task",
    url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    from engine.db.models import (
        task_get, task_sync_get, task_sync_get_by_task_id,
        task_sync_upsert, task_sync_update, task_sync_result_delete_by_sync_id,
    )
    from engine.config import get_brief_path

    title = ""
    md_path = ""

    if sync_from == "task":
        # —— task 来源：验证任务，读取 brief.md ——
        if not task_id:
            raise ValueError("task 来源时 task_id 不能为空")
        task = task_get(task_id)
        if not task:
            raise ValueError(f"任务 {task_id} 不存在")
        status = task.get("status", 0)
        if status < 60 or status > 90:
            raise ValueError(f"任务状态为 {status}，仅支持状态 60-90 的任务同步")

        task_path = _resolve_task_path(task)
        brief_md = get_brief_path(task_path)
        if not markdown_content:
            if os.path.exists(brief_md):
                with open(brief_md, encoding="utf-8") as f:
                    markdown_content = f.read()
            else:
                raise ValueError(f"简报文件不存在: {brief_md}")
        # 确保最新内容写入文件
        if markdown_content:
            with open(brief_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        md_path = brief_md
        # task 来源：记录 brief.md 路径作为 file_path
        if not file_path:
            file_path = brief_md
        title = task.get("title", "") or task.get("topic", "")

        # 查找已有记录，清空旧结果
        existing = task_sync_get_by_task_id(task_id)
        if existing:
            task_sync_result_delete_by_sync_id(existing["id"])
    else:
        # —— local/url 来源：从 file_path 读取 ——
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"文章文件不存在: {file_path}")
        # 写入最新 markdown 内容
        if markdown_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        else:
            with open(file_path, encoding="utf-8") as f:
                markdown_content = f.read()
        md_path = file_path
        # 从 markdown 内容提取 # 标题
        title = _extract_heading(markdown_content) if markdown_content else ""

        # —— 如果传了 sync_id，复用已有记录并清空旧结果 ——
        if sync_id:
            existing = task_sync_get(sync_id)
            if existing:
                task_sync_result_delete_by_sync_id(sync_id)
                task_sync_update(sync_id,
                    markdown_content=markdown_content,
                    platforms=json.dumps(platforms),
                    sync_from=sync_from,
                    url=url,
                    file_path=file_path,
                    status="syncing",
                )

    # —— 保存/更新到 task_sync ——
    if sync_from != "task" and sync_id and task_sync_get(sync_id):
        # local/url 且传了有效 sync_id：已通过 task_sync_update 更新，直接复用
        result_sync_id = sync_id
    else:
        # task 来源，或 local/url 无有效 sync_id：upsert
        result_sync_id = task_sync_upsert(
            task_id=task_id,
            markdown_content=markdown_content,
            platforms=json.dumps(platforms),
            sync_from=sync_from,
            url=url,
            file_path=file_path,
            status="syncing",
        )

    # —— 调用 wechatsync CLI ——
    from engine.multi_publish import sync_to_platforms

    try:
        result = sync_to_platforms(
            md_path=md_path,
            platforms=platforms,
            title=title,
            allow_unknown_platforms=True,
        )
        overall_status = _parse_and_insert_results(result, result_sync_id, platforms)
    except Exception as e:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.exception("同步执行异常 sync_from=%s task_id=%s sync_id=%s platforms=%s",
                          sync_from, task_id, sync_id, platforms)
        from engine.db.models import task_sync_result_insert
        for p in platforms:
            task_sync_result_insert(result_sync_id, p, status="failed", error_msg=f"同步异常: {e}")
        overall_status = "failed"

    # —— 更新状态 ——
    task_sync_update(result_sync_id, status=overall_status)

    return _get_sync_task_sync(result_sync_id)


# ============================================================
# 重试同步
# ============================================================

async def retry_sync(sync_id: int, platforms: Optional[list[str]] = None) -> dict:
    """重试同步：对失败的（或指定的）平台重新同步。"""
    return await asyncio.to_thread(_retry_sync_sync, sync_id, platforms)


def _retry_sync_sync(sync_id: int, platforms: Optional[list[str]] = None) -> dict:
    from engine.db.models import (
        task_sync_get, task_get, task_sync_update,
        task_sync_result_list_by_sync_id, task_sync_result_insert,
    )

    sync = task_sync_get(sync_id)
    if not sync:
        raise ValueError(f"同步记录 {sync_id} 不存在")

    sync_from = sync.get("sync_from", "task")
    sync_task_id = sync.get("task_id") or None

    # 1. 确定要重试的平台
    existing_results = task_sync_result_list_by_sync_id(sync_id)

    if platforms:
        retry_platforms = platforms
    else:
        retry_platforms = [
            r["platform"] for r in existing_results
            if r.get("status") == "failed"
        ]

    if not retry_platforms:
        raise ValueError("没有需要重试的平台（所有平台均已成功）")

    # 仅当已有结果时校验平台有效性
    if existing_results:
        valid_platforms = {r["platform"] for r in existing_results}
        invalid = [p for p in retry_platforms if p not in valid_platforms]
        if invalid:
            raise ValueError(f"以下平台不在本次同步记录中: {invalid}")

    # 2. 获取 markdown 内容：优先从 DB，回退到文件
    markdown_content = sync.get("markdown_content", "")
    if not markdown_content:
        raise ValueError("同步记录中无 markdown 内容，请重新创建同步")

    # 3. 删除要重试平台的旧结果
    import sqlite3
    from engine.db import get_connection
    conn = get_connection()
    placeholders = ",".join(["?" for _ in retry_platforms])
    conn.execute(
        f"DELETE FROM task_sync_result WHERE task_sync_id = ? AND platform IN ({placeholders})",
        [sync_id] + retry_platforms,
    )
    conn.commit()
    conn.close()

    # 4. 确定 md_path 和 title
    if sync_from == "task":
        # task 来源：通过任务获取路径
        if not sync_task_id:
            raise ValueError("task 来源时 task_id 不能为空")
        task = task_get(sync_task_id)
        if not task:
            raise ValueError(f"任务 {sync_task_id} 不存在")
        task_path = _resolve_task_path(task)
        from engine.config import get_brief_path
        md_path = get_brief_path(task_path)
        title = task.get("title", "") or task.get("topic", "")
    else:
        # local/url 来源：从 file_path 读取
        file_path = sync.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"文章文件不存在: {file_path}")
        md_path = file_path
        title = _extract_heading(markdown_content) if markdown_content else ""
        # 确保最新 markdown 内容写入文件
        if markdown_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)

    from engine.multi_publish import sync_to_platforms

    try:
        result = sync_to_platforms(
            md_path=md_path,
            platforms=retry_platforms,
            title=title,
            allow_unknown_platforms=True,
        )
        _parse_and_insert_results(result, sync_id, retry_platforms)
    except Exception as e:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.exception("重试同步异常 sync_id=%s platforms=%s", sync_id, retry_platforms)
        from engine.db.models import task_sync_result_insert
        for p in retry_platforms:
            task_sync_result_insert(sync_id, p, status="failed", error_msg=f"重试异常: {e}")

    # 5. 重新计算整体状态
    all_results = task_sync_result_list_by_sync_id(sync_id)
    all_success = all(r["status"] == "success" for r in all_results)
    any_success = any(r["status"] == "success" for r in all_results)

    if all_success:
        overall_status = "success"
    elif any_success:
        overall_status = "partial"
    else:
        overall_status = "failed"

    task_sync_update(sync_id, status=overall_status)

    return _get_sync_task_sync(sync_id)
