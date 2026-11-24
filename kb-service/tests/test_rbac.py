"""W8-D3 交付物 4：require_role / admin 路由的权限测试。

判据三层：
- **401 问身份**：没票 → 401；**403 问权限**：有票但不是 admin → 403。混了就是设计错。
- **改 role 不用重新登录**：`get_current_user` 每请求查库，把库里 role 一改立刻生效——
  这条测试同时证明"验人不是 JWT 自足"（D3 的核心动机）。
- **封禁闭环**：admin 封人 → 那人立刻登不上、旧 token 也打不动（401）。
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from kb_service.core.security import create_access_token
from kb_service.repositories.models import User

ADMIN_LIST = "/api/v1/admin/users"
REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def _promote_seed_to_admin(db: Session) -> None:
    """把 conftest seed 的 member 提成 admin。

    不改 token：token 里只有 sub，角色是每次请求现查库的——
    这正是 D3 想要的语义（改角色/封禁立即生效，不用等旧票过期）。
    """
    user = db.scalar(select(User).where(User.email == "seed@example.com"))
    assert user is not None
    user.role = "admin"
    db.commit()


def test_member_gets_403_on_admin_routes(client: TestClient) -> None:
    """有票但角色不够 → 403（不是 401：身份验过了，缺的是权限）。"""
    r_list = client.get(ADMIN_LIST)
    assert r_list.status_code == 403, (
        f"member 打 admin 列表必须 403（不是 {r_list.status_code}）：{r_list.text[:300]}"
    )

    r_ban = client.patch(f"{ADMIN_LIST}/{uuid.uuid4()}/ban")
    assert r_ban.status_code == 403, (
        f"member 打封禁接口必须 403（不是 {r_ban.status_code}）：{r_ban.text[:300]}"
    )


def test_anonymous_gets_401_on_admin_routes(app: FastAPI) -> None:
    """没票 → 401。跟 403 分开测，就是防两种错混成一个。"""
    with TestClient(app) as bare:  # 不带 auth_headers 的裸客户端
        r = bare.get(ADMIN_LIST)
    assert r.status_code == 401, f"没票必须 401（不是 {r.status_code}）：{r.text[:300]}"


def test_admin_lists_users_with_ban_flag(client: TestClient, db: Session) -> None:
    _promote_seed_to_admin(db)

    r = client.get(ADMIN_LIST)
    assert r.status_code == 200, f"admin 应能列用户：{r.text[:300]}"

    data = r.json()["data"]
    assert isinstance(data, list), f"data 应是列表：{type(data)}"
    assert data, "用户列表不能为空"
    seed = next((u for u in data if u["email"] == "seed@example.com"), None)
    assert seed is not None, f"列表里没有 seed 用户：{[u['email'] for u in data]}"
    assert seed["is_banned"] is False
    assert "password_hash" not in seed, "列表泄漏了密码哈希"


def test_admin_ban_blocks_login_and_old_token(client: TestClient, db: Session) -> None:
    """封禁闭环：admin 一句 PATCH 之后，被封的人**登录 + 旧 token** 同时失效。"""
    victim = {"email": "victim@example.com", "password": "correct-horse-9"}
    r = client.post(REGISTER, json=victim)
    assert r.status_code == 201
    victim_id = r.json()["data"]["id"]
    victim_headers = {"Authorization": f"Bearer {create_access_token(victim_id)}"}

    # 封之前旧 token 能用（拿 /kbs 探活，200 说明票有效）
    assert client.get("/api/v1/kbs", headers=victim_headers).status_code == 200

    _promote_seed_to_admin(db)
    r_ban = client.patch(f"{ADMIN_LIST}/{victim_id}/ban")
    assert r_ban.status_code == 200, f"admin 封人应成功：{r_ban.text[:300]}"
    assert r_ban.json()["data"]["is_banned"] is True

    r_login = client.post(LOGIN, json=victim)
    assert r_login.status_code == 401, f"封禁后登录必须 401（不是 {r_login.status_code}）"
    r_token = client.get("/api/v1/kbs", headers=victim_headers)
    assert r_token.status_code == 401, (
        f"封禁后旧 token 必须立刻失效（不是 {r_token.status_code}）——验人没查库"
    )


def test_ban_unknown_user_returns_404(client: TestClient, db: Session) -> None:
    _promote_seed_to_admin(db)
    r = client.patch(f"{ADMIN_LIST}/{uuid.uuid4()}/ban")
    assert r.status_code == 404, f"封不存在的人必须 404（不是 {r.status_code}）：{r.text[:300]}"


# ---------------------------------------------------------------- 横向越权（交付物 5：#4 / #9）


def _register_other(client: TestClient, email: str = "other@example.com") -> dict[str, str]:
    """再造一个同级用户，返回他的认证头。横向越权必须两个真人，不能伪造 token。"""
    r = client.post(REGISTER, json={"email": email, "password": "correct-horse-9"})
    assert r.status_code == 201, f"造第二个用户失败：{r.text[:300]}"
    return {"Authorization": f"Bearer {create_access_token(r.json()['data']['id'])}"}


def test_other_user_kb_detail_returns_403(client: TestClient) -> None:
    """#4 `GET /kbs/{id}`：模式二 get_or_403 的实测读数。"""
    kb = client.post("/api/v1/kbs", json={"name": "A-kb"}).json()["data"]
    other = _register_other(client)

    r = client.get(f"/api/v1/kbs/{kb['id']}", headers=other)
    assert r.status_code == 403, (
        f"别人的 KB 必须 403（不是 {r.status_code}）——get_or_403 没生效：{r.text[:300]}"
    )


def test_other_user_doc_detail_returns_403(client: TestClient) -> None:
    """#9 `GET /kbs/{kb_id}/documents/{doc_id}`：doc 归属要经 kb 两跳，漏一跳就是静默泄漏。"""
    kb = client.post("/api/v1/kbs", json={"name": "A-kb-doc"}).json()["data"]
    doc = client.post(
        f"/api/v1/kbs/{kb['id']}/documents",
        json={"title": "A 的文档", "content": "只有 A 能看的内容"},
    ).json()
    other = _register_other(client, email="other2@example.com")

    r = client.get(f"/api/v1/kbs/{kb['id']}/documents/{doc['id']}", headers=other)
    assert r.status_code == 403, (
        f"别人的文档必须 403（不是 {r.status_code}）——doc→kb 两跳归属漏了：{r.text[:300]}"
    )
