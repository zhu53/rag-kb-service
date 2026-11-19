"""迁移 9540b9312d99 半途失败的修复探针。

两次失败记录：
  第 1 次：add_column(content) 报 1101——MySQL 的 TEXT 列不许有 DEFAULT；
          此前 create_unique_constraint(uq_chunk_doc_seq) 已隐式提交生效。
  第 2 次：drop_index(ix_documents_kb_id) 报 1553——FK 列必须有索引覆盖，
          先拆旧索引后建新索引造成裸奔窗口；此时 content 列也已生效。

本探针把已半途生效的部分幂等地还原到 b0846e5e87de 基线。

用法（PowerShell，kb-service 目录下）：
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\fix_mig9540.py
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\fix_mig9540.py --repair
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from kb_service.core.config import get_settings

engine = create_engine(get_settings().database_url)


def show_state() -> tuple[bool, bool]:
    """返回 (uq_chunk_doc_seq 是否存在, documents.content 是否存在)。"""
    with engine.connect() as conn:
        chunk_indexes = conn.execute(text("SHOW INDEX FROM chunks")).mappings().all()
        cols = conn.execute(
            text("SHOW COLUMNS FROM documents LIKE 'content'")
        ).scalars().all()
    has_uq = any(row["Key_name"] == "uq_chunk_doc_seq" for row in chunk_indexes)
    return has_uq, bool(cols)


def restore_baseline() -> None:
    """把这次迁移已半途生效的部分全部还原到 b0846e5e87de 基线。

    幂等：每一步都先检查存在与否。
    """
    has_uq, has_col = show_state()
    with engine.begin() as conn:
        if has_uq:
            conn.execute(text("ALTER TABLE chunks DROP INDEX uq_chunk_doc_seq"))
            print("[还原] DROP INDEX uq_chunk_doc_seq（chunks）")
        if has_col:
            conn.execute(text("ALTER TABLE documents DROP COLUMN content"))
            print("[还原] DROP COLUMN content（documents）")
    has_uq, has_col = show_state()
    print(f"[还原后] uq_chunk_doc_seq 存在 = {has_uq}，content 存在 = {has_col}")
    if not has_uq and not has_col:
        print("[OK] 库已回到迁移前基线，可以重新 upgrade head")


def main() -> None:
    repair = "--repair" in sys.argv

    has_uq, has_col = show_state()
    print(f"[核实] uq_chunk_doc_seq 存在 = {has_uq}")
    print(f"[核实] documents.content 存在 = {has_col}")

    if not repair:
        print("\n（只核实。加 --repair 执行还原：DROP INDEX uq + DROP COLUMN content）")
        return

    if not has_uq and not has_col:
        print("\n[还原] 无残留，无需修复（可能已经修过）")
        return

    restore_baseline()


if __name__ == "__main__":
    main()
