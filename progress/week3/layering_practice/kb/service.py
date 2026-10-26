import logging
from typing import Any

from .error import ConflictError, ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)


class KBService:
    def __init__(self, repo) -> None:  # ← 接收"任何满足 Protocol 的东西"
        self._repo = repo

    def create_kb(self, owner_id: str, name: str) -> dict[str, Any]:
        # 你的工具只有契约四方法。查"同名"没有 get_by_name 可用，
        # 只能：list_by_owner(owner_id) → 遍历看有没有记录的 "name" 等于 name
        # 命中 → raise ConflictError(...)；没命中 → return self._repo.create(owner_id, name)
        existing = self._repo.list_by_owner(owner_id)
        if any(kb["name"] == name for kb in existing):
            raise ConflictError(f"用户 {owner_id} 已存在同名知识库：{name}")
        logger.info("创建知识库 name=%s owner=%s", name, owner_id)
        return self._repo.create(owner_id, name)

    def get_kb(self, owner_id: str, kb_id: str) -> dict[str, Any]:
        # 两步判断，顺序别乱：
        # ① repo.get(kb_id) is None → NotFoundError
        # ② 记录的 "owner_id" 不是这个 owner → ForbiddenError
        # 都过了 → return 记录
        kb = self._repo.get(kb_id)
        if kb is None:
            raise NotFoundError(f"知识库不存在：{kb_id}")
        if kb["owner_id"] != owner_id:
            raise ForbiddenError(f"无权访问知识库：{kb_id}")
        logger.info("命中知识库 id=%s", kb["id"])
        return kb

    def delete_kb(self, owner_id: str, kb_id: str) -> None:
        # 复用 get_kb：先 get_kb(owner_id, kb_id)（它替你把 NotFound/Forbidden 都判了）
        # 过了再 self._repo.delete(kb_id)。
        # 这叫"逻辑复用"——delete 自己不重复写鉴权
        self.get_kb(owner_id, kb_id)
        self._repo.delete(kb_id)
        logger.info("删除知识库 id=%s", kb_id)
