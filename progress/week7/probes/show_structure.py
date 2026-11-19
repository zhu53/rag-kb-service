"""查看 kb_dev 当前结构：索引 / 列 / 外键。演示与 EXPLAIN 前后对照都用它。

用法（PowerShell，kb-service 目录下）：
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\show_structure.py            # 全部
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\show_structure.py documents  # 只看一张表
"""

from __future__ import annotations

import sys

from sqlalchemy import Connection, create_engine, text

from kb_service.core.config import get_settings

engine = create_engine(get_settings().database_url)


def show_table(conn: Connection, table: str) -> None:
    print(f"\n===== {table} 索引 =====")
    rows = conn.execute(text(f"SHOW INDEX FROM {table}")).mappings().all()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["Key_name"], row["Seq_in_index"])
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  {row['Key_name']:<32} seq={row['Seq_in_index']} "
            f"col={row['Column_name']:<12} unique={'否' if row['Non_unique'] else '是'}"
        )
    print(f"===== {table} 列 =====")
    cols = conn.execute(text(f"SHOW COLUMNS FROM {table}")).mappings().all()
    for col in cols:
        print(
            f"  {col['Field']:<14} {col['Type']:<12} "
            f"null={'是' if col['Null'] == 'YES' else '否'} "
            f"key={col['Key'] or '-'} default={col['Default']}"
        )


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with engine.connect() as conn:
        tables = conn.execute(text("SHOW TABLES")).scalars().all()
        targets = [only] if only else [t for t in tables if t != "alembic_version"]
        for table in targets:
            if table not in tables:
                print(f"[跳过] 表 {table} 不存在")
                continue
            show_table(conn, table)


if __name__ == "__main__":
    main()
