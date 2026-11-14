"""W7-D2 探针：N+1 是怎么发生的，两种预加载各自发了什么 SQL。

跑法（PowerShell，仓库根执行）：

    # Windows PowerShell
    & .\kb-service\.venv\Scripts\python.exe .\progress\week7\probes\probe_n_plus_1.py

    # Git Bash / Linux
    ./kb-service/.venv/Scripts/python.exe ./progress/week7/probes/probe_n_plus_1.py

预期（数据：3 个知识库，分别挂 2 / 1 / 3 篇文档）：
  实验 A 懒加载      → 4 条 SELECT（1 条主查询 + 每个知识库补 1 条）
  实验 B selectinload → 2 条 SELECT（1 条主查询 + 1 条 WHERE kb_id IN (1,2,3)）
  实验 C joinedload  → 1 条 SELECT（LEFT JOIN，返回 6 行 = 文档数，要 .unique() 去重）
"""

from pathlib import Path

from sqlalchemy import ForeignKey, String, create_engine, event, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    relationship,
    selectinload,
)


class Base(DeclarativeBase):
    pass


class ProbeKB(Base):
    """探针专用知识库表（与项目 models.py 无关，只服务本实验）。"""

    __tablename__ = "probe_kbs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    docs: Mapped[list["ProbeDoc"]] = relationship(back_populates="kb")


class ProbeDoc(Base):
    __tablename__ = "probe_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(60))
    kb_id: Mapped[int] = mapped_column(ForeignKey("probe_kbs.id"))
    kb: Mapped["ProbeKB"] = relationship(back_populates="docs")


DB_PATH = Path(__file__).parents[3] / "scratch" / "d2_probe.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

# 挂一个监听器：每条真实发出去的 SQL 都记进 sqls（这就是"数 SQL"的裁判）
sqls: list[str] = []


def _record(conn: object, cursor: object, statement: str, *_: object) -> None:
    sqls.append(statement)


event.listen(engine, "before_cursor_execute", _record)


def seed() -> None:
    """建表 + 造数据：3 个知识库，分别挂 2 / 1 / 3 篇文档。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    plan = {"kb-AI": 2, "kb-legal": 1, "kb-news": 3}
    with Session(engine) as session:
        for kb_name, doc_n in plan.items():
            kb = ProbeKB(name=kb_name)
            kb.docs = [ProbeDoc(title=f"{kb_name}-doc{i}") for i in range(doc_n)]
            session.add(kb)
        session.commit()


def run(label: str, options: object) -> None:
    """跑一次「查全部知识库 → 逐个读 docs」，打印发出的 SELECT 条数和原文。

    必须用 Session：Connection.execute 是 Core 上下文，实体查询只会拿到列值行，
    ORM 对象（和关系加载）只有经过 Session 才存在。
    """
    sqls.clear()
    stmt = select(ProbeKB)
    if options is not None:
        stmt = stmt.options(options)  # type: ignore[arg-type]
    with Session(engine) as session:
        kbs = session.execute(stmt).unique().scalars().all()
        for kb in kbs:
            _ = [d.title for d in kb.docs]  # 懒加载在这里被触发
    print(f"=== {label} ===")
    print(f"SELECT 条数: {len(sqls)}")
    for s in sqls:
        first = s.splitlines()[0]
        print(f"  · {first[:110]}")
    print()


seed()

run("实验 A：什么都不加（懒加载，N+1 现场）", None)
run("实验 B：selectinload(ProbeKB.docs)", selectinload(ProbeKB.docs))
run("实验 C：joinedload(ProbeKB.docs)", joinedload(ProbeKB.docs))

# 附：joinedload 的去重要求 —— 集合 joinedload 产生重复行，不 .unique() 直接报错
with Session(engine) as session:
    try:
        session.execute(select(ProbeKB).options(joinedload(ProbeKB.docs))).all()
    except Exception as exc:  # noqa: BLE001 —— 演示用，故意抓宽
        print(f"=== joinedload 忘了 .unique() 会怎样 ===\n{type(exc).__name__}: {str(exc)[:120]}")

with Session(engine) as session:
    kbs = session.execute(
        select(ProbeKB).options(joinedload(ProbeKB.docs))
    ).unique().scalars().all()
    print(f"加上 .unique() 之后 → {len(kbs)} 个对象（3 个知识库，去重正确）")

engine.dispose()
