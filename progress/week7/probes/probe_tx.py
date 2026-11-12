import os
import tempfile

from sqlalchemy import String, create_engine, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

db = os.path.join(tempfile.gettempdir(), "w7probe", "t1.db")
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


def count() -> int:
    with Session(engine) as s:  # with -> 自动 close
        return s.execute(select(func.count()).select_from(KB)).scalar_one()


s = Session(engine)
print("A) 刚建好 in_transaction =", s.in_transaction())
s.execute(select(func.count()).select_from(KB))
print("B) 发过 SQL 后 in_transaction =", s.in_transaction())
s.add(KB(name="未提交"))
s.flush()
print("C) flush 后 另一个 session 看到 =", count())
s.close()
print("D) close 未 commit -> 库里 =", count())

s2 = Session(engine)
k = KB(name="已提交")
s2.add(k)
s2.commit()
print("E) commit 后 库里 =", count())
print("F) commit 后 k.__dict__ 有 name 吗 =", "name" in k.__dict__)
print("G) 读 k.name =", k.name, "| 读完后 __dict__ 有 name 吗 =", "name" in k.__dict__)
print("H) k 还 attached 吗 =", not sa_inspect(k).detached)
s2.close()
print("I) close 后 k detached 吗 =", sa_inspect(k).detached)

s3 = Session(engine)
a = s3.get(KB, 1)
b = s3.get(KB, 1)
print("J) 同一 session 两次 get 同一主键 a is b =", a is b)
s3.close()

s4 = Session(engine)
with s4.begin():  # 显式事务块：自动 commit / 异常 rollback
    s4.add(KB(name="事务块"))
print("K) with begin() 后 库里 =", count(), "| 块结束后 in_transaction =", s4.in_transaction())
s4.close()
