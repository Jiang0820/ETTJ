"""审计中间件：不接 LangSmith 时，把每轮上下文规模和 token 用量打到日志里。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

logger = logging.getLogger("ettj.audit")


class AuditMiddleware(AgentMiddleware):
    """在 agent 生命周期上挂日志钩子，不改变执行结果。"""

    name = "audit"

    @staticmethod
    def _messages(state: Any) -> list[Any]:
        if isinstance(state, dict):
            return state.get("messages", []) or []
        return getattr(state, "messages", []) or []

    def before_agent(self, state, runtime):  # noqa: ANN001
        logger.info("[agent] 开始，历史消息 %d 条", len(self._messages(state)))
        return None

    def before_model(self, state, runtime):  # noqa: ANN001
        messages = self._messages(state)
        chars = sum(len(str(getattr(m, "content", "") or "")) for m in messages)
        logger.info("[model] 输入 %d 条消息 / 约 %d 字符", len(messages), chars)
        return None

    def after_model(self, state, runtime):  # noqa: ANN001
        messages = self._messages(state)
        if not messages:
            return None
        last = messages[-1]
        usage = getattr(last, "usage_metadata", None) or {}
        calls = getattr(last, "tool_calls", None) or []
        logger.info(
            "[model] 输出 tool_calls=%d tokens=%s",
            len(calls),
            usage.get("total_tokens", "-"),
        )
        return None
