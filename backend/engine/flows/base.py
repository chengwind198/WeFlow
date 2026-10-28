"""FlowRunner 抽象基类 —— 所有流程类型继承此类。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class FlowRunner(ABC):
    """流程基类。

    子类需实现：
      - flow_type(): 返回 task.type 字符串
      - execute():   执行完整流程并返回结果 dict
    """

    def __init__(self, topic: str, account: str = "main",
                 output_dir: Optional[str] = None, retry_from: int = 0,
                 **kwargs):
        self.topic = topic
        self.account = account
        self.output_dir = output_dir
        self.retry_from = retry_from  # 断点重试起点状态码，0=完整执行
        self.kwargs = kwargs  # 流程特定参数（provider / theme / ...）

        # 执行过程中填充
        self._account_cfg: Dict[str, Any] = {}
        self.task_id: int = 0

    # ── 抽象方法 ──

    @staticmethod
    @abstractmethod
    def flow_type() -> str:
        """返回 task.type 字符串（如 "article" / "image"）。"""
        ...

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """执行完整流程，返回结果 dict。"""
        ...

    # ── 共享方法 ──

    def _setup_environment(self) -> None:
        """加载环境变量、设置账号、读取配置。"""
        from engine.config import load_env, set_account, get_config

        load_env()
        set_account(self.account)
        try:
            self._account_cfg = get_config(self.account)
        except Exception as e:
            logger.debug("[FlowRunner] 加载账号配置失败 account=%s: %s", self.account, e)
            self._account_cfg = {}

    def _create_task_and_brief(self) -> Tuple[str, int]:
        """阶段一：创建任务 + 生成 brief.md。返回 (brief_path, task_id)。"""
        from engine.understand import understand_requirements

        existing_tid = self.kwargs.get("existing_task_id", 0)
        existing_path = self.kwargs.get("existing_task_path", "")

        brief_path, tid = understand_requirements(
            topic=self.topic,
            account=self.account,
            output_dir=self.output_dir,
            account_cfg=self._account_cfg,
            user_details=self.kwargs.get("user_details"),
            task_type=self.flow_type(),
            need_images=self.kwargs.get("need_images", 1),
            existing_task_id=existing_tid,
            existing_task_path=existing_path,
        )
        self.task_id = tid
        return brief_path, tid

    def _check_review(self, stage: int) -> bool:
        """检查当前阶段是否需要审核。

        从账号配置读取 review_enabled 和 review_stages，
        如果当前阶段在审核列表中且尚无待审核记录，则创建审核记录并返回 True。

        Returns:
            True:  需要审核，已创建审核记录，流程应暂停
            False: 不需要审核，流程继续
        """
        from engine.db.models import task_review_insert, task_review_get_pending

        cfg = self._account_cfg
        if not cfg.get("review_enabled"):
            return False

        review_stages = cfg.get("review_stages") or {}
        stages_to_review: list = review_stages.get(self.flow_type(), [])
        if not stages_to_review or stage not in stages_to_review:
            return False

        # 重试/继续场景：retry_from >= stage 说明该阶段已完成或审核已通过，跳过
        if self.retry_from >= stage:
            return False

        # 已有待审核记录，不重复创建
        existing = task_review_get_pending(self.task_id, stage)
        if existing:
            logger.info(
                "[%s] 阶段 %d 已有待审核记录 review_id=%d，跳过",
                self.flow_type(), stage, existing["id"],
            )
            return True

        review_id = task_review_insert(
            task_id=self.task_id, stage=stage, status="pending",
        )
        logger.info(
            "[%s] 阶段 %d 需要审核，已创建 review_id=%d，流程暂停",
            self.flow_type(), stage, review_id,
        )
        return True

    def _log_completion(self, result: Dict[str, Any]) -> None:
        """打印流程完成摘要。"""
        print(f"\n{'=' * 60}\nPipeline 完成 [{self.flow_type()}] task_id={self.task_id}")
        for k, v in result.items():
            print(f"  {k}: {v}")
        print(f"{'=' * 60}")
