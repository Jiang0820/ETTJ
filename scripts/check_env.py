"""环境体检：python scripts/check_env.py

不依赖模型，检查 Python、依赖包、.env 必填项、数据库连通与存储目录。
"""

from __future__ import annotations

import importlib.metadata as md
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGES = [
    "langchain",
    "langchain-core",
    "langgraph",
    "langgraph-checkpoint-sqlite",
    "sqlalchemy",
    "pymysql",
    "python-dotenv",
    "langsmith",
]


def check_packages() -> bool:
    ok = True
    print("依赖包:")
    for name in PACKAGES:
        try:
            print(f"  {name:32s} {md.version(name)}")
        except md.PackageNotFoundError:
            ok = False
            print(f"  {name:32s} 缺失")
    return ok


def check_env() -> bool:
    from ettj.config import settings

    print("\n配置:")
    print(f"  模型: {settings.model}")
    print(f"  数据库: {settings.mask_mysql()}")
    print(f"  只读: {settings.sql_read_only}")
    missing = settings.missing_required()
    if missing:
        print(f"  缺少必填项: {', '.join(missing)}")
    return not missing


def check_paths() -> bool:
    from ettj.config import settings

    ok = True
    print("\n路径:")
    for label, path in [
        ("日志目录", settings.resolve(settings.log_dir)),
        ("数据目录", settings.resolve(settings.data_dir)),
        ("checkpoint", settings.checkpoint_path),
    ]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  {label:12s} {path}")
        except Exception as exc:
            ok = False
            print(f"  {label:12s} 不可写: {exc}")
    return ok


def check_db() -> bool:
    from ettj.config import settings

    if settings.missing_required():
        print("\n数据库: 跳过（配置不完整）")
        return False
    try:
        from ettj.tools.sql import get_engine, list_tables

        with get_engine().connect() as conn:
            version = conn.exec_driver_sql("SELECT VERSION()").scalar()
            database = conn.exec_driver_sql("SELECT DATABASE()").scalar()
        tables = list_tables()
        print(f"\n数据库: 连接成功 | MySQL {version} | 库 {database} | 表 {len(tables)} 张")
        return True
    except Exception as exc:
        print(f"\n数据库: 连接失败 -> {exc}")
        return False


def main() -> int:
    print(f"Python {sys.version.split()[0]}  ({sys.executable})\n")
    results = {
        "依赖": check_packages(),
        "配置": check_env(),
        "路径": check_paths(),
        "数据库": check_db(),
    }
    print("\n汇总: " + ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
