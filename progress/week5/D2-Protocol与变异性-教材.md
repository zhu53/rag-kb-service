# W5-D2 · Protocol 与变异性（零基础版教材）

> 读者假设：**你从没用过 `Protocol`**，也不知道"变异性"这个词是什么意思。
> 本文从 D1 遗留的 8 个错误讲起，一路讲到"为什么方法参数要反过来看"。
> 所有命令输出都是在本项目 `kb-service/.venv`（Python 3.11）里跑出来的真实结果，不是示意。

---

## 0. 痛点：签名一模一样，mypy 偏说不行

### 0.1 现在的现场

D1 结束时 `mypy` 还剩 8 个错误。它们是长这样的：

```
tests\test_unit_demo.py:23: error: Argument "repo" to "KBService" has incompatible type "FakeRepo"; expected "KBRepository | None"  [arg-type]
tests\test_kb_service_unit.py:34: error: Argument "repo" to "KBService" has incompatible type "FakeKBRepo"; expected "KBRepository | None"  [arg-type]
tests\test_rag_async.py:62: error: Argument "doc_repo" to "RagService" has incompatible type "FakeDocRepo"; expected "DocRepository | None"  [arg-type]
Found 8 errors in 3 files (checked 46 source files)
```

先别急着改。**先想清楚它在说什么。**

错误的意思是：`KBService` 的构造函数要求一个 `KBRepository`，你给了个 `FakeKBRepo`，两者"不兼容"。

可是你打开 `tests/fakes.py` 看一眼，`FakeKBRepo` 的六个方法：

| 方法 | 真 `KBRepository` | `FakeKBRepo` | 一样吗 |
|---|---|---|---|
| `create` | `(UUID, KBCreate) -> dict[str, Any]` | `(UUID, KBCreate) -> dict[str, Any]` | ✅ |
| `get` | `(UUID) -> dict[str, Any] \| None` | `(UUID) -> dict[str, Any] \| None` | ✅ |
| `list_by_owner` | `(UUID, int, int) -> tuple[list[...], int]` | 同左 | ✅ |
| `count_by_owner` | `(UUID) -> int` | 同左 | ✅ |
| `update` | `(UUID, KBUpdate) -> dict[str, Any] \| None` | 同左 | ✅ |
| `delete` | `(UUID) -> bool` | 同左 | ✅ |

**六个全一样。** 那 mypy 凭什么说不兼容？

### 0.2 罪魁祸首是"它怎么判断兼容"

mypy 判断"一个东西能不能当另一个用"，有两种截然不同的规则：

**规则 A（名义类型 / nominal typing）**：看**血缘**。`isinstance` 那一套——你是这个类或它的子类吗？

**规则 B（结构化类型 / structural typing）**：看**长相**。"你有没有那些方法、签名对不对"——不管你是谁生的。

Python 的**普通类**走规则 A。`FakeKBRepo` 没有继承 `KBRepository`，所以血缘上它们是两个陌生人，mypy 直接判死刑——**连签名都不去看**。

看 `kb_service/services/kb_service.py:18`：

```python
def __init__(self, repo: KBRepository | None = None) -> None:
    self.repo = repo or KBRepository()
```

这里的 `KBRepository` 是**一个具体的类**（`kb_repo.py:10: class KBRepository:`）。你写的不是一个"接口"，你写的是"我要这个类本身"。

**这就是根因**：你在构造函数里写的是"我需要 `KBRepository` 这个类"，但你想表达的是"我需要一个**能存取知识库的东西**"。前者是血缘，后者是能力。

### 0.3 一个必须自己踩过的坑：想当然的修法是错的

第一反应通常是："那让 `FakeKBRepo` 继承 `KBRepository` 不就行了？"

```python
class FakeKBRepo(KBRepository):   # ❌ 千万别这么干
    ...
```

这么改，mypy 立刻绿。但你会失去三样东西：

1. **测试不再隔离**：`KBRepository` 的方法直接操作模块级单例 `store`（`repositories/base.py:27: store = InMemoryStore()`）。继承后 fake 会带上全部真实逻辑，测的就不是"一条业务规则"，而是"真实存储 + 业务规则混在一起"。
2. **`__init__` 会连锁**：真类将来有 `__init__(self, session)` 时（W7 换 SQLAlchemy 就是这样），fake 被迫跟着实现一个自己根本不需要的构造。
3. **覆盖不了的假象**：`calls` 账本这类只属于替身的字段，跟真类混在一起后，你自己都分不清哪些是"契约"、哪些是"测试脚手架"。

一句话：**让替身去继承被替身的东西，等于把"契约"和"实现"焊死**。你要的是一个能替换的插头，不是一个必须同厂的插座。

**所以正确方向是：把"能力"单独写出来，声明成 `Protocol`。**

---

## 1. 五分钟：先跑一个 20 行的例子

先不碰项目。随便建个文件（比如 `scratch/proto_demo.py`，跑完就删），把下面这段抄进去。

```python
from typing import Protocol
from uuid import UUID


class Repo(Protocol):
    """我要的只是"能按 id 取一行"这个能力。"""

    def get(self, k: UUID) -> dict[str, object] | None: ...


class Fake:
    """没继承任何东西，只是"长得像"。"""

    def get(self, k: UUID) -> dict[str, object] | None:
        return None


def take(r: Repo) -> None:
    pass


take(Fake())   # ← 关键：这一行会不会报错？
```

跑一下：

```powershell
# Windows PowerShell
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\scratch
& ..\python-backend-roadmap\kb-service\.venv\Scripts\python.exe -m mypy --strict proto_demo.py
```

```bash
# Git Bash / Linux / macOS
cd /c/Users/acer-pc/WorkBuddy/2026-10-20-08-44-29/scratch
../python-backend-roadmap/kb-service/.venv/Scripts/python.exe -m mypy --strict proto_demo.py
```

实测输出：

```
Success: no issues found in 1 source file
```

**`Fake` 一行继承都没写，mypy 放行了。**

对照一下：把 `class Repo(Protocol):` 改成 `class Repo:`（去掉 `Protocol`），同样的代码：

```
proto_demo.py:18: error: Argument 1 to "take" has incompatible type "Fake"; expected "Repo"  [arg-type]
```

**同一份 `Fake`，一个 `Protocol` 关键词之差，结论完全相反。**

这就是今天全部内容的起点：`Protocol` 把"兼容"的判据从**血缘**换成了**长相**。

---

## 2. 概念逐层展开

### 2.1 `Protocol` 到底是什么

一句话：**`Protocol` 是一种"只描述能力、不提供实现"的类，它让 mypy 改用结构化类型来判断兼容。**

拆开说三个要点：

**要点 1：它不能实例化**

```python
class P(Protocol):
    def f(self) -> int: ...

P()   # 会怎样？
```

实测：

```
TypeError: Protocols cannot be instantiated
```

理由：它只有方法签名、没有方法体（方法体是 `...`），实例化出来一个"什么都不会做"的对象毫无意义。

**要点 2：但显式继承它的子类可以实例化**

```python
class Sub(P):
    pass

print(type(Sub()).__name__)   # 实测输出：Sub
```

因为 `Sub` 不写 `Protocol`，它就退化成一个普通类了——只是"承诺实现了 `P` 的接口"。注意：**mypy 会检查你守不守承诺**，但在 Python 里 `Sub` 一个方法都没写，运行时也不会报错，只有在调用 `Sub().f()` 时才 `AttributeError`。

> 这点很重要：`Protocol` 的"承诺"是**静态**的，运行时没有任何强制力。

**要点 3：方法体写 `...` 不是省略号语法糖**

```python
def get(self, k: UUID) -> dict[str, object] | None: ...
```

这里的 `...` 就是"函数体是空语句"。等价于：

```python
def get(self, k: UUID) -> dict[str, object] | None:
    pass
```

但在 `Protocol` 里习惯写 `...`，因为它在视觉上明确表达"这里没有实现，只是签名"。ruff format 会把它留在同一行（本项目 line-length 100）。

**同一个 `...` 在"参数默认值"位置上是另一个意思**：

```python
def create(self, kb_id: UUID, data: DocCreate, *, status: str = ...) -> dict[str, Any]: ...
```

这里的 `= ...` 表示"**有默认值，但具体是多少不重要**"。这是 PEP 544 的约定：协议只关心"调用方能不能省略这个参数"，不关心省略后是多少。

实测这个区别是**真的参与匹配**的。协议写 `def f(self, x: int = 0)`，实现写成 `def f(self, x: int)`（没有默认值）：

```
misc1.py:11: error: Argument 1 to "take" has incompatible type "NoDefault"; expected "P"  [arg-type]
misc1.py:11: note: Following member(s) of "NoDefault" have conflicts:
misc1.py:11: note:     Expected:
misc1.py:11: note:         def f(self, x: int = ...) -> int
misc1.py:11: note:     Got:
misc1.py:11: note:         def f(self, x: int) -> int
```

道理：协议说"调用方可以不传 `x`"，实现说"必须传 `x`"——那调用方按协议省略 `x` 时就炸了。**所以默认值也是契约的一部分。**

### 2.2 `Protocol` 和抽象基类（ABC）有什么区别

你已经见过 ABC 的用法（`abc.ABC` + `@abstractmethod`）。面试常问"为什么有了 ABC 还要 Protocol"，答案在三点：

| | ABC | Protocol |
|---|---|---|
| 实现方要不要显式继承 | **要**（`class Fake(KBRepository)`） | **不要**，长得像就行 |
| 能不能改造别人的类 | **不能**——第三方库的类你改不了 | **能**，只要签名对得上 |
| 运行时检查 | `isinstance` 原生支持 | 要 `@runtime_checkable`，且只查成员名 |
| 主要用途 | 提供共享实现 + 强制子类实现 | 描述依赖方的"最小需求" |

**"能不能改造别人的类"这条最要命**。举个本项目的真实场景：W7 要换成 SQLAlchemy，你的 `kb_repo.py` 会变成一个 `AsyncSession` 的包装。如果 `KBService` 依赖 ABC，那 SQLAlchemy 那边的类必须继承你的 ABC——你没法改 SQLAlchemy。而 `Protocol` 只要"方法签名对得上"就认，**不需要动任何第三方的代码**。

这就是"鸭子类型 + 静态检查"——Python 一直有的鸭子类型（"走起来像鸭子就是鸭子"），`Protocol` 是给它配了个编译期检查器。

### 2.3 名字怎么起：`Protocol` 放哪、叫什么

本项目约定（你可以照这个来）：

- 文件：`src/kb_service/repositories/protocols.py`
- 命名：**不用** `I` 前缀（`IKBRepo` 那种 Java 味道），也不加 `Protocol` 后缀（`KBRepoProtocol` 太啰嗦）。直接叫 `KBRepo` / `DocRepo`。
- 真实现保持原名 `KBRepository` / `DocRepository`，**不改名**——它是"其中一个实现"，不是"接口"。

这样一眼能看出：`KBService` 依赖的是抽象的 `KBRepo`，`KBRepository` 只是碰巧是默认的那个实现。

> 分层术语里这叫 **端口与适配器（ports & adapters）**：`Protocol` 是端口（只声明能力），`KBRepository` 是适配器（把内存/数据库接到端口上）。面试说得出这个词会加分。

---

## 3. 落地到项目（真实全过程）

下面四步是我在项目副本上实测跑过的，输出都是原样抄的。

### 第 1 步：写 `protocols.py`，把 service 的类型标注换掉

新建 `kb-service/src/kb_service/repositories/protocols.py`：

```python
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from kb_service.schemas.doc import DocCreate
from kb_service.schemas.kb import KBCreate, KBUpdate


class KBRepo(Protocol):
    def create(self, owner_id: UUID, data: KBCreate) -> dict[str, Any]: ...

    def get(self, kb_id: UUID) -> dict[str, Any] | None: ...

    def list_by_owner(
        self, owner_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def count_by_owner(self, owner_id: UUID) -> int: ...

    def update(self, kb_id: UUID, data: KBUpdate) -> dict[str, Any] | None: ...

    def delete(self, kb_id: UUID) -> bool: ...

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None: ...


class DocRepo(Protocol):
    def create(self, kb_id: UUID, data: DocCreate, *, status: str = ...) -> dict[str, Any]: ...

    def get(self, doc_id: UUID) -> dict[str, Any] | None: ...

    def list_by_kb(
        self, kb_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def delete(self, doc_id: UUID) -> bool: ...

    def update_status(self, doc_id: UUID, status: str, chunk_count: int | None = None) -> None: ...
```

> **为什么 `KBRepo` 里有 `incr_doc_count`？** 因为 `doc_service.py:26` 真的调了它（`self.kb_service.repo.incr_doc_count(kb_id, 1)`）。一个方法进不进协议，唯一判据是"**依赖方用不用它**"，不是"实现方有没有它"。
>
> 这一步先别管 `incr_doc_count` 会不会惹麻烦——**先照实写**，后面就知道了。

然后三个 service 的构造函数换类型，**其余一个字不动**：

| 文件 | 改哪一行 |
|---|---|
| `services/kb_service.py` | `repo: KBRepository \| None` → `repo: KBRepo \| None` |
| `services/doc_service.py` | `repo: DocRepository \| None` → `repo: DocRepo \| None`；`kb_repo: KBRepository \| None` → `kb_repo: KBRepo \| None` |
| `services/rag_service.py` | `doc_repo: DocRepository \| None` → `doc_repo: DocRepo \| None` |

（三个文件都要加 `from kb_service.repositories.protocols import ...`，但**保留**原来对 `KBRepository` / `DocRepository` 的 import——因为 `repo or KBRepository()` 还要用它当默认实现。）

跑 mypy：

```
tests\test_unit_demo.py:23: error: Argument "repo" to "KBService" has incompatible type "FakeRepo"; expected "KBRepo | None"  [arg-type]
tests\test_unit_demo.py:31: error: Argument "repo" to "KBService" has incompatible type "FakeRepo"; expected "KBRepo | None"  [arg-type]
tests\test_kb_service_unit.py:34: error: Argument "repo" to "KBService" has incompatible type "FakeKBRepo"; expected "KBRepo | None"  [arg-type]
tests\test_kb_service_unit.py:34: note: "FakeKBRepo" is missing following "KBRepo" protocol member:
tests\test_kb_service_unit.py:34: note:     incr_doc_count
tests\test_kb_service_unit.py:43: error: Argument "repo" to "KBService" has incompatible type "FakeKBRepo"; expected "KBRepo | None"  [arg-type]
tests\test_kb_service_unit.py:43: note: "FakeKBRepo" is missing following "KBRepo" protocol member:
tests\test_kb_service_unit.py:43: note:     incr_doc_count
tests\test_kb_service_unit.py:107: error: Argument "repo" to "KBService" has incompatible type "FakeKBRepo"; expected "KBRepo | None"  [arg-type]
tests\test_kb_service_unit.py:107: note: "FakeKBRepo" is missing following "KBRepo" protocol member:
tests\test_kb_service_unit.py:107: note:     incr_doc_count
tests\test_rag_async.py:62: error: Argument "doc_repo" to "RagService" has incompatible type "FakeDocRepo"; expected "DocRepo | None"  [arg-type]
tests\test_rag_async.py:74: error: Argument "doc_repo" to "RagService" has incompatible type "FakeDocRepo"; expected "DocRepo | None"  [arg-type]
tests\test_rag_async.py:86: error: Argument "doc_repo" to "RagService" has incompatible type "FakeDocRepo"; expected "DocRepo | None"  [arg-type]
Found 8 errors in 3 files (checked 47 source files)
```

**还是 8 个。** 但**性质变了**——这是今天最重要的一次观察，别跳过：

| | 改之前 | 改之后 |
|---|---|---|
| `FakeKBRepo` 的报错 | 只有一行 `arg-type`，没有任何解释 | 多了一行 note：**`is missing following "KBRepo" protocol member: incr_doc_count`** |
| 错误含义 | "你没有继承 `KBRepository`"（**血缘问题**） | "你少了 `incr_doc_count` 方法"（**能力问题**） |
| 你能据此做什么 | 无解，除非去继承 | 有解，补一个方法即可 |

**这就是 `Protocol` 的真实价值：它不消错，它把"错误"从"你血统不对"翻译成"你缺什么"。**

换句话说，之前那 8 个错误是**假警报**（`FakeKBRepo` 六个方法明明都在），现在这 8 个的是**真问题**——`FakeKBRepo` 确实少了 `incr_doc_count`，`FakeDocRepo` 确实只有 `list_by_kb` 一个方法。

> 顺带解释一个你会疑惑的细节：`test_unit_demo.py` 那两行**没有** note。因为那个 `FakeRepo` 只实现了 `get` 一个方法，缺 6 个——mypy 只在"替身接近但差一点"时才补 note，差得太多（1/7）就只给一行 error，不展开。
>
> 实测对照：实现 1/4 个成员 → 无 note；实现 1/2 个成员（缺 1） → 有 note。所以**没有 note 不等于问题更轻**，反而往往意味着差得更多。

### 第 2 步：分辨两种"不兼容"

现在去读那 8 个错误，会发现它们是**两种病**：

**病一：契约不完整（缺方法）**

- `FakeKBRepo` 缺 `incr_doc_count` → 补
- `FakeRepo` 缺 6 个 → 见第 3 步
- `FakeDocRepo` 缺 4 个（只有 `list_by_kb`）→ 见第 4 步

**病二：签名冲突（有这个方法，但对不上）**

这时候报错会长这样（这是我在项目外用受控实验复现的，格式与项目内一致）：

```
p_narrow.py:13: error: Argument 1 to "take" has incompatible type "Fake"; expected "Repo"  [arg-type]
p_narrow.py:13: note: Following member(s) of "Fake" have conflicts:
p_narrow.py:13: note:     Expected:
p_narrow.py:13: note:         def get(self, k: UUID) -> dict[str, object] | None
p_narrow.py:13: note:     Got:
p_narrow.py:13: note:         def get(self, k: int) -> dict[str, object] | None
```

**看到 `Following member(s) ... have conflicts` + `Expected / Got` 这个结构，就是签名冲突。** 它比"缺成员"难懂得多，因为 mypy 只告诉你"对不上"，不告诉你**为什么**对不上——明明都是两个参数、都有返回值。

为什么 `k: int` 对不上 `k: UUID`？为什么反过来 `k: object` 就对了？

答案在 §4，那是今天的主菜。

### 第 3 步：补 `FakeKBRepo.incr_doc_count`

在 `tests/fakes.py` 末尾加：

```python
def incr_doc_count(self, kb_id: UUID, delta: int) -> None:
    self._log("incr_doc_count", (kb_id, delta))
    if row := self.kbs.get(kb_id):
        row["doc_count"] = max(0, row["doc_count"] + delta)
```

**注意这里不只是"补个方法让 mypy 别叫"**——`FakeKBRepo` 是替身，它的职责是"行为和真实现一致"。真实现（`kb_repo.py:57`）的逻辑是 `max(0, ...)` 防止负数，你也得抄过来，否则替身和真实现的行为已经悄悄分叉了，测试就是假的。

> 这也是一个值得写进面试答案的点：**`Protocol` 让"替身与契约不一致"从"看不出来的隐患"变成"编译期报错"。**

跑一次：

```
tests\test_unit_demo.py:23: error: ...
tests\test_unit_demo.py:31: error: ...
tests\test_rag_async.py:62: error: ...
tests\test_rag_async.py:74: error: ...
tests\test_rag_async.py:86: error: ...
Found 5 errors in 2 files (checked 47 source files)
```

8 → 5。

### 第 4 步：`FakeDocRepo` 的病不是"缺方法"，是"协议太胖"

`FakeDocRepo` 只实现了一个方法：

```python
class FakeDocRepo:
    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        ...
```

按前面的逻辑，你该给它补 4 个方法。**先停一下，问一个问题：`RagService` 用得到那 4 个吗？**

打开 `rag_service.py`，它只调了 `self.doc_repo.list_by_kb(...)`（第 28 行）。写方法一个都没用。

那要求 `RagService` 的依赖方实现 `create` / `delete` / `update_status` 就是**多余的约束**——替身被迫写一堆永远不会被调用的空方法，而这些空方法本身又可能写错、还得维护。

**这叫接口太胖（违反接口隔离原则 ISP）。正确做法是：按"使用方需要什么"来拆协议，而不是按"实现方有什么"来拆。**

改 `protocols.py`，加一个只读视角：

```python
class DocReader(Protocol):
    """只读视角：RagService 只检索，不需要能写。"""

    def list_by_kb(
        self, kb_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...


class DocRepo(DocReader, Protocol):
    def create(self, kb_id: UUID, data: DocCreate, *, status: str = ...) -> dict[str, Any]: ...

    def get(self, doc_id: UUID) -> dict[str, Any] | None: ...

    def delete(self, doc_id: UUID) -> bool: ...

    def update_status(self, doc_id: UUID, status: str, chunk_count: int | None = None) -> None: ...
```

三个要点：

1. **`DocRepo` 继承了 `DocReader`**——协议可以继承协议，`DocRepo` 自动获得 `list_by_kb` 的要求，不用重写一遍。第二个 `Protocol` 参数不能省，否则 `DocRepo` 会变成一个普通类。
2. **`DocService` 还依赖胖的 `DocRepo`**（它要 create/delete/update_status），`RagService` 换成窄的 `DocReader`。
3. **`FakeDocRepo` 一个字都不用改**——它本来就只有 `list_by_kb`，正好够窄协议用。

改完 `rag_service.py` 的标注：

```python
def __init__(self, doc_repo: DocReader | None = None) -> None:
```

再跑：

```
tests\test_unit_demo.py:23: error: ...
tests\test_unit_demo.py:31: error: ...
Found 2 errors in 1 file (checked 47 source files)
```

8 → 5 → 2。

### 第 5 步：`FakeRepo` 该补全还是该删掉

剩下的是 W1 写的 `test_unit_demo.py` 里的 `FakeRepo`，只有 `get` 一个方法。两条路：

**路线 A：补全 7 个方法。** 能让 mypy 闭嘴，但你会在项目里造出**第二个** fake——和 `tests/fakes.py` 的 `FakeKBRepo` 功能重复。以后契约一变，要改两处。这是坏味道。

**路线 B：删掉它，复用 `FakeKBRepo`。** 一个契约只有一个替身，改一处就够。

正确答案是 B。改完：

```python
from tests.fakes import FakeKBRepo

# 原来：svc = KBService(repo=FakeRepo())
svc = KBService(repo=FakeKBRepo())

# 原来：svc = KBService(repo=FakeRepo(rows={kb_id: {"owner_id": alice}}))
repo = FakeKBRepo()
repo.kbs[kb_id] = {"owner_id": alice}
svc = KBService(repo=repo)
```

（`FakeKBRepo` 的构造不接 `rows` 参数，所以直接往 `kbs` 字典里塞——它是公开属性，本来就是给测试摆数据用的。）

最终：

```
Success: no issues found in 47 source files
```

```
57 passed, 2 warnings in 0.75s
```

**D1 遗留的 8 个错误清零，测试一条没坏。**

### 复盘：这 8 个错误到底说明什么

现在回头看，这 8 个错误里**没有一个**是"D1 的注解没写全"，它们全是**架构问题**：

| 错误 | 真正的问题 | 谁暴露的 |
|---|---|---|
| `FakeKBRepo` 缺 `incr_doc_count` | 替身漏实现了契约的一部分 | `Protocol` |
| `FakeDocRepo` 缺 4 个方法 | `RagService` 依赖了比自己需要更宽的接口 | `Protocol` |
| `FakeRepo` 缺 6 个方法 | 项目里有两个功能重复的 fake | `Protocol` |

**这就是为什么 `mypy --strict` 值钱**：它把"设计欠债"变成了"报错"。如果 D1 结束时你用一个 `cast` 或 `# type: ignore` 把它们压下去，这 8 个错误背后的三个设计问题会一直埋着，等到 W7 换 SQLAlchemy 时一起爆。

> 记住这句话，面试可以直接用：**"类型检查的收益不在'改掉报错'，而在'报错暴露了设计问题'。"**

---

## 4. 变异性（Variance）：为什么参数要反过来看

这一节是今天的硬骨头。慢慢来。

### 4.1 先搞清楚"替换"要满足什么

`Protocol` 的全部意义是"**一个对象能替换另一个对象**"。那什么叫"能替换"？

**判据只有一条：原来能用的地方，换掉之后还能用，而且不炸。**

具体到函数签名，就是两件事：

1. 调用方**传进来的**东西，新实现必须**都能吃下**
2. 调用方**拿出去的**东西，新实现必须**都能提供**

听起来像废话，但这两句话的方向是**相反**的——这就是变异性的全部来源。

### 4.2 参数：新实现必须吃得更宽（逆变）

协议说：

```python
class Repo(Protocol):
    def get(self, k: UUID) -> ...: ...
```

调用方代码是 `repo.get(some_uuid)`。现在换个实现上去，**所有可能的调用仍然要能跑**。所以：

- ✅ 新实现写 `def get(self, k: object)` —— 它能吃 `UUID` 吗？能（`UUID` 是 `object` 的子类）。**通过。**
- ❌ 新实现写 `def get(self, k: int)` —— 它能吃 `UUID` 吗？不能。**失败。**

实测两个方向：

**参数写宽（`object`）→ 通过**

```
===== B. 参数写宽 (object) =====
Success: no issues found in 1 source file
```

**参数写窄（`int`）→ 报错**

```
===== A. 参数写窄 (int) =====
p_narrow.py:13: error: Argument 1 to "take" has incompatible type "Fake"; expected "Repo"  [arg-type]
p_narrow.py:13: note: Following member(s) of "Fake" have conflicts:
p_narrow.py:13: note:     Expected:
p_narrow.py:13: note:         def get(self, k: UUID) -> dict[str, object] | None
p_narrow.py:13: note:     Got:
p_narrow.py:13: note:         def get(self, k: int) -> dict[str, object] | None
```

**结论：参数方向上，"更宽"才合法，"更窄"不合法。术语叫「参数是逆变的（contravariant）」——协变是同方向，逆变是反方向。**

一句话记住：**参数是你"吃"进来的，能吃得更杂才叫兼容。**

### 4.3 返回：新实现必须给得更精确（协变）

协议说：

```python
def get(self, k: UUID) -> dict[str, object] | None: ...
```

调用方拿到返回值后会做 `if row is None: ...` 然后 `row["x"]`。现在换实现：

- ✅ 新实现返回 `dict[str, object]`（去掉了 `None`）—— 调用方原本要处理 `None`，现在永远拿不到 `None` 了，`if row is None` 那支走不到，但**不会炸**。**通过。**
- ❌ 新实现返回 `object` —— 调用方以为拿到的是 dict，实际上是 `object`，`row["x"]` 直接炸。**失败。**

实测：

**返回写窄（去掉 `None`）→ 通过**

```
===== C. 返回写窄（去掉 None）====
Success: no issues found in 1 source file
```

**返回写宽（`object`）→ 报错**

```
===== D. 返回写宽（object）====
r_wide.py:12: error: Argument 1 to "take" has incompatible type "Fake"; expected "Repo"  [arg-type]
r_wide.py:12: note: Following member(s) of "Fake" have conflicts:
r_wide.py:12: note:     Expected:
r_wide.py:12: note:         def get(self) -> dict[str, object] | None
r_wide.py:12: note:     Got:
r_wide.py:12: note:         def get(self) -> object
```

**结论：返回方向上，"更窄"才合法，"更宽"不合法。术语叫「返回是协变的（covariant）」——同方向。**

一句话记住：**返回值是你"给"出去的，给得更具体才叫兼容。**

### 4.4 为什么两边是反的：一句话讲透

因为**参数和返回值在"谁承担风险"这件事上角色相反**：

- **参数是调用方给你的**（你是消费者）→ 风险在你这边 → 你必须能吃下**所有**调用方可能给的东西 → **越宽越安全**
- **返回值是你给调用方的**（你是生产者）→ 风险在调用方那边 → 你必须给出**至少**它需要的精度 → **越窄越安全**

用饭馆打个比方：

- **参数** = 客人点什么。协议是"我能做中餐"。换厨师如果只会川菜（更窄）→ 客人点粤菜就翻车。如果什么菜都会（更宽）→ 稳。
- **返回值** = 端上来的菜。协议是"我给你一盘热菜"。换厨子给"一盘宫保鸡丁"（更窄、更具体）→ 客人更满意。给"一盘东西"（更宽、更含糊）→ 客人不敢吃。

**两边方向相反，是因为一个往里、一个往外。**

### 4.5 一条容易忘的：默认值也参与（且是"逆变"那一侧）

协议写 `def f(self, x: int = 0)`，实现写成 `def f(self, x: int)`（无默认值）：

```
misc1.py:11: note: Following member(s) of "NoDefault" have conflicts:
misc1.py:11: note:     Expected:
misc1.py:11: note:         def f(self, x: int = ...) -> int
misc1.py:11: note:     Got:
misc1.py:11: note:         def f(self, x: int) -> int
```

道理和参数逆变一样：协议允许调用方**省略** `x`，实现却要求必填 → 省略时就炸。所以**"可选"对实现方是更宽的约束，必须保留**。

**记住一条：实现方可以比协议"更宽松"，不能"更严格"。** 参数类型、默认值、`*args` 扩展，都归这一条管。

### 4.6 容器的变异性：`list` 是不变的

这是初学者最容易撞的一堵墙，而且它跟函数参数/返回是**另一套规则**：

```python
def take_list(xs: list[object]) -> None: ...
def take_seq(xs: Sequence[object]) -> None: ...

ys: list[str] = ["a"]
take_list(ys)   # ← ?
take_seq(ys)    # ← ?
```

实测：

```
var_list.py:8: error: Argument 1 to "take_list" has incompatible type "list[str]"; expected "list[object]"  [arg-type]
var_list.py:8: note: "list" is invariant -- see https://mypy.readthedocs.io/en/stable/common_issues.html#variance
var_list.py:8: note: Consider using "Sequence" instead, which is covariant
```

**`list[str]` 不能当 `list[object]` 用**，而 `Sequence[object]` 可以。

为什么？因为 **`list` 是可写的**：

```python
xs: list[object] = ["a"]
xs.append(42)          # 合法：list[object] 当然能放 int
# 如果上面 take_list 允许了你传 list[str]，
# 那这个 append 就往一个 list[str] 里塞了个 int
```

**能写进去的容器必须"不变"（invariant）**：既不能协变也不能逆变，类型参数必须完全一致。

规则表（记住这张就够）：

| 类型 | 变异性 | 为什么 |
|---|---|---|
| `list[T]` / `dict[K, V]` / `set[T]` | **不变** | 可写，塞进去会污染 |
| `Sequence[T]` / `Iterable[T]` | **协变** | 只读 |
| `Mapping[K, V]` | 协变（V），K 不变 | 只读，但 key 要能查 |
| `Callable[[A], R]` | A 逆变、R 协变 | 和函数一样 |

**实用建议**：函数的**参数**位置尽量收窄能力——传进来只读就用 `Sequence` / `Iterable` / `Mapping`，别用 `list` / `dict`。这样调用方传什么都能进，也让你的意图更清楚："我只读，不改你的东西"。

> 这条同时也是 D3 的伏笔：`TypedDict` 也是结构化的，但它的变异性规则又是另一套（`TypedDict` 之间是协变的）。

---

## 5. `@runtime_checkable`：运行时检查的真实能力边界

### 5.1 不加装饰器，`isinstance` 直接炸

```python
class Repo(Protocol):
    def get(self, k: str) -> int: ...

print(isinstance(Fake(), Repo))
```

实测：

```
TypeError: Instance and class checks can only be used with @runtime_checkable protocols
```

理由：结构化类型的 `isinstance` 需要逐个检查成员，这有运行时开销，所以 PEP 544 要求你**显式声明**"我知道这有代价"。

### 5.2 加了装饰器，它只查"有没有"，不查"对不对"

这是最危险的一点。实测：

```python
@runtime_checkable
class Repo(Protocol):
    def get(self, k: str) -> int: ...

class Liar:
    def get(self) -> None:      # 参数没了、返回值也不对
        pass

class Nothing:
    pass

print(isinstance(Liar(), Repo), isinstance(Nothing(), Repo))
```

实测输出：

```
True False
```

**`Liar` 的方法签名完全不对，`isinstance` 却返回 `True`。** 因为运行时检查只看"有没有一个叫 `get` 的属性"，**签名是静态信息，运行时根本不存在**（回忆 D1：注解在运行时被丢掉了）。

**所以 `@runtime_checkable` 的 `isinstance` 是个"成员名存在性检查"，不是"契约符合性检查"。** 把它当类型守卫用，会得到假阳性。

### 5.3 一个更阴的坑：参数名 mypy 不检查

这个我实测过，结论有点惊人。

```python
class Repo(Protocol):
    def get(self, kb_id: UUID) -> int: ...

class Fake:
    def get(self, k: UUID) -> int:      # 参数名不一样
        return 1

d: Repo = Fake()                        # mypy：通过
print(d.get(kb_id=uuid4()))             # 运行时？
```

实测：

```
=== mypy --strict ===
Success: no issues found in 1 source file

=== 运行时 ===
TypeError: Fake.get() got an unexpected keyword argument 'kb_id'
```

**mypy 说没问题，运行时 TypeError。**

为什么 mypy 不管？因为"调用方会不会用关键字传参"它推不出来，所以参数名匹配做得很宽松。**但这是真会炸的**——只要有任何一处用 `repo.get(kb_id=...)` 就挂在运行时。

**教训**：mypy 通过 ≠ 正确。类型检查是"减少某类错误"，不是"证明无错"。所以测试不能省（这条正好呼应 W4 的变异测试：**工具都有盲区，得用另一种手段互相兜底**）。

### 5.4 那到底什么时候用 `@runtime_checkable`

真实场景只有一类：**你要在运行时按"能力"分发**。比如：

```python
def maybe_snapshot(obj: object) -> str:
    if isinstance(obj, SnapshotPort):
        return "支持快照"
    return "不支持"
```

用它的三条纪律：

1. **只用来做"粗筛"**（有没有这个能力），不做"精确校验"
2. **筛完立刻按最坏情况写代码**——比如筛完还是 `try/except` 兜一圈
3. **不要用它替代静态检查**：项目的正常依赖注入路径永远走 `Protocol` 类型标注，`isinstance` 只留给"动态加载插件"、"外部传入对象"这类真的没有静态信息的场景

本项目目前**没有一处**需要 `@runtime_checkable`——所有依赖都是构造注入，静态可查。如果将来加插件机制（比如可切换的 embedding provider），才需要它。

---

## 6. 动手任务（7 个，按顺序做）

> 规矩照旧：卡住了看「提示阶梯」，**一次只看一层**；每层都写了"卡多久再往下看"。

### 任务 1：写 `protocols.py`（约 15 分钟）

新建 `kb-service/src/kb_service/repositories/protocols.py`，声明 `KBRepo` 和 `DocRepo` 两个协议。

**必须先想清楚一件事**：`KBRepo` 里到底要放哪几个方法？判据是"`KBService` 用了哪些"，不是"`KBRepository` 有哪些"。

<details>
<summary>做完再点（自查用）</summary>

`KBService` 用了：`create` / `get` / `list_by_owner` / `count_by_owner` / `update` / `delete`（6 个，看 `services/kb_service.py`）；另外 `doc_service.py:26,57` 通过 `self.kb_service.repo.incr_doc_count(...)` 用了第 7 个。

所以 7 个都要写。**`incr_doc_count` 容易被漏掉**，因为它不是 `KBService` 自己的方法，是从外面绕进去的（这本身也是个设计味道，W7 可以改成 `KBService` 上的方法）。

`DocRepo` 有 5 个：`create` / `get` / `list_by_kb` / `delete` / `update_status`。

`create` 上别忘了 `*, status: str = ...`：`DocRepository.create` 的签名是 `(self, kb_id, data, *, status="pending")`，那个 `status` 是 keyword-only 且有默认值，协议里必须体现"有默认值"（§4.5），但具体值不重要，写 `...`。
</details>

### 任务 2：换三个 service 的类型标注（约 10 分钟）

`kb_service.py` / `doc_service.py` / `rag_service.py`，只改构造函数的参数类型，**方法体一个字不动**。

跑 mypy，观察错误**性质**的变化（还是 8 个，但多了 note）。

<details>
<summary>提示：如果你跑出来不是 8 个</summary>

- **变少了（比如 3 个）**：你可能顺手把 `FakeKBRepo` 也改了。先退回，严格按"只改 service 标注"来，因为这一步的目的是**观察** `Protocol` 如何改变报错的性质。
- **变多了**：大概率是 `protocols.py` 里的签名照抄错了某处（比如 `list_by_owner` 返回类型写成 `list[...]` 而不是 `tuple[list[...], int]`）。对照 `repositories/kb_repo.py` 逐个核。
- **出现 `Module has no attribute`**：import 路径写错，应该是 `kb_service.repositories.protocols`。
- **`Protocol` 名字报 `name-defined`**：忘了 `from typing import Protocol`。
</details>

### 任务 3：判断 `FakeKBRepo` 该补什么（约 5 分钟）

mypy 会告诉你它缺哪个方法。补的时候**注意行为要和真实现一致**（`max(0, ...)` 那段）。

<details>
<summary>做完自查</summary>

补的是 `incr_doc_count(self, kb_id: UUID, delta: int) -> None`，并且内部要记账（`self._log(...)`），因为其他测试可能断言这个调用发生过。
`max(0, ...)` 不能省：真实现有这个保护，替身没有的话，测"删文档后计数不会变负"这条规则时就会假绿。
</details>

### 任务 4：拆 `DocReader` 窄协议（约 15 分钟）

**这是今天最需要"想明白"而不是"敲代码"的一步。** 先回答三个问题再动手：

1. `RagService` 实际用了 `DocRepo` 的哪几个方法？（去 `rag_service.py` 数）
2. 那"要求它实现 5 个"合不合理？
3. `DocService` 呢？它用了几个？

第 2 个问题的答案决定了要不要拆；第 3 个问题决定了拆完谁用哪个。

<details>
<summary>提示阶梯（先想 10 分钟再看）</summary>

**第 1 层：想想"依赖方向"**

依赖应该指向"我需要的最小能力"。`RagService` 只读，那它就不该依赖"能写"的接口。这不是为了少写代码，是为了**不让无关的变化影响它**——将来 `DocRepo.create` 的签名变了，`RagService` 不该被牵连。

**第 2 层：拆成什么样**

一个只有 `list_by_kb` 的 `DocReader`。然后让 `DocRepo` 继承它（`class DocRepo(DocReader, Protocol)`），这样 `DocService` 还能用胖的那个，且胖的自然包含窄的全部。

**第 3 层：为什么 `FakeDocRepo` 不用改**

因为它本来就只有 `list_by_kb`。**窄协议不是"让替身少写几个空方法"，是"承认替身本来就只需要这么多"。** 拆完你去看 `FakeDocRepo`，会觉得它一直是对的——错的是协议。
</details>

### 任务 5：处理 `FakeRepo`（约 10 分钟）

`test_unit_demo.py` 里的 `FakeRepo` 只有 `get`。两条路选一条：补全 7 个方法，或者换成 `FakeKBRepo`。

**先写下你的理由，再动手。**

<details>
<summary>提示（先自己判断 5 分钟）</summary>

问自己一句：如果补全 `FakeRepo`，项目里会有几个"KB 仓库的替身"？契约再变一次，你要改几处？

**同一个契约只该有一个替身。** `tests/fakes.py` 的 `FakeKBRepo` 是那个"官方替身"（有账本、有真实行为），`FakeRepo` 是 W1 学写单元测试时的产物，它的历史使命已经完成。

所以：删 `FakeRepo`，改用 `FakeKBRepo`。注意 `FakeKBRepo()` 不接受 `rows` 构造参数，但 `kbs` 是公开属性，直接赋值即可。
</details>

### 任务 6：三个受控实验（约 20 分钟）

在项目外的临时目录建小文件（**不要放进 `kb-service/`**，会污染指标），把 §4 的四个方向自己跑一遍：

| 实验 | 改什么 | 预期 |
|---|---|---|
| 1 | 实现方参数写窄（`UUID` → `int`） | 报错，`Expected/Got` 里 `Got` 是 `int` |
| 2 | 实现方参数写宽（`UUID` → `object`） | 通过 |
| 3 | 实现方返回写窄（`dict \| None` → `dict`） | 通过 |
| 4 | 实现方返回写宽（`dict \| None` → `object`） | 报错 |

**跑之前先在纸上写预测。** 特别是实验 2 和 3——直觉上"参数类型不一样怎么能算兼容"，但它们是**通过**的。如果你预测错了，说明变异性的方向还没进脑子，回去重读 §4.4。

### 任务 7：验证全绿（约 5 分钟）

```powershell
# Windows PowerShell（在 kb-service/ 下）
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check src tests
& .\.venv\Scripts\python.exe -m ruff format --check src tests
```

```bash
# Git Bash / Linux / macOS（在 kb-service/ 下）
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m ruff format --check src tests
```

**验收标准**：

- `Success: no issues found in 47 source files`
- `57 passed`
- `All checks passed!` + `44 files already formatted`

> 数字不一致的排查：`47 source files` 是 `src`+`tests`+`scripts`+`conftest.py`，多了 `protocols.py` 一个文件（D1 是 46）。如果你看到 46，说明 `protocols.py` 没被算进去（可能建错目录）；看到 48+ 说明你把临时实验文件放进项目了。

---

## 7. 易错点表

| 坑 | 症状 | 正解 |
|---|---|---|
| 让替身继承真实现来消除 `arg-type` | mypy 绿了，但测试开始碰真实 `store`，用例之间互相污染 | 用 `Protocol` 声明能力，别用继承 |
| `Protocol` 里照抄实现方的**全部**方法 | 替身被迫写一堆永不调用的空方法 | 只写**依赖方用到的**；太胖就拆窄协议 |
| 协议方法体写成 `pass` 而不是 `...` | 能跑，但读者以为这里"应该有实现" | `Protocol` 里一律用 `...`（视觉上表明"无实现"） |
| 忘了 `class DocRepo(DocReader, Protocol)` 里的第二个 `Protocol` | `DocRepo` 变成普通类，可以实例化，结构化匹配失效 | 继承协议时必须再写一次 `Protocol` |
| 以为参数"类型必须一样"才兼容 | 看到 `object` 通过、`int` 报错，觉得工具抽风 | 参数**逆变**：能接受更宽才合法；返回**协变**：能返回更窄才合法 |
| 用 `list[str]` 传 `list[object]` 参数 | 报 `"list" is invariant` | 只读场景用 `Sequence` / `Iterable` / `Mapping` |
| 协议里参数有默认值，实现里写成必填 | 报 `Expected: def f(self, x: int = ...)` / `Got: def f(self, x: int)` | 默认值也是契约：实现方只能更宽松，不能更严格 |
| 用 `@runtime_checkable` 的 `isinstance` 当类型守卫 | 签名完全不对的类也返回 `True` | 它只查成员名存在性；精确校验只能靠静态检查和测试 |
| 以为 mypy 绿了就万事大吉 | 参数名不匹配（`kb_id` vs `k`）时 mypy 放过，关键字调用时 `TypeError` | 参数名统一；契约变更时全局搜一遍调用点 |
| 用一个 `cast(XxxRepo, obj)` 压掉 `arg-type` | 报告变绿，但契约冲突还在，且在某个输入下炸 | `cast` 只该用在"知道得比类型系统多"的边界（如 JSON 解析后），不用于掩盖设计冲突 |
| 协议文件里 import 具体实现类 | 循环 import 或分层倒置 | `protocols.py` 只依赖 `schemas` 和标准库，不 import `kb_repo.py` |

---

## 8. 命令速查（双平台）

下面所有命令默认**当前目录是 `kb-service/`**。

### 8.1 跑类型检查

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
```

### 8.2 只看某类错误

```powershell
# Windows PowerShell：过滤 arg-type
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py | Select-String "arg-type"
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep "arg-type"
```

### 8.3 按错误码统计分布

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy --strict --no-error-summary src tests scripts conftest.py |
    Select-String -Pattern '\[([a-z-]+)\]$' |
    ForEach-Object { ($_.Line -split '\[')[-1].TrimEnd(']') } |
    Group-Object | Sort-Object Count -Descending | Format-Table Count, Name
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy --strict --no-error-summary src tests scripts conftest.py |
    grep -oE '\[[a-z-]+\]$' | tr -d '[]' | sort | uniq -c | sort -rn
```

### 8.4 只看"签名冲突"（带 Expected/Got 的）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py | Select-String "have conflicts" -Context 0,4
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep -A4 "have conflicts"
```

### 8.5 查某个协议成员被谁用了

```powershell
# Windows PowerShell
Get-ChildItem -Recurse -Include *.py src, tests |
    Select-String -Pattern '\.repo\.(\w+)\(' |
    ForEach-Object { "$($_.Filename):$($_.LineNumber) $($_.Matches[0].Groups[1].Value)" } |
    Sort-Object
```

```bash
# Git Bash / Linux / macOS
grep -rnE '\.repo\.\w+\(' --include=*.py src tests
```

### 8.6 跑测试 + lint

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check src tests
& .\.venv\Scripts\python.exe -m ruff format --check src tests
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m ruff format --check src tests
```

> `mypy` 的输出全在 **stdout**（实测 stderr 为空）。PowerShell 里**不要**给这些命令加 `2>&1`——会把每行包成 `ErrorRecord` 并让 `$?` 变 `$false`。

---

## 9. 面试问法

### Q1：`Protocol` 和抽象基类（ABC）什么区别？为什么有了 ABC 还要它？

**30 秒版**：

> ABC 要求实现方**显式继承**，走名义类型；`Protocol` 只要求**方法签名对得上**，走结构化类型。关键差别在第三方类——你没法让 SQLAlchemy 的类继承你的 ABC，但可以让它"长得像"你的 Protocol。所以 `Protocol` 适合描述"我要什么能力"（依赖倒置），ABC 适合"提供共享实现 + 强制子类填坑"。

**追问链**：

- 追问 1：`Protocol` 能实例化吗？→ 不能（`TypeError: Protocols cannot be instantiated`），但显式继承它的子类可以。
- 追问 2：`Protocol` 在运行时检查类型吗？→ 默认不能，要 `@runtime_checkable`；而且它**只查成员名存在性，不查签名**。
- 追问 3：那这不是很弱吗？→ 对，所以它不能替代静态检查。它的用途是"动态分发时粗筛能力"，精确校验靠 mypy + 测试。
- 追问 4：`Protocol` 的方法体为什么写 `...`？→ 表示"无实现"。`...` 出现在**默认值**位置时是另一个意思：表示"有默认值但值不重要"，且"有没有默认值"真的参与协议匹配。

### Q2：什么是变异性？参数为什么逆变、返回为什么协变？

**30 秒版**：

> 变异性描述"子类型关系在类型构造器下怎么传递"。函数参数是**逆变**的：实现方的参数必须比协议**更宽或相等**，因为所有原本合法的调用都得能吃下；返回值是**协变**的：实现方的返回值必须比协议**更窄或相等**，因为调用方按协议用，给得更具体才安全。根源是"参数往里、返回值往外"，风险方向相反。

**追问链**：

- 追问 1：`list[str]` 能当 `list[object]` 用吗？→ 不能，`list` 是**不变**的，因为可写（往里 append 会污染）。只读的 `Sequence` 才是协变。
- 追问 2：`dict` 呢？→ key 不变（要能查），value 协变？严格说 `Mapping[K, V]` 里 K 不变、V 协变；`dict` 整体不变（可写）。
- 追问 3：`Callable` 呢？→ 参数逆变、返回协变，和函数签名一致。
- 追问 4：默认值算不算契约？→ 算。协议有默认值而实现没有 → 报错，因为调用方会省略参数。
- 追问 5：`TypeVar` 的 `covariant=True` 是什么？→ 自定义泛型时的变异性声明，标准库容器就是这样标的（`Sequence[_T_co]`）。自己写容器类时才需要。

### Q3：为什么测试替身不该继承真实现？

**30 秒版**：

> 继承会把"契约"和"实现"焊死。替身会带上真实逻辑（碰真实存储、真实连接），失去隔离性；真类的构造函数一改，替身被迫跟着改；替身自己的测试脚手架（调用账本等）也会和实现混在一起。正确做法是用 `Protocol` 描述能力，让替身"长得像"就够了。

**追问链**：

- 追问 1：那 `Protocol` 有什么额外收益？→ 它把"替身漏实现"从看不出来的隐患变成编译期报错。我项目里就是靠它发现 `FakeKBRepo` 少了 `incr_doc_count`。
- 追问 2：`Protocol` 太胖怎么办？→ 拆。按"使用方需要什么"拆，不是按"实现方有什么"拆（ISP）。我把 `DocRepo` 拆出了只读的 `DocReader`，`RagService` 只依赖窄的。
- 追问 3：会不会拆得太碎？→ 判据是"依赖方用不用"。只有一个使用方的协议不要提前拆，出现了第二个不同需求的依赖方再拆。

### Q4：`mypy --strict` 全绿代表代码没问题吗？

**30 秒版**：

> 不代表。类型检查有一批确定抓不到的东西：参数名不匹配（实测 mypy 放过、运行时 `TypeError`）、`Any` 引起的传染、`cast` 的担保错误、运行时的类型转换（`int()` 截断、`str(bytes)` 得到 `"b'x'"`）、以及所有业务逻辑错误。它的价值是"把某一类错误提前到编译期"，不是"证明正确"。所以测试、变异测试、代码评审都不能省。

**追问链**：

- 追问 1：那 `strict` 的意义在哪？→ 它把"能查的"都打开，包括 `disallow_untyped_defs`、`warn_return_any`、`no_implicit_optional` 等。不开 strict 的 mypy 基本等于没装。
- 追问 2：`cast` 和 `# type: ignore` 什么时候正当？→ 只在"知道得比类型系统多"的边界：JSON 解析后、第三方库 stub 缺失、框架动态注入。每个都要能说出**理由**和**删除条件**。
- 追问 3：怎么验证门禁真的有效？→ 注入式验收：故意写 5 类类型错误（参数错、返回值错、`Optional` 未收窄、`Protocol` 不匹配、泛型缺参），看门禁是否全红。漏一类就说明门禁有洞。

---

## 10. 闭卷自测

> 先在纸上写答案，再展开对照。写不出来就回到对应小节。

**1. 一句话说清 `Protocol` 解决了什么问题。**

<details>
<summary>答案</summary>

它让"兼容"的判据从**血缘**（你继承了吗）变成**长相**（你的方法签名对得上吗），从而让不相关的类（测试替身、第三方类）能作为依赖被注入，而不需要改继承关系。

</details>

**2. 下面哪个能通过？为什么？**

```python
class Port(Protocol):
    def get(self, k: UUID) -> dict[str, Any] | None: ...

class A:
    def get(self, k: object) -> dict[str, Any] | None: ...

class B:
    def get(self, k: UUID) -> dict[str, Any]: ...

class C:
    def get(self, k: str) -> dict[str, Any] | None: ...
```

<details>
<summary>答案</summary>

- **A 通过**：参数从 `UUID` 放宽到 `object`（逆变，更宽合法）；返回相同。
- **B 通过**：返回从 `dict | None` 收窄到 `dict`（协变，更窄合法）；参数相同。
- **C 不通过**：参数从 `UUID` 收窄到 `str`（逆变要求更宽），调用方传 `UUID` 就炸。

</details>

**3. 为什么参数和返回值的变异性方向相反？用一句话说。**

<details>
<summary>答案</summary>

因为参数是往里进的（实现方是消费者，必须能吃下所有原本合法的输入 → 越宽越安全），返回值是往外出的（实现方是生产者，调用方按协议使用 → 越具体越安全）。一个负责"接住"，一个负责"提供"，风险承担方相反。

</details>

**4. `list[str]` 为什么不能当 `list[object]` 用？该怎么改？**

<details>
<summary>答案</summary>

因为 `list` 可写：如果允许，就能通过 `list[object]` 的引用往一个实际是 `list[str]` 的列表里 append 一个 `int`，破坏原列表的类型。所以可写容器是**不变**的。

改法：把参数类型收窄成只读的 `Sequence[object]`（协变），或者收到 `Iterable[object]`。原则：函数参数不用 `list` / `dict`，用 `Sequence` / `Mapping` / `Iterable`。

</details>

**5. 协议里写 `def f(self, x: int = ...)`，实现里写 `def f(self, x: int)`。能过吗？为什么？**

<details>
<summary>答案</summary>

**不能过。** 协议承诺"调用方可以省略 `x`"，实现要求必填，那调用方按协议省略时就炸。默认值属于契约的一部分，且和参数类型一样受"实现方只能更宽松"的约束。

报错形如：
```
note: Following member(s) of "NoDefault" have conflicts:
note:     Expected: def f(self, x: int = ...) -> int
note:     Got:      def f(self, x: int) -> int
```

</details>

**6. `@runtime_checkable` 的 `isinstance` 检查什么？不检查什么？**

<details>
<summary>答案</summary>

**检查**：对象上是否存在协议要求的那些成员（按名字）。

**不检查**：成员的签名（参数类型、返回类型、默认值、是不是方法还是属性、是不是 async）。因为签名信息在运行时不存在（注解已被丢弃）。

后果：一个 `def get(self) -> None` 的类会被判定"实现了 `def get(self, k: str) -> int` 的协议"。这是**假阳性**。

</details>

**7. 为什么 `mypy` 全绿还可能运行时 `TypeError`？举一个本项目能复现的例子。**

<details>
<summary>答案</summary>

因为类型检查覆盖不了所有运行时行为。可复现的例子：**参数名不一致**。

```python
class Port(Protocol):
    def find(self, doc_id: UUID) -> dict | None: ...

class Impl:
    def find(self, key: UUID) -> dict | None: ...
```

`Impl` 满足协议（mypy 不比较参数名），但任何 `port.find(doc_id=...)` 的关键字调用会 `TypeError: unexpected keyword argument 'doc_id'`。

其他盲区：`cast` 的担保、`Any` 传染、运行时转换（`int()` 截断）、业务逻辑错误。

</details>

**8. `DocRepo` 报"缺 4 个方法"，你的第一反应应该是什么？**

<details>
<summary>答案</summary>

不是"补 4 个方法"，而是"**这个协议是不是太胖了**"。先查依赖方（`RagService`）实际用了几个——如果只用一个，说明协议要求超出需求（违反 ISP），应该拆出窄协议。

判据：**协议内容 = 依赖方需要的最小能力集合**，不是"实现方拥有的全部能力"。

</details>

**9. 为什么给 `DocRepo` 拆出 `DocReader` 之后，`FakeDocRepo` 一个字都不用改？**

<details>
<summary>答案</summary>

因为 `FakeDocRepo` 本来就只实现了 `list_by_kb`——它一直是对的，**错的是协议**（要求得太多）。拆出窄协议等于承认这个事实，替身刚好满足。

这也说明一件事：`Protocol` 报"缺方法"时，有一半情况不是"替身不够"，而是"接口太宽"。

</details>

**10. `class DocRepo(DocReader, Protocol)` 里第二个 `Protocol` 能不能省？**

<details>
<summary>答案</summary>

**不能省。** 省了之后 `DocRepo` 就变成一个普通类（因为 `DocReader` 是它的基类，而它自己不声明为 `Protocol`），结果是可以被实例化、且不再作为结构化协议参与匹配。

规则：只要你想让它**保持协议身份**，`Protocol` 这个基类必须在列表里。

</details>

**11. 项目里还剩几个 `cast` / `type: ignore` / `overrides`？每个的理由和删除条件是什么？**

<details>
<summary>答案（这是 D4/D6 的活，今天先列清单）</summary>

当前（D1 结束时）共有：

| 位置 | 内容 | 理由 | 删除条件 |
|---|---|---|---|
| `core/config.py` | 已删掉过期的 `# type: ignore[call-arg]` | pydantic v2 插件知道字段可来自环境变量 | 已删 |
| `core/security.py` | `cast(str, ...)` | jose 库的返回值 stub 是 `Any` | 换库或 stub 完善后 |
| `services/llm_client.py` | `cast(...)` | 同上，第三方响应解析 | 同上 |
| `pyproject.toml` overrides | passlib / jose 开 `ignore_missing_imports` | 这两个包没有 `py.typed` 也没 stub 包 | 装上 `types-*` 之后 |

**D4 会把这张表逐条审一遍**，要求"每条都能说出理由和删除条件"，否则就是给自己留的逃生口。

</details>

**12. 白板题：手写一个 `Protocol` + 一个"参数逆变写反"的实现，并说出 mypy 会报什么。**

<details>
<summary>答案</summary>

```python
from typing import Protocol
from uuid import UUID

class Repo(Protocol):
    def get(self, kb_id: UUID) -> dict[str, object] | None: ...

class Broken:
    def get(self, kb_id: int) -> dict[str, object] | None:   # 参数写窄
        return None

def use(r: Repo) -> None: ...

use(Broken())
```

mypy 报：

```
error: Argument 1 to "use" has incompatible type "Broken"; expected "Repo"  [arg-type]
note: Following member(s) of "Broken" have conflicts:
note:     Expected: def get(self, kb_id: UUID) -> dict[str, object] | None
note:     Got:      def get(self, kb_id: int) -> dict[str, object] | None
```

**口述要点**：看到 `have conflicts` + `Expected/Got` 就是签名冲突；参数方向要"Got 比 Expected 宽"，返回方向要"Got 比 Expected 窄"。这里是参数变窄了，所以不合法。

</details>

---

## 附：今天和前后几天的关系

```
D1（注解与 mypy 基线）
  └─ 58 错清到 8 个，剩下的 8 个 arg-type 全是"名义类型"造成的假警报
        ↓
D2（今天）Protocol 与变异性
  ├─ 8 个错误清零，顺带修掉 3 个设计问题（替身不完整 / 接口太胖 / fake 重复）
  ├─ 学会：参数逆变、返回协变、容器不变、默认值也算契约
  ├─ 学会：@runtime_checkable 只查成员名，是粗筛不是校验
  └─ 留下两个伏笔
        ↓
D3  TypedDict / Literal / overload
     ← 伏笔 1：TypedDict 也是结构化类型（和 Protocol 同一族）
     ← 伏笔 2：`dict[str, Any]` 到处都是，D2 只是让接口对了，行内容的类型还没管
        ↓
D4  第三方边界（stub / overrides / pydantic 插件）
     ← 伏笔 3：draft 自测第 11 题那张逃生口清单
```

**今天最该带走的一句话**：

> `Protocol` 不消除错误，它**把"血统不对"翻译成"缺什么"**——翻译之后你才发现，原来那 8 个错误全是真的设计问题。
