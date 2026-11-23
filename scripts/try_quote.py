"""跑几个典型的「报价分析」查询，看清楚数据能回答什么问题。

用法：python scripts/try_quote.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.tools.sql import get_engine


def show(conn, title: str, sql: str) -> None:
    """执行一条 SQL 并打印结果。"""
    print(f"\n=== {title} ===")
    cur = conn.exec_driver_sql(sql)
    print("列名:", list(cur.keys()))
    for row in cur.fetchall():
        print("  ", row)


def main() -> None:
    with get_engine().connect() as conn:
        # 1. 真实报价总量：多少物料行拿到了报价、平均几家供应商报价
        show(
            conn,
            "报价概况",
            """
            SELECT COUNT(DISTINCT i.order_item_id) AS 有报价的物料行,
                   COUNT(DISTINCT s.supplier_code)  AS 参与报价的供应商数,
                   COUNT(*)                        AS 报价记录数,
                   ROUND(AVG(每家数), 2)           AS 每行平均几家报价
            FROM biz_purchase_order_item i
            JOIN biz_purchase_order_item_supplier s
                 ON s.order_item_id = i.order_item_id AND s.tenant_id = i.tenant_id
            JOIN (SELECT order_item_id, COUNT(*) 每家数
                  FROM biz_purchase_order_item_supplier
                  WHERE quote_price > 0
                  GROUP BY order_item_id) c
                 ON c.order_item_id = i.order_item_id
            WHERE s.quote_price > 0
            """,
        )

        # 2. 按物料看报价价差：同一物料，不同供应商报了多少
        show(
            conn,
            "报价家数最多的物料（前 8）",
            """
            SELECT i.number                            AS 物料编码,
                   COUNT(DISTINCT s.supplier_code)     AS 报价家数,
                   MIN(s.quote_price)                  AS 最低价,
                   MAX(s.quote_price)                  AS 最高价,
                   ROUND(AVG(s.quote_price), 2)        AS 均价
            FROM biz_purchase_order_item i
            JOIN biz_purchase_order_item_supplier s
                 ON s.order_item_id = i.order_item_id AND s.tenant_id = i.tenant_id
            WHERE s.quote_price > 0
            GROUP BY i.number
            ORDER BY 报价家数 DESC, 物料编码
            LIMIT 8
            """,
        )

        # 3. 一张询价单里，各家供应商对同一物料的报价横向对比
        show(
            conn,
            "某张询价单的报价对比",
            """
            SELECT o.order_id, i.number AS 物料, i.qty AS 数量,
                   s.supplier_code, s.quote_price AS 单价, s.quote_total AS 总价
            FROM biz_purchase_order o
            JOIN biz_purchase_order_item i
                 ON i.order_id = o.order_id AND i.tenant_id = o.tenant_id
            JOIN biz_purchase_order_item_supplier s
                 ON s.order_item_id = i.order_item_id AND s.tenant_id = i.tenant_id
            WHERE s.quote_price > 0
            ORDER BY o.order_id, i.number, s.quote_price
            LIMIT 12
            """,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 出错只打一行，不再甩整屏 traceback
        print("出错:", str(exc)[:300])
