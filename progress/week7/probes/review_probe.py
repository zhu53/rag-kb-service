"""review 探针：验证三个标准答案断言（先实测再写）。

断言 1：identity map 掩护并发删除——另一会话删了行，本会话 session.get 仍返回缓存对象，
        UPDATE 改了个寂寞且不报错（前提：对象未过期，即期间没有 commit）。
断言 2：kb_repo.update 返回的 KBOut.updated_at 是旧值——onupdate 在 flush 时才生效，
        to_row 在 flush 前调用。
断言 3：KBUpdate 全空 PATCH（{}）合法且是静默 no-op。

用法（kb-service 目录下）：
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\review_probe.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from kb_service.repositories.models import Base, KnowledgeBase
from kb_service.schemas.kb import KBUpdate

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)

with Session(engine) as setup:
    kb = KnowledgeBase(owner_id=uuid4(), name="原始名", updated_at=datetime.now(UTC))
    setup.add(kb)
    setup.commit()
    KB_ID = kb.id
    ORIGINAL_UPDATED_AT = kb.updated_at

# ---- 断言 1：identity map 掩护并发删除 ----
with Session(engine) as s1, Session(engine) as s2:
    # T1：本会话加载（模拟 get_or_403 的 repo.get；期间不 commit，对象未过期）
    obj = s1.get(KnowledgeBase, KB_ID)
    # T2：另一个会话真删了这行并提交（DB 里已经没了）
    s2.execute(delete(KnowledgeBase).where(KnowledgeBase.id == KB_ID))
    s2.commit()

    # T1 继续：repo.update 里的 session.get——identity map 命中还是发 SQL？
    obj2 = s1.get(KnowledgeBase, KB_ID)
    print("[断言1] 另一会话已删除后，本会话 session.get 返回：", "缓存对象（identity map）" if obj2 is not None else "None（发 SQL 重查了）")
    if obj2 is not None:
        obj2.name = "并发下改的名"
        try:
            s1.flush()
            s1.commit()
            print("[断言1] flush 成功——UPDATE 静默改了个寂寞（AI 原预测）")
        except Exception as e:
            print(f"[断言1] flush 抛 {type(e).__name__}：{e}")
            print("[断言1] → 不是静默失败，是硬失败 500；AI 原预测（静默 200）被实测推翻")
        s1.rollback()
        with Session(engine) as check:
            print("[断言1] DB 里这行还在吗：", check.get(KnowledgeBase, KB_ID) is not None)

# ---- 断言 2：update 返回陈旧 updated_at ----
with Session(engine) as s:
    kb2 = KnowledgeBase(owner_id=uuid4(), name="断言2原始名", updated_at=datetime.now(UTC))
    s.add(kb2)
    s.commit()
    obj = s.get(KnowledgeBase, kb2.id)
    original_ts = kb2.updated_at
    obj.name = "新名"
    row = obj.to_row()          # kb_repo.update:80 在这里取快照
    print("[断言2] to_row() 里的 updated_at == 原值？", row["updated_at"] == original_ts)
    s.commit()
    s.refresh(obj)
    print("[断言2] flush+commit 之后 DB 里的 updated_at 才变：", obj.updated_at != original_ts)

# ---- 断言 3：全空 PATCH ----
data = KBUpdate.model_validate({})
print("[断言3] KBUpdate({}) 合法，exclude_unset 后字段数 =", len(data.model_dump(exclude_unset=True)), "→ setattr 循环零次，静默 no-op 返回 200")

# ---- 断言 4：delete 的竞态（bool 被丢弃那条）----
with Session(engine) as s1, Session(engine) as s2:
    kb3 = KnowledgeBase(owner_id=uuid4(), name="断言4")
    s1.add(kb3)
    s1.commit()
    obj = s1.get(KnowledgeBase, kb3.id)   # 本会话加载（模拟 get_or_403）
    s2.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb3.id))
    s2.commit()                            # 另一会话抢先删了
    s1.delete(obj)                         # repo.delete：bool 返回 True
    try:
        s1.flush()
        s1.commit()
        print("[断言4] delete 静默成功（竞态下 200 假成功）")
    except Exception as e:
        print(f"[断言4] flush 抛 {type(e).__name__} → 硬失败，不是静默")
    s1.rollback()
