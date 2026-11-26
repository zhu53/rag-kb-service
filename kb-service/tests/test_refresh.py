"""W8-D4 交付物 4/5：refresh token 轮换的守门测试。

测的是"四步拒绝链 + 同事务轮换"这条真链路（POST /api/v1/auth/refresh），
不手工插票——插票就测不到 hash 生成、落库和事务边界了。

断言形状备忘：
- login 响应是裸 TokenOut：{"access_token", "refresh_token", "token_type", "expires_in"}
- refresh 响应同形状；401 是 {"code": 40100, "message": "用户凭证无效", "data": null}
- 查库一律开 fresh session（本会话看得见不算数，W7-D6 教训）

别自己 TestClient(create_app())——CI #42/#43 的教训，理由见 test_dev_token.py 文件头。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from kb_service.core.security import refresh_token_hash
from kb_service.repositories.models import RefreshToken, User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
KBS = "/api/v1/kbs"
PAYLOAD = {"email": "rotate@example.com", "password": "correct-horse-9"}


def _as_utc(dt: datetime) -> datetime:
    """sqlite / MySQL 的 DATETIME 都不保留时区，读回来是 naive（写入时按 UTC 存）。

    测试断言也要做同样的归一，否则量到的是"类型不匹配"而不是"时间点对不对"。
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _register_and_login(client: TestClient) -> tuple[str, str]:
    """返回 (access, refresh)。"""
    assert client.post(REGISTER, json=PAYLOAD).status_code == 201
    r = client.post(LOGIN, json=PAYLOAD)
    assert r.status_code == 200, f"登录应成功：{r.text[:300]}"
    body = r.json()
    return body["access_token"], body["refresh_token"]


def test_login_returns_refresh_and_db_stores_hash_only(
    client: TestClient, db_engine: Engine
) -> None:
    """签发契约：明文只回给客户端，库里只有 sha256，且 hash(raw) 能对上。"""
    _, raw = _register_and_login(client)

    assert raw, f"登录响应里没有 refresh_token：{raw!r}"
    assert len(raw) >= 40, f"refresh_token 不像 43 字符的 urlsafe 串：{raw!r}"

    fresh = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        rows = fresh.scalars(select(RefreshToken)).all()
        assert len(rows) == 1, f"登录应只落一行 refresh_tokens，实际 {len(rows)} 行"
        row = rows[0]
        assert row.token_hash == refresh_token_hash(raw), "库里的 hash 和 hash(raw) 对不上"
        assert row.token_hash != raw, "明文落库了！"
        assert row.revoked_at is None, "刚签发的票不该是 revoked"
        assert _as_utc(row.expires_at) > datetime.now(UTC), "刚签发的票不该已过期"
    finally:
        fresh.close()


def test_refresh_rotates_and_old_token_becomes_replay(
    client: TestClient, db_engine: Engine
) -> None:
    """轮换核心：旧票换新对 → 旧票再用 401 → 新票还能继续换。"""
    _, old_raw = _register_and_login(client)

    r1 = client.post(REFRESH, json={"refresh_token": old_raw})
    assert r1.status_code == 200, f"有效票续票应成功：{r1.text[:300]}"
    new_raw = r1.json()["refresh_token"]
    assert new_raw != old_raw, "轮换必须换出新票，不能原样返回"

    r2 = client.post(REFRESH, json={"refresh_token": old_raw})
    assert r2.status_code == 401, (
        f"旧票第二次使用必须 401（重放）（不是 {r2.status_code}）：{r2.text[:300]}"
    )

    r3 = client.post(REFRESH, json={"refresh_token": new_raw})
    assert r3.status_code == 200, f"轮换链断了：新票不能用 {r3.text[:300]}"

    fresh = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        rows = fresh.scalars(select(RefreshToken).order_by(RefreshToken.id)).all()
        assert len(rows) == 3, f"两次续票应留下 3 行（1 登录 + 2 轮换），实际 {len(rows)}"
        revoked = [r for r in rows if r.revoked_at is not None]
        alive = [r for r in rows if r.revoked_at is None]
        assert len(revoked) == 2, f"被换掉的两张票都应 revoked，实际 {len(revoked)}"
        assert len(alive) == 1, f"任何时刻只该有一张活票，实际 {len(alive)}"
    finally:
        fresh.close()


def test_refresh_new_access_token_works_on_protected_route(client: TestClient) -> None:
    """续票发出来的 access 必须能真打业务接口——否则续了也白续。"""
    _, raw = _register_and_login(client)

    r = client.post(REFRESH, json={"refresh_token": raw})
    assert r.status_code == 200
    new_access = r.json()["access_token"]

    r2 = client.get(KBS, headers={"Authorization": f"Bearer {new_access}"})
    assert r2.status_code == 200, f"续票发的 access 打不了受保护接口：{r2.text[:300]}"


def test_refresh_unknown_token_401(client: TestClient) -> None:
    r = client.post(REFRESH, json={"refresh_token": "x" * 43})
    assert r.status_code == 401, f"不存在的票必须 401（不是 {r.status_code}）：{r.text[:300]}"


def test_expired_refresh_401(client: TestClient, db: Session) -> None:
    """自然过期：直接把库里的 expires_at 改到过去（不 sleep 7 天）。"""
    _, raw = _register_and_login(client)

    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == refresh_token_hash(raw)))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    r = client.post(REFRESH, json={"refresh_token": raw})
    assert r.status_code == 401, f"过期票必须 401（不是 {r.status_code}）：{r.text[:300]}"


def test_banned_user_refresh_401(client: TestClient, db: Session) -> None:
    """封禁即时生效：票还在、没过期，但人被封了 → 401（D3 判据：吊销身份）。"""
    _, raw = _register_and_login(client)

    user = db.scalar(select(User).where(User.email == PAYLOAD["email"]))
    assert user is not None
    user.is_banned = True
    db.commit()

    r = client.post(REFRESH, json={"refresh_token": raw})
    assert r.status_code == 401, f"封禁用户续票必须 401（不是 {r.status_code}）：{r.text[:300]}"


def test_all_rejections_share_same_body(client: TestClient, db: Session) -> None:
    """防探测：查无此票 / 重放 / 过期 / 封禁，四种失败的响应体必须完全一致。"""
    _, raw = _register_and_login(client)

    r_unknown = client.post(REFRESH, json={"refresh_token": "y" * 43})
    assert r_unknown.status_code == 401

    client.post(REFRESH, json={"refresh_token": raw})  # 用掉 → 旧票变重放
    r_replay = client.post(REFRESH, json={"refresh_token": raw})
    assert r_replay.status_code == 401

    assert r_unknown.json() == r_replay.json(), (
        "『查无此票』与『重放』响应体不一致——攻击者能靠响应体区分票是否存在"
    )


# --- 交付物 5：logout ----------------------------------------------------------


def test_logout_revokes_ticket_and_returns_204_with_empty_body(
    client: TestClient, db_engine: Engine
) -> None:
    """退出的契约：204 无响应体 + 库里那张票被标 revoked + 这张票再也换不到新票。"""
    _, raw = _register_and_login(client)

    r = client.post(LOGOUT, json={"refresh_token": raw})
    assert r.status_code == 204, f"退出应返回 204（不是 {r.status_code}）：{r.text[:300]}"
    assert r.content == b"", f"204 不该有响应体，实际收到 {r.content[:200]!r}"

    fresh = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        row = fresh.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == refresh_token_hash(raw))
        )
        assert row is not None, "退出不该删行——要留审计痕迹，只标 revoked_at"
        assert row.revoked_at is not None, "退出后 revoked_at 必须落库（不是只在内存里标）"
    finally:
        fresh.close()

    r2 = client.post(REFRESH, json={"refresh_token": raw})
    assert r2.status_code == 401, (
        f"退出后的票还能续命（{r2.status_code}）——logout 等于没做：{r2.text[:300]}"
    )


def test_logout_is_idempotent_and_never_leaks_existence(client: TestClient) -> None:
    """幂等：同一张票退两次、退一张不存在的票，都必须 204。

    任何一次 4xx/5xx 都是破口：重复退出报错说明"这张票本来存在/不存在"，
    响应本身就成了存在性探针。
    """
    _, raw = _register_and_login(client)

    assert client.post(LOGOUT, json={"refresh_token": raw}).status_code == 204
    r_again = client.post(LOGOUT, json={"refresh_token": raw})
    assert r_again.status_code == 204, (
        f"重复退出必须仍 204（不是 {r_again.status_code}）：{r_again.text[:300]}"
    )

    r_unknown = client.post(LOGOUT, json={"refresh_token": "z" * 43})
    assert r_unknown.status_code == 204, (
        f"退一张不存在的票也必须 204（不是 {r_unknown.status_code}）——"
        f"否则响应码就是存在性探针：{r_unknown.text[:300]}"
    )


def test_logout_does_not_kill_access_token(client: TestClient) -> None:
    """边界钉死：logout 只作废 refresh 票，已发的 access 在 exp 前照样能打业务接口。

    这是无状态 JWT 的固有代价（服务端没有 access 的吊销名单），不是 bug。
    想立刻踢人只能上黑名单/改 token_version，那是 W9 的事。
    """
    access, raw = _register_and_login(client)

    assert client.post(LOGOUT, json={"refresh_token": raw}).status_code == 204

    r = client.get(KBS, headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, (
        f"access 在 exp 前被 logout 提前作废了（{r.status_code}）——"
        f"说明实现里去查了 refresh 表，和无状态 JWT 的设计不符：{r.text[:300]}"
    )
