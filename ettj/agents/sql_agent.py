"""Agent 层：LangChain 1.5 的 create_agent 组装，模型与工具都从下层注入。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from ..config import PROJECT_ROOT
from ..middleware.audit import AuditMiddleware
from ..middleware.trim import build_trim_middleware
from ..models import get_model
from ..tools.sql import SQL_TOOLS

PROMPT_PATH: Path = PROJECT_ROOT / "ettj" / "prompts" / "sql_agent.md"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_sql_agent(
    *,
    model=None,
    tools: Sequence[BaseTool] | None = None,
    checkpointer=None,
    use_audit: bool = True,
    use_trim: bool = True,
    debug: bool = False,
):
    """构建只读 SQL Agent。

    checkpointer 传入 LangGraph 的持久化实现后，同一个 thread_id 下可多轮对话。
    use_trim 打开后，会话变长会自动清理旧的查询结果，避免撑爆模型上下文。
    """
    middleware = []
    if use_audit:
        middleware.append(AuditMiddleware())   # 打日志：每轮用了什么工具、写了什么 SQL
    if use_trim:
        middleware.append(build_trim_middleware())   # 上下文裁剪：只清旧工具返回，不动对话
    return create_agent(
        model if model is not None else get_model(),
        tools=list(tools) if tools is not None else list(SQL_TOOLS),
        system_prompt=load_system_prompt(),
        middleware=middleware,
        checkpointer=checkpointer,
        debug=debug,
        name="sql_agent",
    )
