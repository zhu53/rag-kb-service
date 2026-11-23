"""dev/token 后门拆除的守门测试（W8-D2 交付物 8）。

这个端点曾经"点一下就白给一个任意身份的 token"——多租户隔离在它面前等于零，
谁都能冒充任何 user_id 查别人的知识库。W8-D2 起：签票只走 /auth/login，
先验密码、再给票；本测试守住"后门不再出现"。

实测记录（2026-11-23 探针）：本应用里**任何**不存在的路径，POST 都回 405、
GET 回 404——因为 StaticFiles 挂在 "/" 兜住所有未匹配路由，它对非 GET/HEAD
方法回 405 Method Not Allowed。所以"端点已拆"的判据不能死磕 404：
真实语义是**这个路径发不出票**——回 404/405 都算拆干净，回 200/201（哪怕是
401/403）都算后门还在。判据来自数据，不来自教材写的那个数字。

历史教训保留（2026-11-19 CI 第 43 次红）：不要在这里自己 `TestClient(create_app())`——
新建的 app 实例上没有 conftest 打在 `app` fixture 上的 `dependency_overrides[get_db]`，
本地会绿着打真库，CI 上 `no such table`。一律用 `client` fixture。
判据：**测试的隔离不能靠"记得加装饰器"，也不能靠本机恰好有 .env。**
"""

from fastapi.testclient import TestClient

# 后门已拆 = 发不出票。405 是 StaticFiles 兜底对 POST 的标准回应，和 404 同义。
GONE = (404, 405)
# 这些状态码出现任何一个，都说明后门还活着（200/201 = 发票了；
# 401/403 = 端点存在只是要鉴权；500 = 路由还在但炸了）
ALIVE = (200, 201, 401, 403, 500)


def test_dev_token_endpoint_is_gone(client: TestClient) -> None:
    r = client.post("/api/v1/dev/token", json={})
    assert r.status_code in GONE, (
        f"dev/token 应该已拆除（期望 {GONE}，实际 {r.status_code}）——"
        f"谁都能白拿任意身份 token 的后门还开着：{r.text[:300]}"
    )


def test_dev_token_variants_cannot_issue_token(client: TestClient) -> None:
    """变体路径一并守：换方法、换尾缀都发不出票，防'删了 POST 留了 GET'的半拆除。"""
    for method, path in [
        ("post", "/api/v1/dev/token"),
        ("get", "/api/v1/dev/token"),
        ("post", "/api/v1/dev/token/random"),
        ("get", "/api/v1/dev/token/3fa85f64-5717-4562-b3fc-2c963f66afa6"),
        ("put", "/api/v1/dev/token"),
        ("delete", "/api/v1/dev/token"),
    ]:
        r = client.request(method, path, json={})
        assert r.status_code not in ALIVE, (
            f"{method.upper()} {path} 返回 {r.status_code}——疑似后门复活：{r.text[:200]}"
        )
