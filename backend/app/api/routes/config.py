"""配置管理路由 —— 读取/更新 config.yaml。"""

import os
import copy
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from app.schemas.common import ApiResponse

router = APIRouter(prefix="/config", tags=["配置管理"])

# ============================================================
# 路径 & 敏感字段
# ============================================================

# config.yaml 位于项目根目录
from engine.config import get_project_root
_CONFIG_PATH = Path(get_project_root()) / "config.yaml"

# 需要脱敏的字段路径（以元组表示的嵌套 key 路径）
_SECRET_PATHS = [
    # accounts.<name>.app_secret
    # llm_providers.providers.<name>.api_key
    # image_generation.<provider>.api_key
    # integrations.wechatsync_mcp_token
]

_MASK_DISPLAY = "****"
_MASK_MIN_LEN = 8  # 短于此长度的密钥全掩


def _mask_value(value: str) -> str:
    """对密钥进行部分脱敏：保留前4后4位，中间用 ****。"""
    if not value or not isinstance(value, str):
        return value
    if len(value) <= _MASK_MIN_LEN:
        return _MASK_DISPLAY
    return value[:4] + _MASK_DISPLAY + value[-4:]


def _deep_mask(data: dict, parent_keys: tuple = ()) -> dict:
    """递归遍历 dict，对敏感字段脱敏。

    识别规则：
      - key 为 app_secret / api_key / wechatsync_mcp_token → 脱敏
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        current_path = parent_keys + (k,)
        if k in ("app_secret", "api_key", "wechatsync_mcp_token") and isinstance(v, str) and v:
            result[k] = _mask_value(v)
        elif isinstance(v, dict):
            result[k] = _deep_mask(v, current_path)
        else:
            result[k] = v
    return result


def _restore_masked(merged: dict, original: dict) -> None:
    """递归扫描 merged，将脱敏占位符替换为 original 中的真实值。"""
    for k, v in merged.items():
        if isinstance(v, str) and _MASK_DISPLAY in v:
            orig_val = original.get(k)
            if orig_val is not None and not (isinstance(orig_val, str) and _MASK_DISPLAY in orig_val):
                merged[k] = orig_val
        elif isinstance(v, dict) and isinstance(original.get(k), dict):
            _restore_masked(v, original[k])


def _deep_merge(base: dict, update: dict) -> dict:
    """深度合并：update 中的值覆盖 base，密钥占位符保留原值。"""
    result = copy.deepcopy(base)
    for k, v in update.items():
        if k not in result:
            result[k] = v
        elif isinstance(v, dict) and isinstance(result[k], dict):
            result[k] = _deep_merge(result[k], v)
        elif isinstance(v, str) and _MASK_DISPLAY in v:
            # 用户未修改密钥（值中包含 **** 占位符），保留原值
            continue
        else:
            result[k] = v
    return result


def _is_masked_placeholder(value: str) -> bool:
    """判断字符串是否为脱敏占位符。"""
    return isinstance(value, str) and _MASK_DISPLAY in value


class _CleanDumper(yaml.Dumper):
    """自定义 Dumper：None 和空字符串均输出为空值（key: 而非 key: null 或 key: ''）。"""


def _represent_none(dumper, _data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


def _represent_str(dumper, data):
    if data == "":
        return dumper.represent_scalar("tag:yaml.org,2002:null", "")
    return dumper.represent_str(data)


_CleanDumper.add_representer(type(None), _represent_none)
_CleanDumper.add_representer(str, _represent_str)


def _dump_yaml_clean(data: dict, stream) -> None:
    """写出 YAML：None 和空字符串均输出为空值（theme: 而非 theme: null 或 theme: ''）。"""
    yaml.dump(
        data,
        stream,
        Dumper=_CleanDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )


# ============================================================
# API 端点
# ============================================================


def _none_to_empty(data):
    """递归将 dict/list 中的 None 转为空字符串 ""。"""
    if isinstance(data, dict):
        return {k: _none_to_empty(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_none_to_empty(v) for v in data]
    return "" if data is None else data


@router.get("", response_model=ApiResponse)
async def get_config():
    """读取 config.yaml 完整内容（敏感字段脱敏）。"""
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config.yaml 不存在，请参考 config.yaml.example 创建")

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=500, detail=f"config.yaml 解析失败: {e}")

    if not isinstance(raw, dict):
        raw = {}

    # YAML 空值 → None，转为 "" 避免前端收到 null
    raw = _none_to_empty(raw)
    # 不再脱敏：前端 SecretField 使用 type="password" 原生隐藏，
    # 用户点击眼睛图标时切换 type="text" 即可查看完整明文
    return ApiResponse(data=raw)


@router.put("", response_model=ApiResponse)
async def update_config(config: dict):
    """保存配置到 config.yaml。

    规则：
      - 前端提交的 dict 深度合并到现有配置
      - 密钥字段值为 "****" 占位符时保留原值（用户未修改）
      - 回写 yaml，保留基本结构
    """
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config.yaml 不存在")

    # 读取现有配置
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=500, detail=f"config.yaml 解析失败: {e}")

    if not isinstance(current, dict):
        current = {}

    # 前端可能发 null，统一转为 "" 再合并
    config = _none_to_empty(config)

    # 深度合并
    merged = _deep_merge(current, config)

    # 安全兜底：merged 中任何脱敏占位符，回退到 current 中的真实值
    _restore_masked(merged, current)

    # 清理被删除的条目：merge 只会新增/更新，不会删除。
    # 前端提交时已移除的 key 应在 merged 中同步移除。
    for section in ("accounts",):
        if section in config and section in merged:
            merged[section] = {
                k: v for k, v in merged[section].items()
                if k in config[section]
            }
    if "llm_providers" in config and "llm_providers" in merged:
        if "providers" in config["llm_providers"] and "providers" in merged["llm_providers"]:
            merged["llm_providers"]["providers"] = {
                k: v for k, v in merged["llm_providers"]["providers"].items()
                if k in config["llm_providers"]["providers"]
            }
    if "image_generation" in config and "image_generation" in merged:
        # image_generation 混合了 provider(标量) 和各 provider 配置(字典)，
        # 仅清理字典类型的 provider 条目
        merged_img = merged["image_generation"]
        config_img = config["image_generation"]
        for k in list(merged_img.keys()):
            if isinstance(merged_img[k], dict) and k not in config_img:
                del merged_img[k]

    # 写回（空字符串不输出引号，None 不输出 null）
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("# weflow 统一配置\n")
            f.write("# 由配置管理页面自动生成，请谨慎手动编辑。\n\n")
            _dump_yaml_clean(merged, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入 config.yaml 失败: {e}")

    # 返回脱敏后的结果
    masked = _deep_mask(merged)
    return ApiResponse(data=masked, message="配置已保存")


@router.get("/constants", response_model=ApiResponse)
async def get_config_constants():
    """返回前端下拉框所需的常量元数据。

    从 engine.constants 中读取 Theme、ImageStyle、ArticleStructure、
    OpeningHook、Platform、Provider 等类的元信息。
    """
    try:
        from engine.constants import (
            Theme, ImageStyle, ArticleStructure, OpeningHook,
            Platform, Provider, Genre,
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"导入 engine.constants 失败: {e}")

    # 主题
    themes = []
    for code in Theme.all_codes():
        themes.append({
            "code": code,
            "label": Theme.label(code),
            "description": Theme.description(code),
        })

    # 配图风格
    image_styles = []
    for code in ImageStyle.all_codes():
        image_styles.append({
            "code": code,
            "label": ImageStyle.label(code),
            "keywords": ImageStyle.keywords(code),
            "topics": ImageStyle.topics(code),
            "density": ImageStyle.density(code),
            "for_news": code in ImageStyle.for_news(),
            "for_newspic": code in ImageStyle.for_newspic(),
        })

    # 文章结构
    article_structures = []
    for code in ArticleStructure.all_codes():
        article_structures.append({
            "code": code,
            "label": ArticleStructure.label(code),
            "topics": ArticleStructure.topics(code),
            "flow": ArticleStructure.flow(code),
        })

    # 开篇钩子
    opening_hooks = []
    for code in OpeningHook.all_codes():
        opening_hooks.append({
            "code": code,
            "label": OpeningHook.label(code),
            "tip": OpeningHook.tip(code),
            "avoid": OpeningHook.avoid(code),
        })

    # 文章体裁
    genres = []
    for code in Genre.all_codes():
        genres.append({
            "code": code,
            "label": Genre.label(code),
            "purpose": Genre.purpose(code),
            "features": Genre.features(code),
        })

    # 同步平台（使用 SyncPlatform 常量）
    try:
        from engine.constants import SyncPlatform
        platforms = [
            {"code": p, "label": SyncPlatform.label(p)}
            for p in SyncPlatform.all_codes()
        ]
    except ImportError:
        platforms = [
            {"code": p, "label": _platform_label(p)}
            for p in Platform.ALL
        ]

    # LLM providers
    llm_providers = [
        {"code": p, "label": _provider_label(p)}
        for p in Provider.LLM_PROVIDERS
    ]

    # 图片 providers
    image_providers = [
        {"code": p, "label": _provider_label(p)}
        for p in Provider.IMAGE_PROVIDERS
    ]

    return ApiResponse(data={
        "themes": themes,
        "image_styles": image_styles,
        "article_structures": article_structures,
        "opening_hooks": opening_hooks,
        "genres": genres,
        "platforms": platforms,
        "llm_providers": llm_providers,
        "image_providers": image_providers,
    })


def _platform_label(code: str) -> str:
    """平台代码 → 中文标签（使用 SyncPlatform 常量）。"""
    try:
        from engine.constants import SyncPlatform
        return SyncPlatform.label(code)
    except ImportError:
        pass
    labels = {
        "wechat": "微信公众号",
        "zhihu": "知乎",
        "juejin": "掘金",
        "csdn": "CSDN",
        "toutiao": "头条",
    }
    return labels.get(code, code)


def _provider_label(code: str) -> str:
    """Provider 代码 → 显示名。"""
    labels = {
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "zhipu": "智谱 GLM",
        "doubao": "豆包 (字节)",
        "minimax": "MiniMax",
        "qwen_image": "通义万相 Qwen-Image",
        "z_image": "Z-Image-Turbo",
        "krea_2_turbo": "Krea 2 Turbo",
        "gemini_proxy": "Gemini Proxy",
        "z_image_turbo_bailian": "Z-Image-Turbo (百炼)",
        "wan_image_bailian": "Wan2.7-Image (百炼)",
    }
    return labels.get(code, code)
