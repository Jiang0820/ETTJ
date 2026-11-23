"""自己测试问题：看火山模型写了什么 SQL、查到什么数据、最后怎么回答。

用法：
    python scripts/try_ask.py "物料 AAHC3901-0018 历史最低价"       # 问一条，只打印回答
    python scripts/try_ask.py -v "..."                             # 加 -v 才打印 SQL 和中间数据
    python scripts/try_ask.py                                      # 进入多轮模式，可以接着追问
    python scripts/try_ask.py -e "..."                             # 出错时打印完整 traceback

多轮模式里：
- 同一个会话内可以直接追问（"那只看租户 000001 呢"），模型记得上一轮问的是什么
- 输入 /new 开一个新会话（旧上下文丢弃），输入 exit 退出
"""

import sys
import uuid
from pathlib import Path

# 让脚本能 import 到 ettj 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.agents.sql_agent import build_sql_agent  # 建 Agent：模型 + 工具 + 提示词
from ettj.config import settings  # 读 .env 的配置，用来确认连的是哪个模型/库
from ettj.memory.checkpointer import get_checkpointer, thread_config  # 多轮对话的记忆


def show(question: str, agent, verbose: bool, config: dict | None = None) -> None:
    """跑一个问题。config 里带 thread_id 时，Agent 会自动带上这个会话的历史。"""
    payload = {"messages": [{"role": "user", "content": question}]}
    # 有 config 就走"记住上下文"的路径，没有就是一次性问答
    result = agent.invoke(payload, config=config) if config else agent.invoke(payload)

    if verbose:
        # 只有加了 -v 才打印中间过程：模型调了什么工具、写了什么 SQL、数据库回了什么
        for msg in result["messages"]:
            for call in getattr(msg, "tool_calls", None) or []:
                if call.get("name") == "mysql_run_query":
                    print("\nSQL  ->", call["args"].get("sql"))
                else:
                    print("\n工具 ->", call.get("name"), call.get("args"))
            if getattr(msg, "type", "") == "tool":
                print("数据 <-", str(msg.content).replace("\n", " ")[:600])

    # 最终回答：倒序找最后一条有文字的 AI 消息
    for msg in reversed(result["messages"]):
        if getattr(msg, "type", "") == "ai" and getattr(msg, "text", "").strip():
            print("\n回答:", msg.text)
            return


def main() -> None:
    # 先把开关参数摘出来，剩下的词才是问题本身
    raw = sys.argv[1:]
    verbose = "-v" in raw or "--verbose" in raw  # 打印 SQL / 数据
    show_stack = "-e" in raw  # 出错时打印完整调用栈
    question = " ".join(a for a in raw if a not in ("-v", "--verbose", "-e"))

    print("模型:", settings.model)
    print("数据库:", settings.mask_mysql())

    # 带 checkpointer 建 Agent：它负责把每轮消息存进 SQLite，key 就是 thread_id
    agent = build_sql_agent(checkpointer=get_checkpointer())
    thread_id = uuid.uuid4().hex[:8]  # 一个 thread_id = 一段独立对话
    print("会话:", thread_id, "（输入 /new 换新会话，exit 退出）")

    try:
        # 命令行直接带问题：问一次就结束
        if question:
            show(question, agent, verbose, thread_config(thread_id))
            return

        # 不带问题：进循环，一行一问，可以接着追问
        while True:
            try:
                q = input("\n问题> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见")
                return
            if not q or q in ("exit", "quit"):
                return
            if q == "/new":
                thread_id = uuid.uuid4().hex[:8]
                print("新会话:", thread_id, "（之前的上下文不会再带上）")
                continue
            show(q, agent, verbose, thread_config(thread_id))
    except Exception as exc:
        # 默认只打一行错误；想看完整调用栈就加 -e 重跑
        print("\n出错:", str(exc)[:300])
        if show_stack:
            raise


if __name__ == "__main__":
    main()
