"""查看采购询价系统的表：直接运行即可。

用法：
    python scripts/try_procurement.py                  # 列出 12 张表的行数
    python scripts/try_procurement.py jd_material      # 看这张表的字段 + 前 5 行
"""

import sys
from pathlib import Path

# 让脚本能 import 到项目里的 ettj 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.tools.sql import get_engine  # 只读引擎，写操作会被数据库拒绝

# 采购询价系统的 12 张表，按业务分组（分组只是方便看，不影响查询）
TABLES = [
    # 一、采购需求
    "jd_purapply_order",  # 金蝶需求列表（需求单主表）
    "jd_purapply_order_detail_item",  # 需求物料明细
    # 二、物料主数据
    "jd_material",  # 物料表
    "jd_material_group",  # 物料分类表
    # 三、供应商
    "jd_supplier",  # 供应商表
    "biz_material_supplier",  # 物料分类 ↔ 供应商对应关系
    "biz_supplier_contact",  # 供应商联系人（微信号、是否主要联系人）
    # 四、询价流程
    "biz_purchase_order",  # 询价单主表
    "biz_purchase_order_item",  # 询价物料明细
    "biz_purchase_order_item_supplier",  # 物料 ↔ 供应商报价记录
    "biz_purchase_order_file",  # 询价附件
    # 五、审批结果
    "biz_purchase_order_checkresult",  # 询价单审批结果
]

SHOW_ROWS = 5  # 看单张表时最多打印几行


def list_counts(conn) -> None:
    """默认动作：列出 12 张表各自有多少行。"""
    print("当前库:", conn.exec_driver_sql("SELECT DATABASE()").scalar())
    print("\n序号  表名                                        行数")
    for i, name in enumerate(TABLES, start=1):
        try:
            # COUNT(*) 查这张表一共有多少条记录
            rows = conn.exec_driver_sql(f"SELECT COUNT(*) FROM `{name}`").scalar()
            print(f"{i:>4}  {name:42s} {rows:>7}")
        except Exception as exc:
            print(f"{i:>4}  {name:42s} 查询失败: {str(exc)[:60]}")


def show_table(conn, name: str) -> None:
    """看单张表：先列字段（DESC），再取前几行数据。"""
    print(f"--- {name} 的字段 ---")
    for row in conn.exec_driver_sql(f"DESC `{name}`").fetchall():
        # DESC 每行是：字段名 / 类型 / 是否可空 / 键 / 默认值 / 附加信息
        print("   ", row)

    print(f"\n--- {name} 的前 {SHOW_ROWS} 行 ---")
    cur = conn.exec_driver_sql(f"SELECT * FROM `{name}` LIMIT {SHOW_ROWS}")
    print("    列名:", [c for c in cur.keys()])
    for row in cur.fetchall():
        print("   ", row)


def main() -> None:
    # sys.argv 是命令行参数列表；[0] 是脚本名，[1] 才是用户输入的第一个参数
    target = sys.argv[1] if len(sys.argv) > 1 else None

    with get_engine().connect() as conn:  # 借一条只读连接，用完自动归还
        if target:
            show_table(conn, target)
        else:
            list_counts(conn)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 出错只打一行，不再甩整屏 traceback
        print("出错:", str(exc)[:300])
