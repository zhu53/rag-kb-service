"""W8-D2 交付物 7：注册/登录真路径测试。

全部走 HTTP 真路径（POST /api/v1/auth/register|login），不手工往库里插——
测的就是"schema 校验 → service 哈希 → repo 落库 → 201"这条链。

断言形状备忘（别再猜）：
- 注册响应是 `ApiResponse[UserOut]` 包过的：{"code": 0, "message": "ok", "data": {...}}；
- 登录响应是裸 `TokenOut`：{"access_token": ..., "token_type": "bearer", "expires_in": 3600}。

第 5/6 条用**自己新开的 session** 查库，不用 conftest 的 `db` fixture session——
那个 session 就是路由注入的同一个对象，"本会话看得见"不算数（W7-D6 教训）。

别自己 TestClient(create_app())——CI #42/#43 的教训，理由见 test_dev_token.py 文件头。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from kb_service.repositories.models import User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
PAYLOAD = {"email": "user@example.com", "password": "correct-horse-9"}


def test_register_returns_201_and_clean_user_out(client: TestClient) -> None:
    r = client.post(REGISTER, json=PAYLOAD)
    assert r.status_code == 201, f"注册应成功：{r.text[:300]}"

    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["email"] == PAYLOAD["email"]
    assert data["role"] == "member"  # 模型默认值（models.py: role default="member"）
    uuid.UUID(data["id"])  # 能解析 = 合法 UUID；不能则直接抛 ValueError 让用例红
    # API 契约不携带任何密码痕迹——三个可能的名字都要查
    for leak in ("password", "password_hash", "pwd_hash"):
        assert leak not in data, f"UserOut 泄漏了 {leak}：{data}"


def test_duplicate_register_returns_409(client: TestClient) -> None:
    r1 = client.post(REGISTER, json=PAYLOAD)
    assert r1.status_code == 201

    r2 = client.post(REGISTER, json=PAYLOAD)
    assert r2.status_code == 409, (
        f"重复注册必须 409（不是 {r2.status_code}）——唯一约束冲突被当成别的错了：{r2.text[:300]}"
    )


def test_wrong_password_returns_401(client: TestClient) -> None:
    client.post(REGISTER, json=PAYLOAD)

    r = client.post(LOGIN, json={"email": PAYLOAD["email"], "password": "wrong-password"})
    assert r.status_code == 401, f"密码错必须 401：{r.text[:300]}"


def test_unknown_user_same_response_as_wrong_password(client: TestClient) -> None:
    """时序侧信道的守门测试：两种失败的状态码和响应体必须完全一致。"""
    client.post(REGISTER, json=PAYLOAD)

    r_wrong_pw = client.post(LOGIN, json={"email": PAYLOAD["email"], "password": "nope"})
    r_unknown = client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope"})

    assert r_wrong_pw.status_code == r_unknown.status_code == 401
    assert r_wrong_pw.json() == r_unknown.json(), (
        "两种失败的响应体不一致——攻击者能靠文案区分『邮箱不存在』和『密码错误』"
    )


def test_user_visible_in_fresh_session(client: TestClient, db_engine: Engine) -> None:
    """注册后另开会话能查到——commit 真发生了（W7-D6：本会话看得见不算数）。"""
    r = client.post(REGISTER, json=PAYLOAD)
    assert r.status_code == 201

    fresh = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        users = fresh.scalars(select(User)).all()
        assert len(users) == 1, f"新 session 应查到 1 个用户，实际 {len(users)}"
        assert users[0].email == PAYLOAD["email"]
    finally:
        fresh.close()


def test_password_hash_not_plaintext(client: TestClient, db_engine: Engine) -> None:
    client.post(REGISTER, json=PAYLOAD)

    fresh = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        user = fresh.scalar(select(User))
        assert user is not None
        assert user.password_hash.startswith("$2b$"), (
            f"库里存的可能不是 bcrypt 哈希：{user.password_hash[:20]}"
        )
        assert user.password_hash != PAYLOAD["password"], "明文落库了！"
    finally:
        fresh.close()


def test_25_hanzi_password_rejected_422(client: TestClient) -> None:
    """25 个汉字 = 50 字节 < 72 字节限制？不对：25 汉字 UTF-8 是 75 字节，超限。
    schema 的字节校验必须拦成 422，不能漏到 bcrypt 层炸 500。"""
    r = client.post(REGISTER, json={"email": "hanzi@example.com", "password": "汉" * 25})
    assert r.status_code == 422, (
        f"75 字节的密码必须 422（不是 {r.status_code}）——字节校验没拦住：{r.text[:300]}"
    )
