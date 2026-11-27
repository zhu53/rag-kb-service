r"""D5 攻击探针 ×6 —— 手敲用（不许复制粘贴，练手感）。

跑法（kb-service 目录）：

    python attack_probes.py 1      # 只跑 1 号探针
    python attack_probes.py all    # 依序全跑

读数约定：每个探针最后打印一行
    PROBE-N  ATTACKED（漏洞还在） / DEFENDED（防住了）

完工标准：6 个全 DEFENDED + `check.py` 全绿。

连接说明：TestClient 直连 create_app()，走 .env 的真库（kb_dev）。
数据隔离：每个探针用独立的随机邮箱注册，不撞历史数据；探针不改别人的行。

注意：服务里有 6 个注入的鉴权漏洞（标注 `BUG-N`），所以现在的门禁是红的
——这不是事故，是今天的靶子。你的任务：敲探针拿到 ATTACKED 读数 →
自己找漏洞、修掉 → 探针变 DEFENDED → 门禁复绿。
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from fastapi.testclient import TestClient

from kb_service.main import create_app

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
KBS = "/api/v1/kbs"
ADMIN_USERS = "/api/v1/admin/users"

PROBES: dict[int, Callable[[TestClient], None]] = {}


def probe(n: int) -> Callable:
    def deco(fn: Callable[[TestClient], None]) -> Callable[[TestClient], None]:
        PROBES[n] = fn
        return fn

    return deco


def _client() -> TestClient:
    return TestClient(create_app())


def _stamp() -> str:
    # .com 结尾：.local/.test/.invalid 这类保留域名会被 EmailStr 拒收（422）
    return f"d5-{int(time.time() * 1000)}@probe-mail.com"


def _register_and_login(c: TestClient, email: str) -> tuple[str, str]:
    """注册 + 登录，返回 (access, refresh)。样板：不用敲。"""
    r = c.post(REGISTER, json={"email": email, "password": "correct-horse-9"})
    assert r.status_code == 201, f"注册失败：{r.text[:200]}"
    r = c.post(LOGIN, json={"email": email, "password": "correct-horse-9"})
    assert r.status_code == 200, f"登录失败：{r.text[:200]}"
    body = r.json()
    return body["access_token"], body["refresh_token"]


def _set_banned(email: str, banned: bool = True) -> None:
    """直接改库把人封掉（模拟管理员动作）。样板：不用敲。"""
    from sqlalchemy import create_engine, text

    from kb_service.core.config import get_settings

    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_banned = :b WHERE email = :e"),
            {"b": int(banned), "e": email},
        )


def _judge(n: int, attacked: bool) -> None:
    print(f"PROBE-{n}  " + ("ATTACKED（漏洞还在）" if attacked else "DEFENDED（防住了）"))


@probe(1)
def probe1_pwned_token_still_works(c: TestClient) -> None:
    """旧票在人被封之后还能不能用？（验签不验人）"""
    email = _stamp()
    access, _ = _register_and_login(c, email)
    _set_banned(email)
    r = c.get(KBS, headers={"Authorization": f"Bearer {access}"})
    _judge(1, r.status_code == 200)


@probe(2)
def probe2_banned_can_still_login(c: TestClient) -> None:
    """被封的人输密码还能不能换到全新双票？（封禁仍可登录）"""
    email = _stamp()
    c.post(REGISTER, json={"email": email, "password": "correct-horse-9"})
    _set_banned(email)
    r = c.post(LOGIN, json={"email": email, "password": "correct-horse-9"})
    _judge(2, r.status_code == 200)


@probe(3)
def probe3_refresh_never_rotates(c: TestClient) -> None:
    """同一张票能不能无限次续？（refresh 不轮换）"""
    _, refresh = _register_and_login(c, _stamp())
    r1 = c.post(REFRESH, json={"refresh_token": refresh})
    assert r1.status_code == 200, f"第一次续票应成功：{r1.text[:200]}"
    r2 = c.post(REFRESH, json={"refresh_token": refresh})
    _judge(3, r2.status_code == 200)


@probe(4)
def probe4_member_reads_admin_list(c: TestClient) -> None:
    """普通用户能不能读全体用户名单？（role 检查绕过）"""
    access, _ = _register_and_login(c, _stamp())  # 默认注册出来的就是 member
    r = c.get(ADMIN_USERS, headers={"Authorization": f"Bearer {access}"})
    _judge(4, r.status_code == 200)


@probe(5)
def probe5_expired_access_token_works(c: TestClient) -> None:
    """过期 10 分钟的 access 还能不能打接口？（过期不校验）"""
    from datetime import UTC, datetime, timedelta

    from kb_service.core.security import create_access_token, decode_access_token

    access, _ = _register_and_login(c, _stamp())
    uid = decode_access_token(access).sub  # 拿到这个用户自己的 id
    dead = create_access_token(uid, extra={"exp": datetime.now(UTC) - timedelta(minutes=10)})
    r = c.get(KBS, headers={"Authorization": f"Bearer {dead}"})
    _judge(5, r.status_code == 200)


@probe(6)
def probe6_read_other_users_kb(c: TestClient) -> None:
    """B 能不能读 A 的知识库？（横向越权）"""
    owner_access, _ = _register_and_login(c, _stamp())  # A：库的主人
    kb = c.post(
        KBS, json={"name": "A 的库"}, headers={"Authorization": f"Bearer {owner_access}"}
    ).json()
    kb_id = kb["data"]["id"]
    attacker_access, _ = _register_and_login(c, _stamp())  # B：无关路人
    r = c.get(f"{KBS}/{kb_id}", headers={"Authorization": f"Bearer {attacker_access}"})
    _judge(6, r.status_code == 200)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = sorted(PROBES) if which == "all" else [int(which)]
    client = _client()
    for n in targets:
        try:
            PROBES[n](client)
        except NotImplementedError:
            print(f"PROBE-{n}  还没敲（NotImplementedError）")
