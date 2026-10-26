import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from retry import retry

logger = logging.getLogger(__name__)


class JSONFileKBRepository:
    """JSON 文件当数据库：每次操作 读完→改→写回，不驻留内存状态。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        if not path.exists():
            path.write_text(
                json.dumps({"kbs": {}}, ensure_ascii=False),
                encoding="utf-8",
            )

    def _load(self) -> dict[str, Any]:
        text = self._path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return {"kbs": {}}
        data.setdefault("kbs", {})
        return data

    @retry(times=3)
    def _save(self, data: dict[str, Any]) -> None:
        logger.info("写盘 kbs=%d", len(data["kbs"]))
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(self, owner_id: str, name: str) -> dict[str, Any]:
        data = self._load()
        record: dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "owner_id": owner_id,
            "name": name,
            "created_at": time.time(),
        }
        data["kbs"][record["id"]] = record
        self._save(data)
        return record

    def get(self, kb_id: str) -> dict[str, Any] | None:
        data = self._load()
        return data["kbs"].get(kb_id)

    def list_by_owner(self, owner_id: str) -> list[dict[str, Any]]:
        data = self._load()
        return [kb for kb in data["kbs"].values() if kb["owner_id"] == owner_id]

    def delete(self, kb_id: str) -> bool:
        data = self._load()
        existed = data["kbs"].pop(kb_id, None) is not None
        if existed:
            self._save(data)
        return existed
