from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "X-Trace-Id" in r.headers


def test_trace_id_passthrough(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"X-Trace-Id": "abc123"})
    assert r.headers["X-Trace-Id"] == "abc123"


def test_requires_auth(client: TestClient) -> None:
    client.headers.pop("Authorization", None)
    r = client.get("/api/v1/kbs")
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"
