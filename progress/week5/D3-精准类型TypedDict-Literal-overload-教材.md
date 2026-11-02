# W5-D3 · 精准类型：把 `dict[str, Any]` 点名（零基础版教材）

> 读者假设：**你没用过 `TypedDict`，没写过 `Literal`，也不知道 `overload` 存在的意义**。
> 本文从"一个 store 行为什么是 `dict[str, Any]`"讲起。所有输出都是在 `kb-service/.venv`（Python 3.11 / mypy）里实测的原样输出，不是示意。
> 昨天留的两个预告坑今天都会撞到：`total=False` 方括号访问、`overload` 顺序。

---

## 0. 痛点：`dict[str, Any]` 是个黑洞

### 0.1 现状盘点

D2 结束时，`src/` 里还剩 **25 处 `dict[str, Any]`**（8 个文件）。分布：

| 文件 | 处数 | 是什么 |
|---|---|---|
| `repositories/`（base/kb_repo/doc_repo/protocols） | 18 | **store 里的"行"**——真正该有类型的 |
| `core/security.py` | 4 | JWT payload（第三方库边界，D4 处理） |
| `core/logging.py` | 1 | 日志字段（真·任意结构，**该保留**） |
| `services/`（get_or_403、_parse_sync） | 2 | 顺着 repo 的返回类型带出来的 |

先建立一个判断力：**不是所有 `dict[str, Any]` 都该消灭**。分三类：

1. **结构固定的**（store 行、JWT payload）→ 该点名，用 `TypedDict`
2. **值域固定的字段**（status 只能是那几个词）→ 用 `Literal` 或枚举
3. **真·任意的**（日志的 extra 字段）→ 保留 `Any`，这就是它的工作

今天消灭第 1 类、约束第 2 类、给第 3 类办"合法居留"。

### 0.2 一个先亮出来的实锤：`Any` 掩盖了一年多的潜伏 bug

这是今天落地预演时 mypy 抓到的真货。`tests/test_rag_async.py` 的集成测试里，往 store 塞数据是这样写的（改前原样）：

```python
now = datetime.now(UTC).isoformat()      # ← 字符串！

store.kbs[kb_id] = {
    ...
    "created_at": now,                   # str 进了 store
}
```

而真实 repo（`kb_repo.py:18`）放进去的是：

```python
now = store.now()                        # datetime 对象
"created_at": now,
```

**同一个字段，两种类型，在 `dict[str, Any]` 底下共存了四个星期。** 测试为什么没炸？因为 `KBOut.model_validate()`（pydantic）把 ISO 字符串自动解析成了 `datetime`——下游宽容救了上游的错。但要是哪天有人直接拿 `row["created_at"]` 做排序或相减，`str - datetime` 就是运行时 `TypeError`。

把行类型换成 `TypedDict` 后，mypy 第一时间报：

```
tests\test_rag_async.py:111: error: Incompatible types (expression has type "str",
    TypedDict item "created_at" has type "datetime")  [typeddict-item]
```

**记住这个案例，面试直接用**：`Any` 的危害不是"宽"，是**黑洞**——它让两种互斥的类型在同一个字段里和平共存，直到类型系统介入才现形。

### 0.3 没有 TypedDict 时人会怎么做

你可能会想："行结构为什么不直接定义一个 pydantic 模型？"

```python
class KBRowModel(BaseModel):
    id: UUID
    name: str
    ...
```

能跑，但代价是：**store 里存的和取出来的每次都要经过校验/转换**（`model_validate` / `model_dump`），repo 每个方法多两行仪式代码；而且 pydantic 模型是"边界翻译器"，store 行是**内部数据结构**——给它套校验器，就像给自家抽屉上海关锁。

需要的是一个"**运行时就是普通 dict，静态期却逐键检查**"的类型。这就是 `TypedDict`（PEP 589）。

---

## 1. 五分钟：先跑一个 15 行的例子

临时目录建 `td_demo.py`（跑完删）：

```python
from typing import TypedDict
from uuid import UUID, uuid4


class KBRow(TypedDict):
    id: UUID
    name: str
    doc_count: int


row: KBRow = {"id": uuid4(), "name": "测试库", "doc_count": 0}
print(row["name"])
```

```powershell
# Windows PowerShell
& ..\python-backend-roadmap\kb-service\.venv\Scripts\python.exe -m mypy --strict td_demo.py
```

```bash
# Git Bash / Linux / macOS
../python-backend-roadmap/kb-service/.venv/Scripts/python.exe -m mypy --strict td_demo.py
```

实测：`Success: no issues found in 1 source file`，运行时打印 `测试库`。

现在少写一个键再跑：

```python
def make() -> KBRow:
    return {"id": uuid4(), "name": "缺 doc_count"}
```

实测：

```
td_missing.py:11: error: Missing key "doc_count" for TypedDict "KBRow"  [typeddict-item]
```

**它就是普通 dict，但 mypy 逐键检查了。** 这 15 行就是 `TypedDict` 的全部本质，剩下的都是边界细节。

---

## 2. 概念逐层展开：TypedDict

### 2.1 一句话定义

**`TypedDict` 是"带字段清单的 dict 标注"：运行时就是一个普通 `dict`，mypy 按声明的键和值类型逐键检查。**

三个立即可验证的性质：

**性质 1：运行时零感知**

```python
row = {"id": "1", "name": "ok"}
print(type(row))    # <class 'dict'> —— 不是 KBRow
```

`TypedDict` 类**在运行时根本不产生类型对象**（准确说会产生一个类对象，但实例不会 `isinstance` 它——见性质 3）。

**性质 2：兼容判断是结构化的**（和 D2 的 `Protocol` 同一族）

普通 dict 字面量直接传给 TypedDict 参数——通过（实测）：

```python
def takes_row(row: KBRow) -> str: return row["name"]
takes_row({"id": "1", "name": "ok"})   # mypy Success
```

而且**字面量内容会被逐键检查**：少键报 `Missing key`，值类型错报 `typeddict-item`。这就是"结构化"：不看血缘，看长得对不对。

**性质 3：不能 `isinstance`——mypy 和运行时都拦**

```python
isinstance(row, KBRow)
```

实测双杀：

```
# mypy
error: Cannot use isinstance() with TypedDict type  [misc]
# 运行时
TypeError: TypedDict does not support instance and class checks
```

原因：运行时所有 dict 长得都一样，没有可靠的办法区分"这个 dict 是不是按 KBRow 的结构造的"（逐键查？查哪些键？多出来的键算不算？）。PEP 589 直接禁止。

### 2.2 `total=False`：可选键，以及今天的第一个预告坑

```python
class DocRowUp(TypedDict, total=False):
    status: str        # 可选
    summary: str       # 可选
```

**坑（实测坐实）**：对可选键直接 `[]` 访问，mypy 完全放行，运行时 `KeyError`：

```python
def show(row: DocRowUp) -> None:
    print(row["status"])    # ← mypy Success！

show({})                    # total=False 允许空 dict
```

```
# mypy --strict
Success: no issues found in 1 source file
# 运行时
KeyError: 'status'
```

**这是 mypy 的真实盲区**（pyright 会在这一行报错，mypy 不会）。所以纪律要靠约定：

| 场景 | 写法 |
|---|---|
| 必填键 | `row["name"]` 随便用 |
| 可选键（`total=False` 或拆分协议里的可选） | **永远** `row.get("summary")`，或先 `if "summary" in row:` |

再补一个容易忘的：`total=False` 是**全类开关**——它让**所有**键可选。想要"一部分必填一部分可选"，用继承拆两个：

```python
class DocRowRequired(TypedDict):
    id: UUID
    content: str

class DocRowPatch(DocRowRequired, total=False):
    status: str          # 可选
```

### 2.3 TypedDict 的规则表

| 规则 | 表现（实测） |
|---|---|
| 字面量直接赋值/传参 → 逐键检查 | 少键 `Missing key`、值错 `typeddict-item` |
| 变量传参（`dict[str, str]` → `KBRow`） | **通过**——mypy 只在字面量处逐键查，变量只查宽度兼容 |
| `row[k] = v`（k 是 str 变量） | `TypedDict key must be a string literal` |
| `row.update(any_dict)` | `Argument 1 to "update" of "TypedDict" has incompatible type` |
| `row \|= any_dict` | 同上，`typeddict-item` |
| `cast("dict[str, Any]", row).update(any_dict)` | **通过**（见 §2.4） |
| `isinstance(row, KBRow)` | 双杀（mypy + 运行时） |

**读表结论**：TypedDict 的保护是"**写在门口**"（构造/返回的字面量处），进门之后的动态操作（按变量名写键、update 任意 dict）都不设防。它防的是"造错"，不防"改坏"。

### 2.4 本项目必撞的坑：`row.update(payload)`

`kb_repo.update()` 里有这么一段（`kb_repo.py:49`）：

```python
payload = data.model_dump(exclude_unset=True)   # dict[str, Any]
row.update(payload)                             # KBRow.update(dict[str, Any])
```

行类型换成 `KBRow` 后，这行报：

```
kb_repo.py:49: error: Argument 1 to "update" of "TypedDict" has incompatible type
    "dict[str, Any]"; expected "TypedDict({'id'?: UUID, 'owner_id'?: UUID, 'name'?: str, ...})"
    [typeddict-item]
```

（注意报错里每个键带 `?`——update 的参数允许是"部分键"，所以 mypy 把目标表示成全可选的形状。）

三种解法实测：

| 解法 | 结果 |
|---|---|
| `for k, v in payload.items(): row[k] = v` | ❌ `TypedDict key must be a string literal` |
| `row \|= payload` | ❌ 同 update |
| `cast("dict[str, Any]", row).update(payload)` | ✅ **通过** |

**本项目采用第三种**，并把这个 `cast` 登记进逃生口清单：

> **`kb_repo.py:49` 与 `fakes.py` 同位置**：`cast("dict[str, Any]", row).update(payload)`
> 理由：payload 来自 `KBUpdate.model_dump(exclude_unset=True)`，键集合由 pydantic 模型决定，mypy 无法静态得知；TypedDict 的 update 只接受另一个 TypedDict，而 pydantic 不会产出 TypedDict。
> 删除条件：W7 换 SQLAlchemy 后 update 走 ORM 字段赋值，这个 cast 自然消失。

这个 cast 和 D1 讲过的"滥用 cast"区别在哪？**滥用是压契约冲突，这里是承认类型系统表达力的边界**（pydantic 的动态性 TypedDict 接不住），且方向是"局部放开一行"，不是"全局关检查"。

### 2.5 TypedDict vs pydantic 模型 vs dataclass：该用哪个

| | TypedDict | pydantic BaseModel | dataclass |
|---|---|---|---|
| 运行时形态 | 普通 dict | 校验器类 | 类实例 |
| 校验 | 无 | 有（类型转换/约束） | 无 |
| 逐键静态检查 | ✅ | ✅（属性访问） | ✅（属性访问） |
| 访问方式 | `row["name"]` | `row.name` | `row.name` |
| 适用位置 | **内部存储结构**（store 行、缓存条目） | **系统边界**（API 请求/响应、外部数据） | 内部不可变值对象 |

**一句话判据：离边界越近越该用 pydantic，离存储越近越该用 TypedDict。** 本项目里 `KBOut`（API 响应）是 pydantic，`KBRow`（store 行）是 TypedDict，中间 `KBOut.model_validate(row)` 是边界翻译——pydantic 的 `model_validate` 接受 `Any`，所以 TypedDict 直接传不报错。

---

## 3. 落地到项目（真实全过程，副本上跑的）

### 第 1 步：建 `rows.py`

新建 `kb-service/src/kb_service/repositories/rows.py`：

```python
from __future__ import annotations

from datetime import datetime
from typing import TypedDict
from uuid import UUID


class KBRow(TypedDict):
    """kb_service.store 里一行知识库的结构。"""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    doc_count: int
    created_at: datetime
    updated_at: datetime


class DocRow(TypedDict):
    """doc_service.store 里一行文档的结构。"""

    id: UUID
    kb_id: UUID
    title: str
    content: str
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime
```

**字段清单不是凭记忆写的**——抄自 `kb_repo.create` / `doc_repo.create` 里 row 字面量的真实键。放 `repositories/` 下（行是持久层概念），`protocols.py` 和两个 repo 都从这里 import，谁也不 import 谁，不产生环。

> `DocRow.status` 先保持 `str`，§4 会讲为什么不急着换 `Literal`。

### 第 2 步：换 `base.py` 和两个 repo

```python
# base.py
self.kbs: dict[UUID, KBRow] = {}
self.docs: dict[UUID, DocRow] = {}
```

`kb_repo.py` / `doc_repo.py` 里所有 `dict[str, Any]` 签名换成 `KBRow` / `DocRow`；`row: dict[str, Any] = {...}` 的局部标注换成 `row: KBRow = {...}`——**这一步 mypy 会顺手检查你的字面量**，键名拼错当场红。

`kb_repo.update` 撞 `update` 坑，按 §2.4 修：

```python
payload = data.model_dump(exclude_unset=True)
cast("dict[str, Any]", row).update(payload)   # 逃生口，登记了理由
row["updated_at"] = store.now()
```

### 第 3 步：换 `protocols.py` 和 service 的返回类型

协议里的 `dict[str, Any]` 全换 `KBRow` / `DocRow`（注意 `DocReader` / `DocRepo` 是 DocRow，别全替换成 KBRow）；`kb_service.get_or_403` 返回 `KBRow`；`doc_service._parse_sync` 收 `DocRow`。

改完 `rag_service.py:32` 的 `content: str = row["content"]` **自动变对了**——这就是 TypedDict 的直接收益：`row["content"]` 的类型从 `Any` 变成 `str`，这一行连"为什么标注"都不需要了。

### 第 4 步：同步 fakes 和测试（16 个错误）

第一轮实测 mypy 共 **16 个错误**，分类：

| 类 | 数量 | 内容 |
|---|---|---|
| update 坑 | 2 | `kb_repo.py:49` + `fakes.py` 同位置 |
| fake 签名不匹配 | 10 | 返回 `dict[str, Any]` 比协议的 `KBRow` **宽** → 返回方向不兼容（D2 的协变规则反着用：实现返回必须更窄或相等，`dict[str, Any]` 比 `KBRow` 宽，所以报） |
| **潜伏 bug** | 4 | `test_rag_async.py` 的 `isoformat()`（见 §0.2） |

修法：

- fakes.py：`self.kbs: dict[UUID, KBRow]`，六个方法签名照抄新 repo；update 同样用 cast
- `test_rag_async.py`：`now = datetime.now(UTC)`（**删掉 `.isoformat()`——这不是"让 mypy 闭嘴"，是把真 bug 修了**）
- `test_unit_demo.py` 里 `repo.kbs[kb_id] = {"owner_id": alice}` 这种**部分行**，TypedDict 要求完整键，补全 7 个字段
- `test_doc_service.py` 的 `SpyDocRepo.list_by_kb` 签名同步换 `DocRow`

### 第 5 步：全绿验收

```
Success: no issues found in 48 source files      （多了 rows.py，46→48）
57 passed
All checks passed! / 45 files already formatted
```

### 第 6 步：清点战场

```
落地前 src/ 的 dict[str, Any]：25 处（8 个文件）
落地后剩余：6 处
├─ core/security.py ×4   JWT payload —— 第三方边界，D4 处理
├─ core/logging.py ×1    日志 extra —— 真任意，合法居留
└─ kb_repo.py ×1         cast("dict[str, Any]", ...) —— §2.4 的逃生口
```

**每个剩下的都有名字和理由，这才叫"消灭"——不是赶尽杀绝，是把无名的都变成有名的。**

---

## 4. `Literal`：把值域钉死

### 4.1 一句话定义

**`Literal["a", "b"]` 表示"这个值只能是这几个字面量之一"**（PEP 586）。

### 4.2 三个实测行为

**行为 1：拼写错误当场红**

```python
Status = Literal["pending", "ready", "failed"]

def set_status(s: Status) -> None: ...

set_status("processsing")     # 手滑多打一个 s
```

```
lit1.py:9: error: Argument 1 to "set_status" has incompatible type
    "Literal['processsing']"; expected "Literal['pending', 'ready', 'failed']"  [arg-type]
```

报错把两个值集都列出来了，排错零成本。对比 `status: str` 世界里，拼错的字符串一路睡进数据库，直到某个 `WHERE status='ready'` 查不到才被发现。

**行为 2：`str` 不能传给 `Literal`——即使值合法**

```python
s: str = "ready"
set_status(s)    # ❌ error: ... "str"; expected "Literal['pending', 'ready', 'failed']"
```

这是**特性不是缺陷**：类型系统的视角里 `str` 是"任何字符串"，它可能值非法。想让一个 `str` 变成 `Status`，必须**显式收窄**——`==` 比较、`in` 判断，或 `cast`（收窄失败的风险你自己背）。

**行为 3：`==` 比较会收窄**

```python
def handle(s: Status) -> str:
    if s == "ready":
        return s.upper()   # 这个分支里 s 已收窄成 Literal["ready"]
    return s
```

实测通过。收窄是 D1 讲过的 `Optional` + `if row is None` 的同款机制，只是判据从"是不是 None"换成了"值等不等于"。

### 4.3 本项目的选择：已有 `DocStatus(StrEnum)`，为什么不用 Literal 改写

`schemas/doc.py` 里已经有：

```python
class DocStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
```

所以 `DocRow.status` 保持 `str`、`doc_repo.create(status: str = "pending")` **不动**——不是偷懒，是**正确的现状**。两者怎么选：

| | `Literal` | `StrEnum` |
|---|---|---|
| 本质 | 类型的值域标注 | 真正的运行时对象（类） |
| 能挂方法/属性吗 | 不能 | 能 |
| 能被 `for` 遍历全部成员吗 | 不能 | `list(DocStatus)` |
| 定义处和使用处 | 同文件即可 | 适合跨模块共享 |
| 值在运行时可迭代/可反射 | 否 | 是 |
| 典型场景 | 局部函数的参数收窄（`mode: Literal["r", "rb"]`） | 领域状态机（pending→processing→ready/failed） |

**判据：需要一个"运行时对象"（遍历、方法、跨层共享身份）用 Enum；只需要"静态约束值域"用 Literal。** `DocStatus` 是领域状态机（W11 Celery 要遍历、API 要序列化、跨 4 个模块用），枚举是对的；`DocRow.status: str` 而不是 `DocStatus` 的真正升级放 D4（pydantic 的序列化边界）之后。

> 一个容易混的点：mypy 对 `def f(s: DocStatus)` 传 `"ready"` 字面量**不放行**（枚举成员和字符串是两个类型），这与 `Literal` 不同。想两边都吃，用 `Literal[DocStatus.READY]` 或 `DocStatus("ready")` 转换。

### 4.4 `Literal` 的兄弟用法

- `Literal[True]`：`assert_isinstance` 风格的布尔细化（TypeGuard 的前身）
- `Literal` + `overload`：按字面量分派返回类型（§5 的标准用例）
- `Final` + 字面量：`TIMEOUT: Final = 30` 让 mypy 把变量当字面量

---

## 5. `overload`：让"同一个函数、不同入参、不同返回"有类型

### 5.1 一句话定义

**`@overload` 给同一个函数声明多套"参数→返回"签名，mypy 按调用点参数选签名；运行时只有最后一个（实现体）存在。**

### 5.2 三必要条件（实测违反后果）

1. **至少两个 `@overload` 变体**——只有一个：`error: Single overload definition, multiple required [misc]`（实测）
2. **变体方法体只有 `...`**——变体不是函数，是签名声明
3. **最后是无装饰器的实现体**——没有它：`error: Missing return statement [empty-body]`（实测，因为 mypy 把唯一的 `@overload` 当成了实现但它是空体）

```python
from typing import overload

@overload
def parse(x: str) -> list[str]: ...
@overload
def parse(x: bytes) -> dict[str, int]: ...
def parse(x: str | bytes) -> list[str] | dict[str, int]:
    if isinstance(x, str):
        return x.split()
    return {"len": len(x)}

a: list[str] = parse("a b c")       # 精确拿到 list[str]
b: dict[str, int] = parse(b"abc")   # 精确拿到 dict[str, int]
```

实测两处调用都通过。没有 overload 的话，返回类型只能写 `list[str] | dict[str, int]`，调用方每次都要 `cast` 或收窄。

### 5.3 顺序坑（昨天预告的）——好消息：mypy 能抓

宽签名放前面、精确签名放后面：

```
ol_bad.py:7: error: Overloaded function signature 2 will never be matched:
    signature 1's parameter type(s) are the same or broader  [overload-cannot-match]
```

**mypy 直接报"签名 2 永远不会被匹配到"**——所以这个坑比想象中安全，前提是你的文件真的过了 mypy。它依然值得知道，因为这个坑的真实形态是：①文件根本没进 mypy 检查范围（脚本、旧代码）②有人用 `# type: ignore` 压掉了。**口诀：变体从最精确到最宽排列**（和 `except` 从子类到父类一个道理）。

### 5.4 真正的坑：运行时只看实现体（实测坐实）

两个更阴的行为，都实测过：

**坑 A：实现体漏分支，mypy 放行**

```python
@overload
def parse(x: str) -> list[str]: ...
@overload
def parse(x: bytes) -> dict[str, int]: ...
def parse(x: str | bytes) -> list[str] | dict[str, int]:
    if isinstance(x, str):
        return x.split()
    return {}          # ← bytes 分支逻辑丢了，但类型"对"
```

```
# mypy --strict
Success: no issues found in 1 source file
# 运行时
parse(b"abc")  →  {}
```

类型满足、语义丢失。**overload 的变体不参与运行时**，mypy 只检查实现体的返回类型与声明兼容，不检查"每个变体都有对应的逻辑分支"。

**坑 B：运行时函数就是实现本身，变体不存在**

```python
@overload
def f(x: int) -> int: ...
@overload
def f(x: str) -> str: ...
def f(x): return x

print(f("hello"), f.__annotations__)   # hello {}
```

`f` 运行时就是最后那个实现；`__annotations__` 是**空的**（实现没写注解）。前面的两个 `@overload` 被**同名覆盖**，彻底消失。所以"给 overload 变体写 docstring、写函数体"都是无效劳动——它们活不过 import。

### 5.5 本项目为什么没有 overload

诚实说：**项目里没有重载需求**（这也是判断力）。`overload` 的典型落点在两类地方：标准库/第三方 stub（`open()` 的 mode、`dict.get` 的多态）和自己写的"多形态入口"（比如未来的 `embed(text: str)` / `embed(texts: list[str])`）。D4 讲第三方 stub 时会见到真身。**没需求不硬造**——为了练 overload 而给项目塞一个重载函数，是给门禁添乱。

---

## 6. 动手任务（7 个，按顺序做）

> 规矩照旧：提示阶梯一次只看一层。

### 任务 1：写 `rows.py`（约 15 分钟）

字段清单**抄自** `kb_repo.create` 和 `doc_repo.create` 的 row 字面量，不要凭记忆。写完先跑 mypy 确认 0 错（此时没人用它，`Success: ... 47 source files`）。

<details>
<summary>做完自查</summary>

- `KBRow.description` 是 `str | None`（`KBCreate.description` 可空）
- `DocRow` 的 `status` 先写 `str`（§4.3 的理由）
- 文件里**不 import** 任何 repo/schemas——只标准库。加了 `Any` 就错了，这个文件的目标就是消灭它
- 类 docstring 写清楚"store 里一行的结构"，这是给三个月后的自己的
</details>

### 任务 2：`base.py` 换类型（约 5 分钟）

`self.kbs: dict[UUID, KBRow]`、`self.docs: dict[UUID, DocRow]`。同时删掉 `typing.Any` 的 import。

### 任务 3：两个 repo 换签名（约 20 分钟）

`kb_repo.py` 5 处、`doc_repo.py` 4 处。**预期会撞 `row.update(payload)` 报错**——先自己读报错（注意那个带 `?` 的形状），再决定怎么改。

<details>
<summary>提示阶梯</summary>

**第 1 层**：报错说 update 的参数期望 `TypedDict({...}?...)`（全可选形状），你给的是 `dict[str, Any]`。想想为什么 TypedDict 拒绝任意 dict 的合并？

**第 2 层**：因为任意 dict 可能带来"声明之外的键"，TypedDict 的类型保证就破了。但你的 payload 键集合确实由 `KBUpdate` 决定——你知道得比类型系统多。这该用什么手段？

**第 3 层**：`cast("dict[str, Any]", row).update(payload)`——把 row **局部**当作普通 dict 来合并，合并完的 row 还是 KBRow。写完把这条 cast 记进逃生口清单（理由 + 删除条件）。**卡住超过 10 分钟再看这层。**
</details>

### 任务 4：`protocols.py` 与 service 返回类型（约 15 分钟）

协议 7 处 + `get_or_403` + `_parse_sync`。注意 `DocReader`/`DocRepo` 用 `DocRow`——全局替换 `dict[str, Any]` → `KBRow` 会把 Doc 系全换错，逐个改。

<details>
<summary>自查</summary>

替换后 `protocols.py` 不该再 import `Any`；`kb_service.py` 的 `get_or_403` 返回 `KBRow`；顺手观察 `rag_service.py:32` 的 `content: str = row["content"]` 现在多了什么保证。
</details>

### 任务 5：fakes 同步（约 15 分钟）

`FakeKBRepo` 六个方法签名 + `self.kbs` 换 `KBRow`。**预期报错和任务 3 同款**（update 坑），用同款解法。

<details>
<summary>注意一个细节</summary>

`_log` 的参数类型 `tuple[Any, ...]` **不要动**——账本本来就是"任意参数的记录"，这是 Any 的合法岗位。逐键消灭 ≠ 全面开战。
</details>

### 任务 6：测试同步——里面埋着今天的宝箱（约 20 分钟）

改完 src，mypy 会指到 `test_rag_async.py` 4 处 `typeddict-item`。**先读懂报错再改**：时间字段类型对不上。谁对？repo 写的是 `store.now()`（datetime），测试写的是 `now.isoformat()`（str）。

<details>
<summary>提示阶梯</summary>

**第 1 层**：这不只是"让 mypy 闭嘴"的改动——问自己：**store 里这个字段的真实类型应该是什么？** 答案在 `kb_repo.create` 怎么写 `"created_at"`。

**第 2 层**：应该统一成 `datetime`（排序、相减都要真时间对象）。测试用 `isoformat()` 是当年"看着像就行"的产物，pydantic 的宽容把它掩盖了。所以修法是删掉 `.isoformat()`，不是把 KBRow 的时间改成 str。

**第 3 层**：`test_unit_demo.py` 里 `repo.kbs[kb_id] = {"owner_id": alice}` 会报 `Missing key`——TypedDict 要求完整行。补全 7 个字段（这个测试只读 `owner_id`，但行的完整性是 store 的契约，不是使用方的）。**卡住再往下看。**
</details>

### 任务 7：全绿 + 清点（约 10 分钟）

```powershell
# Windows PowerShell（kb-service/ 下）
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check src tests
& .\.venv\Scripts\python.exe -m ruff format --check src tests
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py | Select-String "dict\[str, Any\]"
```

```bash
# Git Bash / Linux / macOS（kb-service/ 下）
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m ruff format --check src tests
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep "dict\[str, Any\]"
```

验收：`48 source files` 零错 / `57 passed` / ruff 全过；最后一条命令应该只剩 `core/` 下的 5 处 + `kb_repo.py` 的 1 处 cast。

---

## 7. 易错点表

| 坑 | 症状 | 正解 |
|---|---|---|
| 把 TypedDict 当类用：`isinstance` / 调方法 | mypy `[misc]` + 运行时 `TypeError` 双杀 | 它运行时就是 dict；判断结构用收窄逻辑或重构 |
| `total=False` 键直接 `[]` 取 | **mypy 放行**（盲区），运行时 `KeyError` | 可选键永远 `.get()` 或先 `in` 判断 |
| 给 TypedDict 造"部分行"塞进 store | `Missing key "..." for TypedDict` | 行的完整性是存储契约；测试也要造完整行 |
| `row.update(any_dict)` / `\|=` | `Argument 1 to "update" of "TypedDict"...` | `cast("dict[str, Any]", row).update(...)` + 登记逃生口 |
| `row[k] = v`（k 是变量） | `TypedDict key must be a string literal` | 键必须是字面量；动态键走 cast 边界 |
| 以为"变量传参也逐键查" | 想不通为什么 `dict[str, str]` 传得进去 | 逐键检查只发生在**字面量**；变量只查兼容性 |
| `str` 直接传给 `Literal` 参数 | `expected "Literal[...]"` | 先收窄（`==`/`in`）或显式转换；不合法值自己 `cast` 背锅 |
| overload 变体在前宽在后 | `overload-cannot-match`（mypy 能抓） | 变体从精确到宽排（像 except 从子到父） |
| overload 实现体漏分支 | **mypy 放行**，运行时静默丢语义 | 实现体逐分支对齐变体；用穷尽性检查（`assert_never`）兜底 |
| 给 overload 变体写函数体/docstring | 白写——运行时被同名实现覆盖 | 变体只有签名；文档写实现体上 |
| 把 store 行换成 pydantic 模型 | 每次读写都要 validate/dump 仪式 | 离边界近用 pydantic，离存储近用 TypedDict |
| 看到剩余 `dict[str, Any]` 就全灭 | 日志/动态结构被硬造类型 | 三分类：行结构 → TypedDict；值域 → Literal；真任意 → 保留并说理由 |

---

## 8. 命令速查（双平台，`kb-service/` 下）

### 8.1 找出还剩哪些 `dict[str, Any]`

```powershell
# Windows PowerShell
Get-ChildItem -Recurse -Include *.py src | Select-String "dict\[str, Any\]" |
    ForEach-Object { "$($_.Filename):$($_.LineNumber)" }
```

```bash
# Git Bash / Linux / macOS
grep -rn "dict\[str, Any\]" --include=*.py src
```

### 8.2 看某个 TypedDict 被谁用

```powershell
# Windows PowerShell
Get-ChildItem -Recurse -Include *.py src, tests | Select-String "KBRow"
```

```bash
# Git Bash / Linux / macOS
grep -rn "KBRow" --include=*.py src tests
```

### 8.3 mypy + pytest + ruff 全家桶

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check src tests
& .\.venv\Scripts\python.exe -m ruff format --check src tests
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m ruff format --check src tests
```

> 照旧：mypy 输出全在 stdout，PowerShell 不要加 `2>&1`。

---

## 9. 面试问法

### Q1：TypedDict 是什么？和普通 dict 标注、和 dataclass/pydantic 的区别？

**30 秒版**："TypedDict 是带字段清单的 dict 标注——运行时就是普通 dict 零开销，mypy 逐键检查。和 `dict[str, Any]` 的区别是键被点名了；和 pydantic 的区别是没有运行时校验，所以我用它存内部结构（store 行），pydantic 留给 API 边界。判据是离边界近用 pydantic，离存储近用 TypedDict。"

**追问链**：

→ *"TypedDict 能 isinstance 吗？"* 不能，mypy 和运行时双杀——运行时所有 dict 无法区分结构。

→ *"逐键检查什么时候生效？"* 只在**字面量**处（赋值/传参/return 的字面量）；变量传参只查兼容宽度。

→ *"它防不了什么？挖到底。"* 防不了"改坏"：`row[k] = v`（变量键）、`row.update(任意 dict)` 都不设防，合并动态 payload 只能局部 cast。所以 TypedDict 的保证是"**构造时刻对**"，不是"永远对"。要"永远对"就把行包成不可变对象（dataclass(frozen=True)），代价是失去 dict 生态（pydantic 直接收、`row["x"]` 语法）。这是个真实的工程权衡，我的选择是 TypedDict + update 处一个登记过的 cast。

### Q2：Literal 是什么？和 Enum 怎么选？

**30 秒版**："Literal 把值域钉死成几个字面量，拼写错误在 mypy 当场报，报错还把两个值集都列出来。和 Enum 的选择：需要运行时对象——遍历成员、挂方法、跨模块共享身份——用 Enum；只需要静态约束值域用 Literal。我项目的 DocStatus 是领域状态机所以是 StrEnum，而局部参数（比如模式开关）会写 Literal。"

**追问链**：

→ *"str 能传给 Literal 参数吗？"* 不能，即使值合法——`str` 在类型视角是"任意字符串"。要先 `==` 收窄或显式转换。

→ *"Literal 也能收窄？"* 对，`if s == "ready":` 分支里 s 收窄成 `Literal["ready"]`，和 Optional 收窄同一套机制。

→ *"运行时 Literal 存在吗？挖到底。"* 不存在——`typing.get_type_hints` 里能看到标注（因为它是表达式求值的结果），但没有任何运行时校验发生。传 `"ready "` 带空格照样进函数。所以 Literal 和 TypedDict 一样是"纯静态契约"，防线的全部在于 mypy 在 CI 里跑——又回到 D6 那句话：**没有门禁的类型标注只是注释**。

### Q3：overload 的三个必要条件？运行时是什么形态？

**30 秒版**："至少两个变体、变体只有 `...`、最后一个无装饰器实现体。运行时前面变体被同名覆盖彻底消失，调用的就是实现——我实测 `__annotations__` 都是空的。所以实现体必须覆盖所有变体的逻辑，mypy 只查返回类型兼容，不查分支完整性。"

**追问链**：

→ *"变体顺序错了会怎样？"* mypy 报 `overload-cannot-match`：宽签名在前会让后面的永远匹配不到。口诀从精确到宽，和 except 从子类到父类同构。

→ *"项目里哪用了？"* 现在没有——没有重载需求就不硬造。真正的落点在标准库 stub（`open()` 的 mode）和未来的多形态入口（embed 单个/批量）。D4 讲 stub 时会见到。

→ *"mypy 能查实现体覆盖所有分支吗？挖到底。"* 默认不能（实测放行漏分支）。组合拳是：Python 3.11 的 `typing.assert_never` + `Literal` 参数穷尽匹配——在实现体里 `match` 或 if-chain 每个字面量，else 分支 `assert_never(x)`，漏一个分支 mypy 就红。这是把"分支完整性"从语义问题变成类型问题，比测试更早拦截；代价是实现写法被绑定，简单函数不值得。

---

## 10. 闭卷自测

**1. TypedDict 运行时是什么？**
<details><summary>答案</summary>普通 `dict`。类型对象存在但实例不会与它关联，`isinstance` 被 PEP 589 禁止（mypy 报 `Cannot use isinstance() with TypedDict type`，运行时 `TypeError`）。</details>

**2. 逐键检查在什么时候生效？**
<details><summary>答案</summary>只在字面量上下文：赋值给 TypedDict 变量的字面量、传给 TypedDict 参数的字面量、函数 return 的字面量。少键 `Missing key`、值错 `typeddict-item`。变量传参只做兼容性检查（结构化/宽度），不逐键。</details>

**3. `total=False` 的键能直接 `row["k"]` 吗？mypy 说什么？**
<details><summary>答案</summary>语法上能跑，**mypy 放行（盲区，pyright 会报）**，运行时键缺失就 `KeyError`。纪律：可选键永远 `.get()` 或先 `in`。要"部分可选"用继承：必填类 + `(子类, total=False)` 扩展可选键。</details>

**4. TypedDict 怎么合并一个 `dict[str, Any]`？为什么三种常规写法两种都报错？**
<details><summary>答案</summary>合法解：`cast("dict[str, Any]", row).update(payload)`。`for k,v in ...: row[k]=v` 报 `TypedDict key must be a string literal`（键必须是字面量）；`row |= d` 和 `row.update(d)` 报 `typeddict-item`（任意 dict 可能引入声明之外的键，破坏类型保证）。cast 是"局部放开一行"并登记逃生口。</details>

**5. `Literal["pending","ready"]` 参数收到 `str` 变量（值合法）会怎样？**
<details><summary>答案</summary>报错：`"str"; expected "Literal['pending', 'ready']"`。`str` 在类型视角是任意字符串，可能非法。先 `==`/`in` 收窄，或显式 `cast`（风险自担）。</details>

**6. Literal 和 Enum 的选择判据？**
<details><summary>答案</summary>需要运行时对象（遍历成员、挂方法、跨模块共享身份、序列化行为）→ Enum；只要静态约束值域 → Literal。本项目 DocStatus 是跨 4 模块的领域状态机 → StrEnum；局部模式参数 → Literal。</details>

**7. overload 三必要条件？**
<details><summary>答案</summary>① 至少两个 `@overload` 变体（否则 `Single overload definition, multiple required`）；② 变体体只有 `...`；③ 最后必须有实现体（否则 `Missing return statement`）。</details>

**8. overload 运行时是什么？变体去哪了？**
<details><summary>答案</summary>运行时只有实现体——前面的变体被**同名定义覆盖**，彻底消失（实测 `f.__annotations__` 为空）。所以给变体写函数体/docstring 无效；实现体必须自己覆盖所有变体的逻辑，且 mypy 只查返回类型兼容，**不查分支完整性**（漏分支实测放行）。</details>

**9. 变体顺序错 mypy 会报吗？口诀？**
<details><summary>答案</summary>会：`overload-cannot-match`——"签名 N will never be matched"。口诀：从精确到宽排，和 `except` 从子类到父类同构。坑的真实形态是文件没进 mypy 或被 ignore 压掉。</details>

**10. 哪些 `dict[str, Any]` 该保留？本项目剩的 6 处分别在什么位置？**
<details><summary>答案</summary>真·任意结构的（日志 extra）和第三方边界（JWT payload，D4 处理）。剩余：`core/logging.py` ×1、`core/security.py` ×4、`kb_repo.py` ×1（update 处登记过的 cast）。判断句式：三类——行结构→TypedDict；值域→Literal；真任意→保留并说理由。说不出理由的 `Any` 才是债。</details>

**11. 白板题：写出 KBRow + 一个安全消费 status 可选键的函数。**
<details><summary>答案</summary>

```python
from typing import TypedDict
from datetime import datetime
from uuid import UUID

class DocRow(TypedDict, total=False):
    id: UUID
    content: str
    status: str          # 可选
    summary: str         # 可选

def title_of(row: DocRow) -> str:
    return row.get("summary") or "(无摘要)"   # 可选键 .get()，绝不 row["summary"]
```

要点：可选键一律 `.get()`；`or` 提供缺省时要意识到"空字符串也会触发缺省"（这是 review_11 坑 2 的近亲）。
</details>

**12. 白板题：overload 标注一个"传 str 返回 list、传 int 返回 dict"的函数。**
<details><summary>答案</summary>

```python
from typing import overload

@overload
def f(x: str) -> list[str]: ...
@overload
def f(x: int) -> dict[str, int]: ...
def f(x: str | int) -> list[str] | dict[str, int]:
    if isinstance(x, str):
        return x.split()
    return {"v": x}
```

要点：变体精确在前、实现签名是参数的并集、实现体 `isinstance` 收窄对应分支、`...` 不写函数体。
</details>

---

## 附：今天的实测结论速览（复习用）

| # | 实验 | 结论 |
|---|---|---|
| 1 | TypedDict 缺键字面量 | `Missing key "doc_count" [typeddict-item]` |
| 2 | total=False 键 `[]` 访问 | **mypy Success（盲区）**，运行时 `KeyError` |
| 3 | 普通 dict 字面量传 TypedDict 参数 | 通过（结构化），且内容仍逐键查 |
| 4 | `isinstance` TypedDict | mypy `[misc]` + 运行时 `TypeError` 双杀 |
| 5 | Literal 拼写错 | 报错列出两个值集，排错零成本 |
| 6 | `str` 传 Literal | 报错，即使值合法 |
| 7 | `==` 收窄 Literal | 通过 |
| 8 | overload 宽在前 | `overload-cannot-match`（mypy 能抓） |
| 9 | overload 实现体漏分支 | **mypy 放行**，运行时静默丢语义 |
| 10 | 只有 overload 无实现 | `Single overload definition, multiple required` |
| 11 | 运行时的 overload 函数 | 就是实现体，变体被同名覆盖，`__annotations__` 为空 |
| 12 | TypedDict 合并任意 dict | for/`\|=`/update 三种两种报错，`cast("dict[str, Any]", ...)` 通过 |
| 13 | 落地全程 | 16 错（2 update 坑 + 10 fake 签名 + **4 个 isoformat 潜伏 bug**）→ 0 错 / 57 测全绿 |

**今天最该带走的一句话**：

> `dict[str, Any]` 不是"没类型"，是"类型黑洞"——它让 `datetime` 和 `str` 在同一个字段里和平共存了四周。点名每个键，不是仪式，是把黑洞变成可检查的契约。
