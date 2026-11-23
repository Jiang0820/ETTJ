"""可观测层：LangSmith 开关与初始化，全部由 .env 控制。"""

from __future__ import annotations

import logging
import os

from ..config import settings

logger = logging.getLogger("ettj.tracing")


def setup_tracing() -> bool:
    """按 .env 配置打开 LangSmith 轨迹上报，返回是否真正启用。

    必须在 agent 首次调用之前执行；环境变量是 LangSmith SDK 唯一的读取来源。
    """
    if not settings.langsmith_tracing:
        logger.debug("LangSmith 未启用（LANGSMITH_TRACING=false）")
        return False

    if not settings.langsmith_api_key:
        logger.warning("LANGSMITH_TRACING=true 但缺少 LANGSMITH_API_KEY，已跳过")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    logger.info("LangSmith 已启用，项目 %s", settings.langsmith_project)
    return True


def trace_url(run_id: str | None = None) -> str:
    """给终端输出一个可点的项目地址。"""
    base = settings.langsmith_endpoint.rstrip("/")
    if run_id:
        return f"{base}/o/{settings.langsmith_project}/r/{run_id}"
    return f"{base}/o/{settings.langsmith_project}"
