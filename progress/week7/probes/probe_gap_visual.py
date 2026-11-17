"""探针：三种锁形态到底覆盖哪一段 —— 用 INSERT 反证。

思路：不看 LOCK_MODE 猜，而是让另一个会话去 VALUES 各位置 INSERT，
被挡的说明那段被锁住了。这比读字符串可靠。

跑法（在 kb-service 目录下）：
    ./.venv/Scripts/python.exe ../progress/week7/probes/probe_gap_visual.py
"""

from __future__ import annotations

import pymysql

DB = "kb_lock_probe"
LOCK_SQL = """
SELECT INDEX_NAME, LOCK_TYPE, LOCK_MODE, LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = %s AND OBJECT_NAME = 't'
ORDER BY INDEX_NAME, LOCK_DATA
"""


def conn(
    autocommit: bool = True, database: str | None = None
) -> pymysql.connections.Connection:
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        charset="utf8mb4",
        autocommit=autocommit,
        database=database,
    )


def setup() -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {DB}")
        cur.execute(f"CREATE DATABASE {DB} DEFAULT CHARACTER SET utf8mb4")
        cur.execute(f"USE {DB}")
        cur.execute("CREATE TABLE t (id INT PRIMARY KEY, v INT) ENGINE=InnoDB")
        cur.execute("INSERT INTO t VALUES (10,0),(20,0),(30,0)")


def show_locks() -> list[tuple[object, ...]]:
    with conn() as c, c.cursor() as cur:
        cur.execute(LOCK_SQL, (DB,))
        return list(cur.fetchall())


def try_insert(value: int) -> str:
    """用独立连接插一个值，1 秒超时。返回 OK / BLOCKED。"""
    with conn() as c, c.cursor() as cur:
        cur.execute("SET SESSION innodb_lock_wait_timeout = 1")
        try:
            cur.execute(f"USE {DB}")
            cur.execute("INSERT INTO t (id, v) VALUES (%s, 0)", (value,))
            return "OK"
        except pymysql.err.OperationalError as e:
            code = e.args[0]
            return "BLOCKED" if code == 1205 else f"ERR{code}"


def probe(title: str, sql: str, values: list[int], isolation: str = "REPEATABLE READ") -> None:
    print(f"\n{'=' * 68}")
    print(f"{title}")
    print(f"  隔离级别 : {isolation}")
    print(f"  语句     : {sql.strip()}")
    setup()

    holder = conn(autocommit=False, database=DB)
    try:
        with holder.cursor() as cur:
            cur.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation}")
            cur.execute("BEGIN")
            cur.execute(sql.strip())
        locks = show_locks()
        print("  data_locks:")
        if not locks:
            print("    (无行锁)")
        for idx, ltype, mode, data in locks:
            print(f"    {str(idx):<8} {str(ltype):<6} {str(mode):<22} LOCK_DATA={data}")
    finally:
        holder.rollback()
        holder.close()

    # 锁还在的时候测 INSERT（上面 rollback 了，所以重开一次持锁）
    holder2 = conn(autocommit=False, database=DB)
    try:
        with holder2.cursor() as cur:
            cur.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation}")
            cur.execute("BEGIN")
            cur.execute(sql.strip())
        print(f"  INSERT 测试（1s 超时）:")
        setup_rows = {10, 20, 30}
        for v in values:
            if v in setup_rows:
                print(f"    INSERT {v:<4} -> 跳过（已存在）")
                continue
            print(f"    INSERT {v:<4} -> {try_insert(v)}")
    finally:
        holder2.rollback()
        holder2.close()


def main() -> None:
    print("基线：t 表只有 id = 10, 20, 30 三行（主键是唯一索引）")
    print("序列：  -inf ---- 10 ---- 20 ---- 30 ---- +inf")
    print("缝隙：     g0      g1      g2      g3")

    probe(
        "场景 A · 唯一索引等值命中：WHERE id = 20 FOR UPDATE",
        "SELECT * FROM t WHERE id = 20 FOR UPDATE",
        [5, 15, 25, 35],
    )

    probe(
        "场景 B · 范围命中：WHERE id > 15 AND id < 25 FOR UPDATE",
        "SELECT * FROM t WHERE id > 15 AND id < 25 FOR UPDATE",
        [5, 15, 25, 35],
    )

    probe(
        "场景 C · 范围无命中：WHERE id > 30 FOR UPDATE",
        "SELECT * FROM t WHERE id > 30 FOR UPDATE",
        [25, 35, 40],
    )

    probe(
        "场景 D · 同 C，但 RC 隔离级别",
        "SELECT * FROM t WHERE id > 30 FOR UPDATE",
        [25, 35, 40],
        isolation="READ COMMITTED",
    )

    with conn() as c, c.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {DB}")
    print("\n探针库已清理")


if __name__ == "__main__":
    main()
