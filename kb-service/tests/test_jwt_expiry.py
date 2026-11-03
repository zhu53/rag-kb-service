"""JWT 过期边界测试：freezegun 控制签发时刻与解码时刻。"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from jose import jwt

from kb_service.core.config import get_settings
from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import create_access_token, decode_access_token


def test_fresh_token_roundtrip() -> None:
    """冻结时刻签发并解码，sub 能读回来。"""
    with freeze_time("2026-01-01 00:00:00"):
        token = create_access_token("user-1")
        payload = decode_access_token(token)
        assert payload.sub == "user-1"


def test_expired_token_rejected() -> None:
    """两段式冻结：先签发，再跳到 +61 分钟，应被拒绝。"""
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")

    with freeze_time("2026-01-01 00:00:00") as frozen:
        frozen.tick(delta=timedelta(minutes=61))
        with pytest.raises(UnauthorizedError):
            decode_access_token(token)


def test_token_valid_at_59min() -> None:
    """+59 分钟仍能解码，避免只测过期一侧。"""
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")
        frozen.tick(delta=timedelta(minutes=59))
        payload = decode_access_token(token)
        assert payload.sub == "user-1"


def test_boundary_exactly_60min_still_valid() -> None:
    """恰好 +60 分钟仍不抛异常：记录当前 jose 实测行为。

    实测发现：当 exp 由 datetime.utcnow() + timedelta(minutes=60) 生成时，
    在 freezegun 跳到 exactly +60 分钟后 decode 仍通过。
    这里把它钉进测试，避免以后重构误改边界。
    """
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")
        frozen.tick(delta=timedelta(minutes=60))
        payload = decode_access_token(token)
        assert payload.sub == "user-1"


def test_sub_not_uuid_returns_401(client: TestClient) -> None:
    """sub 不是 UUID：deps 里 UUID(str(sub)) 抛 ValueError，必须翻成 401 而不是 500。"""
    token = create_access_token("not-a-uuid")
    resp = client.get("/api/v1/kbs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_missing_sub_returns_401(client: TestClient) -> None:
    """载荷缺 sub：TokenClaims.model_validate 抛 ValidationError → 401。

    必须手工签：create_access_token 总会写 sub，造不出这个形状。
    这条覆盖 decode_access_token 里 except ValidationError 那条分支 ——
    没有它，这段代码就是"写了但一次没跑过"。
    """
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {"iat": now, "exp": now + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    resp = client.get("/api/v1/kbs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
