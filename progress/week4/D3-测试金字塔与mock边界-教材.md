# W4-D3 教材：测试金字塔与 mock 边界（零基础版）

> 本教材假设你**完全不会**单元测试和 mock。所有术语第一次出现都会解释。
> 所有代码都在你的 kb-service 下实测过（Python 3.11 venv），输出为真实运行结果。

---

## 0. 痛点场景：没有单元测试时，你在怎么活

先看你现在的测试现状。打开 `tests/test_kb_api.py`，它们长这样：

```python
def test_kb_crud_flow(client):
    resp = client.post("/api/v1/kbs", json={"name": "测试库"})
    ...
```

这个测试叫**集成测试**（integration test）：它把整个系统拼起来跑——FastAPI 路由、鉴权、service、repo、内存存储，一个不落。

集成测试好不好？好。但只用集成测试写业务逻辑，有三个真实的痛：

**痛 1：失败定位粗。**
假设 `KBService.update` 里有个 bug：无权访问时应该先拦下，它却放行了。你跑集成测试，看到的是 `test_kb_update_flow` 红了。这个测试从 HTTP 请求一路跑到数据库，红了意味着**这条链路上任何一环都可能有问题**——路由？鉴权？service 的权限判断？repo？你得打断点一层层排查。

单元测试（unit test）只测一个东西。同样是这个 bug，单元测试直接告诉你：`test_update_without_permission_repo_not_called` 红了——**权限判断没拦住**，一秒定位。

**痛 2：有些业务规则，集成测试根本测不到。**
`KBService.delete` 的正确行为是：无权时**先抛 ForbiddenError，绝不调用 `repo.delete`**。用集成测试你怎么证明"repo.delete 没被调用"？你只能看到最终 HTTP 响应是 403——但你不知道 service 是"先检查后删除"，还是"先删除后发现没权限再补一个 403"。这两种实现对外表现一样，内部天差地别（后者已经把数据删了！）。

要断言"某件事**没有发生**"，你需要能观察 repo 的视角——这就是今天的主角：**测试替身（test double）**。

**痛 3：换实现时测试全废。**
W7 你要把内存存储换成 SQLAlchemy。到那时这批集成测试要连真数据库、建表、清理数据，每个测试从 0.01s 变成几十毫秒甚至秒级。而业务规则（权限判断、分页计算、403/404 的产品决策）**一条都没变**——为没变的东西付变慢的代价，冤不冤？

> **诚实的说明**：你的项目现在用内存存储，集成测试其实很快（实测 0.01s/个，全量 26 个 0.34s）。所以"金字塔 = 为了快"这个流行说法在现阶段对你不成立。现阶段金字塔给你的真实红利是**痛 1 和痛 2：定位精度 + 能断言"没发生"**。速度红利在 W7 接真数据库后兑现。面试时能这样分情况说，比背"单元测试快所以要多写"高一个段位。

---

## 1. 最小可跑示例（5 分钟亲手跑）

别急着理解全部概念。先花 5 分钟，亲手把一个单元测试跑起来，获得"我能做到"的实感。

在 `kb-service/tests/` 下新建文件 `test_unit_demo.py`：

```python
"""我的第一个单元测试：只测 KBService，不启 FastAPI。"""

from uuid import uuid4

import pytest

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.services.kb_service import KBService


class FakeRepo:
    """最小 fake：只实现 KBService 用到的 get 方法。"""

    def __init__(self, rows: dict | None = None) -> None:
        self.rows = rows or {}

    def get(self, kb_id):
        return self.rows.get(kb_id)


def test_missing_kb_raises_not_found():
    svc = KBService(repo=FakeRepo())   # ← 把 fake 塞进去
    with pytest.raises(NotFoundError):
        svc.get_or_403(uuid4(), uuid4())


def test_other_users_kb_raises_forbidden():
    alice, bob = uuid4(), uuid4()
    kb_id = uuid4()
    svc = KBService(repo=FakeRepo(rows={kb_id: {"owner_id": alice}}))
    with pytest.raises(ForbiddenError):
        svc.get_or_403(kb_id, bob)
```

跑它：

```powershell
cd kb-service
./.venv/Scripts/python.exe -m pytest tests/test_unit_demo.py -v
```

你会看到（真实输出）：

```
tests/test_unit_demo.py::test_missing_kb_raises_not_found PASSED
tests/test_unit_demo.py::test_other_users_kb_raises_forbidden PASSED

============================== 2 passed in 0.01s ==============================
```

**逐行解读这份输出：**
- `PASSED` × 2：两个测试都绿。
- `2 passed in 0.01s`：0.01 秒。对比一下你的集成测试全量套件 26 个要 0.34s——单位测试快不只是"没有 HTTP"，还有**没有 fixture 链**：你项目里 `client` fixture 依赖 `app`（session 级，建整个 FastAPI 应用）和 `auth_headers`（签 JWT）。单元测试这些全都不要。
- 注意**没有任何 FastAPI、TestClient、HTTP 出现在这个文件里**。`kb_service.services.kb_service` 模块不 import FastAPI（分层设计的直接红利），所以单元测试连框架都不用加载。

这 5 分钟里你已经做到了三件事：
1. **绕过整个 HTTP 栈**，直接把一个对象（fake）塞进 service 的构造函数；
2. 用两个测试锁定了 `get_or_403` 的两条业务规则（不存在 → 404；别人的 → 403）；
3. 每条规则的失败定位是**一条测试 = 一条规则**。

跑通了吗？跑通了就继续。没跑通，把报错原样贴给我。

---

## 2. 概念逐层展开

### 2.1 测试金字塔：三层各管什么

```
        ／  E2E  ＼          少量：全链路冒烟，最慢最脆
       ／ 集成 API ＼        中量：TestClient 打路由，验证"拼起来还对"
      ／   单元     ＼       大量：一个类/一个函数，毫秒级，失败即定位
```

金字塔的形状来自一个朴素的权衡：**测试越靠上层，越真实，但越慢、失败时越难定位**。所以越便宜的层次，数量越多。

放到你的 kb-service 上，三层各管什么：

| 层 | 测什么 | 你的例子 | 不该测什么 |
|---|---|---|---|
| 单元 | 一个类的业务规则 | `KBService.get_or_403` 的 404/403 判断、`list` 的 offset 计算 | HTTP 状态码、JSON 序列化 |
| 集成 | 层与层的拼接 | `client.post("/api/v1/kbs")` 返回 201、鉴权头生效、全局异常处理器把 `ForbiddenError` 翻成 403 | 业务规则的每个分支（那是单元的事） |
| E2E | 用户视角的完整场景 | 建库 → 传文档 → chat 引用来源（你现在的 `test_chat_returns_sources` 就是） | 每个边缘分支 |

**"绝不能 mock"的第一条答案在这里就出现了**：层与层的拼接本身（路由能不能找到 handler、异常处理器有没有挂上、Pydantic 能不能解析请求体）是集成层的被测对象。如果你在集成测试里把 service mock 掉，那这条集成测试就在测一个幻想世界。

### 2.2 Test Double 五兄弟：fake、stub、spy、mock、dummy

"Test Double（测试替身）"是总称：**凡是"冒充真实现、让被测代码以为自己拿到了真依赖"的对象**，都叫 double。这个词来自电影里的"特技替身"（stunt double）。

五兄弟按"有多少真实行为"排序（定义来自 Gerard Meszaros 的经典分类，pytest 社区通用）：

| 替身 | 一句话定义 | 有真实行为吗 | kb-service 里的例子 |
|---|---|---|---|
| **dummy** | 只为填参数，从来不会被用到 | 无 | 一个永远不会被调用的 repo，只为凑齐构造参数 |
| **stub** | 返回写死的答案："被问到就答这个" | 无（答案硬编码） | `get()` 永远返回 `{"owner_id": alice}`，不管问的是谁 |
| **spy** | stub + 记录自己被怎么调用 | 部分（记录） | 记录 `calls: [("delete", (kb_id,))]`，供测试断言"没被调用" |
| **mock** | 预先编排"期待被怎么调、调了算过、没调算挂" | 无 | `Mock(spec=...)` + `mock.assert_called_once_with(...)` |
| **fake** | **一个真实现的简化版**：有真实行为，能放东西进去取东西出来 | **有** | 内存 dict 版 KBRepository：真能 create/get/delete |

**重点区分（面试高频）三组对比：**

**stub vs fake**：stub 是"问答机"——不管内部状态，问就答固定的。fake 是"缩小版真货"——你往里 create 三条，它 list 就真返回三条，排序、分页都是它自己算的。上面 §1 的 `FakeRepo(rows={kb_id: {...}})` 偏 stub；练习里你要写的 `FakeKBRepo` 是完整 fake。

**spy vs mock**：两者都记录调用，但**判定权在谁手里**不同。spy 只负责记录，断言由你自己在测试里写（`assert repo.calls == []`）；mock 是先编排期待（"我期待 delete 被调一次"），末尾 `mock.assert_called_once()` 一锤定音。功能重叠，spy 更直白、更 Python。

**mock vs fake（最重要的一个）**：mock 的每个行为都是你在测试里**编排**出来的；fake 的行为是它**自己实现**的。编排 = 你的假设，实现 = 可验证的逻辑。这就是为什么 fake 更不容易"测了个寂寞"——D2 第四档 #07 你已经踩过这个坑：`monkeypatch.setattr` 换上一个 lambda，被调链路里**被测逻辑消失了**，测试全绿但什么都没验证。fake 不会犯这个错，因为 fake 里跑的是真代码。

### 2.3 mock 边界判据：什么该隔离，什么绝不能 mock

一句话判据：

> **凡是被测逻辑本身，绝不能替换；凡是被测逻辑的"外部世界"（慢的、不确定的、会烂的），才值得替换。**

对号入座（针对你的 kb-service）：

| 依赖 | 该不该隔离 | 用什么 | 理由 |
|---|---|---|---|
| repo（存储） | **该**，在 service 的单元测试里 | **fake**（今天的练习） | service 的被测逻辑是业务规则；存储是它的边界。且 fake 有真行为，不丢验证力 |
| 时间（`store.now()`、JWT 过期） | 该 | fake clock / freezegun（D5） | 时间不等人，真实时间让测试不可重复 |
| 外部 HTTP（LLM API） | 该 | respx / fake transport（D5） | 网络会抖、会花钱、会超时 |
| **service 的权限判断** | **绝不能** | — | 这就是被测逻辑本身。mock 掉它 = 测试不存在 |
| **Pydantic 校验**（KBCreate 的 min_length） | 单元测试里不碰它；集成测试里**用真的** | — | 校验是真实行为，mock 掉它，schema 改坏了你都不知道 |
| **异常处理器把 AppError 翻成 HTTP 状态码** | 绝不能（在集成层） | — | 这是"层与层拼接"的核心价值 |
| **repo 的 SQL 语义**（W7 起） | repo 自己的单元测试里用假 SQL 方言或真 SQLite 测 | — | 换个角度：repo 的被测逻辑是"正确地跟数据库说话"，这里数据库就成了边界 |

注意表里有两行"绝不能"。**mock 的滥用模式就一句话：图省事，把被测路径上的真东西全换成了自己的假设，最后测试全绿、产品上线炸了。** 你在 D2 第四档已经亲眼见过一次这个模式的微型版。

### 2.4 fake repo 为什么是"正规解法"——W3 Protocol 红利兑现

回忆 W3-D4 你做过的事：`layering_practice/kb/interfaces.py` 里定义了

```python
class KBRepository(Protocol):
    def create(self, owner_id, data) -> dict[str, Any]: ...
    def get(self, kb_id) -> dict[str, Any] | None: ...
    def list_by_owner(self, owner_id, offset, limit) -> tuple[list, int]: ...
    def delete(self, kb_id) -> bool: ...
```

Protocol（结构化契约）：**不看血统（不要求继承），只看形状（方法签名对不对）**。当时你用"内存 repo / JSON repo 双实现 + 对拍"验证了依赖倒置。

今天的 fake repo 就是**同一件事换了个受益方**：

- W3 的受益方是**架构**：换存储实现，service 零改动；
- 今天的受益方是**测试**：fake 是"契约的第三个实现"，专门为测试而生的实现。

```
                KBRepository 契约（方法签名）
                ／        ｜         ＼
        InMemoryRepo   SQLAlchemyRepo   FakeKBRepo
        （生产-内存）   （W7 生产-真库）   （测试专用）
```

service 只依赖契约，所以它不知道、也不关心塞进来的是哪个实现。**这就是为什么 fake repo 不是"歪门邪道的 hack"，而是分层架构的正当红利**：没有契约的系统里，service 直接 `import` 具体存储类，你想塞 fake 都塞不进去（得动 service 源码）；有契约的系统里，构造函数一传就完事。

### 2.5 一个真实细节：kb-service 的注解还不是 Protocol，为什么 fake 也能塞

打开你项目里的 `src/kb_service/services/kb_service.py` 第 18 行：

```python
def __init__(self, repo: KBRepository | None = None) -> None:
    self.repo = repo or KBRepository()
```

这个 `KBRepository` 注解指向的是 `repositories/kb_repo.py` 里的**具体类**，不是 Protocol（Protocol 只存在于你 W3 的 layering_practice 练习里）。那为什么 fake 塞进去也能跑？

因为 **Python 运行时不检查类型注解**。注解是写给人看和给 mypy（静态类型检查器）看的，运行时 `KBService(repo=FakeRepo())` 就是简单地把对象赋给 `self.repo`，然后调 `self.repo.get(...)`——只要 fake 有 `get` 方法且签名兼容，就能跑。这是鸭子类型（"走起来像鸭子叫起来像鸭子，那就是鸭子"）在起作用。

那注解错了吗？没全错，但有改进空间，两个选择：

- **方案 A（够用）**：保持具体类注解。运行时无所谓，fake 照塞。缺点是 mypy 会抱怨 fake 不是 KBRepository 的子类。
- **方案 B（正规化，本日选做）**：在 kb-service 里真正建一个 Protocol，让注解指向契约。这正是把 W3 练习里的认知**落到生产代码**的一步。

**一个藏在构造函数里的暗坑**（易错点表会再见）：`repo or KBRepository()` 用的是**真值判断**。Python 里对象默认为真，但如果哪天你的 fake 定义了 `__len__` 且返回 0，`repo or ...` 就会把你的 fake **当成假值丢掉、悄悄换成真 repo**——测试表面上还能跑，实际测的是真实现，而真实现用的全局 `store` 会被 conftest 的 `_clear_store` 清掉，你可能只觉得"数据怎么莫名消失了"。你练习里的 fake 不会踩这个坑（它不是 dict 子类，没有 `__len__`），但**知道这个坑的存在**，是"能看出 AI 写的代码哪里不对"的一部分。

---

## 3. 机制：怎么断言"没发生"——spy 手法

痛 2 说过的那个问题：怎么证明"无权时 `repo.delete` 没被调用"？

fake + 调用记录，三步：

```python
class FakeKBRepo:
    def __init__(self) -> None:
        self.kbs: dict[UUID, dict] = {}
        self.calls: list[tuple[str, tuple]] = []   # ① 记账本

    def get(self, kb_id):
        self.calls.append(("get", (kb_id,)))        # ② 每次被调，记一笔
        return self.kbs.get(kb_id)

    def delete(self, kb_id):
        self.calls.append(("delete", (kb_id,)))
        return self.kbs.pop(kb_id, None) is not None
```

```python
def test_delete_without_permission_repo_not_called():
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    kb_id = uuid4()
    repo.kbs[kb_id] = {"owner_id": ALICE, ...}

    with pytest.raises(ForbiddenError):
        svc.delete(kb_id, BOB)                      # BOB 无权

    delete_calls = [c for c in repo.calls if c[0] == "delete"]
    assert delete_calls == []                       # ③ 账本上没有 delete 这一笔
```

这个手法叫 **spy（间谍）**：fake 一边提供真实行为（dict 存取），一边把收到的每次调用记在账本上。测试末尾翻账本。

为什么不用 `assert "delete" not in str(repo.calls)` 这种写法？——精确性。账本里存的是结构化数据 `("delete", (kb_id,))`，你可以按方法名过滤、按参数断言（比如练习里要验证 `list_by_owner` 收到的 `offset` 是不是 `(page-1)*size`）。字符串匹配是 D2 教训（`match="error"` 永真）的又一变体。

---

## 4. 易错点表

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | fake 没实现 service 会调到的方法 | `AttributeError: 'FakeKBRepo' object has no attribute 'list_by_owner'` | fake 之前先读 service 源码，列出它调了 repo 的哪些方法，逐一实现 |
| 2 | fake 方法签名与真 repo 不一致 | 能跑，但那是巧合；service 改了参数顺序 fake 静默接不住 | 照抄真 repo 的签名；有 Protocol 就照 Protocol 抄 |
| 3 | fake 自己返回假数据误导断言 | fake 的 `get` 忘了 `return`，返回 None，测试把 None 的行为当成了"repo 没数据" | fake 也是代码，也要 review；写完 fake 先写一个"fake 自测"（create 后 get 得回来） |
| 4 | `repo or KBRepository()` 真值坑 | 带 `__len__` 的 fake 被静默丢弃 | fake 不要定义 `__len__`；或给 service 改成 `if repo is None` |
| 5 | 测试间共享同一个 fake 实例（module 级变量） | 用例顺序一换就红——fake 里的状态泄漏 | 每个 fixture/测试里新建 fake；fake 本身无全局状态 |
| 6 | 用 MagicMock 顶替一切，断言变成"镜像断言" | `assert repo.get.assert_called_with(kb_id)` 只证明"你编排的东西发生了"，不证明业务规则对 | 有真实行为可用就用 fake；mock 只留给"没有简化实现价值的边界"（如 HTTP 客户端） |
| 7 | 断言了调用次数却没断言行为 | `assert_called_once` 绿了，但返回值根本不对 | 交互断言（调没调、参数对不对）和结果断言（返回值/异常）**都要有** |
| 8 | 单元测试里 import 了 conftest 的 client fixture | 顺手把 FastAPI 依赖链拉回来了，单元测试变慢、变脆 | 单元测试文件不请求 `client`；只 new service + fake |
| 9 | fake 里的时间戳用了 `datetime.now()` 导致不可重复 | 极端情况排序不稳定（还记得 3.11 的 15.6ms 精度坑吗） | fake 固定时间或单调递增；需要精确时间控制等 D5 freezegun |
| 10 | 给每个 repo 方法都写调用记录，账本断言铺天盖地 | 测试变成"复读 service 源码"：service 改个内部顺序，测试全红，但行为没变 | 只 spy **有业务含义的交互**（"无权不得删"、"分页参数怎么传"）；内部无关顺序不锁死 |

---

## 5. 命令速查

```powershell
# 只跑单元测试文件（毫秒级）
./.venv/Scripts/python.exe -m pytest tests/test_kb_service_unit.py -v

# 看每个测试耗时（找慢测试）
./.venv/Scripts/python.exe -m pytest tests/test_kb_service_unit.py --durations=10 -vv

# 只跑某个测试函数
./.venv/Scripts/python.exe -m pytest tests/test_kb_service_unit.py::test_missing_kb_raises_not_found -v

# 按关键字跑（名字含 forbidden 的）
./.venv/Scripts/python.exe -m pytest -k forbidden -v

# 全量回归（确认新测试没破坏别人）
./.venv/Scripts/python.exe -m pytest -q
```

---

## 6. 动手实验（跑之前先猜）

对着 §1 的 `test_unit_demo.py` 做实验。**每个实验先在纸上写下你的猜测，再跑**，猜错的地方就是你的知识缝。

1. 把 `KBService(repo=FakeRepo())` 改成 `KBService(repo=None)` 再跑——会发生什么？（提示：回看 §2.5 的构造函数源码）
2. 把 fake 的 `get` 方法体里的 `return` 删掉再跑 `test_other_users_kb_raises_forbidden`——红还是绿？为什么？（提示：`get_or_403` 收到 None 走哪个分支？这对应易错点 #3）
3. 在 `test_missing_kb_raises_not_found` 里把 `NotFoundError` 换成 `ForbiddenError`——pytest.raises 会怎么报？报错信息里能看出"抛了 A 你却等 B"吗？
4. 在文件里加一个 `class EmptyFake: pass`，`KBService(repo=EmptyFake())` 后调 `get_or_403`——报什么错？这个错误发生在 setup 阶段还是 call 阶段？

（答案在 §9 闭卷自测后面，做完再看。）

---

## 7. 今日练习任务书（主菜）

**目标**：给 `KBService` 建立单元测试层。不启 FastAPI、不碰 `client` fixture、不用 MagicMock。

### 产出两个文件

**文件 1：`kb-service/tests/fakes.py`** —— `FakeKBRepo`

要求：
- 内存 dict 存储（`self.kbs`），**有真实行为**：create 后真能 get 回来、list 真按创建时间倒序、count 真数得出来；
- **实现 KBService 实际调用的 6 个方法**（create / get / list_by_owner / count_by_owner / update / delete。提示：先读 `kb_service.py` 源码数一遍，`incr_doc_count` service 没用到，不实现——这个差异要在总结里说清为什么可以不做）；
- 带 `calls` 账本（每笔记 `("方法名", (参数...))`）；
- 行为对齐真 repo：`create` 生成 uuid 和时间戳；`update` 只改传入字段、刷新 `updated_at`；`delete` 返回 bool。

**文件 2：`kb-service/tests/test_kb_service_unit.py`** —— 至少 8 个测试：

| # | 测试 | 锁定的业务规则 | 断言类型 |
|---|---|---|---|
| 1 | create 返回 KBOut，字段回读正确 | create 链路（repo 行 → Pydantic 模型） | 结果 |
| 2 | get 不存在 → NotFoundError | 404 规则 | 异常 |
| 3 | get 别人的库 → ForbiddenError | 403 规则 | 异常 |
| 4 | get 自己的库 → 返回 row | 正常路径 | 结果 |
| 5 | **delete 无权 → ForbiddenError 且账本里没有 delete** | 先鉴权后删除（痛 2） | 异常 + 交互 |
| 6 | update 不存在的 id → NotFoundError 且账本里没有 update | 同上 | 异常 + 交互 |
| 7 | list(page=3, size=10) → repo 收到的 offset 是 20 | 分页计算 | 交互（参数） |
| 8 | count_owned 正确委托并返回 | 委托链路 | 结果 |

骨架（填空处标 `# TODO`，卡住了按老规矩，找我要提示，一次一层）：

```python
"""KBService 单元测试：fake repo，不启 FastAPI。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.schemas.kb import KBCreate, KBUpdate
from kb_service.services.kb_service import KBService

from tests.fakes import FakeKBRepo

ALICE = uuid4()
BOB = uuid4()


def _svc_with_kb(owner: UUID) -> tuple[KBService, FakeKBRepo, UUID]:
    """造一个带 1 个知识库的 service。返回 (service, repo, kb_id)。"""
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    row = repo.create(owner, KBCreate(name="测试库"))
    repo.calls.clear()          # 清掉 setup 的账，测试只看自己的账
    return svc, repo, row["id"]


def test_create_returns_kbout():
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    out = svc.create(ALICE, KBCreate(name="新库"))
    # TODO: 断言 out.name / out.owner_id / out.doc_count
    ...


def test_missing_kb_raises_not_found():
    # TODO
    ...


def test_other_users_kb_raises_forbidden():
    # TODO
    ...


def test_own_kb_returns_row():
    # TODO
    ...


def test_delete_without_permission_repo_not_called():
    # TODO: pytest.raises(ForbiddenError) + 翻账本证明没删
    ...


def test_update_missing_raises_not_found():
    # TODO: 注意 service.update 先走 get_or_403，再调 repo.update
    ...


def test_list_offset_computed_from_page():
    # TODO: page=3, size=10 → 断言账本里最后一笔是 ("list_by_owner", (owner, 20, 10))
    ...


def test_count_owned_delegates():
    # TODO: 造 2 个库，断言返回 2
    ...
```

**验收标准**：
- 全部跑绿：`pytest tests/test_kb_service_unit.py -v`；
- 文件里**没有**出现 `TestClient` / `client` / `FastAPI` 字样；
- 没有使用 `MagicMock` / `unittest.mock`；
- 每个测试独立新建 fake（不允许模块级共享 repo 实例）；
- `pytest -q` 全量回归仍全绿（现在是 26 个，你加完应该是 34+）。

**时间预算**：fakes.py 约 60-80 行，测试文件约 100 行。预计卡点在 ⑤⑥ 的账本断言和 ⑦ 的"怎么从账本里取出参数"。

---

## 8. 面试问法

### Q1："单元测试和集成测试怎么划分？"（30 秒版）

> "我按**被测对象的边界**划分：单元测试测一个类的业务规则，它的依赖用 fake 替换——比如我给 KBService 写单元测试时，塞了一个内存 dict 实现的 fake repo，毫秒级跑完，失败即定位到具体规则。集成测试测层与层的拼接，用 TestClient 走真路由、真 Pydantic 校验、真异常处理器，mock 掉的只有外部网络。我的原则是：业务规则的全部分支放单元层，拼接正确性放集成层，绝不在集成测试里 mock 掉 service。"

**追问链**：
- ①"为什么不全部用集成测试？"→ 定位粗（一条链路红了不知道哪环）+ 有些断言集成层做不到（"repo 没被调用"这种交互断言需要替身视角）+ 换存储实现时业务规则测试不用重写。
- ②"fake 和 mock 有什么区别？你为什么选 fake？"→ fake 有真实行为（缩小版实现），mock 的行为全是我编排的假设。选 fake 是因为存储语义简单（dict 就能模拟），真实行为比编排假设更有验证力；mock 留给没有简化实现价值的外部服务。
- ③"什么情况下你绝不 mock？"→ 被测逻辑本身、真实校验逻辑（Pydantic）、层间拼接（异常翻译）。再往深挖会到"金字塔形状的依据"——越上层越慢越难定位，所以大量规则下沉到单元层。
- ④"你的 fake 怎么保证和真 repo 行为一致？"（深）→ 契约视角：两者实现同一组方法签名；W7 换 SQLAlchemy 时会对拍。诚实边界：fake 与真实现可能不一致（比如真 SQL 的排序语义），这正是集成层还要存在的原因——单元层抓规则，集成层抓契约。

### Q2："测试金字塔是什么？一定要金字塔形吗？"（30 秒版）

> "金字塔是按'真实度换成本'排的形状：底层单元测试又快又好定位所以最多，上层集成/E2E 又慢又粗所以最少。但我不会教条——我的项目现在用内存存储，集成测试也很快，现阶段金字塔给我的是定位精度和交互断言能力；等接真数据库后速度红利才显现。也有反金字塔场景：遗留系统没有单元测试基础时，先从上层冒烟测试兜住，再往下补。"

**追问链**："冰淇淋筒反模式是什么？"（大量 E2E + 几乎没有单元层，测试套件又慢又脆，CI 排队半小时）→ "你的项目哪些测试将来会变成集成层的负担？"（test_kb_api 的全分支测试，W7 后应下沉一部分到单元层）。

---

## 9. 闭卷自测（先做，再折叠对答案）

1. Test Double 五兄弟分别是什么？fake 和 mock 的本质区别一句话？
2. "什么该 mock 什么绝不能 mock"的一句话判据？
3. 为什么 fake repo 是分层架构的"正当红利"而不是 hack？
4. kb-service 的 service 注解指向具体类而非 Protocol，为什么 fake 也能传进去？这叫什么类型机制？
5. `repo or KBRepository()` 有什么暗坑？
6. 怎么断言"无权时 delete 没被调用"？这个手法叫什么？
7. 你的项目现阶段（内存存储），测试金字塔的主要红利是什么？（不是速度！）
8. 单元测试文件里请求了 conftest 的 `client` fixture 会发生什么？

<details><summary>点击对答案</summary>

1. dummy/stub/spy/mock/fake。fake 是**有真实行为的简化实现**（dict 存取是真的）；mock 的每个行为都是测试里**编排**出来的假设，没有自己的逻辑。
2. 被测逻辑本身绝不能替换；被测逻辑的"外部世界"（慢、不确定、会坏的）才值得替换。
3. service 只依赖方法签名契约（鸭子类型/Protocol），构造函数传什么实现都行——fake 是"为测试而生的契约实现"，与 W3 内存/JSON 双 repo 同理。
4. Python 运行时不检查类型注解，只要求对象有同签名方法。结构化子类型/鸭子类型。注解升级为 Protocol 是选做改进（mpy 才会认账）。
5. 真值判断：带 `__len__` 且返回 0 的 fake 会被当假值，静默换成真 repo，测试测了真实现还浑然不觉。
6. spy 手法：fake 带 `calls` 账本记录每次调用，测试末尾按方法名过滤断言账本里没有该笔。
7. 定位精度（一条测试 = 一条规则）+ 交互断言能力（"没发生"类断言）；速度红利等 W7 换 SQLAlchemy 后兑现。
8. 拉回整个 FastAPI 依赖链（app fixture 建应用、auth_headers 签 JWT、TestClient 启动），单元测试变慢变脆，且失败定位又变粗了。

</details>

### §6 实验答案（先做完再看）

<details><summary>实验答案</summary>

1. `repo=None` → 构造函数 truthy 判断走 `KBRepository()`，用真 repo + 全局 store。测试可能照样绿（store 恰好没数据）——**这正是坑 4 的危险：不报错，静默换了被测对象**。
2. **红**，且报错是原始的 `NotFoundError: 知识库不存在` traceback（实测确认）。机制：`pytest.raises(ForbiddenError)` 遇到**别的类型**异常时会把它原样放行，测试直接以该异常失败——注意不是 `DID NOT RAISE`，那句话只在**完全没抛异常**时出现。fake 忘了 `return` 是易错点 #3 的活例子：fake 自己坏了，误导 service 走进另一个分支。
3. 抛的是 NotFoundError，pytest.raises(ForbiddenError) 失败，报错信息明确指出实际抛出的异常类型与你期待的不符。
4. `AttributeError: 'EmptyFake' object has no attribute 'get'`，发生在 call 阶段（service 执行中调 repo.get 时炸），不是 fixture setup 阶段。

</details>

---

## 下一步

完成 §7 练习后把两个文件交给我验收：我检查后发**第四档 #08**（本周主题定制版），然后写 D3 总结（面试参考版）。
