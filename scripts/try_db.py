"""最简单的"看看库里有什么"脚本：直接运行即可。

运行方式：PyCharm 右键 Run，或命令行 python scripts/try_db.py
"""

import sys
from pathlib import Path

# 让脚本能 import 到项目里的 ettj 包（和 scripts/try_llm.py 的写法一样）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.tools.sql import get_engine  # 只读引擎：连接一建立就被钉成 READ ONLY


def main() -> None:
    # with ... as conn：借一条连接，代码块结束后自动关闭并还给连接池
    with get_engine().connect() as conn:
        # 1. 先确认连的是谁
        print("服务器版本 :", conn.exec_driver_sql("SELECT VERSION()").scalar())
        print("当前所在的库:", conn.exec_driver_sql("SELECT DATABASE()").scalar())

        # 2. 这台服务器上有哪些库（一个库 = 一个项目的数据集合）
        print("\n--- 所有数据库 ---")
        for row in conn.exec_driver_sql("SHOW DATABASES").fetchall():
            print("   ", row[0])

        # 3. 当前库里有哪张表（SHOW 语句不支持 LIMIT，所以在 Python 里切片取前 20 张）
        print("\n--- 当前库的表 ---")
        tables = conn.exec_driver_sql("SHOW TABLES").fetchall()
        print(f"    共 {len(tables)} 张，下面只打印前 20 张：")
        for row in tables[:20]:
            print("   ", row[0])

        # 4. 看某一张表的字段（表名不写死，直接取上面清单里的第一张）
        #    之所以不写死：表是"属于某个库"的，换了 MYSQL_DB 之后旧表名可能就不在这个库里了
        if not tables:
            print("\n当前库没有表")
            return
        sample = tables[0][0]
        print(f"\n--- 表 {sample} 有哪些字段 ---")
        for row in conn.exec_driver_sql(f"DESC `{sample}`").fetchall():
            print("   ", row)

        # 5. 看这张表的前 3 行数据（真正"看到内容"的一步）
        print(f"\n--- 表 {sample} 的前 3 行 ---")
        cur = conn.exec_driver_sql(f"SELECT * FROM `{sample}` LIMIT 3")
        print("    列名:", [c for c in cur.keys()])
        for row in cur.fetchall():
            print("   ", row)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 出错只打一行，不再甩整屏 traceback
        print("出错:", str(exc)[:300])
