"""Flow 策略模式 —— 根据 task.type 路由到对应的流程实现。"""

from __future__ import annotations

from typing import Dict, Optional, Type

from .base import FlowRunner

_registry: Dict[str, Type[FlowRunner]] = {}


def register_flow(flow_cls: Type[FlowRunner]) -> None:
    """注册一个 FlowRunner 子类（按 flow_type() 标识）。"""
    _registry[flow_cls.flow_type()] = flow_cls


def get_flow(task_type: str) -> Optional[Type[FlowRunner]]:
    """按 task.type 查找对应的 FlowRunner 类。"""
    return _registry.get(task_type)


def list_flow_types() -> list:
    """返回所有已注册的流程类型标识。"""
    return list(_registry.keys())


# 导入即注册内置流程
from .news_flow import NewsFlow        # noqa: E402
from .newspic_flow import NewspicFlow  # noqa: E402
from .md_flow import MdFlow            # noqa: E402

register_flow(NewsFlow)
register_flow(NewspicFlow)
register_flow(MdFlow)
