# D1 教材 · pytest 机制基础（零基础版）

> 假设你**从来没写过一行测试**。从"测试到底是什么"讲起，到你能看懂 pytest 的每一个输出。
> 读完本篇 + 做完三步实验，你就超过了大多数"会写 `def test_xxx()` 但不知道为什么"的人。

---

## §0 先回答最根本的问题：测试是什么？

**测试 = 用代码去调你的代码，并自动判断结果对不对。**

回想你之前的做法（W1 之前的样子）：

```python
# 方法一：print 大法
result = split_text("人工智能" * 500)
print(result)          # 然后人眼去看……大概对吧？

# 方法二：手动点
# 启动 uvicorn → 打开浏览器 → 点创建 → 点删除 → 看页面……
```

这两种方法的共同问题：**验证靠人眼，回归靠记性。**

- "大概对吧"——你不可能每次都仔细看
- 今天改了一行代码，你怎么知道没有把上周的功能改坏？把所有功能手动点一遍？功能有 50 个的时候呢？
- 三个月后你回来看这段代码，`print(result)` 输出 `[{...}]`——这是对的还是错的？你早忘了

**测试就是把这个过程自动化**：

```python
def test_split_text():
    chunks = split_text("人工智能" * 500)      # 调你的代码
    assert len(chunks) > 1                     # 自动判断，不用人眼
    assert all(len(c) <= 64 for c in chunks)   # 多个角度判断
```

判断是机器做的。以后每次改完代码跑一句 `pytest`，**几百个历史功能同时被重新验证**——这就是测试的全部意义：**它不是证明代码是对的，它是让你敢于改代码。** 改错了它会喊，你才敢重构、敢加功能。

> **核心认知：测试的价值 = 你下次改代码时它拦住了多少次手滑。**
> 一个"永远绿"的测试没价值；一个在你引入 bug 的瞬间变红的测试，价值千金。

---

## §1 你的第一个测试（5 分钟上手）

在 `kb-service/tests/` 下随便建个文件 `test_demo.py`：

```python
def test_addition():
    assert 1 + 1 == 2


def test_string_upper():
    assert "abc".upper() == "ABC"


def test_intentional_failure():
    assert 1 + 1 == 3        # 故意写错，看看失败长什么样
```

跑它：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_demo.py -v
```

输出（简化版）：

```
tests/test_demo.py::test_addition PASSED
tests/test_demo.py::test_string_upper PASSED
tests/test_demo.py::test_intentional_failure FAILED
...
E       assert 2 == 3
E        +  where 2 = 1 + 1
```

逐个读：

- pytest 自己找到了文件（文件名必须 `test_*.py` 或 `*_test.py`）和函数（必须 `test_*` 开头）——**这就是"收集"**
- 每个函数一个状态：`PASSED` / `FAILED` / `ERROR`（还有 `SKIPPED`、`XFAIL`）
- **FAILED 不是"报错"，是"断言不成立"**——它和异常一样会被完整打印，`where 2 = 1 + 1` 是 pytest 告诉你"左边的 2 是 `1 + 1` 算出来的"
- 把 `1 + 1 == 3` 改回 `== 2`，再跑就全绿

**你发现了吗：没写任何 import pytest、没写类、没写 main。** 一个普通函数 + 普通 `assert` 就是测试。这是 pytest 的设计哲学：**测试代码和普通 Python 代码长得一样。**

把 `test_demo.py` 删掉，它只是敲门砖。

---

## §2 assert：测试的全部判定手段

普通 Python 的 `assert 条件, 消息` 就是测试断言，pytest 只是**把它变得很好看**：

```python
def test_name():
    got = {"name": "kb-1", "doc_count": 0}
    assert got["doc_count"] == 1
```

失败时 pytest 不只说"False"，而是把**表达式里每个子项的值**都打印出来：

```
E       assert 0 == 1
E        +  where 0 = {'name': 'kb-1', 'doc_count': 0}['doc_count']
```

你一眼就知道：`got["doc_count"]` 是 0，期望 1——**不用加 print，不用打断点**。

### 常用断言写法对照（记住这几个够用 90%）

| 想判断什么 | 写法 |
|---|---|
| 相等 | `assert a == b` |
| 不等 | `assert a != b` |
| 在集合里 | `assert x in items` |
| 是 None / 不是 None | `assert x is None` / `assert x is not None` |
| 抛了指定异常 | `with pytest.raises(ValueError): do()` |
| 接近的浮点 | `assert a == pytest.approx(0.1 + 0.2)` |
| 带说明的断言 | `assert a == b, f"期望 {b}，实际 {a}"` |

### 一个重要细节：断言消息是**失败才求值**的

```python
assert result == expected, f"got={result}"    # ✓ 只在失败时才拼字符串
```

f-string 在这里不浪费——它不会在每次测试通过时都白算一遍。这也是为什么不推荐"先 `print` 再 `assert`"（print 永远白付钱）。

### `pytest.raises`：测"该炸的时候要炸"

```python
import pytest

def test_create_empty_name_raises():
    with pytest.raises(ConflictError) as exc_info:
        service.create_kb("alice", "重复名")     # 期望这里抛异常
    assert "已存在" in exc_info.value.message    # 还能继续检查异常内容
```

**测异常和测正常返回一样重要**——业务代码一半的价值在"错误路径对不对"（404 该 404、403 该 403）。你 W3 写的 `ConflictError/NotFoundError/ForbiddenError` 三连，就该这样各测一条。

---

## §3 pytest 跑起来的完整生命周期（懂了这个，后面都不玄）

```
① 收集 collect
   从 testpaths（pyproject 里配的 tests/）递归找测试文件
   → 文件里找 test_* 函数、Test* 类
   → 同时处理 @parametrize（一个函数展开成 N 个用例）和 mark 标记
② 组装 fixture
   对每个用例，解析它要的 fixture 及其依赖，按作用域决定新建还是复用
③ 执行
   setup（各 fixture 的 yield 之前）→ 测试函数体 → teardown（yield 之后）
④ 断言求值
   assert 不成立 → 拼装失败信息 → 记为 FAILED
⑤ 报告
   汇总 dots/进度、warnings、总耗时、退出码
```

### ERROR 和 FAILED 必须分清（新手最大的混淆点）

| 状态 | 含义 | 典型原因 | 排查方向 |
|---|---|---|---|
| `FAILED` | **测试跑了**，结果不对 | 业务代码 bug、断言写错 | 看断言信息，查业务逻辑 |
| `ERROR` | **测试没跑起来** | fixture 里抛异常、收集阶段 import 失败 | 看 ERROR 的 traceback，查 fixture/环境 |

例：fixture 里 `db.connect()` 连不上 → 所有用它的测试都是 ERROR（一个都没执行）。这时候改业务代码是白费劲，先修 fixture。

### 退出码（CI 靠它判断）

```powershell
./.venv/Scripts/python.exe -m pytest; echo "退出码=$?"
```

- `0` = 全过（哪怕 0 个测试也是 0！注意陷阱）
- `1` = 有 FAILED
- `2` = 使用错误（参数写错等）
- `4` = 没收集到任何测试
- `5` = 有 ERROR（收集/fixture 阶段挂）

> **陷阱："0 个测试也退出码 0"**——如果你把 testpaths 配错，pytest 优雅地"全绿通过"。所以 CI 里要配 `--strict-markers` 且警惕"测试数突然变 0"。你 W6 的 kbcli CLI 退出码知识和这里是同构的：**进程用退出码向外界汇报成败。**

---

## §4 为什么 pytest 的 assert 这么聪明？（原理一句话）

pytest 在 import 测试模块时**改写了模块的字节码**：把 `assert 表达式` 替换成一段"先求出表达式每个子项的值、存起来、失败时打印"的代码。这叫 **assertion rewriting**。

两个直接后果：

1. **不能用 `python tests/test_x.py` 直接跑**——没有重写，失败只剩干巴巴的 `AssertionError`。**永远用 `pytest` 命令跑。**
2. 不需要 unittest 那套 `assertEqual/assertTrue/assertTrueIn`——裸 assert + 重写 = 更强的报错。

### 和 unittest 的对照（面试会问"为什么选 pytest"）

| | unittest（标准库） | pytest |
|---|---|---|
| 断言 | `self.assertEqual(a, b)` 等几十个方法 | 裸 `assert`，失败信息更全 |
| 组织 | 必须继承 `TestCase` | 裸函数即可 |
| 前置/后置 | `setUp/tearDown` 继承链硬绑定 | **fixture：按名字请求、可组合、可选作用域** |
| 参数化 | `subTest` 绕着写 | `@parametrize` 一行 |
| 生态 | 少 | 插件海（asyncio/cov/mock/freezegun/respx…） |

---

## §5 fixture：从"没有它有多痛"讲起

### 5.1 痛点：setup 代码到处复制

假设 10 个测试都要"一个连着假数据库的 service"：

```python
def test_create():
    repo = InMemoryRepo(); svc = KBService(repo); repo.seed(...)
    ...  # 业务断言

def test_delete():
    repo = InMemoryRepo(); svc = KBService(repo); repo.seed(...)   # 又抄一遍
    ...
```

三行 setup × 10 个测试 = 30 行复制粘贴。哪天 `InMemoryRepo` 构造函数加参数，你改 10 处，漏 1 处。

### 5.2 fixture 的解法：setup 代码取名字

```python
import pytest

@pytest.fixture
def svc():
    repo = InMemoryRepo()
    repo.seed()
    return KBService(repo)          # return 够用（不需要清理时）

def test_create(svc):               # ← 参数名 = fixture 名，pytest 自动注入
    kb = svc.create_kb("alice", "测试库")
    assert kb["name"] == "测试库"

def test_delete(svc):
    ...
```

**机制一句话：pytest 看到函数参数名，就去已注册的 fixture 里找同名者，把返回值塞进来。** 这叫依赖注入——和 FastAPI 的 `Depends` 是同一个思想（W6 你会看到 FastAPI 的依赖注入几乎是 pytest fixture 的翻版）。

### 5.3 需要清理时：`yield` 替代 `return`

`return` 之前只做 setup；**`yield` 之后是 teardown**，无论测试成败都执行：

```python
@pytest.fixture
def conn():
    conn = open_connection()      # setup：yield 之前
    yield conn                    # 把资源交给测试
    conn.close()                  # teardown：yield 之后，测试炸了也执行
```

这正是 `try/finally` 的语义。**需要清理就必须用 `yield`**，用 `return` 会泄漏资源。

**一个真实例子**（你项目里现成的）：

```python
# kb-service/tests/conftest.py
@pytest.fixture(autouse=True)
def _clear_store() -> Iterator[None]:
    store.kbs.clear()             # setup：清库
    yield                         # 测试跑
    store.kbs.clear()             # teardown：再清一次（保险）
```

它没有返回值（`Iterator[None]`），存在的唯一意义就是**每个测试前后清场**——保证用例之间互不污染。这就是"测试独立性"：任何测试单跑、全跑、乱序跑结果都一样。

### 5.4 作用域 scope：控制"建几次"

```python
@pytest.fixture(scope="session")     # 默认是 "function"
def app():
    return create_app()
```

| scope | 生命周期 | 适合放什么 | 陷阱 |
|---|---|---|---|
| `function`（默认） | 每个测试函数一次 | 大多数东西 | 贵的东西放这里会拖慢测试 |
| `class` | 每个测试类一次 | 类内共享的只读数据 | 类内测试可能互相污染 |
| `module` | 每个文件一次 | 只读大对象 | 文件内顺序依赖 |
| `session` | 整个 pytest 进程一次 | app、DB 引擎、容器 | 被"改了状态"就影响所有测试 |

**经验法则：默认 function；只有"建起来很贵且只读"的东西才升级作用域。** `create_app()` 建一次要几百毫秒且只读 → 值得 session；带状态的数据（store 里的 kbs）→ 必须 function + 清场。

### 5.5 作用域的方向规则（必考）

> **短作用域可以请求长作用域，反之不行。**

```python
@pytest.fixture(scope="session")
def app(): ...

@pytest.fixture
def client(app): ...        # ✓ function 请求 session，没问题

@pytest.fixture(scope="session")
def bad(client): ...        # ✗ ScopeMismatch！
```

为什么：session 级 fixture 在整个进程只建**一次**，而 `client` 每个函数都新建——session 的 `bad` 建的时候，pytest 根本不知道该绑定**哪一个** `client`。类比：全公司唯一的一台服务器（session）不能依赖"每个员工的人体工学椅"（function）——它等不到。

### 5.6 依赖链：fixture 可以请求 fixture

```python
@pytest.fixture
def settings(): return get_settings()

@pytest.fixture
def auth_headers(settings):
    return {"Authorization": f"Bearer {create_access_token(str(TEST_USER_ID))}"}

@pytest.fixture
def client(app, auth_headers): ...
```

pytest 沿参数名自动搭建整条链，**先建叶子再建枝干**。每个 fixture 职责单一，组合出千变万化的测试环境——这就是"组合优于继承"。

### 5.7 autouse：不写参数也生效

```python
@pytest.fixture(autouse=True)
def _clear_store(): ...
```

测试函数**不写这个参数**，它也会在每个测试前执行。**只用于"清场/环境"类**（清库、冻结时区、禁外网）。

⚠️ **不要用 autouse 提供数据**——数据依赖必须显式写在参数里，否则读测试的人看不出它靠什么跑的。隐式依赖是测试可读性的头号杀手。

### 5.8 用 `--setup-show` 亲眼看执行顺序（今天必做）

```powershell
./.venv/Scripts/python.exe -m pytest --setup-show -q tests/test_health.py
```

你昨天跑出来的真实输出，逐行解读：

```
SETUP    S event_loop_policy        ← S = session 级，整个进程建一次
SETUP    F _clear_store             ← F = function 级，每个测试建一次
SETUP    F auth_headers
SETUP    F client (fixtures used: auth_headers)
tests/test_health.py::test_health ... .          ← 用例本体
TEARDOWN F client                   ← teardown 是 setup 的完全镜像（LIFO）
TEARDOWN F auth_headers
TEARDOWN F _clear_store
SETUP    F _clear_store             ← 下一个测试，function 级全部重建
...
TEARDOWN S event_loop_policy        ← session 级直到最后才拆
```

四个可读出的事实：

1. **`S`/`F` 就是作用域**：session 建一次拆一次，function 每个测试一建一拆
2. **`event_loop_policy` 不是你写的**——conftest 里没有它，是 **pytest-asyncio 插件**注入的（pyproject 的 `asyncio_mode="auto"` 激活）。插件会往你的测试里"凭空"塞 fixture，这是插件生态的形状
3. **SETUP 顺序 = 依赖拓扑序，且 autouse 优先**：`_clear_store`（autouse，无依赖）最先，保证 `client` 建立时库已干净
4. **TEARDOWN 是 SETUP 的镜像（LIFO）**：和 FastAPI 中间件、`try/finally` 同一个洋葱模型——谁后建谁先拆，保证拆的时候它依赖的东西还活着

---

## §6 conftest.py：fixture 的公共仓库（规则最容易误解）

**问题**：fixture 定义在 `tests/test_kb_api.py` 里，`test_health.py` 想用怎么办？复制粘贴？

**conftest.py 是 pytest 的约定文件**：放在某个目录下，里面的 fixture 自动对**该目录及所有子目录**的测试可见——**不需要 import**。

### 三条规则（背下来）

1. **自动加载**：pytest 把 conftest.py 当插件，启动时自动 import。里面**不要放测试函数**（不会被收集），只放 fixture / hook / 配置。
2. **只向上生效**：`tests/unit/conftest.py` 里的 fixture，`tests/unit/` 及其子目录能用，`tests/integration/` **看不到**。
3. **同名就近遮蔽**：子目录定义同名 fixture → 子目录的测试用子目录版本（父版被遮蔽，不是报错）。这是**分层特化的正规手段**。

### 本周要搭的目标结构

```
tests/
├── conftest.py              # 全局：清库(autouse)、app、auth_headers
├── unit/
│   ├── conftest.py          # 单元层专属：fake repo、service
│   └── test_kb_service.py
├── integration/
│   └── test_kb_api.py       # 直接复用全局的 client
└── e2e/
    └── test_smoke.py
```

层级 = 测试金字塔的物理形状（D3 细讲）。

---

## §7 参数化：把复制粘贴的测试压成一张表

### 7.1 先看没有参数化的惨状

```python
def test_normalize_strips_space():
    assert normalize_name("  考研资料  ") == "考研资料"

def test_normalize_empty():
    assert normalize_name("") == ""

def test_normalize_truncate():
    assert normalize_name("a" * 65) == "a" * 64
```

三个测试只差输入输出，结构一模一样。第 10 个用例时你会开始复制粘贴，第 20 个时你会漏改一个。

### 7.2 参数化版本

```python
import pytest

@pytest.mark.parametrize(
    ("raw", "expected"),                      # 参数名
    [
        ("  考研资料  ", "考研资料"),           # 一行 = 一个用例
        ("", ""),
        ("a" * 65, "a" * 64),
    ],
    ids=["strip", "empty", "truncate"],       # 用例名（报告里可读）
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected
```

运行时展开成 3 个独立用例，失败报告长这样：

```
tests/test_x.py::test_normalize_name[truncate] FAILED
E       assert 'aaa...a' == 'aaa...64a'
```

**失败的 id（`truncate`）直接告诉你是哪组输入**——这是参数化最大的价值：不是省代码，是**失败时一眼定位**。

### 7.3 三个进阶点

- **叠加 = 笛卡尔积**：`@parametrize("a",[1,2])` + `@parametrize("b",["x","y","z"])` → 2×3 = 6 个用例
- **单个用例挂标记**：`pytest.param("旧输入", ..., marks=pytest.mark.xfail(reason="W7 才支持"))`
- **indirect=True**：参数先传给 fixture 再到测试函数（D3 用来造"每个用例不同的 repo"）

---

## §8 常用命令速查（贴墙上）

```powershell
pytest                                   # 全跑
pytest tests/unit -q                     # 只跑某个目录
pytest -k "kb and not chat"              # 按名字过滤
pytest -x                                # 第一个失败就停（调试时省时间）
pytest --lf                              # 只跑上次失败的（last-failed）
pytest -vv                               # 超详细失败信息
pytest -s                                # 不吞 print（调试 fixture 时用）
pytest --setup-show                      # 打印 fixture 的 setup/teardown 顺序
pytest --fixtures                        # 列出所有可用 fixture 及其来源文件
pytest --collect-only -q                 # 只看会跑哪些用例（不执行）
pytest --cov=src/kb_service --cov-branch --cov-report=term-missing   # 覆盖率
```

优先级建议：`--lf` 和 `-x` 是日常调试主力；`--setup-show` 是理解作用域的**唯一可靠方式**（别脑补，让它打给你看）。

---

## §9 易错点清单（今天就会踩的）

| 坑 | 症状 | 正解 |
|---|---|---|
| `python tests/test_x.py` 直接跑 | 失败只有 `AssertionError`，没细节 | 一律 `pytest`（assert 重写只在这个入口生效） |
| fixture 用 `return` 但需要清理 | 资源泄漏、文件句柄堆积 | 需要 teardown 就用 `yield` |
| session fixture 请求 function fixture | `ScopeMismatch` | 方向规则：短可请求长，反之不行 |
| autouse 用来提供数据 | 测试看不出依赖从哪来 | autouse 只做清场；数据走参数 |
| 参数化写成测试内 `for` 循环 | 一个失败全挂、定位不到输入 | `@parametrize`，让每个输入独立成用例 |
| 断言太弱：`assert r.status_code` | 200/201/404 都算真，抓不住 bug | 断言**具体值 + 关键字段**：`assert r.status_code == 201 and r.json()["doc_count"] == 0` |
| 测试共享可变状态 | 单跑过、全跑挂 | 每用例清场（autouse `_clear_store` 已经在做） |
| 测试里改 `os.environ` 不还原 | 污染后面的用例 | `monkeypatch.setenv`（D2 讲，自动还原） |
| 只测 happy path | 异常路径全是裸奔 | 每个业务异常至少一条 `pytest.raises` |
| "0 个测试也退出码 0" | testpaths 配错也"全绿" | CI 里盯测试数量，别只看退出码 |

---

## §10 今天的三步实验（对应聊天里的任务）

**第一步（观察）**：

```powershell
./.venv/Scripts/python.exe -m pytest --setup-show -q tests/test_health.py
```

✅ 已完成。产出：上面 §5.8 的四条解读。

**第二步（作用域实验）**：新建 `tests/test_mechanics.py`（实验品，验完删）：

```python
import pytest


@pytest.fixture(scope="session")
def expensive():
    print("\n[setup] session 级 expensive")
    yield "EXPENSIVE"
    print("[teardown] session 级 expensive")


@pytest.fixture
def cheap():
    print("\n[setup] function 级 cheap")
    yield "CHEAP"
    print("[teardown] function 级 cheap")


def test_one(expensive, cheap):
    assert expensive == "EXPENSIVE"


def test_two(expensive, cheap):
    assert cheap == "CHEAP"


@pytest.mark.parametrize(
    ("a", "b"),
    [(1, "x"), (1, "y"), (2, "x")],
    ids=["1x", "1y", "2x"],
)
def test_cartesian(a, b):
    assert a in (1, 2) and b in ("x", "y")
```

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_mechanics.py -s --setup-show
```

**观察任务（跑之前先猜，再验证）**：
- `expensive` 的 setup/teardown 各打印几次？（猜完再跑）
- `cheap` 呢？
- 参数化展开成几个用例？失败报告里 id 长什么样？
- 顺手验证方向规则：加一个 `@pytest.fixture(scope="session")` 去**请求** `cheap`，看它报什么错

**第三步（真改造）**：改 `tests/conftest.py`，把 `client` 拆成两层：

```python
@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture
def client(app, auth_headers):
    with TestClient(app, headers=auth_headers) as c:
        yield c
```

然后 `pytest -q`——**15 个测试必须仍然全绿**。挂了别慌，先读报错：是 `ScopeMismatch`（方向错了）还是行为变了（app 复用引入了状态）？这个差异本身是今天的知识点。

---

## §11 面试问法（今天的知识点怎么被考）

**Q：pytest 相比 unittest 好在哪？（高频）**
> 30 秒版："三个层面。断言用裸 assert，pytest 重写字节码给出每个子表达式的值，比 assertEqual 信息全；fixture 是组合式的依赖注入，按名字请求、支持四档作用域、teardown 必执行，比 setUp/tearDown 的继承绑定灵活；插件生态全——asyncio、cov、mock 都是即插即用。"

**Q：fixture 的 scope 有哪些？怎么选？**
> 30 秒版："function/class/module/session 四档，控制 fixture 的新建频率。默认 function；只有建得贵且只读的才升 session。方向规则是短作用域可请求长作用域，反过来会 ScopeMismatch——因为 session 级只建一次，它等不到每个函数的依赖。"

**Q：怎么保证测试之间互不影响？**
> 30 秒版："三层：状态用 function 级 fixture 每次重建；共享资源用 autouse fixture 前后清场（yield 后 teardown 必执行）；外部副作用用 monkeypatch/tmp_path 隔离。检验标准是测试可以单跑、全跑、乱序跑结果一致。"

**Q：ERROR 和 FAILED 的区别？**
> 30 秒版："FAILED 是测试跑了但断言不成立，查业务代码；ERROR 是 fixture 或收集阶段就挂了，测试根本没执行，先查 fixture 和环境。"

**追问链预警**：fixture 机制 → 和 FastAPI `Depends` 的异同（都是依赖注入，解析方式不同）→ 测试金字塔怎么分层 → 覆盖率 100% 意味着什么（什么都不意味，行覆盖 ≠ 行为验证）。

---

## §12 闭卷自测（先自己答，再展开）

<details>
<summary>1. pytest 收集阶段找什么？ERROR 和 FAILED 区别？</summary>

收集 `test_*.py`/`*_test.py` 里的 `test_*` 函数与 `Test*` 类（无 `__init__`），参数化在此展开。FAILED = 跑了但断言不成立；ERROR = fixture/收集阶段挂了，测试没执行。

</details>

<details>
<summary>2. 为什么 fixture 比 setUp 强？至少说两点</summary>

① 组合式依赖注入：按名字请求、任意拼装，不受继承链约束；② `yield` 后的 teardown 必执行，即使断言失败；③ 四档作用域可选，贵的资源可 session 级共享；④ 子目录 conftest 可分层特化。

</details>

<details>
<summary>3. 子目录 conftest 定义同名 fixture 会怎样？</summary>

就近遮蔽：子目录测试用子目录版本，父目录测试不受影响。这是分层特化的正规手法，不是错误。

</details>

<details>
<summary>4. 两个 @parametrize 叠加跑几个用例？失败的 id 有什么用？</summary>

笛卡尔积（2×3=6）。id 出现在失败报告的用例名里，直接定位是哪组输入挂了。

</details>

<details>
<summary>5. session 级 fixture 为什么不能请求 function 级？</summary>

session 只建一次，而 function 级每个测试都新建——session 建立时 pytest 不知道该绑定哪一份，pytest 直接报 ScopeMismatch 拒绝。

</details>

<details>
<summary>6. 怎么亲眼确认 fixture 执行顺序？</summary>

`pytest --setup-show`：按时间顺序打印每个 fixture 的 SETUP/TEARDOWN 和作用域标记（S/F）。

</details>
