"""删父对象时到底发什么 SQL？ORM 级联与数据库级联的分工（实测）。

对应 D2 §5.2。跑法（仓库根）：
    kb-service/.venv/Scripts/python.exe progress/week7/probes/probe_cascade_order.py
"""

from sqlalchemy import ForeignKey, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

SQLS: list[str] = []


def new_engine():
    eng = create_engine("sqlite://")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(eng, "before_cursor_execute")
    def _cap(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        SQLS.append(" ".join(statement.split()))

    return eng


# ---------- 族 A：kb_id NOT NULL、外键无 ondelete、relationship 无 cascade ----------
class BaseA(DeclarativeBase):
    pass


class KBA(BaseA):
    __tablename__ = "kb_a"
    id: Mapped[int] = mapped_column(primary_key=True)
    docs: Mapped[list["DocA"]] = relationship(back_populates="kb")


class DocA(BaseA):
    __tablename__ = "doc_a"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("kb_a.id"))
    kb: Mapped["KBA"] = relationship(back_populates="docs")


# ---------- 族 B：同上，但 kb_id 可空 ----------
class BaseB(DeclarativeBase):
    pass


class KBB(BaseB):
    __tablename__ = "kb_b"
    id: Mapped[int] = mapped_column(primary_key=True)
    docs: Mapped[list["DocB"]] = relationship(back_populates="kb")


class DocB(BaseB):
    __tablename__ = "doc_b"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int | None] = mapped_column(ForeignKey("kb_b.id"), nullable=True)
    kb: Mapped["KBB"] = relationship(back_populates="docs")


# ---------- 族 C：有 ORM cascade ----------
class BaseC(DeclarativeBase):
    pass


class KBC(BaseC):
    __tablename__ = "kb_c"
    id: Mapped[int] = mapped_column(primary_key=True)
    docs: Mapped[list["DocC"]] = relationship(
        back_populates="kb", cascade="all, delete-orphan"
    )


class DocC(BaseC):
    __tablename__ = "doc_c"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("kb_c.id"))
    kb: Mapped["KBC"] = relationship(back_populates="docs")


# ---------- 族 D：外键有 ondelete=CASCADE，但 relationship 没有 cascade ----------
class BaseD(DeclarativeBase):
    pass


class KBD(BaseD):
    __tablename__ = "kb_d"
    id: Mapped[int] = mapped_column(primary_key=True)
    docs: Mapped[list["DocD"]] = relationship(back_populates="kb")


class DocD(BaseD):
    __tablename__ = "doc_d"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("kb_d.id", ondelete="CASCADE"))
    kb: Mapped["KBD"] = relationship(back_populates="docs")


# ---------- 族 E：ondelete=CASCADE + passive_deletes=True（把删除交给数据库） ----------
class BaseE(DeclarativeBase):
    pass


class KBE(BaseE):
    __tablename__ = "kb_e"
    id: Mapped[int] = mapped_column(primary_key=True)
    docs: Mapped[list["DocE"]] = relationship(
        back_populates="kb", passive_deletes=True
    )


class DocE(BaseE):
    __tablename__ = "doc_e"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("kb_e.id", ondelete="CASCADE"))
    kb: Mapped["KBE"] = relationship(back_populates="docs")


def scenario(label: str, Base, KB, Doc, *, load_docs: bool) -> None:
    eng = new_engine()
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(KB(id=1, docs=[Doc(id=1), Doc(id=2)]))
        s.commit()

    SQLS.clear()
    with Session(eng) as s:
        kb = s.get(KB, 1)
        if load_docs:
            _ = [d.id for d in kb.docs]
        s.delete(kb)
        try:
            s.commit()
            outcome = "commit 成功"
        except Exception as exc:  # noqa: BLE001
            outcome = f"{type(exc).__name__}: {str(exc).splitlines()[0][:70]}"

    with Session(eng) as s:
        left = s.query(Doc).count()
        nulls = s.query(Doc).filter(Doc.kb_id.is_(None)).count()

    print(f"\n=== {label} ===")
    for sql in SQLS:
        print("  ·", sql[:110])
    print(f"  结果：{outcome}")
    print(f"  子表剩余 {left} 行，其中 kb_id 为 NULL 的 {nulls} 行")
    eng.dispose()


scenario("族A 无 cascade / NOT NULL / 子已加载", BaseA, KBA, DocA, load_docs=True)
scenario("族A 无 cascade / NOT NULL / 子未加载", BaseA, KBA, DocA, load_docs=False)
scenario("族B 无 cascade / 可空 / 子已加载", BaseB, KBB, DocB, load_docs=True)
scenario("族C 有 ORM cascade / 子已加载", BaseC, KBC, DocC, load_docs=True)
scenario("族D 只有 ondelete=CASCADE / 子已加载", BaseD, KBD, DocD, load_docs=True)
scenario("族D 只有 ondelete=CASCADE / 子未加载", BaseD, KBD, DocD, load_docs=False)
scenario("族E ondelete=CASCADE + passive_deletes=True / 子已加载", BaseE, KBE, DocE, load_docs=True)
scenario("族E ondelete=CASCADE + passive_deletes=True / 子未加载", BaseE, KBE, DocE, load_docs=False)
