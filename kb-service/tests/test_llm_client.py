"""LLMClient 测试：respx 拦截，不真出网。"""

import json

import httpx
import pytest
import respx

from kb_service.services.llm_client import LLMClient, LLMResponseError


@pytest.fixture
def llm_client() -> LLMClient:
    return LLMClient(
        base_url="https://llm.example.test",
        api_key="sk-test-key",
        model="gpt-4o-mini",
    )


@respx.mock
async def test_chat_success(llm_client: LLMClient) -> None:
    route = respx.post("https://llm.example.test/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "RAG 是检索增强生成。"}}]},
        )
    )

    text = await llm_client.chat("什么是 RAG？")
    assert text == "RAG 是检索增强生成。"
    assert route.called


@respx.mock
async def test_request_shape(llm_client: LLMClient) -> None:
    respx.post("https://llm.example.test/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )
    )

    await llm_client.chat("什么是 RAG？")

    last = respx.calls.last.request
    assert last.headers["authorization"] == "Bearer sk-test-key"

    body = json.loads(last.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0]["content"] == "什么是 RAG？"


@respx.mock
async def test_500_raises_status_error(llm_client: LLMClient) -> None:
    respx.post("https://llm.example.test/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await llm_client.chat("什么是 RAG？")


@respx.mock
async def test_timeout_raises(llm_client: LLMClient) -> None:
    respx.post("https://llm.example.test/chat/completions").mock(
        side_effect=httpx.ConnectTimeout("boom")
    )

    with pytest.raises(httpx.ConnectTimeout):
        await llm_client.chat("什么是 RAG？")


@respx.mock
async def test_missing_content_raises(llm_client: LLMClient) -> None:
    respx.post("https://llm.example.test/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {}}]})
    )
    with pytest.raises(LLMResponseError):
        await llm_client.chat("hi")


@respx.mock
async def test_non_string_content_raises(llm_client: LLMClient) -> None:
    """content 是 123：键在、类型错。

    这条是「cast 换成 model_validate」的唯一证据：
    cast(str, 123) 会原样返回 123（错误延迟到调用方拼字符串才炸），
    model_validate 在边界当场抛 LLMResponseError。
    """
    respx.post("https://llm.example.test/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": 123}}]})
    )
    with pytest.raises(LLMResponseError):
        await llm_client.chat("hi")
