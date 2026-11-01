"""LLM 网关：带结果缓存的问答入口（占位实现，W14 接真实 LLM）。

自检：python review_07_gateway.py
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

import httpx
import respx

DEGRADED = "（AI 服务暂时不可用，请稍后再试）"


class ChatTransport(Protocol):
    """传输契约：给一个问题，还一段文本。"""

    async def chat(self, prompt: str) -> str: ...


class HTTPTransport:
    """真实调用：POST {base_url}/chat/completions。"""

    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(self, prompt: str) -> str:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            resp = await client.post(
                "/chat",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            body = resp.json()
            return body["choices"][0]["message"]["content"]


class Gateway:
    """问答网关：TTL 缓存 + 失败降级。"""

    def __init__(self, transport: ChatTransport, ttl: float = 60.0) -> None:
        self.transport = transport
        self.ttl = ttl
        self._cache: dict[str, tuple[str, float]] = {}

    async def ask(self, prompt: str) -> str:
        """先查缓存，未命中再调用；调用失败时降级返回兜底文案。"""
        hit = self._cache.get(prompt)
        if hit is not None:
            text, deadline = hit
            if time.monotonic() < deadline:
                return text
            del self._cache[prompt]

        try:
            text = await self.transport.chat(prompt)
        except httpx.HTTPError:
            text = DEGRADED

        self._cache[prompt] = (text, time.monotonic() + self.ttl)
        return text


# ---------------------------- 自检 ----------------------------


def _payload(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


def _transport() -> HTTPTransport:
    return HTTPTransport(base_url="https://llm.example.test/v1", api_key="sk-test")


async def test_ask_returns_answer() -> None:
    with respx.mock:
        respx.route(host="llm.example.test").respond(json=_payload("回答A"))
        gateway = Gateway(_transport())
        assert await gateway.ask("q1") == "回答A"


async def test_request_carries_model_and_key() -> None:
    with respx.mock:
        respx.route(host="llm.example.test").respond(json=_payload("ok"))
        gateway = Gateway(_transport())
        await gateway.ask("q2")

        last = respx.calls.last.request
        assert last.headers["authorization"] == "Bearer sk-test"
        assert json.loads(last.content)["model"] == "gpt-4o-mini"


async def test_degraded_on_timeout() -> None:
    with respx.mock:
        respx.route(host="llm.example.test").mock(side_effect=httpx.ConnectTimeout("boom"))
        gateway = Gateway(_transport())
        assert await gateway.ask("q3") == DEGRADED


async def test_cache_expires() -> None:
    with respx.mock:
        route = respx.route(host="llm.example.test").respond(json=_payload("回答B"))
        gateway = Gateway(_transport(), ttl=0.05)

        await gateway.ask("q4")
        await asyncio.sleep(0.12)
        await gateway.ask("q4")

        assert route.call_count == 2


async def test_cache_stores_result() -> None:
    with respx.mock:
        respx.route(host="llm.example.test").respond(json=_payload("回答C"))
        gateway = Gateway(_transport())
        await gateway.ask("q5")

        text, deadline = gateway._cache["q5"]
        assert text == "回答C"
        assert deadline > time.monotonic()


TESTS = [
    test_ask_returns_answer,
    test_request_carries_model_and_key,
    test_degraded_on_timeout,
    test_cache_expires,
    test_cache_stores_result,
]


def main() -> int:
    """逐个跑自检。"""
    failed = 0
    for test in TESTS:
        try:
            asyncio.run(test())
        except AssertionError:
            failed += 1
            print(f"FAIL {test.__name__}")
        else:
            print(f"PASS {test.__name__}")

    print(f"\n{len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
