"""极简 LLM 客户端占位（W14 换真实流式实现）。"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ValidationError


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatCompletion(BaseModel):
    choices: list[_Choice]


class LLMResponseError(RuntimeError):
    """LLM 返回的结果不符合 OpenAI 兼容协议"""


class LLMClient:
    """同步整段式问答：发一次请求，拿回完整文本。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(self, prompt: str, timeout: float = 10.0) -> str:  # noqa: ASYNC109
        """POST /chat/completions，返回 assistant 文本。

        timeout 是 httpx 客户端的连接/读超时，不是 asyncio 超时域，故屏蔽 ASYNC109。
        """
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        ) as client:
            resp = await client.post(
                "/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            # resp.json() 返回 Any：HTTP 响应体里是什么只有运行时才知道。
            # 这里 cast(str, ...) 是"我保证了 JSON 结构"的声明，代价是如果 API
            # 改结构这里不会有人替你挡——所以 W14 换成带 pydantic 模型校验的版本。
            data = resp.json()  # Any —— 边界在这里
            try:
                parsed = _ChatCompletion.model_validate(data)
            except ValidationError as exc:
                raise LLMResponseError("LLM 响应结构不符合预期") from exc
            if not parsed.choices:
                raise LLMResponseError("LLM 响应 choices 为空")
            return parsed.choices[0].message.content
