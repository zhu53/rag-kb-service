"""dev token 端点的契约测试。

保两件事：① 随机签发可用 ② 指定 user_id 会原样进 token 的 sub。
端点本身只在非 prod 挂载（main.py 条件 include），测试默认 env=dev 所以可见。

**不要在这里自己 `TestClient(create_app())`**（2026-11-19 CI 第 43 次红）：
新建的 app 实例上没有 `dependency_overrides[get_db]`——那个覆盖是 conftest 的
`db` fixture 打在 `app` fixture 实例上的。自己造 app = 绕过覆盖 = 打真数据库：

- 本地 `.env` 指向 MySQL `kb_dev`（有表）→ 200，**绿得毫无破绽**
- CI 没有 `.env`（被 .gitignore 排除），默认 `sqlite:///./kb_dev.db` 是空文件
  → `OperationalError: no such table: knowledge_bases` → 500

所以这里一律用 `client` fixture：它背后是同一个 app 实例 + sqlite 内存库。
判据：**测试的隔离不能靠"记得加装饰器"，也不能靠本机恰好有 .env。**
"""

from fastapi.testclient import TestClient


def test_dev_token_random_user_works(client: TestClient) -> None:
    r = client.post("/api/v1/dev/token", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]

    # 拿新签的 token 打列表接口：覆盖生效时这里是 sqlite 空库，必须是 200 + 空页
    token = body["access_token"]
    r2 = client.get("/api/v1/kbs", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200, f"token 过不了鉴权或打了真库：{r2.text[:300]}"
    assert r2.json()["total"] == 0


def test_dev_token_echoes_user_id(client: TestClient) -> None:
    uid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    r = client.post("/api/v1/dev/token", json={"user_id": uid})
    assert r.status_code == 200
    assert r.json()["user_id"] == uid
