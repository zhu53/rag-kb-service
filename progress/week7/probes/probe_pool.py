"""W7-D1b 连接池实测：教材 §七 的数字来源。

跑法（仓库根 python-backend-roadmap 下）：
    .\\kb-service\\.venv\\Scripts\\python.exe .\\progress\\week7\\probes\\probe_pool.py

做两件事：
  1. pre_ping 开关对比 —— 用 KILL 精确模拟"服务端已断开"（等价于 wait_timeout=28800 到期）
  2. 池子容量 —— pool_size + max_overflow，以及归还后池里留几个

需要 MySQL 在 3307 上跑着（start-mysql.ps1）。
"""

from sqlalchemy import create_engine, text

URL = "mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4"


def part1_pre_ping() -> None:
    print("=== 1. pool_pre_ping：KILL 掉池里的连接，再借出来用 ===")
    for pre_ping in (False, True):
        engine = create_engine(URL, pool_pre_ping=pre_ping)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
            tid = c.execute(text("SELECT CONNECTION_ID()")).scalar_one()

        # 从另一条连接把它杀掉 == 服务端主动断开（wait_timeout 到期就是这样）
        killer = create_engine(URL)
        with killer.connect() as k:
            k.execute(text(f"KILL {tid}"))
        killer.dispose()

        try:
            with engine.connect() as c2:
                ok = c2.execute(text("SELECT 1 AS ok")).scalar_one()
            print(f"  pre_ping={pre_ping!s:5} -> 复用成功，结果 {ok}")
        except Exception as exc:
            orig = getattr(exc, "orig", exc)
            print(
                f"  pre_ping={pre_ping!s:5} -> {type(exc).__name__}: {str(orig).splitlines()[0][:80]}"
            )
        engine.dispose()


def part2_pool_capacity() -> None:
    print("\n=== 2. 池子容量：pool_size=5 + max_overflow=10 ===")
    engine = create_engine(URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
    held = []
    for i in range(8):
        held.append(engine.connect())  # 借了不还，逼池子扩容
        with engine.connect() as probe:
            n = probe.execute(
                text("SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE user='kb'")
            ).scalar_one()
        print(f"  借出 {i + 1:2} 条 -> 服务端 kb 连接数 = {n}")
    print(f"  扩容中: {engine.pool.status()}")

    for c in held:
        c.close()
    print(f"  全部归还: {engine.pool.status()}")
    print("  ↑ 归还后 Connections in pool 回到 5（overflow 的会被真正关掉）")
    engine.dispose()


def part3_wait_timeout() -> None:
    print("\n=== 3. 服务端空闲断开阈值 ===")
    engine = create_engine(URL)
    with engine.connect() as c:
        row = c.execute(
            text("SELECT @@wait_timeout, @@interactive_timeout, @@max_connections")
        ).one()
    print(
        f"  wait_timeout={row[0]}s（{row[0] / 3600:.0f} 小时）"
        f"  interactive_timeout={row[1]}s  max_connections={row[2]}"
    )
    print("  pool_recycle 必须小于 wait_timeout，否则等于没设")
    engine.dispose()


if __name__ == "__main__":
    part1_pre_ping()
    part2_pool_capacity()
    part3_wait_timeout()
