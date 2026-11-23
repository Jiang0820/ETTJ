"""记忆层：LangGraph 的 SQLite checkpointer，按 thread_id 保存对话状态。"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from ..config import settings


def get_checkpointer() -> SqliteSaver:
    """返回基于本地 SQLite 的 checkpointer，库文件路径来自 CHECKPOINT_DB。"""
    path = settings.checkpoint_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)


def thread_config(thread_id: str) -> dict:
    """多轮对话用的 config，传给 agent.invoke(..., config=...)。"""
    return {"configurable": {"thread_id": thread_id}}
