"""债② 验收：PATCH 的两种 null 语义必须分开（W8-D2 清债槽 ②）。

债②的真身（W8-D2 实测）：`kb_repo.update` 里 `if v is not None` 让
`{"description": null}` 变成"静默忽略"——返回 200、原值不变、description 永远清不掉。
没有报错、没有 500、门禁全绿，只有用户发现"我清空不了描述"。

修后的两条契约：
- `{"name": null}` → **422**（名称必须有值，想改名就传新名字）；
- `{"description": null}` → **200 且真的变 NULL**（GET 一次确认，不信 PATCH 自己的回显）。

判据：**None 不是一个值，是两个意图**——"没传这个字段"（部分更新）vs
"传了这个字段，值为空"（清空）。区分靠 `model_fields_set`，不靠 `is None`。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_kb(client: TestClient, name: str = "patch-null-kb") -> str:
    r = client.post("/api/v1/kbs", json={"name": name, "description": "初始描述"})
    assert r.status_code == 201, f"前置建库失败：{r.text[:300]}"
    body = r.json()
    kb = body.get("data", body)
    kb_id: str = kb["id"]
    return kb_id


def test_patch_name_null_is_422(client: TestClient) -> None:
    kb_id = _create_kb(client)

    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"name": None})
    assert r.status_code == 422, (
        f'{{"name": null}} 必须 422（实际 {r.status_code}）——名称被清空或静默忽略了：{r.text[:300]}'
    )


def test_patch_description_null_actually_clears(client: TestClient) -> None:
    kb_id = _create_kb(client)

    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"description": None})
    assert r.status_code == 200, f"清空描述应该成功：{r.text[:300]}"

    # 关键：GET 一次确认落库为 NULL。PATCH 的响应体只是"我改了"，不是"库变了"。
    g = client.get(f"/api/v1/kbs/{kb_id}")
    assert g.status_code == 200
    body = g.json()
    kb = body.get("data", body)
    assert kb["description"] is None, (
        f"description 没有真的清空（仍是 {kb['description']!r}）——"
        f"repo 层的 `if v is not None` 还在静默忽略 None"
    )


def test_patch_omitted_fields_untouched(client: TestClient) -> None:
    """范围控制：不传 description 时它不能被连带清掉（把"没传"误当"清空"）。"""
    kb_id = _create_kb(client)

    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"name": "renamed-kb"})
    assert r.status_code == 200

    g = client.get(f"/api/v1/kbs/{kb_id}")
    kb = g.json()["data"]
    assert kb["name"] == "renamed-kb"
    assert kb["description"] == "初始描述", "没传 description，它却被清空了——exclude_unset 失效"
