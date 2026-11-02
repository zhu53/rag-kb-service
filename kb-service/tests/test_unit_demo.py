"""我的第一个单元测试：只测 KBService，不启 FastAPI。"""

from uuid import uuid4

import pytest
from tests.fakes import FakeKBRepo

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.services.kb_service import KBService


def test_missing_kb_raises_not_found() -> None:
    svc = KBService(repo=FakeKBRepo())  # ← 把 fake 塞进去
    with pytest.raises(NotFoundError):
        svc.get_or_403(uuid4(), uuid4())


def test_other_users_kb_raises_forbidden() -> None:
    alice, bob = uuid4(), uuid4()
    kb_id = uuid4()
    repo = FakeKBRepo()
    repo.kbs[kb_id] = {"owner_id": alice}
    svc = KBService(repo=repo)
    with pytest.raises(ForbiddenError):
        svc.get_or_403(kb_id, bob)
