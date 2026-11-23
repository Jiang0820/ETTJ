"""编排层：用 LangGraph 把 agent 包成一张图，后续加节点（校验、人工确认、汇总）都在这层。"""

from __future__ import annotations

from langgraph.graph import END, START, MessagesState, StateGraph

from ..agents.sql_agent import build_sql_agent


def build_sql_graph(checkpointer=None):
    """单节点图：把 SQL agent 作为节点接进 LangGraph 运行时。

    节点只把本轮新增的消息写回 state，避免历史被重复追加。
    """
    agent = build_sql_agent(checkpointer=None)

    def agent_node(state: MessagesState) -> dict:
        history = state.get("messages", [])
        result = agent.invoke({"messages": history})
        produced = result["messages"]
        new_messages = produced[len(history):] or produced[-1:]
        return {"messages": new_messages}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer)
