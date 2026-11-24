# ETTJ

基于 LangChain 1.5 的 Agent 工作台。当前落地一条完整链路：只读 MySQL 的自然语言问答 Agent。

## 目录与 LangChain 架构的对应

| 路径 | 对应组件 | 职责 |
|---|---|---|
| `ettj/config.py` | — | 唯一配置入口，所有 `.env` 读取都在这里 |
| `ettj/models.py` | `langchain` / `init_chat_model` | 模型工厂，换 provider 只改 `MODEL` |
| `ettj/prompts/sql_agent.md` | Prompt | 系统提示词，与代码分离便于迭代 |
| `ettj/tools/sql.py` | `langchain-core` 的 `@tool` | 能力边界：三个只读查询工具 |
| `ettj/agents/sql_agent.py` | `langchain` 的 `create_agent` | Agent 组装，模型与工具从下层注入 |
| `ettj/middleware/` | `langchain.agents.middleware` | 横切逻辑：`audit.py` 打日志，`trim.py` 长会话裁剪 |
| `ettj/pipelines/graph.py` | `langgraph` | 图编排：多 agent、校验节点、批处理 |
| `ettj/memory/checkpointer.py` | LangGraph checkpoint | 按 `thread_id` 持久化多轮会话 |
| `ettj/observability/tracing.py` | LangSmith | 轨迹与评估开关 |
| `scripts/check_env.py` | — | 环境体检，部署前先跑 |
| `scripts/try_llm.py` | — | 模型连通性试跑脚本，直接运行即可 |
| `scripts/try_ask.py` | — | 命令行问答试跑（`-v` 看 SQL，多轮可追问） |
| `scripts/try_web.py` | — | 网页版对话窗口，浏览器访问本地端口 |
| `scripts/try_export.py` | — | 把某个会话导出成 Markdown |
| `scripts/try_db.py` `try_procurement.py` `try_relations.py` `try_quote.py` | — | 看库/看表/验关系/跑报价分析的只读小脚本 |
| `docs/` | — | 关系笔记 `采购12表关系.md`、会话导出 `会话记录/` |
| `data/` `logs/` `notebooks/` | — | 运行产物、导出、实验 |

依赖方向是单向的：`config → models/tools → agents → pipelines/cli`，下层不反向依赖上层。

## 本地环境（作者本机实测通过）

| 项 | 版本 / 说明 |
|---|---|
| 操作系统 | Windows 11，项目位于 `D:\AI_Development\Projects\ETTJ` |
| Python | 3.13.18（conda 环境名 `langchain1.5`） |
| langchain | 1.5.0 |
| langchain-core | 1.8.1 |
| langgraph | 1.2.22 |
| langchain-openai | 1.8.1（走 `openai:` provider 接方舟） |
| openai | 3.55.0 |
| SQLAlchemy | 2.1.9 |
| PyMySQL | 1.2.4 |
| python-dotenv | 1.2.4 |
| 数据库 | MySQL 8.0.45，只读会话（库地址与账号不进仓库，只放本地 `.env`） |
| 模型 | 火山方舟 `doubao-seed-2-1-lite-260915` |
| 界面 | 标准库 `http.server`（无第三方 Web 框架） |

从零复现：

```powershell
conda create -n langchain1.5 python=3.13 -y
conda activate langchain1.5
cd D:\AI_Development\Projects\ETTJ
pip install -e ".[openai]"
copy .env.example .env      # 本仓库不含 .env，请按「快速开始」自己填
```

> `.env` 与 `data/*.sqlite`（会话记录）已在 `.gitignore` 中，不会提交到仓库。

## 快速开始

```powershell
conda activate langchain1.5
cd D:\AI_Development\Projects\ETTJ

python scripts/check_env.py          # 先看缺什么
# 编辑 .env，至少填 MYSQL_DB、MYSQL_PASSWORD、VOLCENGINE_API_KEY
python scripts/check_env.py          # 再跑一次，四项应全 OK

python -m ettj.cli check             # 只验数据库连通
python -m ettj.cli ask "最近30天每天订单量"
python -m ettj.cli chat              # 多轮，带对话记忆
python -m ettj.cli -v ask "..."      # 打印每一步工具调用
```

火山方舟的两个必填项（方舟兼容 OpenAI 协议）：

```ini
VOLCENGINE_API_KEY='...'
VOLCENGINE_BASE_URL='https://ark.cn-beijing.volces.com/api/v3'   # 只到 /api/v3，别带 /chat/completions
MODEL=doubao-seed-2-1-lite-260915                                 # 真实 Model ID 带版本号，可在 /api/v3/models 查
```

## 网页版对话窗口

```powershell
python scripts/try_web.py            # 启动后自动打开 http://127.0.0.1:8000
```

单页对话窗口，只做一件事：把问题发给 Agent、显示回答。模型、数据库全部来自 `.env`，页面里没有任何配置项；`ettj/` 一行不改，脚本只是复用 `build_sql_agent` + `checkpointer`。

- **多轮**：页面顶部的 8 位编号就是 `thread_id`，同一编号内模型记得上文；点「新会话」换编号即清空上下文。
- **保存记录**：会话自动存在 `data/checkpoints.sqlite`；要可读版本用 `python scripts/try_export.py <thread_id>`，导出到 `docs/会话记录/<thread_id>.md`。
- **查会话编号**：忘了编号就跑 `python scripts/try_export.py`，列表按更新时间倒序列出「时间 + 消息数 + 对话开头」，扫一眼就能认出来。

## 长会话自动裁剪

同一会话内所有消息都累积在 checkpoint 里，越聊越长，迟早顶到模型上下文上限。`ettj/middleware/trim.py` 用 LangChain 自带的 `ContextEditingMiddleware` + `ClearToolUsesEdit` 解决：输入 token 超过 12000 时，把**旧的工具返回**（也就是那些几十行的 SQL 结果）换成一句 `[历史查询结果已清理]`，最近 3 条结果原样保留。

刻意只清工具返回、不清对话轮次——占 token 的几乎全是查询数据，对话文字很少，这样既能压住体积，又不会让模型忘掉刚才聊了什么。实测：6 轮大结果 30220 token → 15223 token。

调参在文件顶部两个常量：`TRIGGER_TOKENS`（触发阈值）、`KEEP_TOOL_RESULTS`（保留几条）。不想用时 `build_sql_agent(use_trim=False)`。

和额度直接相关的三个旋钮：

| 旋钮 | 位置 | 当前值 | 作用 |
|---|---|---|---|
| `SQL_MAX_ROWS` | `.env` | 50 | 单次查询最多返回几行，超出会明确提示"已截断" |
| `SQL_MAX_CHARS` | `.env` | 6000 | 返回文本总长度上限，超了按字符硬截 |
| `TRIGGER_TOKENS` | `ettj/middleware/trim.py` | 12000 | 超过就往回清旧工具返回 |

明细类问题只拿 50 行时，聚合类问题（总数、家数、均价）不受影响——提示词要求这类问题走 `COUNT/GROUP BY`，所以结论仍完整，省下的都是重复传输的明细。

## 当前数据范围

默认库是 `procurement`，业务问题只用 12 张采购询价表回答；表名、主键、状态字典、表间关系、字段坑与报价口径都写在 `ettj/prompts/sql_agent.md` 里（知识小且稳定，所以放提示词，没有做向量库）。

业务侧的口径约束（来自公司 2026-11 回复信，已写进提示词）：

| 约束 | 落地方式 |
|---|---|
| 只查正式租户 | 所有查询固定带 `WHERE tenant_id = 'tenant_id_000001'`，回答不提租户编号 |
| 禁止查旧快照 | 库里有 `*_copy1` 表（同步前的备份，数据过期），提示词明令禁用 |
| 金额口径 | 一律视为**含税价**，不再标"未知" |
| 禁用词 | 不出现"中标""成交价"，改称"审批通过价格" |
| 供应商展示 | 用 `jd_supplier.name`，不用 `supplier_code`；join 时必带 `tenant_id` |
| 报价进度三分类 | 已完成 = 询价单 `status IN (2,3)`；报价中 = `status = 1`；未完成 = 询价单 `status = 1` 的单 + 需求明细 `conn_status IN (0, NULL)` 的行（两者粒度不同，须分别说清） |
| 采购员业绩 | 按 `creat_man` 分组、`COUNT(DISTINCT order_id)`，不能按明细行 |
| 新供应商 | 用 `jd_supplier.createtime` 判建档时间窗口（默认近 90 天） |

其他口径：

- **状态字典来自表字段注释，不是猜的**：`status` 1 询价中 / 2 已报价 / 3 已关闭；`close_type` 1 正常完成 / 2 超时；`conn_status` 0 或 NULL 待询价 / 1 询价中 / 2 已报价
- `mysql_table_schema` 通过 SQLAlchemy 反射读取，**返回的字段带 `-- 注释`、末尾带表注释**，字段含义优先信注释
- 有效报价 = `quote_price > 0`；`price` / `priceandtax` / `historyprice` / `last_price` 实际没有可用数据
- `biz_purchase_order_checkresult` 只有十余条，成交侧样本极少
- 数据持续写入，行数每天在变，别引用固定行数
- 关系与实测结论见 `docs/采购12表关系.md`

## 只读怎么保证

| 层 | 实现 | 位置 |
|---|---|---|
| 账号 | 只授 `SELECT`（推荐） | 数据库侧，需你自己建账号 |
| 会话 | `SET SESSION TRANSACTION READ ONLY` | `tools/sql.py` 的 connect 钩子 |

代码层不做任何 SQL 过滤，只依靠会话级只读：连接一建立就被钉死，DML/DDL 一律被服务器拒绝。

## 常见扩展点

- **加工具**：在 `ettj/tools/` 下新建模块，用 `@tool` 装饰，再加进 `SQL_TOOLS`。工具描述直接决定模型什么时候调它，要写清输入格式。
- **加中间件**：1.5 自带 `ModelRetryMiddleware`、`ModelCallLimitMiddleware`、`ToolCallLimitMiddleware`、`SummarizationMiddleware`、`ContextEditingMiddleware`、`PIIMiddleware`、`HumanInTheLoopMiddleware`。需要写操作时用 `HumanInTheLoopMiddleware(interrupt_mode="per_call")`（1.4.6 起）逐次确认。
- **加图节点**：`pipelines/graph.py` 里 `builder.add_node(...)`，适合放结果校验、人工审核、多源汇总。
- **接 MCP**：1.4 起 MCP 已内置，`pip install "langchain[mcp]"` 后用 `langchain.mcp.MCPAdapter`，不再需要 `langchain-mcp-adapters`。
- **深度研究型 Agent**：`pip install deepagents`，自带规划、子 agent、文件系统工具。
- **开 LangSmith**：`.env` 里 `LANGSMITH_TRACING=true` 并填 key，轨迹会进 `LANGSMITH_PROJECT`。

## 已知限制

- 只有只读能力，写操作需要另建工具并加人工确认。
- 方舟账号额度用完会报 `429 usage limit`（"安全体验模式"的免费额度用尽即暂停服务），到模型开通页面调整或关闭该模式，与代码无关。
- 表结构在进程内缓存，改了表要 `/refresh` 或重启。
- 表名大小写：Linux 上 `lower_case_table_names=0` 时大小写敏感，12 张表名已写在提示词里，跨库查别的表要先拿原始写法。
- 生产环境务必给只读账号限定来源 IP，公网再加 `REQUIRE SSL`。
