"""D1 §3.3 身份映射（identity map）实测探针。

跑法（仓库根）：
    ./kb-service/.venv/Scripts/python.exe ./progress/week7/probes/probe_identity_map.py

它回答五个问题：
    A/B  同一个 Session 里 get 两次，第二次还发 SQL 吗？
    C    identity map 到底长什么样（它的 key 是什么）
    D    用 select() 查同一行，会发 SQL 吗？返回的是不是同一个对象？
    E    一个对象改了属性，select() 回来的是新值还是库里的旧值？
    F    expunge 之后再 get，还是同一个对象吗？
    G    两个 Session 各 get 同一行，会互相覆盖吗（lost update）
"""

import os.path as p

from sqlalchemy import String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

db = p.join(p.dirname(p.abspath(__file__)), "_identity_map.db")
if p.exists(db):
    p.remove(db)
engine = create_engine(f"sqlite:///{db}")

# 只记录 SELECT，用来数"到底查了几次库"
sqls: list[str] = []


@event.listens_for(engine, "before_cursor_execute")
def _log(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
    if statement.strip().upper().startswith("SELECT"):
        sqls.append(" ".join(statement.split()))


class Base(DeclarativeBase):
    pass


class KB(Base):
    __tablename__ = "kb"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


Base.metadata.create_all(engine)
with Session(engine) as s0:
    s0.add(KB(name="初始"))
    s0.commit()

s = Session(engine)

print("A) 第一次 get(KB, 1):", end=" ")
a = s.get(KB, 1)
print(f"发了 {len(sqls)} 条 SELECT")

print("B) 第二次 get(KB, 1):", end=" ")
b = s.get(KB, 1)
print(f"累计 {len(sqls)} 条 SELECT（没增加 = 没查库）| a is b -> {a is b}")

print(f"C) identity_map 类型={type(s.identity_map).__name__} 长度={len(s.identity_map)}")
for key, obj in s.identity_map.items():
    print(f"   key={key!r}")
    print(f"   value is a -> {obj is a}")

before = len(sqls)
c = s.scalars(select(KB).where(KB.id == 1)).one()
print(f"D) 用 select() 查同一行: 发了 {len(sqls) - before} 条 SELECT | c is a -> {c is a}")

print("E) 把 a.name 改掉，再 select 一次，看拿到的是新值还是库里的旧值:")
a.name = "改过的名字"
d = s.scalars(select(KB).where(KB.id == 1)).one()
print(f"   d is a -> {d is a} | d.name = {d.name!r}")
s.rollback()

print("F) expunge(a) 之后再 get:")
a2 = s.get(KB, 1)
s.expunge(a2)
e = s.get(KB, 1)
print(f"   e is a2 -> {e is a2} | map 长度={len(s.identity_map)}")
s.rollback()
s.close()

print("G) 两个 Session 各 get 同一行（身份映射不跨 Session）:")
s1, s2 = Session(engine), Session(engine)
o1, o2 = s1.get(KB, 1), s2.get(KB, 1)
print(f"   o1 is o2 -> {o1 is o2}（同一个主键，两个对象）")
o1.name = "session1 写的"
s1.commit()
s1.close()
o2.name = "session2 写的（基于它读到的旧值）"
s2.commit()
s2.close()
with Session(engine) as s3:
    print(f"   最终库里 name = {s3.get(KB, 1).name!r}")
    print("   ↑ session1 的改动被静默覆盖了 —— 这就是 lost update")
