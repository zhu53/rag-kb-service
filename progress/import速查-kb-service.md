# Import 速查表（kb-service）

> 用法：写代码先写名字不写 import，红了按 Alt+Enter 让 PyCharm 补。
> 这张表只负责「想不起来全名/路径」时查。import 属于样板，不属于手写范围。

## 标准库 / 第三方

| 要用的东西 | import 语句 |
|---|---|
| 列表达式 / update / select / func / event | `from sqlalchemy import update, select, func, event` |
| Session / sessionmaker | `from sqlalchemy.orm import Session, sessionmaker` |
| Engine 类型注解 | `from sqlalchemy.engine import Engine` |
| UUID | `from uuid import UUID` |
| UTC / datetime | `from datetime import UTC, datetime` |
| pytest.raises / fixtures | `import pytest` |

## 项目内（按分层记：上层只能依赖下层）

| 要用的东西 | import 语句 | 记法 |
|---|---|---|
| 业务异常（NotFoundError 等） | `from kb_service.core.exceptions import NotFoundError` | core 层，谁都能用 |
| get_db / SessionLocal | `from kb_service.core.db import get_db` | core 层 |
| ORM 模型 KnowledgeBase / Base | `from kb_service.repositories.models import KnowledgeBase, Base` | repositories 层 |
| KBRepository | `from kb_service.repositories.kb_repo import KBRepository` | repositories 层 |
| KBRow DTO | `from kb_service.repositories.rows import KBRow` | repositories 层 |
| 仓储协议 | `from kb_service.repositories.protocols import KBRepositoryProtocol` | repositories 层 |
| KBCreate / KBUpdate / KBOut | `from kb_service.schemas.kb import KBCreate` | schemas 层 |
| 依赖注入 fake | `from tests.fakes import FakeKBRepository` | 只在测试里 |

## 事件回调的标准签名（mypy strict 必须带注解）

```python
def _rec(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
    ...
```

## PyCharm 快捷键

| 键 | 作用 |
|---|---|
| Alt+Enter | 补 import（光标放在红色名字上） |
| Ctrl+Q | 快速文档 |
| Ctrl+Alt+O | 清理 unused import |
| 双击 Shift | 全局搜类名（只知道名字不知道路径时用） |
