#!/usr/bin/env python3
"""
通用 LLM 客户端。
从 config.yaml → llm_providers 读取配置，支持 OpenAI 兼容 API（DeepSeek / 智谱 / 豆包 / MiniMax / OpenAI）。

用法:
    from engine.llm_client import LLMClient
    client = LLMClient()                         # 用 default provider
    client = LLMClient("deepseek")               # 指定 provider
    reply = client.chat("你好")                   # 单轮对话
    reply = client.chat([                         # 多轮（system + user）
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "你好"}
    ])
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Union

import requests

from engine.config import load_env
from engine.constants import CallType, LLMDefaults, Role
from engine.logger import get_logger

logger = get_logger(__name__)

# ── 环境变量名映射 ──
_PROVIDER_ENV_MAP = {
    "deepseek": ("LLM_DEEPSEEK_API_KEY", "LLM_DEEPSEEK_BASE_URL", "LLM_DEEPSEEK_MODEL"),
    "openai":   ("LLM_OPENAI_API_KEY",   "LLM_OPENAI_BASE_URL",   "LLM_OPENAI_MODEL"),
    "zhipu":    ("LLM_ZHIPU_API_KEY",    "LLM_ZHIPU_BASE_URL",    "LLM_ZHIPU_MODEL"),
    "doubao":   ("LLM_DOUBAO_API_KEY",   "LLM_DOUBAO_BASE_URL",   "LLM_DOUBAO_MODEL"),
    "minimax":  ("LLM_MINIMAX_API_KEY",  "LLM_MINIMAX_BASE_URL",  "LLM_MINIMAX_MODEL"),
}


class LLMClient:
    """OpenAI 兼容 LLM 客户端。"""

    def __init__(self, provider: Optional[str] = None, stage: str = ""):
        load_env()
        self.provider = provider or _resolve_default_provider()
        self.api_key, self.base_url, self.model = _load_provider_config(self.provider)
        self.stage = stage  # 当前 pipeline 阶段（用于 DB 记录）
        self.task_id = 0    # 关联任务 ID（外部设置）
        self.last_assistant_msg_id = 0  # 最近一次 chat() 写入的 assistant message id
        if not self.api_key:
            raise ValueError(
                f"LLM provider '{self.provider}' 的 API Key 未配置。"
                f"请在 config.yaml → llm_providers.{self.provider}.api_key 中填写。"
            )
        logger.info("LLM 客户端就绪: provider=%s model=%s base=%s stage=%s",
                     self.provider, self.model, self.base_url, self.stage or "-")

    def chat(
        self,
        messages: Union[str, List[Dict[str, str]]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """
        发送对话请求，返回模型回复文本。

        Args:
            messages: 单轮字符串或消息列表 [{"role":"system","content":"..."}, ...]
            temperature: 温度
            max_tokens: 最大输出 token
            json_mode: True 时要求模型返回 JSON（仅支持的模型生效）

        Returns:
            模型回复文本
        """
        if isinstance(messages, str):
            messages = [{"role": Role.USER, "content": messages}]

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.api_key}",
        }

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        t_start = time.time()

        resp = requests.post(endpoint, json=body, headers=headers, timeout=LLMDefaults.TIMEOUT_SEC)
        duration_ms = int((time.time() - t_start) * 1000)

        if not resp.ok:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:500]}"
            logger.error("[LLM] 请求失败 (status=%d, provider=%s): %s",
                         resp.status_code, self.provider, resp.text[:500])
            # 记录失败日志到 llm_call_log
            _try_log_llm_call(self.provider, self.model, messages, "",
                              0, 0, duration_ms, self.stage, self.task_id,
                              status="failed", finish_msg=error_msg)
            raise RuntimeError(f"LLM API error ({resp.status_code}): {resp.text[:500]}")

        data = resp.json()
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        finish_reason = _extract_finish_reason(data, self.provider)

        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.error("[LLM] 响应格式异常: %s", json.dumps(data, ensure_ascii=False)[:500])
            _try_log_llm_call(self.provider, self.model, messages, "",
                              tokens_in, tokens_out, duration_ms, self.stage, self.task_id,
                              finish_reason=finish_reason, status="failed",
                              finish_msg="响应格式异常: 缺少 choices[0].message.content")
            raise RuntimeError("LLM response missing choices[0].message.content")

        if not content or not content.strip():
            # 模型返回了空内容（可能是安全过滤、token 限制或模型内部错误）
            logger.error(
                "[LLM] 模型返回空内容: provider=%s model=%s finish_reason=%s tokens_in=%d tokens_out=%d",
                self.provider, self.model, finish_reason, tokens_in, tokens_out,
            )
            _try_log_llm_call(self.provider, self.model, messages, "",
                              tokens_in, tokens_out, duration_ms, self.stage, self.task_id,
                              finish_reason=finish_reason, status="failed",
                              finish_msg=f"空内容")
            raise RuntimeError(
                f"LLM 返回空内容 (provider={self.provider}, model={self.model}, "
                f"finish_reason={finish_reason})，可能被安全过滤或模型内部错误"
            )

        logger.info("[LLM] 调用完成: provider=%s model=%s tokens_in=%d tokens_out=%d "
                     "finish_reason=%s duration=%dms",
                     self.provider, self.model, tokens_in, tokens_out,
                     finish_reason, duration_ms)

        # 记录成功日志到 llm_call_log
        _try_log_llm_call(self.provider, self.model, messages, content,
                          tokens_in, tokens_out, duration_ms, self.stage, self.task_id,
                          finish_reason=finish_reason)

        # 记录对话到 task_message（首次写入允许所有 role，后续仅允许 user/tool）
        self.last_assistant_msg_id = _try_log_task_message(
            self.task_id, self.stage, self.provider, self.model, messages, content)

        return content


# ── finish_reason 归一化 ──

def _extract_finish_reason(data: dict, provider: str) -> str:
    """从 LLM 响应中提取并归一化 finish_reason。

    支持多提供商格式（字段名不同、值不同），统一映射为:
      "stop"  — 正常结束
      "length" — 因 max_tokens 限制截断
      "content_filter" — 安全过滤
      空字符串 — 无法提取
      原始值 — 未知原因（保留以便排查）
    """
    try:
        choice = data.get("choices", [{}])[0]

        # OpenAI 兼容格式: choices[0].finish_reason
        # （DeepSeek / 智谱 / 豆包 / MiniMax / 百度文心 / 腾讯混元 均兼容）
        if "finish_reason" in choice:
            raw = "finish_reason=" + choice.get("finish_reason", "")
        # Anthropic 格式: stop_reason
        elif "stop_reason" in choice:
            raw = "stop_reason=" + choice.get("stop_reason", "")
        elif "FinishReason" in choice:
            raw = "FinishReason=" + choice.get("FinishReason", "")            
        else:
            return ""
        return raw
    except Exception:
        return ""



def _resolve_default_provider() -> str:
    """从环境变量或 config.yaml 读取默认 LLM provider。"""
    import os
    return os.environ.get("WECHAT_PUBLISHER_LLM_DEFAULT") or "deepseek"


def _load_provider_config(provider: str) -> tuple[str, str, str]:
    """返回 (api_key, base_url, model)。"""
    import os
    key_env, url_env, model_env = _PROVIDER_ENV_MAP.get(
        provider,
        (f"LLM_{provider.upper()}_API_KEY",
         f"LLM_{provider.upper()}_BASE_URL",
         f"LLM_{provider.upper()}_MODEL"),
    )
    api_key = os.environ.get(key_env, "")
    base_url = os.environ.get(url_env, "https://api.openai.com/v1")
    model = os.environ.get(model_env, "gpt-3.5-turbo")
    return api_key, base_url, model


def _try_log_llm_call(provider: str, model: str, messages: list,
                      response: str, tokens_in: int, tokens_out: int,
                      duration_ms: int, stage: str = "", task_id: int = 0,
                      finish_reason: str = "", status: str = "success",
                      finish_msg: str = "") -> None:
    """尝试写入 llm_call_log。

    Args:
        status: "success" | "failed"
        finish_reason: 归一化后的结束原因（stop / length / content_filter / 原始值）
        finish_msg: 结束信息（HTTP 状态码 / 异常信息 / 空内容原因 / finish_reason）
    """
    try:
        from engine.db.models import llm_log_insert
        prompt_text = json.dumps(messages, ensure_ascii=False)
        # 将 finish_reason 合并到 finish_msg 中（成功时若为 length 也值得记录）
        full_error = finish_msg
        if finish_reason:
            full_error = (finish_msg + finish_reason) if finish_msg else finish_reason
        llm_log_insert(
            task_id=task_id, call_type=CallType.TEXT,
            stage=(stage or "pipeline"), provider=provider, model=model,
            prompt=prompt_text, prompt_chars=len(prompt_text),
            response=response[:2000],
            tokens_in=tokens_in, tokens_out=tokens_out,
            duration_ms=duration_ms, status=status,
            finish_msg=full_error[:1000],
        )
    except Exception as e:
        logger.warning("[LLM] 写入 llm_call_log 失败: task=%d stage=%s provider=%s: %s",
                       task_id, stage, provider, e)


def _try_log_task_message(task_id: int, stage: str, provider: str, model: str,
                          messages: list, response: str) -> int:
    """尝试写入 task_message 对话记录。返回 assistant 消息的 id（0 表示失败）。
    - 首次写入：记录全部消息（system + 所有 user + assistant）
    - 已有记录：仅记录最后一条 user（本轮新提问）+ assistant
    """
    if not task_id:
        return 0
    try:
        from engine.db.models import task_message_append, task_message_exists, task_message_insert

        def _extract_text(content) -> str:
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content
                              if isinstance(p, dict) and p.get("type") == "text"]
                return "\n".join(text_parts) or json.dumps(content, ensure_ascii=False)
            return str(content)

        exists = task_message_exists(task_id, stage)
        # 首次写入时直接用 task_message_insert（不做角色守卫），
        # 避免 task_message_append 内部的 exists 重检查导致 assistant 被拦截
        insert_fn = task_message_insert if not exists else task_message_append

        for msg in messages:
            role = msg.get("role", "")
            if role not in (Role.SYSTEM, Role.USER):
                continue
            if exists and role == Role.USER and msg is not _last_user_msg(messages):
                # 已有记录时，跳过历史 user 消息，只保留最后一条（新提问）
                continue
            insert_fn(
                task_id=task_id, stage=stage, provider=provider, model=model,
                role=role, message=_extract_text(msg.get("content", ""))[:8000],
            )

        # 记录模型回复（assistant 每次都是新内容，始终直接插入，不走守卫逻辑）
        return task_message_insert(
            task_id=task_id, stage=stage, provider=provider, model=model,
            role=Role.ASSISTANT, message=str(response)[:8000],
        )
    except Exception as e:
        logger.warning("[LLM] 写入 task_message 失败: task=%d stage=%s provider=%s: %s",
                       task_id, stage, provider, e)
        return 0


def _last_user_msg(messages: list) -> dict:
    """返回消息列表中最后一条 user 消息。"""
    for m in reversed(messages):
        if m.get("role") == Role.USER:
            return m
    return {}


# ============================================================
# CLI 测试
# ============================================================

if __name__ == "__main__":
    import sys
    client = LLMClient()
    prompt = sys.argv[1] if len(sys.argv) > 1 else "说'你好，LLM 客户端已就绪'"
    print(client.chat(prompt))
