"""极简 LLM 客户端占位（W14 换真实流式实现）。"""

from __future__ import annotations

import httpx


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
            return resp.json()["choices"][0]["message"]["content"]
