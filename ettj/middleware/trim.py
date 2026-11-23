"""上下文裁剪：会话越聊越长时，自动清掉旧的工具返回，避免顶到模型上下文上限。

思路：一轮问答里真正占 token 的是 SQL 查询结果（几十上百行数据），
对话本身的文字很少。所以不清对话，只清"旧的那几条工具返回"，
把最近几次查询结果留着，更早的换成一句占位符。
用的是 LangChain 1.5 自带的 ContextEditingMiddleware，不自己写逻辑。
"""

from __future__ import annotations

from langchain.agents.middleware import ClearToolUsesEdit, ContextEditingMiddleware

# 输入 token 超过这个数就开始清理。方舟 lite 类模型窗口一般几万 token，
# 留出余量给这一轮的回答，取 12000。
TRIGGER_TOKENS: int = 12000

# 最近 N 条工具返回必须保留（模型正在用它们推理，清掉会答错）
KEEP_TOOL_RESULTS: int = 3


def build_trim_middleware() -> ContextEditingMiddleware:
    """造一个裁剪中间件，挂到 create_agent 的 middleware 列表里即可生效。"""
    return ContextEditingMiddleware(
        edits=[
            ClearToolUsesEdit(
                trigger=TRIGGER_TOKENS,          # 超了才动手，没超什么都不做
                keep=KEEP_TOOL_RESULTS,          # 最近几条工具结果原样留着
                clear_tool_inputs=False,         # 工具入参（就是那条 SQL）不清，方便回看
                placeholder="[历史查询结果已清理]",  # 清掉的位置换成这句话
            )
        ]
    )
