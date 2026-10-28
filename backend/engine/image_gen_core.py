#!/usr/bin/env python3
"""
生图核心逻辑（Python 版，替代 baoyu_image_gen.ts / baoyu_image_gen_core.ts）。

支持的 provider: openai / gemini_proxy / z_image / krea_2_turbo /
                 qwen_image / z_image_turbo_bailian / wan_image_bailian
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from engine.config import load_env
from engine.constants import LLMDefaults
from engine.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 类型定义
# ============================================================

VALID_PROVIDERS = {
    "openai", "gemini_proxy", "z_image", "krea_2_turbo",
    "qwen_image", "z_image_turbo_bailian", "wan_image_bailian",
}

# 平台 → provider 映射（优先按平台路由，再兜底 provider）
PLATFORM_MAP: Dict[str, List[str]] = {
    "dashscope":   ["qwen_image", "z_image_turbo_bailian", "wan_image_bailian"],
    "modelscope":  ["z_image", "krea_2_turbo"],
    "gemini_proxy": ["gemini_proxy"],
    "openai":      ["openai"],
}

# provider → 平台 反向映射
_PROVIDER_TO_PLATFORM: Dict[str, str] = {}
for _plat, _providers in PLATFORM_MAP.items():
    for _p in _providers:
        _PROVIDER_TO_PLATFORM[_p] = _plat

# 各 provider 的 API Key 环境变量名（用于自动检测优先级）
_PROVIDER_KEY_ENV = [
    "KREA_2_TURBO_API_KEY",
    "Z_IMAGE_API_KEY",
    "QWEN_IMAGE_API_KEY",
    "Z_IMAGE_TURBO_BAILIAN_API_KEY",
    "WAN_IMAGE_BAILIAN_API_KEY",
    "GEMINI_PROXY_API_KEY",
    "OPENAI_API_KEY",
]

_PROVIDER_BY_KEY = {
    "KREA_2_TURBO_API_KEY": "krea_2_turbo",
    "Z_IMAGE_API_KEY": "z_image",
    "QWEN_IMAGE_API_KEY": "qwen_image",
    "Z_IMAGE_TURBO_BAILIAN_API_KEY": "z_image_turbo_bailian",
    "WAN_IMAGE_BAILIAN_API_KEY": "wan_image_bailian",
    "GEMINI_PROXY_API_KEY": "gemini_proxy",
    "OPENAI_API_KEY": "openai",
}

def get_platform_for_provider(provider: str) -> str:
    """根据 provider 返回所属平台标识，未知返回空字符串。"""
    return _PROVIDER_TO_PLATFORM.get(provider, "")


# ============================================================
# Provider 检测 / 模型默认值
# ============================================================

def detect_provider(cli_provider: Optional[str] = None) -> str:
    """按优先级确定生图 provider: CLI > WECHAT_PUBLISHER_IMAGE_PROVIDER > API Key 自动检测。"""
    # 1. CLI --provider 参数
    if cli_provider:
        _validate_provider(cli_provider)
        return cli_provider

    # 2. config.yaml 显式指定
    env_provider = os.environ.get("WECHAT_PUBLISHER_IMAGE_PROVIDER", "").strip()
    if env_provider:
        _validate_provider(env_provider)
        return env_provider

    # 3. 按 api_key 自动检测
    for key_env in _PROVIDER_KEY_ENV:
        if os.environ.get(key_env):
            return _PROVIDER_BY_KEY[key_env]

    raise RuntimeError(
        "未找到任何已配置的 image provider。请在 config.yaml 中设置 provider 或配置 API Key。"
    )


def _validate_provider(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"无效的 provider: '{provider}'，可用值: {', '.join(sorted(VALID_PROVIDERS))}"
        )


def get_default_model(provider: str) -> str:
    """返回各 provider 的默认模型 ID。"""
    defaults = {
        "qwen_image": ("QWEN_IMAGE_MODEL", "qwen-image-2.0-pro"),
        "z_image_turbo_bailian": ("Z_IMAGE_TURBO_BAILIAN_MODEL", "z-image-turbo"),
        "wan_image_bailian": ("WAN_IMAGE_BAILIAN_MODEL", "wan2.7-image-pro"),
        "krea_2_turbo": ("KREA_2_TURBO_MODEL", "krea/Krea-2-Turbo"),
        "z_image": ("Z_IMAGE_MODEL", "Tongyi-MAI/Z-Image-Turbo"),
        "gemini_proxy": ("GEMINI_PROXY_IMAGE_MODEL", "gemini-2.5-flash"),
        "openai": ("OPENAI_IMAGE_MODEL", "gpt-image-1"),
    }
    env_key, fallback = defaults.get(provider, ("OPENAI_IMAGE_MODEL", "gpt-image-1"))
    return os.environ.get(env_key) or fallback


# ============================================================
# Prompt 构建
# ============================================================

def build_prompt(
    cli_prompt: Optional[str] = None,
    prompt_files: Optional[List[str]] = None,
) -> str:
    """从 CLI --prompt / --promptfiles / stdin 拼接提示词。"""
    if cli_prompt:
        return cli_prompt

    if prompt_files:
        parts = []
        for f in prompt_files:
            parts.append(Path(f).read_text(encoding="utf-8"))
        return "\n\n".join(parts).strip()

    # 尝试从 stdin 读取
    if not sys.stdin.isatty():
        try:
            stdin_text = sys.stdin.read()
            if stdin_text.strip():
                return stdin_text.strip()
        except Exception as e:
            logger.debug("从 stdin 读取提示词失败: %s", e)

    raise ValueError("提示词为空（--prompt / --promptfiles / stdin 均未提供）")


# ============================================================
# 输出路径处理
# ============================================================

def normalize_output_path(file_path: str) -> str:
    """确保输出路径有 .png 后缀。"""
    full = str(Path(file_path).resolve())
    return full if Path(full).suffix else f"{full}.png"


# ============================================================
# 工具函数
# ============================================================

def _build_headers(api_key: Optional[str] = None,
                   extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """构建统一请求头，默认 Content-Type 显式声明 UTF-8 编码。"""
    headers: Dict[str, str] = {
        "Content-Type": "application/json; charset=utf-8",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra:
        headers.update(extra)
    return headers


def _apply_prompt_hints(prompt: str, aspect_ratio: Optional[str] = None,
                        quality: str = "normal", size: Optional[str] = None) -> str:
    result = prompt.strip()
    if aspect_ratio:
        result += f"\nAspect ratio: {aspect_ratio}."
    if quality == "2k":
        result += "\nHigh resolution target: 2048px."
    if size:
        result += f"\nTarget size: {size}."
    return result


def _get_openai_size(aspect_ratio: Optional[str], quality: str) -> str:
    base = 2048 if quality == "2k" else 1024
    if not aspect_ratio:
        return f"{base}x{base}"
    if aspect_ratio == "16:9":
        return "2048x1024" if quality == "2k" else "1792x1024"
    if aspect_ratio == "9:16":
        return "1024x2048" if quality == "2k" else "1024x1792"
    return f"{base}x{base}"


def _read_image_as_data_url(file_path: str) -> str:
    """将图片文件读取为 data: URL 格式（供 Gemini Proxy 传参考图）。"""
    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif",
    }
    mime = mime_map.get(ext, "image/png")
    data = Path(file_path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _normalize_gemini_base_url(raw: Optional[str]) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    url = raw.strip().rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


# ============================================================
# 图片提取（从 API 响应中递归搜索 image URL / base64）
# ============================================================

def _extract_image_bytes(payload: Any, model: str = "") -> bytes:
    """从 API 响应 JSON 中提取图片二进制数据。优先级：base64 > URL。"""
    # 先尝试 base64 内联图片
    inline = _extract_inline_image(payload)
    if inline:
        return inline

    # 再尝试 URL
    url = _extract_image_url(payload)
    if url:
        return _download_image(url, model)

    preview = json.dumps(payload, ensure_ascii=False)[:500]
    logger.error("[%s] 无法从 API 响应中提取图片数据，响应预览: %s", model, preview)
    raise RuntimeError("Cannot extract image data from response.")


def _extract_inline_image(payload: Any) -> Optional[bytes]:
    data_url = _find_string(payload, lambda v: v.startswith("data:image/"))
    base64_value = data_url or _find_string(payload, _is_likely_image_base64)
    if not base64_value:
        return None
    raw = base64_value.split(",", 1)[1] if base64_value.startswith("data:image/") else base64_value
    return base64.b64decode(raw)


def _extract_image_url(payload: Any) -> Optional[str]:
    return _find_string(payload, lambda v: (
        v.startswith("https://") and
        any(ext in v for ext in (".png", ".jpg", ".jpeg", ".webp", "image"))
    ))


def _find_string(value: Any, match) -> Optional[str]:
    """递归遍历 JSON 对象树，返回第一个匹配的字符串。"""
    if isinstance(value, str):
        return value if match(value) else None
    if isinstance(value, list):
        for item in value:
            found = _find_string(item, match)
            if found:
                return found
        return None
    if isinstance(value, dict):
        for child in value.values():
            found = _find_string(child, match)
            if found:
                return found
    return None


def _is_likely_image_base64(value: str) -> bool:
    """启发式判断字符串是否可能是图片 base64 编码。"""
    if len(value) < 256:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", value):
        return False
    try:
        prefix = base64.b64decode(value[:64])
        # PNG magic
        if prefix[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        # JPEG magic
        if prefix[:3] == b"\xff\xd8\xff":
            return True
        # WebP/RIFF magic
        if prefix[:4] == b"RIFF":
            return True
    except Exception as e:
        logger.debug("检测 WebP 格式时读取文件失败 (%s): %s", path, e)
    return False


def _download_image(url: str, model: str = "") -> bytes:
    """从 URL 下载图片二进制数据。"""
    resp = requests.get(url, timeout=60)
    if not resp.ok:
        logger.error("[%s] 图片下载失败 (status=%d, url=%s…)", model, resp.status_code, url[:120])
        raise RuntimeError(f"Failed to download image from {url}")
    return resp.content


# ============================================================
# Provider 1: OpenAI Images API
# ============================================================

def _generate_openai(prompt: str, model: str, size: Optional[str] = None,
                     aspect_ratio: Optional[str] = None, quality: str = "normal",
                     n: int = 1) -> bytes:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置")

    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": model,
        "prompt": prompt,
        "size": size or _get_openai_size(aspect_ratio, quality),
        "n": n,
    }

    resp = requests.post(f"{base_url}/images/generations", json=body, timeout=LLMDefaults.TIMEOUT_SEC,
                         headers=_build_headers(api_key))

    if not resp.ok:
        logger.error("[OpenAI] API 请求失败 (status=%d, model=%s): %s", resp.status_code, model, resp.text[:500])
        raise RuntimeError(f"OpenAI image API error: {resp.text[:500]}")

    return _extract_image_bytes(resp.json(), model)


# ============================================================
# Provider 2: Gemini Proxy（OpenAI 兼容端点）
# ============================================================

def _generate_gemini_proxy(prompt: str, model: str, reference_images: Optional[List[str]] = None,
                           size: Optional[str] = None, aspect_ratio: Optional[str] = None,
                           quality: str = "normal") -> bytes:
    base_url = _normalize_gemini_base_url(os.environ.get("GEMINI_PROXY_BASE_URL"))
    api_key = os.environ.get("GEMINI_PROXY_API_KEY")
    if not base_url:
        raise RuntimeError("GEMINI_PROXY_BASE_URL 未配置")
    if not api_key:
        raise RuntimeError("GEMINI_PROXY_API_KEY 未配置")

    content: List[Dict[str, Any]] = []
    for ref_path in (reference_images or []):
        data_url = _read_image_as_data_url(ref_path)
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    gemini_prompt = (
        "Generate exactly one image.\n"
        "Return image data directly if the proxy supports it.\n"
        "Preferred response order: base64 image, image URL, then nothing else.\n"
        + prompt
    )
    content.append({"type": "text", "text": gemini_prompt})

    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }

    resp = requests.post(f"{base_url}/chat/completions", json=body, timeout=LLMDefaults.TIMEOUT_SEC,
                         headers=_build_headers(api_key))

    if not resp.ok:
        logger.error("[Gemini-Proxy] API 请求失败 (status=%d, model=%s): %s", resp.status_code, model, resp.text[:500])
        raise RuntimeError(f"Gemini proxy API error: {resp.text[:500]}")

    return _extract_image_bytes(resp.json(), model)


# ============================================================
# Provider 3 & 4: ModelScope 异步任务（z_image / krea_2_turbo）
# ============================================================

def _get_modelscope_env(provider: str) -> Tuple[str, str]:
    """返回 (base_url, api_key)。"""
    if provider == "krea_2_turbo":
        api_key = os.environ.get("KREA_2_TURBO_API_KEY")
        if not api_key:
            raise RuntimeError("KREA_2_TURBO_API_KEY 未配置")
        base_url = (os.environ.get("KREA_2_TURBO_BASE_URL") or "https://api-inference.modelscope.cn/").rstrip("/")
    else:  # z_image
        api_key = os.environ.get("Z_IMAGE_API_KEY")
        if not api_key:
            raise RuntimeError("Z_IMAGE_API_KEY 未配置")
        base_url = (os.environ.get("Z_IMAGE_BASE_URL") or "https://api-inference.modelscope.cn/").rstrip("/")
    return base_url, api_key


def _generate_modelscope_async(provider: str, prompt: str, model: str) -> bytes:
    base_url, api_key = _get_modelscope_env(provider)

    # ModelScope API 提示词上限 2000 字符，超长截断
    MAX_PROMPT_LEN = 2000
    if len(prompt) > MAX_PROMPT_LEN:
        cut = prompt.rfind(" ", 0, MAX_PROMPT_LEN)
        prompt = prompt[:cut if cut > 0 else MAX_PROMPT_LEN]
        logger.warning("[%s] prompt 超过 %d 字符，已截断至 %d 字符",
                       provider, MAX_PROMPT_LEN, len(prompt))

    body = {"model": model, "prompt": prompt}
    headers = _build_headers(api_key, {"X-ModelScope-Async-Mode": "true"})

    # Step 1: 创建异步任务
    create_resp = requests.post(f"{base_url}/v1/images/generations", json=body, headers=headers, timeout=60)
    if not create_resp.ok:
        logger.error("[%s] 创建异步任务失败 (status=%d): %s", provider, create_resp.status_code, create_resp.text[:500])
        raise RuntimeError(f"ModelScope create task error ({create_resp.status_code}): {create_resp.text[:500]}")

    create_data = create_resp.json()
    task_id = create_data.get("task_id")
    if not task_id:
        logger.error("[%s] 响应中缺少 task_id: %s", provider, json.dumps(create_data, ensure_ascii=False)[:500])
        raise RuntimeError(f"{provider} did not return a task_id")

    logger.info("[%s] 异步任务已创建: task_id=%s", provider, task_id)

    # Step 2: 轮询结果
    max_wait_s = 300  # 5 分钟
    poll_interval_s = 5
    start = time.time()

    while time.time() - start < max_wait_s:
        time.sleep(poll_interval_s)
        poll_headers = _build_headers(api_key, {"X-ModelScope-Task-Type": "image_generation"})
        poll_resp = requests.get(f"{base_url}/v1/tasks/{task_id}", headers=poll_headers, timeout=30)
        if not poll_resp.ok:
            logger.error("[%s] 轮询失败 (taskId=%s, status=%d): %s", provider, task_id, poll_resp.status_code, poll_resp.text[:500])
            raise RuntimeError(f"ModelScope poll error ({poll_resp.status_code}): {poll_resp.text[:500]}")

        data = poll_resp.json()
        status = data.get("task_status", "")

        if status == "SUCCEED":
            images = data.get("output_images") or []
            if not images:
                logger.error("[%s] 任务标记为 SUCCEED 但无 output_images (taskId=%s)", provider, task_id)
                raise RuntimeError("ModelScope returned SUCCEED but no output_images")
            return _download_image(images[0], model)

        if status == "FAILED":
            logger.error("[%s] 任务失败 (taskId=%s): %s", provider, task_id, json.dumps(data, ensure_ascii=False)[:500])
            raise RuntimeError("ModelScope generation failed")

        logger.debug("[%s] 轮询中… taskId=%s status=%s 已等待 %.0fs", provider, task_id, status, time.time() - start)

    logger.error("[%s] 任务超时 (taskId=%s, 已等待 %ds)", provider, task_id, max_wait_s)
    raise RuntimeError(f"ModelScope task {task_id} timed out after {max_wait_s}s")


# ============================================================
# Provider 5/6/7: 阿里云百炼 DashScope（qwen_image / z_image_turbo_bailian / wan_image_bailian）
# ============================================================

def _generate_dashscope(provider: str, prompt: str, model: str,
                        size: Optional[str] = None, n: int = 1) -> bytes:
    cfg = _DASHSCOPE_CONFIGS.get(provider, {})

    api_key_env = cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} 未配置")

    base_url_env = cfg.get("base_url_env", "")
    raw_base = os.environ.get(base_url_env) or "https://dashscope.aliyuncs.com/api/v1"
    base_url = raw_base.rstrip("/")

    size_env = cfg.get("size_env", "")
    resolved_size = os.environ.get(size_env) or size or cfg.get("default_size", "2048*2048")

    parameters: Dict[str, Any] = {
        "result_format": "message",
        "prompt_extend": cfg.get("prompt_extend", True),
        "size": resolved_size,
    }
    watermark = cfg.get("watermark")
    if watermark is not None:
        parameters["watermark"] = watermark
    if cfg.get("thinking_mode"):
        parameters["thinking_mode"] = True
    if n > 1:
        parameters["n"] = n
    negative_prompt_env = cfg.get("negative_prompt_env", "")
    if negative_prompt_env:
        neg = os.environ.get(negative_prompt_env) or cfg.get("default_negative_prompt", "")
        if neg:
            parameters["negative_prompt"] = neg

    body = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": [{"text": prompt}]}]
        },
        "parameters": parameters,
    }

    endpoint = f"{base_url}/services/aigc/multimodal-generation/generation"
    resp = requests.post(endpoint, json=body, timeout=LLMDefaults.TIMEOUT_SEC,
                         headers=_build_headers(api_key))

    if not resp.ok:
        logger.error("[%s] API 请求失败 (status=%d, size=%s): %s",
                     model, resp.status_code, resolved_size, resp.text[:500])
        raise RuntimeError(f"{model} API error ({resp.status_code}): {resp.text[:500]}")

    return _extract_image_bytes(resp.json(), model)


# DashScope 平台各 provider 配置
_DASHSCOPE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "qwen_image": {
        "api_key_env": "QWEN_IMAGE_API_KEY",
        "base_url_env": "QWEN_IMAGE_BASE_URL",
        "size_env": "QWEN_IMAGE_SIZE",
        "default_size": "2048*2048",
        "prompt_extend": True,
        "watermark": False,
        "negative_prompt_env": "QWEN_IMAGE_NEGATIVE_PROMPT",
        "default_negative_prompt": (
            "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，"
            "人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"
        ),
    },
    "z_image_turbo_bailian": {
        "api_key_env": "Z_IMAGE_TURBO_BAILIAN_API_KEY",
        "base_url_env": "Z_IMAGE_TURBO_BAILIAN_BASE_URL",
        "size_env": "Z_IMAGE_TURBO_BAILIAN_SIZE",
        "default_size": "1120*1440",
        "prompt_extend": False,
    },
    "wan_image_bailian": {
        "api_key_env": "WAN_IMAGE_BAILIAN_API_KEY",
        "base_url_env": "WAN_IMAGE_BAILIAN_BASE_URL",
        "size_env": "WAN_IMAGE_BAILIAN_SIZE",
        "default_size": "2K",
        "prompt_extend": False,
        "watermark": False,
        "thinking_mode": True,
    },
}


# ============================================================
# 统一生图入口
# ============================================================

def generate_image(provider: str, model: str, prompt: str,
                   size: Optional[str] = None, aspect_ratio: Optional[str] = None,
                   quality: str = "normal", reference_images: Optional[List[str]] = None,
                   n: int = 1, platform: Optional[str] = None) -> bytes:
    """
    统一生图入口。优先按 platform 路由，否则按 provider 路由。

    Args:
        provider: 生图提供商标识
        model: 模型 ID
        prompt: 提示词文本
        size: 显式尺寸（如 1024x1024）
        aspect_ratio: 宽高比（如 16:9）
        quality: 质量预设 (normal / 2k)
        reference_images: 参考图文件路径列表（仅 gemini_proxy 支持）
        n: 生成图片数量
        platform: 平台标识（dashscope / modelscope / gemini_proxy / openai），优先于 provider 路由

    Returns:
        图片二进制数据 (bytes)
    """
    # 统一应用 prompt 提示（宽高比、质量、尺寸），确保所有 provider 都生效
    enhanced_prompt = _apply_prompt_hints(prompt, aspect_ratio, quality, size)

    if platform :
        if platform == "modelscope":
            return _generate_modelscope_async(provider, enhanced_prompt, model)
        if platform == "dashscope":
            return _generate_dashscope(
                provider=provider, prompt=enhanced_prompt, model=model,
                size=size, n=n,
            )
        if platform == "gemini_proxy":
            return _generate_gemini_proxy(enhanced_prompt, model, reference_images, size, aspect_ratio, quality)

        if platform == "openai":
            return _generate_openai(enhanced_prompt, model, size, aspect_ratio, quality, n)

    # 兜底：未识别 platform，按 provider 字符串判断
    if provider in ("qwen_image", "z_image_turbo_bailian", "wan_image_bailian"):
        return _generate_dashscope(
            provider=provider, prompt=enhanced_prompt, model=model,
            size=size, n=n,
        )

    if provider in ("z_image", "krea_2_turbo"):
        return _generate_modelscope_async(provider, enhanced_prompt, model)

    if provider == "gemini_proxy":
        return _generate_gemini_proxy(enhanced_prompt, model, reference_images, size, aspect_ratio, quality)

    # 兜底: openai
    return _generate_openai(enhanced_prompt, model, size, aspect_ratio, quality, n)


# ============================================================
# CLI 入口（独立运行时，保持与旧 TS 行为的兼容性）
# ============================================================

def _cli_main():
    import argparse

    parser = argparse.ArgumentParser(description="统一生图入口（Python 版）")
    parser.add_argument("-p", "--prompt")
    parser.add_argument("--promptfiles", nargs="+")
    parser.add_argument("--image", required=True)
    parser.add_argument("--provider")
    parser.add_argument("-m", "--model")
    parser.add_argument("--ar")
    parser.add_argument("--size")
    parser.add_argument("--quality", default="normal")
    parser.add_argument("--ref", nargs="+")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # 加载环境
    load_env()

    # 确定 provider / model / prompt
    provider = detect_provider(args.provider)
    model = args.model or get_default_model(provider)
    prompt = build_prompt(args.prompt, args.promptfiles)
    output_path = normalize_output_path(args.image)

    logger.info("生图请求: provider=%s, model=%s, size=%s, n=%d, quality=%s",
                provider, model, args.size or "(auto)", args.n, args.quality)

    # 重试逻辑
    image: Optional[bytes] = None
    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            image = generate_image(
                provider=provider, model=model, prompt=prompt,
                size=args.size, aspect_ratio=args.ar, quality=args.quality,
                reference_images=args.ref, n=args.n,
            )
            break
        except Exception as e:
            last_error = e
            logger.error("[生图失败] 第 %d 次尝试出错 (provider=%s, model=%s): %s",
                         attempt + 1, provider, model, e)
            if attempt == 0:
                logger.warning("将重试第 2 次…")

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

    size_mb = len(image) / 1048576
    logger.info("生图完成 → %s (provider=%s, %.1fMB)", output_path, provider, size_mb)


if __name__ == "__main__":
    try:
        _cli_main()
    except Exception as e:
        logger.error("生图异常: %s", e)
        sys.exit(1)
