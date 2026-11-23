"""网页版对话窗口：只用 Python 标准库，不需要安装任何界面/前端库。

运行：python scripts\try_web.py
然后浏览器打开 http://127.0.0.1:8000 （脚本会自动帮你打开）

设计原则：
- 不碰 ettj 里的任何代码，只 import 现成的 build_sql_agent / checkpointer
- 数据库与模型配置全部来自 .env，网页里没有任何配置项
- 多轮对话靠 thread_id + checkpointer，和命令行 chat 用的是同一套
"""

import json
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 让脚本能 import 到项目里的 ettj 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.agents.sql_agent import build_sql_agent
from ettj.config import settings
from ettj.memory.checkpointer import get_checkpointer, thread_config

HOST = "127.0.0.1"  # 只在本地监听，不对外网开放
PORT = 8000

_agent = None  # 复用同一个 Agent，避免每次请求都重新初始化
_agent_lock = threading.Lock()


def get_agent():
    """第一次用到时创建 Agent（带 checkpointer，所以支持多轮）。"""
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = build_sql_agent(checkpointer=get_checkpointer())
        return _agent


def last_ai_text(result: dict) -> str:
    """取 Agent 返回消息里最后一条有文字的模型回复。"""
    for msg in reversed(result["messages"]):
        if getattr(msg, "type", "") == "ai" and getattr(msg, "text", "").strip():
            return msg.text
    return "（模型没有返回内容）"


# ---------------------------------------------------------------- 前端页面
PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>ETTJ 数据库问答</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Microsoft YaHei", system-ui, sans-serif; background: #f5f6f8; }
  header { padding: 12px 16px; background: #fff; border-bottom: 1px solid #e3e5e8; }
  header h1 { margin: 0; font-size: 16px; color: #222; }
  header p { margin: 4px 0 0; font-size: 12px; color: #777; }
  main { max-width: 900px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; height: calc(100vh - 64px); }
  #chat { flex: 1; overflow-y: auto; padding-right: 6px; }
  .msg { margin-bottom: 12px; display: flex; }
  .msg.user { justify-content: flex-end; }
  .bubble { max-width: 78%; padding: 10px 14px; border-radius: 10px; line-height: 1.6; font-size: 14px; white-space: pre-wrap; word-break: break-word; }
  .user .bubble { background: #2563eb; color: #fff; }
  .bot .bubble { background: #fff; color: #222; border: 1px solid #e3e5e8; }
  .bot .bubble.waiting { color: #888; }
  #bar { display: flex; gap: 8px; padding-top: 12px; }
  #q { flex: 1; padding: 10px 12px; font-size: 14px; border: 1px solid #d5d8dd; border-radius: 8px; font-family: inherit; resize: none; height: 46px; }
  #send { padding: 0 18px; border: none; border-radius: 8px; background: #2563eb; color: #fff; font-size: 14px; cursor: pointer; }
  #send:disabled { background: #a9b6d6; cursor: default; }
  #new { padding: 0 14px; border: 1px solid #d5d8dd; border-radius: 8px; background: #fff; font-size: 14px; cursor: pointer; }
</style>
</head>
<body>
<header>
  <h1>ETTJ 数据库问答</h1>
  <p>MODEL_MODEL_PLACEHOLDER　|　MODEL_DB_PLACEHOLDER　|　会话 <span id="tid">MODEL_THREAD_PLACEHOLDER</span></p>
</header>
<main>
  <div id="chat"></div>
  <div id="bar">
    <textarea id="q" placeholder="例如：物料 AAHC3901-0018 历史最低价（回车发送，Shift+回车换行）"></textarea>
    <button id="send">发送</button>
    <button id="new">新会话</button>
  </div>
</main>
<script>
let thread = "MODEL_THREAD_PLACEHOLDER";   // 一个 thread 就是一段对话，多轮靠它
const chat = document.getElementById("chat");
const q = document.getElementById("q");
const send = document.getElementById("send");

function add(role, text) {
  const row = document.createElement("div");
  row.className = "msg " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble" + (role === "bot" ? " waiting" : "");
  bubble.textContent = text;
  row.appendChild(bubble);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

async function ask() {
  const text = q.value.trim();
  if (!text) return;
  q.value = "";
  add("user", text);
  const bubble = add("bot", "正在查询数据库…");
  send.disabled = true;

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, thread: thread })
    });
    const data = await resp.json();
    bubble.textContent = data.answer;
    bubble.classList.remove("waiting");
    thread = data.thread;   // 服务端可能会补一个 thread_id，记住它才能连续追问
    document.getElementById("tid").textContent = thread;   // 顶部始终显示当前会话编号
  } catch (e) {
    bubble.textContent = "请求失败：" + e;
    bubble.classList.remove("waiting");
  } finally {
    send.disabled = false;
    q.focus();
  }
}

send.onclick = ask;
q.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
});
document.getElementById("new").onclick = () => {
  thread = Math.random().toString(16).slice(2, 10);   // 换 thread = 上下文清空
  document.getElementById("tid").textContent = thread;   // 顶部那行也跟着换成新编号
  add("bot", "（已开启新会话 " + thread + "）");
};
q.focus();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 服务端逻辑
class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        """只提供首页；其他路径一律 404。"""
        if self.path not in ("/", "/index.html"):
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        # 把模型名、库信息、初始会话号填进页面
        page = (
            PAGE.replace("MODEL_MODEL_PLACEHOLDER", settings.model)
            .replace("MODEL_DB_PLACEHOLDER", settings.mask_mysql())
            .replace("MODEL_THREAD_PLACEHOLDER", uuid.uuid4().hex[:8])
        )
        self._send(200, page, "text/html; charset=utf-8")

    def do_POST(self) -> None:
        """接收一个问题，调 Agent 查库，把回答以 JSON 返回。"""
        if self.path != "/ask":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, '{"answer":"请求格式不对"}', "application/json; charset=utf-8")
            return

        question = (payload.get("question") or "").strip()
        thread = (payload.get("thread") or "").strip() or uuid.uuid4().hex[:8]
        if not question:
            self._send(400, '{"answer":"问题不能为空"}', "application/json; charset=utf-8")
            return

        try:
            # 只传本轮问题，历史由 checkpointer 按 thread 自动带回来
            result = get_agent().invoke(
                {"messages": [{"role": "user", "content": question}]},
                config=thread_config(thread),
            )
            answer = last_ai_text(result)
        except Exception as exc:
            answer = "出错：" + str(exc)[:300]

        body = json.dumps({"answer": answer, "thread": thread}, ensure_ascii=False)
        self._send(200, body, "application/json; charset=utf-8")

    def log_message(self, *args) -> None:
        """屏蔽默认的访问日志，控制台只留启动信息。"""
        return


def main() -> None:
    url = f"http://{HOST}:{PORT}"
    print("模型:", settings.model)
    print("数据库:", settings.mask_mysql())
    print(f"页面地址: {url}  （关掉这个窗口服务就停了）")

    server = ThreadingHTTPServer((HOST, PORT), Handler)  # 多线程，避免一个请求卡住全部
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()  # 1 秒后自动打开浏览器
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("出错:", str(exc)[:300])
