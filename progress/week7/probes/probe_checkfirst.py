"""探针：create_all 的 checkfirst 到底在干什么？为什么 SQLite 会查 main 和 temp 两个 schema？

对应教材 D2 §5.5。跑法（仓库根）：

    kb-service/.venv/Scripts/python.exe progress/week7/probes/probe_checkfirst.py

四个 SQLite 实验 + 一个 MySQL 对照（MySQL 3307 不在线时那节自动跳过）。
"""

from sqlalchemy import String, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProbeKB(Base):
    __tablename__ = "min_kbs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class ProbeDoc(Base):
    __tablename__ = "min_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(60))


def new_engine(url: str = "sqlite://"):
    """建引擎并把每条执行过的 SQL 记到 engine.sqls 上。"""
    eng = create_engine(url)
    eng.sqls = []  # type: ignore[attr-defined]

    @event.listens_for(eng, "before_cursor_execute")
    def _cap(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        eng.sqls.append(" ".join(statement.split()))  # type: ignore[attr-defined]

    return eng


def show(title: str, eng) -> None:
    print(f"\n=== {title} ===")
    for s in eng.sqls:  # type: ignore[attr-defined]
        print("  ·", s[:120])
    print(f"  共 {len(eng.sqls)} 条")  # type: ignore[attr-defined]


# ---------- 实验 1：默认 checkfirst=True ----------
e1 = new_engine()
Base.metadata.create_all(e1)
show("实验1 create_all() 默认 checkfirst=True（两张表都不存在 → 每表两条 PRAGMA）", e1)

# ---------- 实验 2：checkfirst=False ----------
e2 = new_engine()
Base.metadata.create_all(e2, checkfirst=False)
show("实验2 create_all(checkfirst=False)（0 条 PRAGMA）", e2)

# ---------- 实验 3：表已存在时的短路 ----------
e3 = new_engine()
Base.metadata.create_all(e3)
e3.sqls.clear()  # type: ignore[attr-defined]
Base.metadata.create_all(e3)
show("实验3 表已存在再跑一次（main 命中即 return → 每表只剩一条）", e3)

# ---------- 实验 4：temp 同名表会骗过存在性检查 ----------
e4 = new_engine()
with e4.begin() as c:
    c.execute(text("CREATE TEMP TABLE min_kbs (id INTEGER PRIMARY KEY)"))
e4.sqls.clear()  # type: ignore[attr-defined]
Base.metadata.create_all(e4)
show("实验4 temp 已有同名表 min_kbs 时的 create_all（min_kbs 被跳过）", e4)

with e4.connect() as c:
    main_tables = [r[0] for r in c.execute(text("SELECT name FROM main.sqlite_master"))]
    temp_tables = [r[0] for r in c.execute(text("SELECT name FROM sqlite_temp_master"))]
    c.execute(text("INSERT INTO min_kbs (id) VALUES (999)"))
    hit_temp = c.execute(text("SELECT COUNT(*) FROM min_kbs")).scalar()
    print("  main 里的表:", main_tables)
    print("  temp 里的表:", temp_tables)
    print("  不带命名空间的 SELECT 命中 temp，行数:", hit_temp)
    try:
        c.execute(text("SELECT COUNT(*) FROM main.min_kbs")).scalar()
        print("  main.min_kbs 行数:", "可查")
    except Exception as exc:  # noqa: BLE001
        print("  显式 main.min_kbs →", str(exc).splitlines()[0])

# ---------- 实验 5：MySQL 上对应的是 DESCRIBE ----------
MYSQL_URL = "mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4"
try:
    e5 = new_engine(MYSQL_URL)
    with e5.connect():
        pass
except Exception as exc:  # noqa: BLE001
    print(f"\n=== 实验5 MySQL 对照：跳过（3307 未启动：{type(exc).__name__}）===")
else:
    try:
        Base.metadata.create_all(e5)
        show("实验5 MySQL 8.4 同一套模型（只有一条 DESCRIBE）", e5)
    finally:
        Base.metadata.drop_all(e5)
        e5.dispose()

for e in (e1, e2, e3, e4):
    e.dispose()
