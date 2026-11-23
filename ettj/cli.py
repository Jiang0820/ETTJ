"""命令行入口：python -m ettj.cli {check,ask,chat}"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from .agents.sql_agent import build_sql_agent
from .config import settings
from .memory.checkpointer import get_checkpointer, thread_config
from .models import get_model
from .observability.tracing import setup_tracing
from .tools.sql import get_engine, list_tables, refresh_schema_cache

console = Console()


def setup_logging() -> None:
    log_dir = settings.resolve(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "ettj.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, "WARNING", logging.WARNING))
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        handlers=[file_handler, console_handler],
        force=True,
    )


def _last_ai_text(messages: list) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") != "ai":
            continue
        text = getattr(message, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        content = getattr(message, "content", "")
        return content if isinstance(content, str) else str(content)
    return ""


def _print_trace(messages: list) -> None:
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            console.print(f"  [dim]-> {call.get('name')}({call.get('args')})[/dim]")
        if getattr(message, "type", "") == "tool":
            preview = str(getattr(message, "content", ""))[:300]
            console.print(f"  [dim]<- {preview}[/dim]")


# --------------------------------------------------------------- 子命令
def cmd_check() -> int:
    console.print(f"模型: [cyan]{settings.model}[/cyan]")
    console.print(f"数据库: [cyan]{settings.mask_mysql()}[/cyan]")
    console.print(f"只读模式: [cyan]{settings.sql_read_only}[/cyan]")

    missing = settings.missing_required()
    if missing:
        console.print(f"[red]缺少必填项: {', '.join(missing)}[/red]")
        return 1

    with get_engine().connect() as conn:
        version = conn.exec_driver_sql("SELECT VERSION()").scalar()
        database = conn.exec_driver_sql("SELECT DATABASE()").scalar()
    tables = list_tables()
    console.print(f"连接成功 | MySQL {version} | 当前库 {database} | 表 {len(tables)} 张")
    if tables:
        console.print("表名: " + ", ".join(tables[:30]) + ("..." if len(tables) > 30 else ""))
    return 0


def _invoke(agent, question: str, thread_id: str | None, verbose: bool) -> None:
    config = thread_config(thread_id) if thread_id else None
    payload = {"messages": [{"role": "user", "content": question}]}
    result = agent.invoke(payload, config=config) if config else agent.invoke(payload)
    messages = result["messages"]
    if verbose:
        _print_trace(messages)
    console.print(Markdown(_last_ai_text(messages)))


def cmd_ask(question: str, model_id: str | None, verbose: bool) -> int:
    agent = build_sql_agent(model=get_model(model_id) if model_id else None)
    _invoke(agent, question, None, verbose)
    return 0


def cmd_chat(model_id: str | None, verbose: bool) -> int:
    checkpointer = get_checkpointer()
    agent = build_sql_agent(
        model=get_model(model_id) if model_id else None,
        checkpointer=checkpointer,
    )
    thread_id = uuid.uuid4().hex[:12]
    console.print(f"会话 ID: [cyan]{thread_id}[/cyan]（/new 开新会话，/exit 退出）")
    console.print("命令: /tables 列表  /refresh 清表结构缓存  /new 新会话  /exit 退出")

    while True:
        try:
            question = console.input("\n[bold]> [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n再见")
            return 0
        if not question:
            continue
        if question in ("/exit", "/quit"):
            return 0
        if question == "/tables":
            console.print(", ".join(list_tables()))
            continue
        if question == "/refresh":
            refresh_schema_cache()
            console.print("表结构缓存已清空")
            continue
        if question == "/new":
            thread_id = uuid.uuid4().hex[:12]
            console.print(f"新会话: [cyan]{thread_id}[/cyan]")
            continue
        try:
            _invoke(agent, question, thread_id, verbose)
        except Exception as exc:  # 交互模式下不退出
            console.print(f"[red]执行出错: {exc}[/red]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ettj", description="ETTJ 只读 SQL 问答 Agent")
    parser.add_argument("--model", help="覆盖 .env 的 MODEL，如 openai:gpt-6.1-sol")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印工具调用过程")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="检查配置与数据库连通")
    ask_parser = sub.add_parser("ask", help="问一个问题后退出")
    ask_parser.add_argument("question")
    sub.add_parser("chat", help="多轮交互（带对话记忆）")

    args = parser.parse_args(argv)
    setup_logging()
    setup_tracing()

    if args.command == "check":
        return cmd_check()
    if args.command == "ask":
        return cmd_ask(args.question, args.model, args.verbose)
    if args.command == "chat":
        return cmd_chat(args.model, args.verbose)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
