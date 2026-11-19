"""review 探针 2：反例构造实测（手段 3）。

五个反例打真 app（sqlite override，同 conftest 模式）：
PATCH null / description null / 全空白正文 / 同名重复 / （并发同名见断言5 说明）

用法（kb-service 目录下）：
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week7\\probes\\review_probe2.py
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from kb_service.core.db import get_db
from kb_service.main import create_app
from kb_service.repositories.models import Base

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Base.metadata.create_all(engine)
session = sessionmaker(bind=engine, expire_on_commit=False)()

app = create_app()


# 必须是生成器函数：get_db 是 yield 型依赖，override 也得是（conftest.py:60 有注释）
from collections.abc import Iterator  # noqa: E402


def _override_get_db() -> Iterator[Session]:
    yield session


app.dependency_overrides[get_db] = _override_get_db

with TestClient(app) as c:
    tok = c.post("/api/v1/dev/token", json={}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    kb_id = c.post(
        "/api/v1/kbs", json={"kbName": "反例库", "description": None}, headers=h
    ).json()["data"]["id"]

    r = c.patch(f"/api/v1/kbs/{kb_id}", json={"name": None}, headers=h)
    print(f"[反例1] PATCH name=null → {r.status_code} {r.json().get('message', '')[:40]}")

    r = c.patch(f"/api/v1/kbs/{kb_id}", json={"description": None}, headers=h)
    print(f"[反例2] PATCH description=null → {r.status_code}（description 本来 nullable）")

    r = c.post(f"/api/v1/kbs/{kb_id}/documents", json={"title": "t", "content": "   "}, headers=h)
    print(f"[反例3] 正文全空白 → {r.status_code}")

    r = c.post("/api/v1/kbs", json={"kbName": "反例库"}, headers=h)
    print(f"[反例4] 同 owner 同名重复创建 → {r.status_code}")

    r = c.post(f"/api/v1/kbs/{kb_id}/documents", json={"title": "", "content": "x"}, headers=h)
    print(f"[反例5] 空标题 → {r.status_code}")
