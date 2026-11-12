import os
import tempfile

from sqlalchemy import String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

db = os.path.join(tempfile.gettempdir(), "w7probe", "t9.db")
if os.path.exists(db):
    os.remove(db)
engine = create_engine(f"sqlite:///{db}", echo=True)


class Base(DeclarativeBase):
    pass


class KB(Base):
    __tablename__ = "kb"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


Base.metadata.create_all(engine)

print("=== begin() 套在已有事务上 ===")
s = Session(engine)
s.execute(select(func.count()).select_from(KB))
try:
    with s.begin():
        pass
except Exception as e:
    print(">>>", type(e).__name__, ":", e)
s.rollback()
s.close()

print("=== autoflush：add 后直接 execute SELECT 会发生什么 ===")
s = Session(engine)
s.add(KB(name="autoflush-未提交"))
print(">>> SELECT 结果 =", s.execute(select(func.count()).select_from(KB)).scalar_one())
s.rollback()
s.close()

print("=== no_autoflush 块 ===")
s = Session(engine)
s.add(KB(name="no_autoflush"))
with s.no_autoflush:
    print(">>> SELECT 结果 =", s.execute(select(func.count()).select_from(KB)).scalar_one())
s.rollback()
s.close()
