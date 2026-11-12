import os
import tempfile

from sqlalchemy import String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

db = os.path.join(tempfile.gettempdir(), "w7probe", "t3.db")
if os.path.exists(db):
    os.remove(db)
engine = create_engine(f"sqlite:///{db}")


class Base(DeclarativeBase):
    pass


class KB(Base):
    __tablename__ = "kb"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


Base.metadata.create_all(engine)

print("场景A：泄漏的 session 只读过（SELECT）")
leak = Session(engine)
leak.execute(select(func.count()).select_from(KB))
try:
    with Session(engine) as s:
        s.add(KB(name="A"))
        s.commit()
    print("  -> 写入成功")
except Exception as e:
    print("  -> 写入失败:", type(e).__name__, str(e).splitlines()[0])
leak.close()

print("场景B：泄漏的 session 写过（flush 未提交）")
leak = Session(engine)
leak.add(KB(name="B-未提交"))
leak.flush()
try:
    with Session(engine) as s:
        s.add(KB(name="B"))
        s.commit()
    print("  -> 写入成功")
except Exception as e:
    print("  -> 写入失败:", type(e).__name__, str(e).splitlines()[0])
print("  泄漏 session 里再 flush 一次会怎样：")
try:
    leak.flush()
    print("    -> 没报错（连接还在，锁还在自己手里）")
except Exception as e:
    print("    ->", type(e).__name__, str(e).splitlines()[0])
leak.close()
with Session(engine) as s:
    s.add(KB(name="B-重试"))
    s.commit()
print("  -> leak.close() 后写入成功，库里 =", end=" ")
with Session(engine) as s:
    print(
        s.execute(select(func.count()).select_from(KB)).scalar_one(),
        [r[0] for r in s.execute(select(KB.name)).all()],
    )
