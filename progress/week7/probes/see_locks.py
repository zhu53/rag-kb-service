"""看一眼：现在有哪些事务活着、某张表上挂了几个锁。

用法（在 kb-service 目录）：
    ./.venv/Scripts/python.exe ../progress/week7/probes/see_locks.py

默认查 kb_dev.documents。改下面的 DB / TABLE 即可查别的。
不传参数、不需要 PROCESS 授权 —— 因为用的是 root。
"""

from __future__ import annotations

import pymysql

DB = "kb_dev"
TABLE = "documents"


def main() -> None:
    c = pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        database=DB,
        charset="utf8mb4",
        autocommit=True,
    )
    with c, c.cursor() as cur:
        cur.execute(
            "SELECT trx_id, trx_state, trx_started, trx_rows_locked, trx_rows_modified "
            "FROM information_schema.innodb_trx"
        )
        trx = cur.fetchall()
        print("=== 活动事务（A 的 BEGIN 应该在里面）===")
        if not trx:
            print("   (无) —— A 的事务已经不在了，锁已释放")
        for r in trx:
            print(f"   trx_id={r[0]}  state={r[1]}  started={r[2]}  rows_locked={r[3]}  rows_modified={r[4]}")

        cur.execute(
            "SELECT COUNT(*) FROM performance_schema.data_locks "
            "WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s",
            (DB, TABLE),
        )
        total = cur.fetchone()
        print(f"\n=== {DB}.{TABLE} 的锁对象总数 ===")
        print("   ", total[0] if total else 0)

        cur.execute(
            "SELECT LOCK_TYPE, LOCK_MODE, COUNT(*) FROM performance_schema.data_locks "
            "WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s "
            "GROUP BY LOCK_TYPE, LOCK_MODE ORDER BY 3 DESC",
            (DB, TABLE),
        )
        print("\n=== 按类型分布 ===")
        rows = cur.fetchall()
        if not rows:
            print("   (无行锁)")
        for t, m, n in rows:
            print(f"   {str(t):<8}{str(m):<24}{n}")

        cur.execute(
            "SELECT INDEX_NAME, LOCK_MODE, LOCK_DATA FROM performance_schema.data_locks "
            "WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s ORDER BY LOCK_DATA LIMIT 8",
            (DB, TABLE),
        )
        print("\n=== 前 8 条明细（看 LOCK_DATA 长什么样）===")
        for idx, mode, data in cur.fetchall():
            print(f"   {str(idx):<26}{str(mode):<24}{data}")

        cur.execute(
            "SELECT (LOCK_DATA LIKE %s) AS is_sup, COUNT(*) "
            "FROM performance_schema.data_locks "
            "WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s AND LOCK_TYPE='RECORD' "
            "GROUP BY is_sup",
            ("supremum%", DB, TABLE),
        )
        print("\n=== 记录锁拆解：普通记录 vs 页尾 supremum ===")
        rows = cur.fetchall()
        for is_sup, n in rows:
            label = "supremum（每页一个）" if is_sup else "普通记录"
            print(f"   {label:<22}{n}")
        if len(rows) == 1 and rows[0][0] == 0:
            print("   （没有 supremum —— 说明没有扫到任何页尾）")

        cur.execute(
            "SELECT w.REQUESTING_ENGINE_TRANSACTION_ID, w.BLOCKING_ENGINE_TRANSACTION_ID, "
            "r.LOCK_MODE, r.LOCK_DATA, r.INDEX_NAME "
            "FROM performance_schema.data_lock_waits w "
            "JOIN performance_schema.data_locks r ON w.REQUESTING_ENGINE_LOCK_ID = r.ENGINE_LOCK_ID "
            "JOIN performance_schema.data_locks b ON w.BLOCKING_ENGINE_LOCK_ID = b.ENGINE_LOCK_ID"
        )
        waits = cur.fetchall()
        print("\n=== 正在等锁的会话（data_lock_waits）===")
        if not waits:
            print("   (无人等待)")
        for req, blk, mode, data, idx in waits:
            print(f"   trx {req}  等  trx {blk}  要 {mode} @ {idx}  LOCK_DATA={data}")


if __name__ == "__main__":
    main()
