"""ORM 级联执行完之后，数据库级联还会不会执行？（InnoDB 实测）

对应 D2 §5.2 的追问。跑法（仓库根，需 3307 在线）：
    kb-service/.venv/Scripts/python.exe progress/week7/probes/probe_both_cascade.py

三个场景，度量 = 删父行前后 `Innodb_rows_deleted` 的差值：
  A 只有 ORM 级联（外键无 ondelete）        —— ORM 自己删 2 子 + 1 父
  B ORM 级联 + ondelete=CASCADE，无并发插入 —— 库级联有没有"再删一遍"？
  C ORM 级联 + ondelete=CASCADE，有并发插入 —— 库里有一行 ORM 从没见过，
                                               只剩库级联能删它
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

URL = "mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4"
engine = create_engine(URL)


def rows_deleted() -> int:
    """MySQL 全局计数器：到目前为止 InnoDB 删了多少行。"""
    with engine.connect() as c:
        row = c.execute(text("SHOW GLOBAL STATUS LIKE 'Innodb_rows_deleted'")).one()
    return int(row[1])


# ---------- 族 1：ORM 级联，外键**没有** ondelete ----------
class Base1(DeclarativeBase):
    pass


class KB1(Base1):
    __tablename__ = "probe_kb_c1"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
    docs: Mapped[list[Doc1]] = relationship(back_populates="kb", cascade="all, delete-orphan")


class Doc1(Base1):
    __tablename__ = "probe_doc_c1"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(40))
    kb_id: Mapped[int] = mapped_column(ForeignKey("probe_kb_c1.id"), nullable=False)
    kb: Mapped[KB1] = relationship(back_populates="docs")


# ---------- 族 2：ORM 级联 + 外键 ondelete=CASCADE ----------
class Base2(DeclarativeBase):
    pass


class KB2(Base2):
    __tablename__ = "probe_kb_c2"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
    docs: Mapped[list[Doc2]] = relationship(back_populates="kb", cascade="all, delete-orphan")


class Doc2(Base2):
    __tablename__ = "probe_doc_c2"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(40))
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("probe_kb_c2.id", ondelete="CASCADE"), nullable=False
    )
    kb: Mapped[KB2] = relationship(back_populates="docs")


def seed(Base, KB, Doc) -> int:
    """建表 + 造 1 个 kb、2 篇 doc。返回 kb 主键。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        kb = KB(name="kb-AI")
        kb.docs = [Doc(title="doc-a"), Doc(title="doc-b")]
        s.add(kb)
        s.commit()
        return int(kb.id)


def run(label: str, Base, KB, Doc, *, concurrent_insert: bool) -> None:
    kb_id = seed(Base, KB, Doc)
    before = rows_deleted()

    with Session(engine) as s:
        kb = s.get(KB, kb_id)
        _ = [d.title for d in kb.docs]  # 让 ORM 知道"我有 2 篇子对象"
        if concurrent_insert:
            # 另一条连接、独立事务：这一行 ORM 的快照里根本没有
            with engine.begin() as other:
                other.execute(
                    text(f"INSERT INTO {Doc.__tablename__} (title, kb_id) VALUES (:t, :k)"),
                    {"t": "doc-c-并发插入", "k": kb_id},
                )
        s.delete(kb)
        err = ""
        try:
            s.commit()
        except Exception as exc:
            orig = getattr(exc, "orig", None)
            err = str(orig).strip().splitlines()[0] if orig is not None else type(exc).__name__

    after = rows_deleted()
    with engine.connect() as c:
        left = c.execute(text(f"SELECT COUNT(*) FROM {Doc.__tablename__}")).scalar_one()
        total = c.execute(text(f"SELECT COUNT(*) FROM {KB.__tablename__}")).scalar_one()

    print(f"=== {label} ===")
    print(f"  删除前行数: 父 1 + 子 {'3（含并发插入）' if concurrent_insert else '2'}")
    print(f"  Innodb_rows_deleted 差值: {after - before}")
    print(f"  删除后: 父表剩 {total} 行 / 子表剩 {left} 行")
    if err:
        print(f"  commit 报错: {err}")
    print()


for p in (Base1, Base2):
    p.metadata.drop_all(engine)

run("A 只有 ORM 级联（外键无 ondelete）/ 无并发", Base1, KB1, Doc1, concurrent_insert=False)
run("B ORM 级联 + ondelete=CASCADE / 无并发", Base2, KB2, Doc2, concurrent_insert=False)
run("C ORM 级联 + ondelete=CASCADE / 有并发插入", Base2, KB2, Doc2, concurrent_insert=True)
run("D 只有 ORM 级联 / 有并发插入（反证）", Base1, KB1, Doc1, concurrent_insert=True)

for p in (Base1, Base2):
    p.metadata.drop_all(engine)
engine.dispose()
print("探针表已清理。")
