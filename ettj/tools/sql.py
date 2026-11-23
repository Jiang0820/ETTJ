"""数据访问层：MySQL 只读连接 + 三个查询工具。

只读只靠一处兜底：连接建立时 SET SESSION TRANSACTION READ ONLY，
服务器端直接拒绝写操作，代码里不做任何 SQL 过滤。
"""

from __future__ import annotations  # 让类型注解延迟求值，才能写 list[str]、-> Engine

from functools import lru_cache  # 缓存函数结果，保证引擎全局只创建一次
from typing import Any  # "任意类型"，用于不挑类型的地方

from langchain.tools import tool  # 把普通函数包装成大模型可以调用的工具
from sqlalchemy import create_engine, event, inspect  # 建引擎 / 挂事件 / 反射表结构
from sqlalchemy.engine import Engine  # 只用于类型标注，运行时不参与

from ..config import settings  # 全局配置对象，值都来自项目根目录的 .env

# 表名 -> 建表语句文本。放在模块级 = 进程内共享，同一张表第二次问不用再查库
_schema_cache: dict[str, str] = {}

MAX_ROWS = settings.sql_max_rows  # 单次查询最多返回多少行（SQL_MAX_ROWS，默认 100）
MAX_CHARS = settings.sql_max_chars  # 返回文本总长度上限（SQL_MAX_CHARS，默认 12000）
SAMPLE_ROWS = settings.sql_sample_rows  # 表结构里附带几行样本数据（默认 3）
TIMEOUT_MS = settings.sql_statement_timeout_ms  # 单条语句最长执行毫秒数（默认 15000）


# --------------------------------------------------------------- 连接

# @lru_cache(maxsize=1)：第二次调用 get_engine() 不会再建引擎，直接返回第一次那个，
# 所以全项目共用一个连接池。
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    engine = create_engine( #create 造一个连接工厂
        settings.mysql_url(), #连接串来自 `config.py` 的 `mysql_url()`
        pool_pre_ping=True, #每次从池里拿连接前先 ping 一下，坏连接自动换掉。
        pool_recycle=3600, #连接活满 1 小时就回收重建，防止被服务器单方面踢掉后拿到 "僵尸连接"。
        pool_size=settings.mysql_pool_size, # 常驻 5 条连接；
        max_overflow=settings.mysql_pool_size, #`max_overflow` 高峰时最多再临时加 5 条。
        connect_args={  # 这里的键值原样透传给 pymysql，SQLAlchemy 不解析
            "connect_timeout": settings.mysql_connect_timeout,  # 建立连接超时（秒）
            "read_timeout": 30,  # 读取超时（秒）
            "write_timeout": 30,  # 写入超时（秒）
        },
    )

    # connect 事件：连接池每新建一条底层连接都会走这里，所以只读是"每条连接"级别的
    @event.listens_for(engine, "connect")
    def _force_readonly(dbapi_conn, _record):  # noqa: ANN001  dbapi_conn 是 pymysql 原始连接
        cur = dbapi_conn.cursor()  # 游标：在这条连接上执行 SQL 的句柄
        try:
            if settings.sql_read_only:  # 对应 .env 里的 SQL_READ_ONLY=true
                # 唯一的一道只读防线：本会话设成只读事务，之后任何写操作都会被 MySQL 拒绝
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            # 单条语句最多跑 15 秒，超时由服务器中断查询，避免大表全扫描把连接拖死
            cur.execute(f"SET SESSION max_execution_time = {TIMEOUT_MS}")
        except Exception:
            # 老版本 MySQL 不支持 max_execution_time 时忽略，不阻断连接
            pass
        finally:
            cur.close()  # 无论成功失败都关闭游标，避免连接泄漏

    return engine  # 注意：因为上面的缓存，这段函数体整个进程只真正跑一次


def refresh_schema_cache() -> None:
    """清空表结构缓存。改过表结构后调用一次就能拿到最新的。"""
    _schema_cache.clear()  # 直接清空字典


# --------------------------------------------------------------- 格式化
def _cell(value: Any, limit: int = 80) -> str:
    """把一个单元格的值转成一行文本。"""
    if value is None:
        return "NULL"  # 数据库的 NULL 显示成 NULL，而不是 Python 的 None，模型更好理解
    # 真实换行替换成字面量 \n（否则会把拼好的表格撑散），\r 直接删掉
    text = str(value).replace("\n", "\\n").replace("\r", "")
    # 单格太长就截断：保留 79 个字符加一个省略号，合计 80
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_rows(columns: list[str], rows: list[Any]) -> str:
    """把二维结果拼成 'a | b' 这种纯文本表格。"""
    if not rows:
        return "(0 行)"  # 空结果明确写出来，比返回空字符串更清楚
    header = " | ".join(columns)  # 列名用竖线连起来
    # 嵌套推导式：外层遍历行，内层把每个单元格转文本，行与行之间用换行连接
    body = "\n".join(" | ".join(_cell(v) for v in row) for row in rows)
    return f"{header}\n{body}"


def _truncate(payload: str) -> str:
    """总文本超过 MAX_CHARS 就截断，避免把几万字符塞给模型（贵且慢）。"""
    if len(payload) <= MAX_CHARS:
        return payload
    return payload[:MAX_CHARS] + f"\n...(已截断，原始长度 {len(payload)} 字符)"


def list_tables() -> list[str]:
    """返回当前库的所有表名（通过反射读 information_schema）。"""
    return inspect(get_engine()).get_table_names()


def describe_table(table: str) -> str:
    """返回某张表的建表语句形式文本：字段、主外键、表注释、3 行样本数据。"""
    if table in _schema_cache:  # 先查缓存，命中就直接返回，不重复查库
        return _schema_cache[table]

    insp = inspect(get_engine())  # 反射器：能读列、主键、外键、注释等元数据
    existing = insp.get_table_names()
    if table not in existing:
        # 表不存在时不仅报错，还把可用表名一起给出——方便模型自己改口重问
        return f"Error: 表 {table} 不存在。可用表: {', '.join(existing)}"

    lines: list[str] = []  # 攒每一列的 DDL 片段
    for col in insp.get_columns(table):  # get_columns 返回每个字段的字典
        piece = f"  `{col['name']}` {col['type']}"  # 反引号是 MySQL 的标识符转义
        if not col.get("nullable", True):  # 取不到这个键时默认当作可空
            piece += " NOT NULL"
        if col.get("default") is not None:
            # 用 is not None 判断：默认值是 0 或空字符串时不能用真假判断
            piece += f" DEFAULT {col['default']}"
        if col.get("comment"):
            piece += f"  -- {col['comment']}"  # 字段注释给模型理解含义，比字段名可靠
        lines.append(piece)

    # 链式防御：可能返回 None，用 or {} / or [] 兜成空字典、空列表
    pks = (insp.get_pk_constraint(table) or {}).get("constrained_columns") or []
    if pks:
        lines.append("  PRIMARY KEY (" + ", ".join(f"`{k}`" for k in pks) + ")")
    for fk in insp.get_foreign_keys(table):  # 逐条外键拼成标准写法
        lines.append(
            "  FOREIGN KEY ("
            + ", ".join(fk["constrained_columns"])
            + f") REFERENCES `{fk['referred_table']}` ("
            + ", ".join(fk["referred_columns"])
            + ")"
        )

    # 所有列定义用逗号换行连起来，外面套 CREATE TABLE，产出一段像真 DDL 的文本
    # 不用 JSON 是因为大模型读 DDL 更自然
    ddl = f"CREATE TABLE `{table}` (\n" + ",\n".join(lines) + "\n)"

    try:
        comment = (insp.get_table_comment(table) or {}).get("text")
        if comment:
            ddl += f"\n-- 表注释: {comment}"
    except NotImplementedError:
        pass  # 有些 MySQL 版本/驱动不支持读表注释，跳过就好，不该让整个工具失败

    try:
        with get_engine().connect() as conn:  # with 结束会自动关闭连接并归还连接池
            # exec_driver_sql 把字符串原样发给驱动，适合 SHOW / DESC 这类非标准语句
            result = conn.exec_driver_sql(f"SELECT * FROM `{table}` LIMIT {SAMPLE_ROWS}")
            columns = [str(k) for k in result.keys()]
            rows = result.fetchmany(SAMPLE_ROWS)  # 只取需要的行，别用 fetchall 读整表
            ddl += "\n\n/* 样本数据:\n" + _fmt_rows(columns, rows) + "\n*/"
    except Exception as exc:
        ddl += f"\n\n/* 取样本失败: {exc} */"  # 取样本失败不影响整体结构，末尾留个说明

    _schema_cache[table] = ddl  # 存进缓存，下次直接命中
    return ddl


def run_query(sql: str) -> str:
    """直接执行 SQL。写操作由连接上的 READ ONLY 会话兜底拒绝。"""
    try:  # 整段包 try：这是给 Agent 用的工具，返回值必须是字符串，异常不能崩出去
        with get_engine().connect() as conn:  # 从池里借一条连接，用完自动归还
            result = conn.exec_driver_sql(sql)  # 原样执行，不做任何 SQL 改写
            if not result.returns_rows:
                # 没有结果集的语句，只报影响行数
                return f"执行成功，无结果集返回（影响行数: {result.rowcount}）"
            columns = [str(k) for k in result.keys()]
            rows = result.fetchmany(MAX_ROWS + 1)  # 故意多取 1 行，用来判断"是否还有更多"
            more = len(rows) > MAX_ROWS  # 取到 101 行说明被截断了
            rows = rows[:MAX_ROWS]  # 真正返回的只保留前 100 行
            payload = _fmt_rows(columns, rows)
            # 三元表达式：被截断就提示模型缩小范围，否则正常结束括号
            payload += f"\n(共返回 {len(rows)} 行" + ("，已截断，请缩小 WHERE 或 LIMIT)" if more else ")")
            return _truncate(payload)  # 最后再按总长度截一刀
    except Exception as exc:
        # 把 MySQL 原始错误原样返回，模型看到 Unknown column 之类会自行改 SQL
        return f"Error: {exc}"


# --------------------------------------------------------------- 工具
# 注意：下面三个函数的 docstring 不是给人看的，是写给大模型看的"说明书"
# 模型靠这段话判断什么时候调用、参数怎么传，所以里面写了不少行为约束
@tool
def mysql_list_tables() -> str:
    """列出当前数据库中的所有表名。输入为空字符串。查表结构前必须先调用它确认表名。"""
    tables = list_tables()
    if not tables:
        return "Error: 数据库中没有表，或当前账号无查看权限"
    return f"共 {len(tables)} 张表: " + ", ".join(tables)


@tool
def mysql_table_schema(table_names: str) -> str:
    """输入逗号分隔的表名，返回字段定义、主外键和最多 3 行样本数据。

    表名必须先用 mysql_list_tables 确认存在，不要臆造。"""
    # 一行做四件事：按逗号切分 -> 去空格 -> 去掉可能多写的反引号 -> 过滤空片段
    names = [t.strip().strip("`") for t in table_names.split(",") if t.strip()]
    if not names:
        return "Error: 未提供表名"
    return _truncate("\n\n".join(describe_table(t) for t in names))  # 多张表之间空一行


@tool
def mysql_run_query(sql: str) -> str:
    """执行一条 SQL 并返回结果集。连接是只读的，写操作会被数据库拒绝。

    报错会返回数据库原始错误，请据此改写后重试；遇到 Unknown column
    时先用 mysql_table_schema 核对字段。"""
    return run_query(sql)


# 这个列表就是对外接口：agents/sql_agent.py 把它交给 create_agent，模型能用的工具就是这三个
SQL_TOOLS = [mysql_list_tables, mysql_table_schema, mysql_run_query]
