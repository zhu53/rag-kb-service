"""dev token 端点的契约测试。

保两件事：① 随机签发可用 ② 指定 user_id 会原样进 token 的 sub。
端点本身只在非 prod 挂载（main.py 条件 include），测试默认 env=dev 所以可见。
"""

from fastapi.testclient import TestClient

from kb_service.main import create_app


def test_dev_token_random_user_works() -> None:
    client = TestClient(create_app())
    r = client.post("/api/v1/dev/token", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    # 签出来的 token 必须能通过 kbs 列表的鉴权（走 get_db override 的 sqlite）
    r2 = client.get("/api/v1/kbs", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r2.status_code == 200


def test_dev_token_echoes_user_id() -> None:
    client = TestClient(create_app())
    uid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    r = client.post("/api/v1/dev/token", json={"user_id": uid})
    assert r.status_code == 200
    assert r.json()["user_id"] == uid
