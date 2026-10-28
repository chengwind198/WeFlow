#!/usr/bin/env python3
"""
统一生图入口。

调用项目内置 Python 生图模块 image_gen_core，支持 7 个 provider：
  openai / gemini_proxy / z_image / krea_2_turbo /
  qwen_image / z_image_turbo_bailian / wan_image_bailian

配置写在 config.yaml → image_generation 段。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import time as _time

from engine.config import load_env
from engine.logger import get_logger

from engine.image_gen_core import (
    build_prompt,
    detect_provider,
    generate_image,
    get_default_model,
    normalize_output_path,
)

# DB 集成（可选，不传 --task-id 时静默跳过）
try:
    from engine.constants import Status, Stage, Operator, CallType, Role, TaskType
    from engine.db.models import image_insert, llm_log_insert, status_transition, task_ensure
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

logger = get_logger(__name__)


def _log_request_params(args: argparse.Namespace, provider: str, model: str) -> None:
    """调用生图接口前记录完整参数信息（含提示词）。"""
    params = []
    if args.prompt:
        preview = args.prompt[:200] + "…" if len(args.prompt) > 200 else args.prompt
        params.append(f"prompt={preview}")
    if args.promptfiles:
        params.append(f"promptfiles={args.promptfiles}")
    if args.ref:
        params.append(f"ref={args.ref}")
    params.append(f"image={args.image}")
    params.append(f"model={model}")
    if args.ar:
        params.append(f"ar={args.ar}")
    if args.size:
        params.append(f"size={args.size}")
    if args.quality:
        params.append(f"quality={args.quality}")
    if args.n:
        params.append(f"n={args.n}")

    logger.info("生图请求参数: %s (provider=%s)", " | ".join(params), provider)
    if args.prompt:
        logger.debug("生图完整提示词 (%d 字符):\n%s", len(args.prompt), args.prompt)


def _print_command(args: argparse.Namespace) -> None:
    """打印等效 CLI 命令（--print-command）。"""
    parts = ["python", "engine/image_gen_core.py"]
    if args.prompt:
        parts += ["--prompt", args.prompt]
    if args.promptfiles:
        parts += ["--promptfiles"] + args.promptfiles
    if args.image:
        parts += ["--image", args.image]
    if args.provider:
        parts += ["--provider", args.provider]
    if args.model:
        parts += ["--model", args.model]
    if args.ar:
        parts += ["--ar", args.ar]
    if args.size:
        parts += ["--size", args.size]
    if args.quality:
        parts += ["--quality", args.quality]
    if args.ref:
        parts += ["--ref"] + args.ref
    if args.n:
        parts += ["--n", str(args.n)]
    if args.json:
        parts.append("--json")
    print(" ".join(parts))


def execute_generation(args: argparse.Namespace) -> int:
    """执行生图。"""
    load_env()

    if args.print_command:
        _print_command(args)
        return 0

    prompt = build_prompt(args.prompt, args.promptfiles)
    provider = detect_provider(args.provider)
    model = args.model or get_default_model(provider)
    output_path = normalize_output_path(args.image)

    _log_request_params(args, provider, model)

    # 重试逻辑（最多 2 次）
    image: Optional[bytes] = None
    last_error: Optional[Exception] = None
    t_start = _time.time()
    retry = 0
    for attempt in range(2):
        retry = attempt
        try:
            image = generate_image(
                provider=provider, model=model, prompt=prompt,
                size=args.size, aspect_ratio=args.ar,
                quality=args.quality or "normal",
                reference_images=args.ref,
                n=args.n or 1,
            )
            break
        except Exception as e:
            last_error = e
            logger.error("[生图失败] 第 %d 次尝试出错 (provider=%s, model=%s): %s",
                         attempt + 1, provider, model, e)
            if attempt == 0:
                logger.warning("将重试第 2 次…")

    duration_ms = int((_time.time() - t_start) * 1000)

    # ── 记录 LLM 调用日志 ──
    if _DB_AVAILABLE:
        llm_status = "success" if image else "failed"
        llm_error = "" if image else str(last_error)
        try:
            llm_log_insert(
                task_id=getattr(args, 'task_id', 0) or 0,
                call_type=CallType.IMAGE,
                stage=Stage.GENERATE,
                provider=provider, model=model,
                prompt=prompt, prompt_chars=len(prompt),
                image_count=args.n or 1, image_size=args.size or "",
                duration_ms=duration_ms,
                status=llm_status, finish_msg=llm_error,
                retry_count=retry,
            )
        except Exception as e:
            logger.warning("DB 写入 llm_call_log 失败: %s", e)

    if image is None:
        logger.error("[致命错误] 生图流程异常终止")
        raise last_error or RuntimeError("生图失败（未知原因）")

    # 写文件
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)

    if args.json:
        print(json.dumps({
            "savedImage": output_path,
            "provider": provider,
            "model": model,
            "promptPreview": prompt[:160],
        }, ensure_ascii=False, indent=2))
    else:
        print(output_path)

    # 尝试读取图片尺寸
    try:
        from engine.utils import get_png_dimensions
        w, h = get_png_dimensions(image)
    except Exception as e:
        logger.debug("[生图] 解析图片尺寸失败: %s", e)
        w, h = 0, 0

    # ── 记录生图到 DB ──
    if _DB_AVAILABLE:
        task_id = getattr(args, 'task_id', 0) or 0
        slug = getattr(args, 'slug', '') or ''
        seq = getattr(args, 'seq', 1) or 1
        # 如果提供了 slug 但没 task_id，自动确保任务存在
        if not task_id and slug:
            try:
                task_id = task_ensure(slug=slug, account=args.account or 'main',
                                      task_type=TaskType.NEWS)
                logger.debug('DB: 自动创建/查找 task_id=%d (slug=%s)', task_id, slug)
            except Exception as e:
                logger.warning('DB: task_ensure 失败: %s', e)
        if task_id > 0:
            try:
                # 获取 draft 阶段 assistant 消息 id（如有）
                draft_msg_id = 0
                try:
                    from engine.db.models import task_message_get_last_assistant
                    draft_msg_id = task_message_get_last_assistant(task_id, Stage.DRAFT)
                except Exception as e:
                    logger.debug("[生图] 获取 draft assistant message_id 失败: %s", e)

                img_id = image_insert(
                    task_id=task_id, message_id=draft_msg_id, seq=seq,
                    prompt=prompt, provider=provider, model=model,
                    size=args.size or "", local_path=Path(output_path).name,
                    local_size=len(image), width=w, height=h, fmt="png",
                )
                logger.debug("DB: task_image 写入成功 (task=%d, seq=%d)", task_id, seq)
                # 记录文生图对话到 task_message
                if img_id:
                    try:
                        from engine.db.models import task_message_append
                        task_message_append(
                            task_id=task_id, stage=Stage.GENERATE,
                            provider=provider, model=model,
                            role=Role.USER, message=prompt, image_id=img_id,
                        )
                        task_message_append(
                            task_id=task_id, stage=Stage.GENERATE,
                            provider=provider, model=model,
                            role=Role.ASSISTANT,
                            message=f"图片已生成: {output_path} ({w}x{h}, {len(image)}字节)",
                            image_id=img_id,
                        )
                    except Exception as e:
                        logger.warning("[生图] 写入 task_message 失败: task=%d img_id=%d: %s",
                                       task_id, img_id, e)
                # 首张图片 → 自动推进到 images_generated (60)
                if seq == 1:
                    status_transition(task_id, 60,
                        to_info=f"首张配图: {output_path} ({provider}, {w}x{h})",
                        operator=Operator.GENERATE_IMAGE)
            except Exception as e:
                logger.warning("DB 写入 task_image 失败: %s", e)

    if w and h:
        logger.info("生图完成 → %s (provider=%s, %dx%d, %.1fMB)", output_path, provider, w, h, len(image) / 1048576)
    else:
        logger.info("生图完成 → %s (provider=%s, %.1fMB)", output_path, provider, len(image) / 1048576)
    return 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一生图入口")
    parser.add_argument("--account", help="用于读取 config.yaml 中的 provider 配置")
    parser.add_argument("-p", "--prompt")
    parser.add_argument("--promptfiles", nargs="+")
    parser.add_argument("--image", required=True)
    parser.add_argument("-m", "--model")
    parser.add_argument("--ref", nargs="+")
    parser.add_argument("--provider")
    parser.add_argument("--ar")
    parser.add_argument("--size")
    parser.add_argument("--quality")
    parser.add_argument("--n", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--task-id", type=int, default=0, help="关联任务 ID（用于 DB 记录）")
    parser.add_argument("--slug", default="", help="任务 slug（无 task-id 时自动创建或查找任务）")
    parser.add_argument("--seq", type=int, default=1, help="图片序号（用于 DB 记录）")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    return execute_generation(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
