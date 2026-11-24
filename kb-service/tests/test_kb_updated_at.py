"""债④ 验收：PATCH 响应里的 `updated_at` 必须是新值（W8-D3 清债槽 ④）。

真身：`kb_repo.update` 改完属性直接 `return obj.to_row()`，**没 flush**——
`updated_at` 的 `onupdate` 钩子还没执行，快照里带出来的是旧值。
症状是"PATCH 返回的时间和 GET 回来的时间不一样"，或者"改完 updated_at 跟 created_at 还是同一个值"。

判据：**响应的 updated_at 必须等于库里的 updated_at**。
PATCH 的回显和 GET 的读数是两个观测点，只有它们一致才说明快照不是旧值。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient


def _dt(s: str) -> datetime:
    """把接口返回的时间串解析成时刻：PATCH 回显带 `Z`、GET 返回值不带，
    按字符串比会假红。两种格式都是 UTC，缺 tzinfo 时按 UTC 补。"""
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _create_kb(client: TestClient, name: str = "updated-at-kb") -> str:
    r = client.post("/api/v1/kbs", json={"name": name})
    assert r.status_code == 201, f"前置建库失败：{r.text[:300]}"
    kb_id: str = r.json()["data"]["id"]
    return kb_id


def test_patch_response_updated_at_equals_db(client: TestClient) -> None:
    kb_id = _create_kb(client)

    before = client.get(f"/api/v1/kbs/{kb_id}").json()["data"]

    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"name": "renamed-for-updated-at"})
    assert r.status_code == 200, f"PATCH 应成功：{r.text[:300]}"
    # PATCH 返回裸 KBOut（GET 是 ApiResponse 包过的）——两种形状都兜一下，
    # 顺带记一笔：同一个资源两种响应外壳，是接口一致性问题，见 D3 走读文档。
    patched = r.json()
    patched = patched.get("data", patched)

    fresh = client.get(f"/api/v1/kbs/{kb_id}").json()["data"]

    assert _dt(patched["updated_at"]) == _dt(fresh["updated_at"]), (
        f"PATCH 回显的 updated_at={patched['updated_at']} 与库里 {fresh['updated_at']} 不是同一时刻"
        "——快照是改之前的旧值（repo.update 改完没 flush）"
    )
    assert _dt(fresh["updated_at"]) > _dt(before["updated_at"]), (
        f"改完 updated_at 没前进：{before['updated_at']} → {fresh['updated_at']}"
        "——onupdate 钩子没触发"
    )
    assert fresh["created_at"] == before["created_at"], "created_at 不该被 UPDATE 改掉"
