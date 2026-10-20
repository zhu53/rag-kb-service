from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from kb_service.repositories.doc_repo import DocRepository
from kb_service.schemas.chat import ChatSource, ChatResponse
from kb_service.services.kb_service import KBService


class RagService:
    """RAG 问答服务（占位实现）。

    当前实现：检索 = 朴素关键词命中（保证无 LLM 也能跑通链路）。
    后续升级点（按周次）：
      W12: 接入 embedding + pgvector 向量检索 / BM25 混合检索 + RRF
      W14: answer_stream 走真实 LLM 流式 token
      W15: 加入多轮会话记忆
      W16: 评测脚本对比改动前后的 Recall@K / 忠实度
    """

    def __init__(self, doc_repo: DocRepository | None = None) -> None:
        self.doc_repo = doc_repo or DocRepository()
        self.kb_service = KBService()
        self._llm: object | None = None

    def _retrieve(self, kb_id: UUID, question: str, top_k: int) -> list[ChatSource]:
        rows, _ = self.doc_repo.list_by_kb(kb_id, 0, 200)
        keywords = [w for w in question.replace("？", " ").split() if w]
        scored: list[tuple[float, ChatSource]] = []
        for row in rows:
            content: str = row["content"]
            hit = sum(content.count(kw) for kw in keywords) or (1 if question in content else 0)
            if hit == 0:
                continue
            score = hit / max(len(content), 1) * 100
            scored.append(
                (
                    score,
                    ChatSource(
                        doc_id=row["id"],
                        chunk_index=0,
                        score=round(score, 4),
                        snippet=content[:200],
                    ),
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    async def answer(self, kb_id: UUID, user_id: UUID, question: str, top_k: int) -> ChatResponse:
        self.kb_service.get_or_403(kb_id, user_id)
        sources = self._retrieve(kb_id, question, top_k)
        if not sources:
            return ChatResponse(answer="知识库中没有找到相关内容。", sources=[])
        # W14 TODO：替换为真实 LLM 调用
        ctx = "\n---\n".join(s.snippet for s in sources)
        return ChatResponse(answer=f"（占位回答）根据检索到的片段：\n{ctx}", sources=sources)

    async def answer_stream(
        self, kb_id: UUID, user_id: UUID, question: str, top_k: int
    ) -> AsyncIterator[str]:
        """SSE 流式输出。

        W14 TODO：透传 LLM 的真实 token 流，处理超时与客户端断开（CancelledError）。
        """
        result = await self.answer(kb_id, user_id, question, top_k)
        for chunk in _fake_token_stream(result.answer):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"


def _fake_token_stream(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
