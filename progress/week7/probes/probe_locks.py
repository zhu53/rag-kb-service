"""D4·下 锁与死锁探针

跑法（在 kb-service 目录）：
    ./.venv/Scripts/python.exe ../progress/week7/probes/probe_locks.py

做四件事：
  P1 无索引 UPDATE 锁多少行（RR）
  P2 有索引 UPDATE 锁多少行（对照）
  P3 RR vs RC 的间隙锁差异
  P4 造一次真死锁 + 抓 INNODB STATUS 的 LATEST DETECTED DEADLOCK
"""

from __future__ import annotations

import re
import threading
import time

import pymysql
from pymysql.connections import Connection

DSN = dict(
    host="127.0.0.1",
    port=3307,
    user="root",
    password="",
    database="kb_dev",
    charset="utf8mb4",
    autocommit=False,
)

KB = "kb000001000000000000000000000000"


def conn() -> Connection:
    return pymysql.connect(**DSN)


def q(c: Connection, sql: str):
    with c.cursor() as cur:
        cur.execute(sql)
        try:
            return cur.fetchall()
        except Exception:
            return None


def count_locks(c: Connection, table: str) -> tuple[int, list]:
    rows = q(
        c,
        "SELECT INDEX_NAME, LOCK_TYPE, LOCK_MODE, LOCK_DATA "
        "FROM performance_schema.data_locks "
        f"WHERE OBJECT_SCHEMA='kb_dev' AND OBJECT_NAME='{table}'",
    ) or []
    modes: dict[str, int] = {}
    for idx, ltype, mode, _data in rows:
        key = f"{ltype}:{mode}"
        modes[key] = modes.get(key, 0) + 1
    return len(rows), sorted(modes.items())


def p1_p2_lock_scope() -> None:
    print("=" * 72)
    print("P1 无索引 UPDATE：WHERE status='ready'（status 无索引）")
    c = conn()
    q(c, "BEGIN")
    q(c, "UPDATE documents SET title = title WHERE status = 'ready'")
    total, modes = count_locks(c, "documents")
    print(f"  锁对象总数 = {total}")
    for m, n in modes:
        print(f"    {m:24} {n}")
    q(c, "ROLLBACK")
    c.close()

    print("-" * 72)
    print("P2 有索引 UPDATE：WHERE kb_id=?（ix_documents_kb_created 最左前缀）")
    c = conn()
    q(c, "BEGIN")
    q(c, f"UPDATE documents SET title = title WHERE kb_id = '{KB}'")
    total, modes = count_locks(c, "documents")
    print(f"  锁对象总数 = {total}")
    for m, n in modes:
        print(f"    {m:24} {n}")
    q(c, "ROLLBACK")
    c.close()


def p3_gap_lock() -> None:
    print("=" * 72)
    print("P3 间隙锁：查一个不存在的区间，RR vs RC")
    for iso in ("REPEATABLE READ", "READ COMMITTED"):
        c = conn()
        q(c, f"SET SESSION TRANSACTION ISOLATION LEVEL {iso}")
        q(c, "BEGIN")
        q(
            c,
            "SELECT id FROM documents "
            "WHERE id > 'ffffffffffffffffffffffffffffffff' FOR UPDATE",
        )
        rows = q(
            c,
            "SELECT INDEX_NAME, LOCK_MODE, LOCK_DATA FROM performance_schema.data_locks "
            "WHERE OBJECT_SCHEMA='kb_dev' AND OBJECT_NAME='documents'",
        ) or []
        print(f"  {iso:16} 锁对象 = {len(rows)}  ->  {rows}")
        q(c, "ROLLBACK")
        c.close()

    print("-" * 72)
    print("P3b 同一行上的等值 FOR UPDATE（记录锁，无间隙）")
    c = conn()
    q(c, "BEGIN")
    q(c, f"SELECT id FROM knowledge_bases WHERE id='{KB}' FOR UPDATE")
    rows = q(
        c,
        "SELECT INDEX_NAME, LOCK_MODE, LOCK_DATA FROM performance_schema.data_locks "
        "WHERE OBJECT_SCHEMA='kb_dev' AND OBJECT_NAME='knowledge_bases'",
    ) or []
    print(f"  锁对象 = {len(rows)}  ->  {rows}")
    q(c, "ROLLBACK")
    c.close()


def p4_deadlock() -> None:
    print("=" * 72)
    print("P4 死锁：A 先锁 k1 再锁 k2，B 先锁 k2 再锁 k1")
    c0 = conn()
    ids = [r[0] for r in (q(c0, "SELECT id FROM knowledge_bases ORDER BY id LIMIT 2") or [])]
    c0.close()
    k1, k2 = ids[0], ids[1]
    print(f"  k1 = {k1}\n  k2 = {k2}")

    gate = threading.Barrier(2)
    errors: dict[str, tuple] = {}

    def worker(name: str, first: str, second: str) -> None:
        c = conn()
        try:
            q(c, "BEGIN")
            q(c, f"UPDATE knowledge_bases SET doc_count = doc_count + 1 WHERE id='{first}'")
            gate.wait(timeout=10)
            time.sleep(0.2)
            q(c, f"UPDATE knowledge_bases SET doc_count = doc_count + 1 WHERE id='{second}'")
            q(c, "COMMIT")
            errors[name] = ("OK",)
        except pymysql.err.OperationalError as e:
            errors[name] = e.args
            try:
                q(c, "ROLLBACK")
            except Exception:
                pass
        finally:
            c.close()

    ta = threading.Thread(target=worker, args=("A", k1, k2))
    tb = threading.Thread(target=worker, args=("B", k2, k1))
    ta.start()
    tb.start()
    ta.join(timeout=30)
    tb.join(timeout=30)
    for name in ("A", "B"):
        print(f"  会话{name} 结果: {errors.get(name)}")

    c = conn()
    raw = q(c, "SHOW ENGINE INNODB STATUS")
    c.close()
    text = raw[0][2] if raw else ""
    m = re.search(r"LATEST DETECTED DEADLOCK.*?(?=\n-{10,}|\Z)", text, re.S)
    print("-" * 72)
    print("INNODB STATUS / LATEST DETECTED DEADLOCK：")
    print(m.group(0)[:2600] if m else "(没抓到，可能这次没真死锁)")


if __name__ == "__main__":
    p1_p2_lock_scope()
    p3_gap_lock()
    p4_deadlock()
    print("=" * 72)
    print("完成")
