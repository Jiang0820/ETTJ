"""把某个会话的对话导出成 Markdown 文件（只在代码端做，界面上不加按钮）。

用法：
    python scripts/try_export.py                  # 列出所有会话（编号 + 消息数 + 最后时间）
    python scripts/try_export.py f1b19644         # 把这一个会话导出到 docs\会话记录\f1b19644.md
    python scripts/try_export.py f1b19644 -f      # 连工具调用和查询结果一起导出（默认只导问答文字）
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 让脚本能 import 到项目里的 ettj 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.config import settings  # 用来拿到 checkpoint 数据库的路径
from ettj.memory.checkpointer import get_checkpointer, thread_config  # 读回历史消息

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "会话记录"  # 导出文件放这里

ROLE_NAMES = {"human": "你", "ai": "助手", "tool": "工具结果", "system": "系统提示词"}


def list_sessions() -> None:
    """列出所有会话：按最后更新时间倒序，并显示对话的第一句话，方便认出是哪一个。"""
    path = settings.checkpoint_path
    if not path.exists():
        print("还没有任何会话记录:", path)
        return

    # 先从 sqlite 里按 thread_id 分组，拿到每个会话有多少条 checkpoint 记录
    conn = sqlite3.connect(str(path))
    rows = conn.execute(
        "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id"
    ).fetchall()
    conn.close()

    # 再用 checkpointer 读回每个会话的最后状态，拿时间和第一句问话
    checkpointer = get_checkpointer()
    sessions = []
    for thread_id, count in rows:
        saved = checkpointer.get(thread_config(thread_id)) or {}
        messages = saved.get("channel_values", {}).get("messages", [])
        first_ask = next(
            (message_text(m) for m in messages if getattr(m, "type", "") == "human"), ""
        )
        sessions.append(
            {
                "thread_id": thread_id,
                "count": count,
                "msg": len(messages),
                "ts": str(saved.get("ts", "")),  # 形如 2026-11-20T03:46:01.857814+00:00
                "first": first_ask.replace("\n", " ")[:34],
            }
        )

    sessions.sort(key=lambda s: s["ts"], reverse=True)  # 最近的排最前

    print(f"checkpoint 文件: {path}")
    print(f"共 {len(sessions)} 个会话（按最后更新时间倒序）：\n")
    print("时间(UTC)            会话        消息数  对话开头")
    for s in sessions:
        ts = s["ts"][:16].replace("T", " ")  # 只留到分钟
        print(f"{ts:20s} {s['thread_id']:10s} {s['msg']:>4}   {s['first']}")
    print("\n导出某一个：python scripts/try_export.py <会话编号>")


def message_text(msg) -> str:
    """取出一条消息里的文字内容（不同消息类型的存放位置不一样）。"""
    text = getattr(msg, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = getattr(msg, "content", "")
    return content if isinstance(content, str) else str(content)


def export(thread_id: str, with_tools: bool) -> None:
    """从 checkpointer 里读回这个会话的全部消息，写成 markdown。"""
    checkpointer = get_checkpointer()
    saved = checkpointer.get(thread_config(thread_id))  # 拿到该会话最后存下的状态
    messages = (saved or {}).get("channel_values", {}).get("messages", [])

    if not messages:
        print(f"会话 {thread_id} 里没有消息，编号对吗？先用不带参数的方式看一下列表")
        return

    lines = [
        f"# 会话 {thread_id}",
        "",
        f"- 导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 消息条数：{len(messages)}",
        f"- 数据来源：{settings.checkpoint_path}",
        "",
        "---",
        "",
    ]

    for msg in messages:
        kind = getattr(msg, "type", "")
        if kind == "system":
            continue  # 提示词太长，不导出

        if kind == "tool" and not with_tools:
            continue  # 默认不导工具返回的原始数据

        # AI 消息如果调用了工具，额外标一行调了什么（只标名字，不贴整段 SQL，除非 -f）
        calls = getattr(msg, "tool_calls", None) or []
        if calls and (with_tools or kind == "ai"):
            for call in calls:
                sql = (call.get("args") or {}).get("sql")
                label = f"`{call.get('name')}`" + (f" → `{sql[:120]}`" if sql and with_tools else "")
                lines.append(f"> 调用 {label}")
            lines.append("")

        text = message_text(msg).strip()
        if text:
            lines.append(f"**{ROLE_NAMES.get(kind, kind)}**：{text}")
            lines.append("")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{thread_id}.md"
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {len(messages)} 条消息 -> {out_file}")


def main() -> None:
    raw = sys.argv[1:]
    with_tools = "-f" in raw  # 是否连工具调用与查询结果一起导出
    args = [a for a in raw if a != "-f"]

    if not args:
        list_sessions()
        return

    export(args[0], with_tools)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 出错只打一行，不甩整屏 traceback
        print("出错:", str(exc)[:300])
