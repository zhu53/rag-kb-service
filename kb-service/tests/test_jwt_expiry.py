"""JWT 过期边界测试：freezegun 控制签发时刻与解码时刻。"""

from datetime import timedelta

import pytest
from freezegun import freeze_time

from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import create_access_token, decode_access_token


def test_fresh_token_roundtrip():
    """冻结时刻签发并解码，sub 能读回来。"""
    with freeze_time("2026-01-01 00:00:00"):
        token = create_access_token("user-1")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"


def test_expired_token_rejected():
    """两段式冻结：先签发，再跳到 +61 分钟，应被拒绝。"""
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")

    with freeze_time("2026-01-01 00:00:00") as frozen:
        frozen.tick(delta=timedelta(minutes=61))
        with pytest.raises(UnauthorizedError):
            decode_access_token(token)


def test_token_valid_at_59min():
    """+59 分钟仍能解码，避免只测过期一侧。"""
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")
        frozen.tick(delta=timedelta(minutes=59))
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"


def test_boundary_exactly_60min_still_valid():
    """恰好 +60 分钟仍不抛异常：记录当前 jose 实测行为。

    实测发现：当 exp 由 datetime.utcnow() + timedelta(minutes=60) 生成时，
    在 freezegun 跳到 exactly +60 分钟后 decode 仍通过。
    这里把它钉进测试，避免以后重构误改边界。
    """
    with freeze_time("2026-01-01 00:00:00") as frozen:
        token = create_access_token("user-1")
        frozen.tick(delta=timedelta(minutes=60))
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"
