"""D1 探针：验证 users 表真实落库 + 唯一约束站岗（教材 §二 第 3 步）。

四段读数（对照用户预测，2026-11-21）：
  ① flush 未 commit → 新 session 查 → 预期 None（跨会话不可见）
  ② commit 之后     → 新 session 查 → 预期查到（落库，不依赖进程内存）
  ③ 同 email 再插   → 预期 IntegrityError（uq_user_email 站岗）
  ④ 清理探针数据    → 复查 → 预期 None（不留脏数据给 D3）
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb_service.core.db import SessionLocal
from kb_service.repositories.models import User

EMAIL = "probe@test.dev"


def find(label: str) -> None:
    """另开一个全新 session 查——W7 教训：本会话看得见不算数。"""
    with SessionLocal() as s:
        obj: User | None = s.scalar(select(User).where(User.email == EMAIL))
        print(f"{label}: {'查到 ' + obj.email if obj else 'None'}")


def insert_probe(session: Session, email: str, tag: str) -> None:
    u = User(id=uuid4(), email=email, password_hash=tag * 60)
    session.add(u)


print("=== ① flush 未 commit，另开会话查 ===")
with SessionLocal() as s1:
    insert_probe(s1, EMAIL, "x")
    s1.flush()
    find("①")

print("=== ② commit 之后，另开会话查 ===")
with SessionLocal() as s1:
    insert_probe(s1, EMAIL, "x")
    s1.commit()
find("②")

print("=== ③ 同 email 再插并 commit（预期 IntegrityError）===")
try:
    with SessionLocal() as s3:
        insert_probe(s3, EMAIL, "y")
        s3.commit()
    print("③ 意外：插入成功 —— 唯一约束没站岗，验证失败！")
except IntegrityError as e:
    detail = str(e.orig) if getattr(e, "orig", None) else str(e)
    print(f"③ 预期内：IntegrityError —— {detail[:110]}")

print("=== ④ 清理探针数据 ===")
with SessionLocal() as s4:
    obj: User | None = s4.scalar(select(User).where(User.email == EMAIL))
    if obj is not None:
        s4.delete(obj)
        s4.commit()
        print("④ 已删除探针行")
find("④ 清理后复查")
