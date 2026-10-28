#!/usr/bin/env python3
"""
weflow 全局常量定义。

所有魔法字符串、状态码、枚举值集中管理，避免硬编码分散在各脚本中。

用法:
    from engine.constants import FileName, Status, Stage, ArticleStructure, OpeningHook, ImageStyle
"""

from __future__ import annotations

from typing import Dict, List


# ============================================================
# 产物文件名
# ============================================================

class FileName:
    """Pipeline 各阶段产物文件名（不含路径，仅文件名）。"""
    BRIEF: str = "brief.md"
    RESEARCH: str = "research.md"
    ARTICLE: str = "article.md"
    ARTICLE_HTML: str = "article.html"


# ============================================================
# 任务状态码
# ============================================================

class Status:
    """任务状态码（对应 task_status.code）。"""
    ABANDONED: int = 0
    CREATED: int = 10
    BRIEF_READY: int = 20
    RESEARCH_DONE: int = 30
    CARDS_PLANNED: int = 35
    DRAFT_READY: int = 40
    HUMANIZED: int = 50
    IMAGES_GENERATED: int = 60
    HTML_CONVERTED: int = 70
    AI_SCORE_PASSED: int = 80
    AI_SCORE_FAILED: int = 85
    PUBLISH_FAILED: int = 88
    PUBLISHED: int = 90

    # 状态流转路径
    NEWS_FLOW: List[int] = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    NEWSPIC_FLOW: List[int] = [10, 20, 35, 60, 80, 90]

    @classmethod
    def label(cls, code: int) -> str:
        return _STATUS_LABELS.get(code, f"未知({code})")


_STATUS_LABELS: Dict[int, str] = {
    0: "出错了",
    10: "已创建",
    20: "简报已就绪",
    30: "调研已完成",
    35: "贴图已规划",
    40: "文章已写好",
    50: "人味化完成",
    60: "配图已生成",
    70: "HTML 已转换",
    80: "AI 味通过",
    85: "AI 味未过",
    88: "发布失败",
    90: "已发布",
}


class ReviewStage:
    """审核节点定义。"""

    # 各任务类型的默认审核节点
    NEWS_STAGES: List[int] = [20, 40, 60]    # 简报 + 文章 + 配图
    NEWSPIC_STAGES: List[int] = [20, 60]      # 简报 + 配图

    # 审核通过后恢复执行的 stage 映射
    RESUME_MAP: Dict[int, str] = {
        20: "search_and_research",   # 简报通过 → 继续调研/卡片规划
        35: "generate_images",       # 卡片通过 → 生成配图
        40: "convert_to_html",       # 文章通过 → HTML 转换
        60: "images_reviewed",       # 配图通过 → 继续后续流程
    }

    @classmethod
    def for_task_type(cls, task_type: str) -> List[int]:
        """返回某任务类型的默认审核节点。"""
        if task_type == "image":
            return cls.NEWSPIC_STAGES
        return cls.NEWS_STAGES

    @classmethod
    def label(cls, stage: int) -> str:
        """审核节点中文标签。"""
        return _STATUS_LABELS.get(stage, f"阶段{stage}")


class RetryResume:
    """断点重试映射：从失败状态确定应从哪里恢复执行。

    用法:
        resume_status = RetryResume.get_resume_status(
            task_type="image",
            current_status=Status.PUBLISH_FAILED,  # 88
        )
        # → 80 (AI_SCORE_PASSED), 即仅重试发布阶段
    """

    # article 图文: 失败状态 → 恢复起点
    NEWS_MAP = {
        Status.PUBLISH_FAILED: Status.AI_SCORE_PASSED,    # 88 → 80 (仅发布)
        Status.AI_SCORE_FAILED: Status.DRAFT_READY,        # 85 → 40 (重新草拟+)
    }

    # image 贴图: 失败状态 → 恢复起点
    NEWSPIC_MAP = {
        Status.PUBLISH_FAILED: Status.AI_SCORE_PASSED,     # 88 → 80 (仅发布)
        Status.AI_SCORE_FAILED: Status.BRIEF_READY,        # 85 → 20 (重新生成)
    }

    # md 去味发布: 失败状态 → 恢复起点
    # 85 → 40 而非 50：retry_from=50 会因 `retry_from >= 50` 跳过 humanize 阶段，
    # 导致"AI 味未过 → 重试却不再改写"。85 审核通过续跑走 stage 直传（85），与此无关。
    MD_MAP = {
        Status.PUBLISH_FAILED: Status.AI_SCORE_PASSED,     # 88 → 80 (仅发布)
        Status.AI_SCORE_FAILED: Status.DRAFT_READY,        # 85 → 40 (重新人味化)
    }

    @classmethod
    def get_resume_status(
        cls,
        task_type: str,
        current_status: int,
        business_key: str = "",
    ) -> int:
        """确定重试应从哪个阶段开始。

        Args:
            task_type: "article" 或 "image"
            current_status: 当前失败状态码 (0/85/88)
            business_key: status_history 中记录的 business_key,
                          仅 ABANDONED(0) 时使用，记录了崩溃前的状态码

        Returns:
            int: 恢复起点状态码。0 表示从头开始。
        """
        if current_status == Status.ABANDONED:
            # business_key 存储了崩溃前所处阶段的状态码
            try:
                return int(business_key)
            except (ValueError, TypeError):
                return Status.CREATED  # 兜底：从头开始

        task_map = {"image": cls.NEWSPIC_MAP, "md": cls.MD_MAP}.get(task_type, cls.NEWS_MAP)
        return task_map.get(current_status, 0)


# ============================================================
# Pipeline 阶段标识
# ============================================================

class Stage:
    """Pipeline 阶段标识（用于 LLMClient.stage / task_message.stage / llm_call_log.stage）。"""
    UNDERSTAND: str = "understand_requirements"
    RESEARCH: str = "search_and_research"
    DRAFT: str = "write_draft"
    GENERATE: str = "generate"
    HUMANIZE: str = "humanize"
    HTML_CONVERT: str = "html_convert"
    AI_SCORE: str = "ai_score"
    PUBLISH: str = "publish"
    SYNC: str = "sync"


# ============================================================
# 操作者
# ============================================================

class Operator:
    """status_transition 的 operator 字段取值。"""
    SYSTEM: str = "system"
    AGENT: str = "agent"
    PIPELINE: str = "pipeline"
    UNDERSTAND: str = "understand"
    PUBLISH: str = "publish"
    AI_SCORE: str = "ai_score"
    GENERATE_IMAGE: str = "generate_image"


# ============================================================
# 任务类型
# ============================================================

class TaskType:
    """task.type 取值。"""
    NEWS: str = "article"
    NEWSPIC: str = "image"
    MD: str = "md"   # AI去味发布：已有 md 文章 + 配图，LLM 去味改写后发布


# ============================================================
# 对话角色
# ============================================================

class Role:
    """task_message.role / LLM 消息角色。"""
    SYSTEM: str = "system"
    USER: str = "user"
    ASSISTANT: str = "assistant"
    TOOL: str = "tool"


# ============================================================
# LLM / 图片 Provider
# ============================================================

class Provider:
    """模型提供商标识。"""
    # 文本 LLM
    DEEPSEEK: str = "deepseek"
    OPENAI: str = "openai"
    ZHIPU: str = "zhipu"
    DOUBAO: str = "doubao"
    MINIMAX: str = "minimax"

    # 图片生成
    QWEN_IMAGE: str = "qwen_image"
    Z_IMAGE: str = "z_image"
    KREA_2_TURBO: str = "krea_2_turbo"
    GEMINI_PROXY: str = "gemini_proxy"
    Z_IMAGE_TURBO_BAILIAN: str = "z_image_turbo_bailian"
    WAN_IMAGE_BAILIAN: str = "wan_image_bailian"

    # 集合
    LLM_PROVIDERS: List[str] = ["deepseek", "openai", "zhipu", "doubao", "minimax"]
    IMAGE_PROVIDERS: List[str] = [
        "openai", "gemini_proxy", "z_image", "krea_2_turbo",
        "qwen_image", "z_image_turbo_bailian", "wan_image_bailian",
    ]


# ============================================================
# 调用类型
# ============================================================

class CallType:
    """llm_call_log.call_type 取值。"""
    TEXT: str = "text"
    IMAGE: str = "image"


# ============================================================
# 图片上传状态
# ============================================================

class UploadStatus:
    """task_image.upload_status 取值。"""
    PENDING: str = "pending"                   # 占位记录，尚未生成
    GENERATED: str = "generated"               # 已生成本地图片，等待上传
    GENERATE_FAILED: str = "generate_failed"   # 图片生成失败
    UPLOADING: str = "uploading"               # 正在上传到微信
    UPLOADED: str = "uploaded"                 # 已上传到微信 CDN
    FAILED: str = "failed"                     # 上传失败
    SKIPPED: str = "skipped"                   # 跳过


# ============================================================
# 发布
# ============================================================

class PublishType:
    """publish_record.publish_type 取值。"""
    DRAFT: str = "draft"
    PUBLISH: str = "publish"


class PublishStatus:
    """publish_record.status 取值。"""
    PENDING: str = "pending"
    SUBMITTED: str = "submitted"
    SUCCESS: str = "success"
    FAILED: str = "failed"


class Platform:
    """发布平台标识。"""
    WECHAT: str = "wechat"
    ZHIHU: str = "zhihu"
    JUEJIN: str = "juejin"
    CSDN: str = "csdn"
    TOUTIAO: str = "toutiao"

    ALL: List[str] = ["wechat", "zhihu", "juejin", "csdn", "toutiao"]


# ============================================================
# 多平台同步目标平台
# ============================================================

class SyncPlatform:
    """多平台同步支持的平台（对应 wechatsync CLI）。"""

    PLATFORMS: Dict[str, str] = {
        "zhihu": "知乎",
        "bilibili": "哔哩哔哩",
        "weixin": "微信公众号",
        "zip-download": "Markdown 压缩包",
        "x": "X (Twitter)",
        "xiaohongshu": "小红书",
        "juejin": "掘金",
        "weibo": "微博",
        "baijiahao": "百家号",
        "csdn": "CSDN",
        "yuque": "语雀",
        "douban": "豆瓣",
        "sohu": "搜狐号",
        "xueqiu": "雪球",
        "woshipm": "人人都是产品经理",
        "51cto": "51CTO",
        "imooc": "慕课手记",
        "oschina": "开源中国",
        "segmentfault": "思否",
        "cnblogs": "博客园",
        "eastmoney": "东方财富",
        "dayu": "大鱼号",
        "douyin": "抖音图文",
        "jianshu": "简书",
        "netease": "网易号",
        "smzdm": "什么值得买",
        "sohufocus": "搜狐焦点",
        "toutiao": "头条",
        "yidian": "一点号",
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls.PLATFORMS.get(code, code)

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls.PLATFORMS.keys())


# ============================================================
# AI 检测结论
# ============================================================

class AIVerdict:
    """task.ai_verdict 取值。"""
    PASS: str = "PASS"
    WARN: str = "WARN"
    FAIL: str = "FAIL"


# ============================================================
# 文章结构（article_structure）
# ============================================================

class ArticleStructure:
    """文章结构代码及元信息。"""
    DEFAULT: str = "teardown"

    _STRUCTURES: Dict[str, dict] = {
        "data-first": {
            "label": "数据砸脸",
            "topics": "榜单 / benchmark / 融资 / 财报 / 模型能力",
            "flow": "反常数字开场 → 数字是什么 → 谁做的 → 为什么可信 → 行业意义 → 我的判断",
        },
        "question-led": {
            "label": "问题追踪",
            "topics": "争议 / 真假难辨 / 产品变化 / 用户困惑",
            "flow": "抛具体问题 → 从哪来 → 证据A/B → 已确认/存疑 → 结论边界",
        },
        "contrarian": {
            "label": "反常识",
            "topics": "舆论一边倒但事实更复杂",
            "flow": "先说反直觉判断 → 大家怎么想 → 为什么不完全对 → 关键证据 → 重新理解 → 后续影响",
        },
        "teardown": {
            "label": "拆解地图",
            "topics": "新框架 / 新协议 / Agent架构 / SDK",
            "flow": "先给结构图或总览 → 分层拆解 → 关键设计取舍 → 和旧方案对比 → 适用边界",
        },
        "field-notes": {
            "label": "实测笔记",
            "topics": "工具体验 / 教程 / 踩坑 / 本机实验",
            "flow": "从一条命令、日志、失败结果切入 → 我试了什么 → 怎么跑 → 哪里顺 → 哪里坑 → 用法建议",
        },
        "timeline-news": {
            "label": "时间线",
            "topics": "热点新闻 / 公司动作 / 政策 / 安全事故",
            "flow": "用具体时间点或事件链开场 → 发生了什么 → 时间线 → 关键角色 → 影响范围 → 接下来盯什么",
        },
        "playbook": {
            "label": "行动清单",
            "topics": "方法论 / 技巧合集 / 入门指南 / 生产力",
            "flow": "先给结果承诺或适用人群 → 最短路径 → 3-5个关键动作 → 常见坑 → 何时不该用",
        },
        "case-file": {
            "label": "案卷复盘",
            "topics": "翻车 / 处罚 / 安全事件 / 商业事故",
            "flow": "用'案情摘要'或核心矛盾开场 → 案件事实 → 证据链 → 错在哪里 → 反方解释 → 对普通人的启发",
        },
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._STRUCTURES.get(code, {}).get("label", code)

    @classmethod
    def topics(cls, code: str) -> str:
        return cls._STRUCTURES.get(code, {}).get("topics", "")

    @classmethod
    def flow(cls, code: str) -> str:
        return cls._STRUCTURES.get(code, {}).get("flow", "")

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls._STRUCTURES.keys())


# ============================================================
# 开篇钩子（opening_hook）
# ============================================================

class OpeningHook:
    """开篇钩子代码及元信息。"""

    DEFAULT: str = "sharp-question"

    _HOOKS: Dict[str, dict] = {
        "hard-number": {
            "label": "硬数字开场",
            "tip": "第一屏出现具体数字、金额、比例、版本号",
            "avoid": "数字后面空泛感慨",
        },
        "sharp-question": {
            "label": "尖锐提问",
            "tip": "用一个读者真会问的问题开场",
            "avoid": "连续自问自答三四句",
        },
        "contradiction": {
            "label": "冲突并置",
            "tip": "把两个冲突事实并排放出来",
            "avoid": "为反转而反转",
        },
        "quote-first": {
            "label": "引用开局",
            "tip": "用当事人原话 / issue / commit message 开场",
            "avoid": "编造无法溯源的'有人说'",
        },
        "artifact-first": {
            "label": "产物开场",
            "tip": "用命令输出、日志、截图描述、排行榜条目开场",
            "avoid": "贴一大段无解释的技术细节",
        },
        "timeline-first": {
            "label": "时间线开场",
            "tip": "用具体日期 / 小时时间线开场",
            "avoid": "宏观时代背景",
        },
        "scene-first": {
            "label": "场景开场",
            "tip": "用个人经历或具体场景开场",
            "avoid": "每篇都这样写；故事必须短，不要铺陈",
        },
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._HOOKS.get(code, {}).get("label", code)

    @classmethod
    def tip(cls, code: str) -> str:
        return cls._HOOKS.get(code, {}).get("tip", "")

    @classmethod
    def avoid(cls, code: str) -> str:
        return cls._HOOKS.get(code, {}).get("avoid", "")

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls._HOOKS.keys())


# ============================================================
# 文章体裁/表达方式（genre）
# ============================================================

class Genre:
    """文章体裁/表达方式代码及元信息。"""

    DEFAULT: str = ""  # 空字符串表示 AI 自动选择

    _GENRES: Dict[str, dict] = {
        "narrative": {
            "label": "记叙文",
            "purpose": "讲述人物经历或事件过程，传递情感与体验，让读者「感同身受」",
            "features": "生动形象，时态明确，常用第一或第三人称，多细节描写和对话",
        },
        "expository": {
            "label": "说明文",
            "purpose": "清晰解释事物或事理，传授知识，让读者「明白理解」",
            "features": "平实准确，客观冷静，术语规范，避免主观抒情，多用定义、分类等方法",
        },
        "argumentative": {
            "label": "议论文",
            "purpose": "提出并论证观点，说服读者接受主张，让读者「信服并行动」",
            "features": "严谨慎重，逻辑性强，多用关联词和判断句，论证层次分明",
        },
        "lyrical": {
            "label": "抒情文",
            "purpose": "抒发内心主观感受，引发读者共鸣，让读者「受到感染」",
            "features": "富于感染力，多用修饰语、感叹句、排比、比喻，节奏感强",
        },
        "practical": {
            "label": "应用文",
            "purpose": "处理具体事务、传递实用信息，让读者「依此办事」",
            "features": "规范得体，简洁明了，针对性强，忌空泛抒情，常用固定套语和格式化表达",
        },
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._GENRES.get(code, {}).get("label", code)

    @classmethod
    def purpose(cls, code: str) -> str:
        return cls._GENRES.get(code, {}).get("purpose", "")

    @classmethod
    def features(cls, code: str) -> str:
        return cls._GENRES.get(code, {}).get("features", "")

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls._GENRES.keys())


# ============================================================
# 配图风格（image_style）
# ============================================================

class ImageStyle:
    """配图风格代码及元信息。"""

    # ── 文章（news）默认风格 ──
    DEFAULT_NEWS: str = "warm-handdrawn"
    # ── 贴图（newspic）默认风格 ──
    DEFAULT_NEWSPIC: str = "infographic-warm"

    # 风格列表（名称 → 元信息）
    _STYLES: Dict[str, dict] = {
        # 手账 / 卡片风（中密度，文章 & 贴图通用）
        "warm-handdrawn": {
            "label": "暖色手绘手账",
            "keywords": "细黑线 + 米白 + 粉/暖黄手账卡片",
            "topics": "工具测评、功能对比、上手指南、概念科普",
            "density": "中",
            "newspic": True,
            "news": True,
            "default_news": True,
        },
        "flat-editorial": {
            "label": "扁平编辑风",
            "keywords": "黑线 + 米白 + 克制柔彩(桃/绿/黄/紫高亮)",
            "topics": "步骤讲解、工具/功能对比、概念拆解、调试复盘",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "morandi": {
            "label": "莫兰迪灰调",
            "keywords": "细黑线 + 莫兰迪灰调(手账手写)",
            "topics": "人文、随笔、深度评论、有质感的内容",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "mint": {
            "label": "薄荷绿",
            "keywords": "细黑线 + 薄荷绿/天蓝(清爽冷调,手账)",
            "topics": "生产力、工具、效率、清单",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "blue": {
            "label": "蓝调技术",
            "keywords": "细黑线 + 蓝调 + 橙点缀(冷静偏技术,手账)",
            "topics": "技术、架构、协议、SDK、评测",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        # 标题大字风（低密度）
        "marker-lime": {
            "label": "荧光黄绿",
            "keywords": "白底刷体大字 + 荧光黄绿高亮 + 宝蓝强调",
            "topics": "标题党、爆点、热评、金句、短观点",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        "marker-pink": {
            "label": "樱粉标记",
            "keywords": "白底刷体大字 + 樱粉高亮 + 青绿强调",
            "topics": "同上,樱粉配色",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        "marker-sky": {
            "label": "天蓝标记",
            "keywords": "白底刷体大字 + 天蓝高亮 + 亮橙强调",
            "topics": "同上,天蓝配色",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        "marker-coral": {
            "label": "珊瑚标记",
            "keywords": "白底刷体大字 + 珊瑚橙高亮 + 靛蓝强调",
            "topics": "同上,珊瑚配色",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        "marker-violet": {
            "label": "藕紫标记",
            "keywords": "白底刷体大字 + 藕紫高亮 + 玫红强调",
            "topics": "同上,藕紫配色",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        # 插画风（中密度）
        "hand-drawn-blue": {
            "label": "手绘蓝",
            "keywords": "手绘线条 + 蓝点缀",
            "topics": "概念解释、架构图、流程图(全能选手)",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "illustrated-warm": {
            "label": "暖色插画",
            "keywords": "暖橙 + 卡通人物 + 气泡",
            "topics": "体验讲解、使用指南、亲切感强的技巧",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "xiaohongshu-colorful": {
            "label": "小红书多彩",
            "keywords": "暖色渐变 + emoji + 大字",
            "topics": "生活提示、上手指南、清单类",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "magazine-editorial": {
            "label": "杂志编辑风",
            "keywords": "米色 + 衬线 + 栏位感",
            "topics": "深度评论、专栏、长篇随笔",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "knowledge-card": {
            "label": "知识卡片",
            "keywords": "白底 + 编号 + 结构化",
            "topics": "教程、方法论、清单、复习卡",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "data-chart": {
            "label": "数据图表",
            "keywords": "白底 + 图表 + 数字",
            "topics": "数据观察、行业报告、对比",
            "density": "中",
            "newspic": True,
            "news": True,
        },
        "meme-illustration": {
            "label": "梗图插画",
            "keywords": "黄底 + 卡通 + 对话气泡",
            "topics": "吐槽、段子、行业梗",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        "slice-of-life": {
            "label": "治愈生活手绘",
            "keywords": "细墨线 + 中性淡彩 + 单点红(治愈系生活手绘)",
            "topics": "生活观察、打工人共鸣、段子、轻科普",
            "density": "低",
            "newspic": True,
            "news": True,
        },
        # 高密度信息图（贴图专用）
        "infographic-warm": {
            "label": "暖色信息图",
            "keywords": "暖色手绘 + 高密度信息图",
            "topics": "贴图默认,通用话题",
            "density": "高",
            "newspic": True,
            "news": True,
            "default_newspic": True,
        },
        "infographic-blue": {
            "label": "冷蓝信息图",
            "keywords": "冷蓝手绘 + 高密度信息图",
            "topics": "SDK/协议/产品拆解",
            "density": "高",
            "newspic": True,
            "news": True,
        },
        "infographic-dark": {
            "label": "深色信息图",
            "keywords": "深色手绘 + 高密度信息图",
            "topics": "前沿模型、基建、赛博",
            "density": "高",
            "newspic": True,
            "news": True,
        },
        "infographic-mint": {
            "label": "薄荷信息图",
            "keywords": "薄荷手绘 + 高密度信息图",
            "topics": "生产力/工具/方法论",
            "density": "高",
            "newspic": True,
            "news": True,
        },
    }

    @classmethod
    def label(cls, code: str) -> str:
        info = cls._STYLES.get(code, {})
        return info.get("label", code)

    @classmethod
    def keywords(cls, code: str) -> str:
        info = cls._STYLES.get(code, {})
        return info.get("keywords", "")

    @classmethod
    def topics(cls, code: str) -> str:
        info = cls._STYLES.get(code, {})
        return info.get("topics", "")

    @classmethod
    def density(cls, code: str) -> str:
        info = cls._STYLES.get(code, {})
        return info.get("density", "")

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls._STYLES.keys())

    @classmethod
    def for_density(cls, density: str) -> List[str]:
        return [k for k, v in cls._STYLES.items() if v.get("density") == density]

    @classmethod
    def for_newspic(cls) -> List[str]:
        return [k for k, v in cls._STYLES.items() if v.get("newspic")]

    @classmethod
    def for_news(cls) -> List[str]:
        return [k for k, v in cls._STYLES.items() if v.get("news")]


# ============================================================
# 排版主题（theme）
# ============================================================

class Theme:
    """排版主题标识（对应 assets/themes/<name>.json）。"""

    DEFAULT: str = "refined-blue"

    _THEMES: Dict[str, dict] = {
        "refined-blue": {
            "label": "精致蓝调",
            "description": "蓝调极简 + 精致的层次 / 数字标号 / 渐变高亮,适合 AI / 产品 / 深度分析(main 号默认)",
        },
        "warm-editorial": {
            "label": "暖色杂志风",
            "description": "栗色 + 米白 + 宋体,温厚的长文阅读感,适合观点 / 随笔 / 生活随笔",
        },
        "warm-orange": {
            "label": "温暖橙调",
            "description": "暖橙 · 生活 · 美食号,亲切日常感,适合生活方式 / 美食 / 旅行 / 记录类",
        },
        "business-navy": {
            "label": "商务蓝金",
            "description": "深蓝主色 + 金色点缀,权威克制的金融感,适合商业 / 投研 / 行业分析",
        },
        "elegant-ink": {
            "label": "水墨雅韵",
            "description": "墨黑 + 朱砂红,衬线字体,克制雅致的现代宋体,适合观点 / 人文 / 深度长文",
        },
        "girly-pink": {
            "label": "少女粉系",
            "description": "粉紫渐变 + 可爱风,甜美轻盈,适合时尚 / 美妆 / 情感 / 少女向内容",
        },
        "ink-wash": {
            "label": "古风水墨",
            "description": "米黄纸 + 朱砂宋体,中式留白美学,适合传统文化 / 人文 / 诗意随笔",
        },
        "magazine-grid": {
            "label": "杂志衬线",
            "description": "衬线大标题 + 大留白,杂志内页感,适合专题报道 / 长篇深度 / 艺术人文",
        },
        "minimal-bw": {
            "label": "极简黑白",
            "description": "瑞士现代主义 · Helvetica,只用粗细 / 留白 / 对齐做层级,适合 essay / 观点 / 技术长文",
        },
        "minimal-mono": {
            "label": "极简等宽",
            "description": "纯黑白 + 等宽字,偏工程师审美,适合技术 / 工程 / 开发类长文",
        },
        "mint-fresh": {
            "label": "小清新薄荷",
            "description": "薄荷绿 + 圆角卡片,轻盈透气,适合日常 / 生活方式 / 轻话题",
        },
        "news-bold": {
            "label": "新闻时讯",
            "description": "红黑强对比 + 快节奏,信息密度高,适合资讯 / 热点 / 速读类短文",
        },
        "sage-premium": {
            "label": "鼠尾草墨绿",
            "description": "深绿 + 象牙白,克制专业的自然色,适合数据分析 / 研究报告 / 长篇深度内容",
        },
        "sunset-coral": {
            "label": "夕阳珊瑚",
            "description": "暖橙 + 奶白,热烈克制的活力色,适合热点 / 榜单 / 潮流 / 轻快话题",
        },
        "academic-paper": {
            "label": "学术严谨",
            "description": "论文格式 + 衬线正字,章节编号式层级,适合研究 / 论述 / 严肃长文",
        },
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._THEMES.get(code, {}).get("label", code)

    @classmethod
    def description(cls, code: str) -> str:
        return cls._THEMES.get(code, {}).get("description", "")

    @classmethod
    def all_codes(cls) -> List[str]:
        return list(cls._THEMES.keys())


# ============================================================
# 目录路径
# ============================================================

class DirPath:
    """项目固定目录（相对于项目根目录）。"""
    GENERATED: str = "generated"
    ASSETS: str = "assets"
    THEMES: str = "assets/themes"
    IMAGE_STYLES: str = "assets/image-styles"
    ENGINE: str = "engine"
    ENGINE_DB: str = "engine/db"
    LOGS: str = "logs"
    IMAGES: str = "images"   # 任务产物子目录：配图输出


# ============================================================
# LLM 默认参数
# ============================================================

class LLMDefaults:
    """LLM 调用的默认参数。"""
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 4096
    TIMEOUT_SEC: int = 120

    # 各阶段差异化的温度和 token 数
    UNDERSTAND_TEMPERATURE: float = 0.7
    UNDERSTAND_MAX_TOKENS: int = 8192

    RESEARCH_TEMPERATURE: float = 0.5
    RESEARCH_MAX_TOKENS: int = 8192

    DRAFT_TEMPERATURE: float = 0.8
    DRAFT_MAX_TOKENS: int = 16384


# ============================================================
# 数据库
# ============================================================

class DB:
    """数据库相关常量。"""
    DB_FILE: str = "engine/db/weflow.db"
    WAL_MODE: str = "WAL"
