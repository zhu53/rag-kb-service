from typing import Any

from kbcli.caching import LRUCache
from kbcli.errors import ConflictError, ForbiddenError, NotFoundError


class KBService:
    def __init__(self, repo, cache: LRUCache) -> None:
        self._repo = repo
        self._cache = cache

    def get_kb(self, owner_id, kb_id):
        cached = self._cache.get(kb_id)
        if cached is not None and cached["owner_id"] == owner_id:
            return cached  # ← 命中直接回
        kb = self._repo.get(kb_id)
        if kb is None:
            raise NotFoundError("没有该数据库")
        if kb["owner_id"] != owner_id:
            raise ForbiddenError("无权操作该数据库")
        self._cache.put(kb_id, kb)
        return kb

    def create_kb(self, owner_id: str, name: str) -> dict[str, Any]:
        existing = self._repo.list_by_owner(owner_id)
        if any(kb["name"] == name for kb in existing):
            raise ConflictError(f"用户 {owner_id} 已存在同名知识库：{name}")
        return self._repo.create(owner_id, name)

    def delete_kb(self, owner_id: str, kb_id: str) -> None:
        # 先校验权限（复用 get_kb 的逻辑）
        self.get_kb(owner_id, kb_id)
        self._repo.delete(kb_id)
        self._cache.delete(kb_id)

    def list_kbs(self, owner_id: str) -> list[dict[str, Any]]:
        return self._repo.list_by_owner(owner_id)
