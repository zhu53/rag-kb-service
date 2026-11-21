"""债① 验收：唯一约束撞车必须 409，不是 500（W8-D1 清债槽）。

打真路径：`POST /api/v1/kbs` 同 owner 同名建两次，第二次撞 `uq_kb_owner_name`
→ repo 层抛 IntegrityError → main.py 的 exception_handler 翻译成 409。

测试环境是 conftest override 的 sqlite（话术 "UNIQUE constraint failed: ..."）；
MySQL 上话术是 "Duplicate entry ... for key ..."——handler 两种都认，本测试只
覆盖 sqlite 路径，方言兼容性由探针读数（D1-实测记录）佐证。

注意别自己 TestClient(create_app())——2026-11-19 CI #43 的教训，
见 test_dev_token.py 文件头。
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from kb_service.schemas.kb import KBCreate, KBOut
from kb_service.services.kb_service import KBService


def test_duplicate_kb_name_returns_409(client: TestClient) -> None:
    payload = {"name": "dup-conflict-kb"}

    r1 = client.post("/api/v1/kbs", json=payload)
    assert r1.status_code == 201, f"第一次创建就应该成功：{r1.text[:300]}"

    r2 = client.post("/api/v1/kbs", json=payload)
    assert r2.status_code == 409, (
        f"第二次同名必须 409（不是 {r2.status_code}）——约束冲突被当成服务器故障了：{r2.text[:300]}"
    )
    body = r2.json()
    assert body["code"] == 40900
    assert "冲突" in body["message"] or "存在" in body["message"]


def test_non_unique_integrity_error_still_raises(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """范围控制：非唯一约束的 IntegrityError 不被误译成 409。

    项目里没有外键可撞，用 monkeypatch 让 service.create 直接抛一个
    "foreign key" 语义的 IntegrityError。handler 应该不认识它 → 重新抛出
    → TestClient(raise_server_exceptions=True) 下直接传到测试端。
    """

    def bomb(self: KBService, owner_id: UUID, data: KBCreate) -> KBOut:
        raise IntegrityError("stmt", {}, Exception("foreign key constraint failed"))

    monkeypatch.setattr(KBService, "create", bomb)
    with pytest.raises(IntegrityError):
        client.post("/api/v1/kbs", json={"name": "fk-bomb"})
