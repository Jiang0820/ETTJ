"""验证 12 张采购表之间的关联关系（一对多 / 多对一）。

用法：python scripts/try_relations.py

判断思路：
- 主表那个字段「去重后数量 == 总行数」→ 值唯一，它才是关系里的「1」那头
- 子表同一字段会重复很多次 → 「多」那头
- 子表的去重值有多少能在主表里找到 → 关系到不到位（能不能真 join 上）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.tools.sql import get_engine  # 只读连接

# (子表, 子表字段, 主表, 主表字段, 人话说明)
RELATIONS = [
    ("jd_purapply_order_detail_item", "billno", "jd_purapply_order", "billno", "需求单 ← 明细"),
    ("jd_purapply_order_detail_item", "materialnumber", "jd_material", "number", "明细 → 物料"),
    ("jd_material", "group_number", "jd_material_group", "number", "物料 → 物料分类"),
    ("biz_material_supplier", "material_code", "jd_material", "group_number", "物料分类 → 供应商对应"),
    ("biz_material_supplier", "supplier_code", "jd_supplier", "number", "对应关系 → 供应商"),
    ("biz_supplier_contact", "supplier_number", "jd_supplier", "number", "联系人 → 供应商"),
    ("biz_purchase_order_item", "order_id", "biz_purchase_order", "order_id", "询价单 ← 物料行"),
    ("biz_purchase_order_item", "number", "jd_material", "number", "询价物料行 → 物料"),
    # 注意：biz_purchase_order_item 的主键叫 order_item_id（不是文档里说的 id）
    ("biz_purchase_order_item_supplier", "order_item_id", "biz_purchase_order_item", "order_item_id", "报价 → 物料行"),
    ("biz_purchase_order_item_supplier", "supplier_code", "jd_supplier", "number", "报价 → 供应商"),
    ("biz_purchase_order_file", "jd_id", "jd_purapply_order_detail_item", "id", "附件 → 需求明细"),
    ("biz_purchase_order_checkresult", "order_id", "biz_purchase_order", "order_id", "审批 → 询价单"),
    ("biz_purchase_order_checkresult", "order_item_id", "biz_purchase_order_item", "order_item_id", "审批 → 物料行"),
    (
        "biz_purchase_order_checkresult",
        "order_item_supplier_id",
        "biz_purchase_order_item_supplier",
        "id",
        "审批 → 报价",
    ),
]


def check(conn, child, child_col, parent, parent_col) -> str:
    """返回一行结论文字，例如「1:N  子表 432 行 / 131 个单据，主表字段唯一」。"""
    # 子表：多少行、这个字段去重后多少个值
    child_rows = conn.exec_driver_sql(f"SELECT COUNT(*) FROM `{child}`").scalar()
    child_dist = conn.exec_driver_sql(f"SELECT COUNT(DISTINCT `{child_col}`) FROM `{child}`").scalar()

    # 主表：这个字段是否唯一（唯一才能当「1」那头）
    parent_rows = conn.exec_driver_sql(f"SELECT COUNT(*) FROM `{parent}`").scalar()
    parent_dist = conn.exec_driver_sql(f"SELECT COUNT(DISTINCT `{parent_col}`) FROM `{parent}`").scalar()
    unique = "唯一" if parent_rows == parent_dist else f"不唯一({parent_dist}/{parent_rows})"

    # 子表的去重值里，有多少能在主表里找到（判断能不能 join 上）
    matched = conn.exec_driver_sql(
        f"SELECT COUNT(DISTINCT c.`{child_col}`) FROM `{child}` c "
        f"JOIN `{parent}` p ON c.`{child_col}` = p.`{parent_col}`"
    ).scalar()

    shape = "1:N" if parent_rows == parent_dist else "N:N?"
    return (
        f"{shape}  子表 {child_rows} 行 / 去重 {child_dist} 个值；"
        f"主表字段 {unique}；能匹配上 {matched}/{child_dist}"
    )


def main() -> None:
    with get_engine().connect() as conn:
        print("当前库:", conn.exec_driver_sql("SELECT DATABASE()").scalar(), "\n")
        for child, child_col, parent, parent_col, note in RELATIONS:
            head = f"{child}.{child_col} → {parent}.{parent_col}"
            try:
                print(f"{note}\n  {head}\n  {check(conn, child, child_col, parent, parent_col)}\n")
            except Exception as exc:
                # 字段名写错、表不存在都会走到这里，报错信息本身就是线索
                print(f"{note}\n  {head}\n  验证失败: {str(exc)[:80]}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 出错只打一行，不再甩整屏 traceback
        print("出错:", str(exc)[:300])
