# W6-D1 教材 · 依赖注入 Depends：调用链解析与缓存（零基础版）

> 阅读对象：对 FastAPI 的 `Depends` 只会"抄着写"、不知道它背后发生了什么的你。
> 所有输出均为本机实测（fastapi 0.150.0 / Python 3.11 / `kb-service/.venv`），不是文档摘抄。
> 阅读时间约 60 分钟，动手实验约 40 分钟，读源码约 40 分钟——正好一轮 3h。

---

## 一、痛点场景：没有依赖注入时，你在写什么

先看一个**没有 DI**的鉴权写法（你 W3 之前的状态）：

```python
@app.get("/api/v1/kbs")
def list_kbs(request: Request):
    # 每个需要鉴权的接口，都要自己写一遍这段
    auth = request.headers.get("Authorization")
    if auth is None or not auth.startswith("Bearer "):
        raise UnauthorizedError("缺少认证信息")
    token = auth.removeprefix("Bearer ")
    claims = decode_access_token(token)
    user_id = UUID(claims.sub)
    ...
```

三个问题，每个都比看起来严重：

1. **重复**：20 个接口要鉴权，这段代码抄 20 遍。改一处漏十九处。
2. **测不了**：`decode_access_token` 在函数体里被**直接调用**。测试时你想换成一个假的"已登录用户"？改不了——除非 mock，而 mock 是 W4 讲过的最后手段。
3. **依赖关系不可见**：这个接口依赖"当前用户"，但函数签名只说"我要一个 Request"。谁依赖谁，代码里看不出来，只有读函数体才知道。

W3 你学过**依赖倒置**：高层模块不该直接依赖低层实现，两者都依赖抽象。W5 你把 repo 接口收成了 `Protocol`——那是"抽象"的部分。**依赖注入是另一半：实现从外面塞进来，而不是在函数体里 new。**

DI 有三种常见形态，你都已经见过或马上要见：

| 形态 | 谁来"塞" | 你的例子 |
|---|---|---|
| 构造器注入 | 类的 `__init__` | W3 kbcli：`DocService(repo)` 构造时传入 |
| 参数注入 | 函数调用方 | W4 测试：`test_x(fake_repo)` 直接传参 |
| **框架注入** | **框架在运行时解析并调用** | **FastAPI `Depends`——本周主角** |

前两种的"塞"是你自己写的。第三种最玄：**你只是声明"我需要什么"，框架负责"算出来给你"**。它怎么算的？按什么顺序？同一个依赖会不会被算两次？这就是今天要拆开的黑盒。

---

## 二、最小可跑示例（5 分钟亲手跑）

不谈原理，先让现象出现。在 `kb-service` 下建一个临时文件（跑完就删）：

```python
# /tmp/probe_depends.py —— 与本节输出一一对应
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

calls: list[str] = []          # 记录每个依赖被调用的时刻

app = FastAPI()

def dep_a() -> str:
    calls.append("a")
    return "A"

def dep_b(a: str = Depends(dep_a)) -> str:   # b 依赖 a
    calls.append("b")
    return f"b({a})"

def dep_c(a: str = Depends(dep_a)) -> str:   # c 也依赖 a
    calls.append("c")
    return f"c({a})"

@app.get("/nested")
def nested(b: str = Depends(dep_b), c: str = Depends(dep_c)) -> dict:
    return {"b": b, "c": c}                  # 菱形：endpoint → b,c → a

client = TestClient(app)
r = client.get("/nested")
print("响应:", r.json())
print("调用顺序:", calls)
```

**跑之前先猜**：`calls` 打印出来是什么？（把你的猜测写在纸上，猜完再跑）

```powershell
# Windows PowerShell
cd F:\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\kb-service
& .\.venv\Scripts\python.exe C:\tmp\probe_depends.py
```

```bash
# Git Bash / Linux / macOS
cd /f/WorkBuddy/2026-10-20-08-44-29/python-backend-roadmap/kb-service
./.venv/Scripts/python.exe /tmp/probe_depends.py
```

实测输出（2026-11-05，fastapi 0.150.0）：

```
响应: {'b': 'b(A)', 'c': 'c(A)'}
调用顺序: ['a', 'b', 'c']     ← a 只出现一次
```

如果你的猜测是 `['a', 'b', 'a', 'c']`（b 算一次 a、c 又算一次 a）——**恭喜，你猜到了大多数人凭直觉的答案，而它是错的**。这就是"缓存"的存在证据，§四 拆。

还有一个反直觉点要先立住：

> **`def dep_b(a: str = Depends(dep_a))` 这里的 `Depends(dep_a)` 不是默认值！**

语法上它坐在"默认值"的位置上，但 FastAPI 在**导入时**就把这些位置扫走、注册成依赖图；运行时它的值由框架解析后传入。你从没见过"调用 `dep_b()` 不传参数会怎样"这种讨论——因为**你永远不会手动调用它，调用者是 FastAPI**。理解了这一点，后面一半的机制都顺了。

---

## 三、概念逐层展开：一个请求里，FastAPI 到底做了什么

### 3.1 路由注册时：把签名变成"依赖图"

当 `@app.get("/nested")` 装饰执行时，FastAPI 做的事（源码层面调 `inspect` 扫签名）：

1. 取出 `nested` 的每个参数
2. 参数默认值是 `Depends(...)` 的 → 记成一个"子依赖"，记下它又依赖谁
3. 参数默认值是 `Path()`/`Query()`/`Body()` 的 → 记成"从请求取值"
4. 递归处理子依赖的签名 → 最终得到一棵**树**

`/nested` 的依赖树：

```
nested
├── dep_b
│   └── dep_a
└── dep_c
    └── dep_a        ← 同一个 dep_a 出现两次！
```

**注册期只建图，不执行任何依赖函数。** 图建好后缓存起来（存在 route 对象的 `dependant` 字段里），每个请求来时直接用。

### 3.2 请求到来时：`solve_dependencies` 递归解析

每个请求，FastAPI 对这棵树做一次**深度优先**解析：

```
solve_dependencies(nested):
    解析 dep_b:
        解析 dep_a:              → 调用 dep_a() 得 "A"，存入本请求的缓存
        用缓存里的 "A" 作为实参   → 调用 dep_b(a="A") 得 "b(A)"
    解析 dep_c:
        解析 dep_a:              → 缓存命中！不调用，直接拿 "A"
        → 调用 dep_c(a="A") 得 "c(A)"
    用 "b(A)" "c(A)" 作为实参     → 调用 nested(...)
```

这就是实测输出 `['a', 'b', 'c']` 的来历：**后序遍历**——先算叶子（a），再算中间节点（b、c），最后算根（endpoint）。

### 3.3 你的项目里：一个真实请求的完整旅程

前面两小节用的是玩具例子。现在换成你项目里真在跑的路由，把"建树 → 解析 → 执行"三步走一遍。不要跳，逐行看值。

#### 第一步：路由长什么样（真实代码）

`kb-service/src/kb_service/api/v1/knowledge_bases.py`：

```python
@router.get("", summary="分页查询我的知识库")
async def list_kbs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),      # ← 依赖
) -> Page[KBOut]:
    return KBService().list(user_id, page, size)
```

`kb-service/src/kb_service/api/deps.py`：

```python
_bearer_scheme = HTTPBearer(scheme_name="Bearer Token", auto_error=False)   # 一个对象

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),   # ← 又一层依赖
) -> UUID:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)
    try:
        return UUID(claims.sub)
    except ValueError as exc:
        raise UnauthorizedError("凭证 subject 不是合法用户") from exc
```

#### 第二步：注册期建的树（每个节点对应上面一个"参数"）

```
list_kbs                      ← 根：你的路由函数
├── page:   Query(default=1)          ← 从 query string 取，不是依赖函数
├── size:   Query(default=20)
└── user_id: Depends(get_current_user_id)     ← 依赖节点
        └── credentials: Depends(_bearer_scheme)   ← HTTPBearer 实例，也是依赖节点
```

**看图的三条规则**（这是你之前卡住的地方，说透）：

1. **一个节点 = 路由函数的一个参数**。`page` 也是节点，只是它是"从请求取值的节点"，不需要调用任何函数。
2. **箭头方向 = "我需要谁"**。`list_kbs` 需要 `get_current_user_id` 的返回值；`get_current_user_id` 需要 `_bearer_scheme` 的返回值。
3. **`_bearer_scheme` 是对象不是函数，为什么还能当节点？** 见本节最后的"事实 1"——因为它**可调用**。

#### 第三步：请求期，框架按什么顺序执行

来一个真实请求：

```
GET /api/v1/kbs?page=1&size=20
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI3ZjM2...
```

`list_kbs` 的依赖树只有三层，解析过程是**自底向上**（先子后父，和 §3.2 的 `['a','b','c']` 是同一套规则）：

| 步 | 框架做什么 | 这一步的值 |
|---|---|---|
| ① | 调 `_bearer_scheme(request)` | `HTTPAuthorizationCredentials(scheme="Bearer", credentials="eyJhbGciOiJIUzI1NiJ9...")` |
| ② | 把①的值当实参，调 `get_current_user_id(credentials=...)` | 内部 `decode_access_token` → `TokenClaims(sub="7f36...")` → `UUID("7f36...")`，返回 `UUID('7f36...')` |
| ③ | 把②和 query 参数一起当实参，调 `list_kbs(page=1, size=20, user_id=UUID('7f36...'))` | 进入你的业务代码，返回 `Page[KBOut]` |

**注意顺序**：你的业务代码（③）是**最后**才跑的；鉴权（①②）全部发生在它之前，而且**值是一层一层喂进去的**——`get_current_user_id` 里你从来没写过 `request.headers`，因为 header 的读取发生在更下游的 `_bearer_scheme` 里。

一句话概括这条链：**路由只声明"我要一个 UUID 形式的用户 id"，不关心它从哪来；header → token → UUID 的转换被拆到两个更小的依赖里，各自只干一件事。**

#### 出错时走哪条路（这段是 D2 的引子）

把 header 去掉再请求，走的是①②之间的一个分支：

```
① _bearer_scheme(request) → Authorization 头不存在
   → auto_error=False → 返回 None（不抛异常）
② get_current_user_id(credentials=None)
   → if credentials is None: raise UnauthorizedError("缺少认证信息")
   → 被你 main.py 里注册的 AppError 异常处理器接住
   → 401 {"code": "UNAUTHORIZED", "message": "缺少认证信息", "detail": null}
```

**这里的 `auto_error=False` 是有代价的取舍**，不是随便写的——详见下面事实 2。

#### 三个"以前没注意、现在能解释"的事实

**事实 1：`_bearer_scheme` 是对象，为什么能当依赖？**

因为 FastAPI 对依赖的唯一要求是：**能被调用，且参数也能被框架解析**。对象只要实现了 `__call__` 就行。看 `HTTPBearer.__call__` 的真实源码（`fastapi/security/http.py`，节选核心）：

```python
async def __call__(self, request: HTTPConnection) -> HTTPAuthorizationCredentials | None:
    authorization = request.headers.get("Authorization")
    scheme, credentials = get_authorization_scheme_param(authorization)
    if not (authorization and scheme and credentials):
        if self.auto_error:
            raise self.make_not_authenticated_error()     # 默认：抛 HTTPException(401, "Not authenticated")
        else:
            return None                                   # auto_error=False：返回 None
    if scheme.lower() != "bearer":
        if self.auto_error:
            raise self.make_not_authenticated_error()
        else:
            return None
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
```

对照着看就明白了：**它就是一个"从 header 里抠 token"的普通依赖函数**，只不过写成了类的 `__call__`，好处是 `auto_error`、`scheme_name` 这些配置能存在实例属性上。

顺带解答一个常见疑问：既然是"可调用对象"，那 `Depends(Auth)`（传类）和 `Depends(Auth())`（传实例）有什么区别？——**传类时每次请求都新建实例**（因为没有状态可共享），**传实例时状态在请求间共享**。你的 `_bearer_scheme` 是模块级实例，正是"配置只读、可共享"的用法。这个留到 §十 实验 3 亲手验。

**事实 2：`auto_error=False` 到底改变了什么？**

上面源码里那个 `if self.auto_error` 分支就是全部答案。下面是**本机实测**（fastapi 0.150.0，不带 Authorization 头打 `GET /api/v1/kbs`）：

| | `auto_error=True`（FastAPI 默认） | `auto_error=False`（你项目里用的） |
|---|---|---|
| 头缺失时 | 抛 `HTTPException(401, detail="Not authenticated")` | 返回 `None` |
| 实际状态码 | **401** | **401** |
| 实际响应体 | `{"detail": "Not authenticated"}` | `{"code": "UNAUTHORIZED", "message": "缺少认证信息", "detail": null}` |
| 谁的代码产生它 | HTTPBearer 内部（框架） | 你的 `UnauthorizedError` + `AppError` 处理器 |

**注意 ①：状态码两边都是 401——这点和很多老教程写的不一样。** 早期 FastAPI 的 `HTTPBearer` 抛的是 **403**，0.150.0 的 `make_not_authenticated_error()` 已经改成了 401 并带上 `WWW-Authenticate` 头（符合 HTTP 语义：缺凭证是"未认证"，不是"禁止访问"）。**教程会过期，源码和实测不会**——这也是为什么本教材要求你先跑再信。

**注意 ②：那 `auto_error=False` 换来了什么？不是状态码，是响应体契约。**

```
默认：  401 {"detail": "Not authenticated"}
你的：  401 {"code": "UNAUTHORIZED", "message": "...", "detail": null}
```

如果让它走默认，你项目里所有错误响应就分成两种格式——业务错误是 `{"code","message","detail"}`，鉴权错误是 `{"detail"}`。前端要写两套解析、日志没法统一按 `code` 聚合、OpenAPI 里也描述不出这个结构。

这就是"框架默认值不一定是你系统的正确值"的典型例子。D2 会把这条展开成完整的执行顺序图：**异常在依赖解析阶段抛出、在 handler 之后被翻译**，两者层级不同，能接住它们的处理器也不同。

**验证方法**（30 秒，自己跑一遍）：把 `deps.py` 里 `auto_error=False` 改成 `True`，然后打一次不带头的请求，你会看到响应体变成 `{"detail": ...}`。**改完记得改回来**——`tests/test_chat.py` 或 `test_rag_async.py` 里那条 `assert code == "UNAUTHORIZED"` 的断言会因此变红，这正是它该有的作用。

**事实 3：可组合——为什么 10 个路由写同一行，却不算重复**

`grep` 你项目现在的统计（实测，2026-11-05）：

| 文件 | 路由数 | 挂了 `Depends(get_current_user_id)` |
|---|---|---|
| `knowledge_bases.py` | 6 | **6** |
| `documents.py` | 4 | **4** |
| `chat.py` | 1 | **1** |
| `health.py` | 1 | 0（探活接口不该要鉴权） |
| **合计** | **12** | **11** |

**每个路由都写了同一行，但"实现"只有一份**——这就是依赖注入和"抄代码"的区别：抄代码是逻辑复制 N 份，改一处漏 N-1 处；声明依赖是**引用同一个函数对象** N 次，函数体只存在一份。

更进一步，树还可以往下长而不改任何现有代码。比如 D6 之后你想加"管理员才能删库"：

```python
async def require_admin(user_id: UUID = Depends(get_current_user_id)) -> UUID:
    if not await is_admin(user_id):
        raise ForbiddenError("需要管理员权限")
    return user_id

@router.delete("/{kb_id}")
async def delete_kb(kb_id: UUID, admin_id: UUID = Depends(require_admin)) -> None: ...
```

新增一个节点，**`get_current_user_id` 一行没改**，而且同一个请求里它只会被执行一次（§四 的缓存）。这就是"依赖树可组合"的实际含义——**你不是在写路由，你是在拼装一棵可复用的图**。

---

## 四、机制深挖：请求级缓存（今天最重要的概念）

### 4.1 缓存的范围：一次请求，不是全局

实测（§二 已跑）菱形依赖中 `dep_a` 只被调用一次。为什么？

源码位置（本机路径）：
`kb-service/.venv/Lib/site-packages/fastapi/dependencies/utils.py`，`solve_dependencies` 的缓存核心在 **660–680 行**：

```python
# utils.py:660-661（节选，源码就是这两行）
if sub_dependant.use_cache and sub_dependant_cache_key in dependency_cache:
    solved = dependency_cache[sub_dependant_cache_key]

# utils.py:679-680
if sub_dependant_cache_key not in dependency_cache:
    dependency_cache[sub_dependant_cache_key] = solved
```

三列读法（按周计划的源码笔记格式）：

| 行号 | 做什么 | 为什么这么设计 |
|---|---|---|
| 660 | 解析子依赖前，先查 `dependency_cache` 里有没有 | 避免同一个依赖（如"取当前用户"）在一次请求里被重复执行——鉴权、查库都可能有副作用 |
| 661 | 命中就直接用缓存的值 | 值相同 + 副作用不重复，语义和性能双赢 |
| 679-680 | 没命中才真正调用，然后写进缓存 | 缓存的是**调用结果**，key 是依赖的"**身份**"——注意"身份"具体是什么，见下面这段 |

**0.150.0 里 cache key 到底是哪三项**（源码 `dependencies/models.py:92-96`，`_get_cache_key`）：

```python
return (
    dependant.call,                                    # ① 函数对象本身
    scopes_for_cache,                                  # ② oauth scopes 元组
    _get_computed_scope(dependant=dependant) or "",     # ③ "function" / "request" / ""
)
```

三项里**没有实参**。这是本版必须记住的一条：同一个函数 + 不同参数，**不会**自动拆成两个缓存条目。后果在 §4.2 展开。

注意两个关键属性：

- **`dependency_cache` 是每次请求新建的**（`utils.py:615-616`：`if dependency_cache is None: dependency_cache = {}`）。所以缓存范围 = **一个请求的生命周期**，请求结束缓存就没了。**不是全局单例**——这与 `functools.lru_cache`、模块级变量有本质区别，面试必考。
- **`use_cache: bool = True`** 在 `fastapi/params.py:748`（`Depends` 类的字段）。

### 4.2 关掉缓存：`use_cache=False`

什么时候一个请求里**需要**同一依赖被调用两次？举两个真实场景：

- 一个接口同时要"当前用户的完整资料"和"目标用户的公开资料"——都靠 `get_user(id)` 取，两个不同的 id **必须**查两次。
  ⚠️ 光是参数不同**不够**：cache key 不含实参（§4.1），不显式关缓存的话，第二处会直接复用第一处的值 → **你拿到的"目标用户"其实是自己**。这是一个真实的越权漏洞形态，不是性能问题。
- 某依赖内部读文件/发请求，每次调用点的语义就是"重新拿一次"

写法与实测：

```python
@app.get("/nocache")
def nocache(
    x: str = Depends(dep_fresh),
    y: str = Depends(dep_fresh, use_cache=False),   # 只对 y 这一处关缓存
):
    ...
```

实测输出：

```
响应: {'x': 'F', 'y': 'F'}
调用顺序: ['fresh', 'fresh']     ← 两次调用
```

### 4.3 一个高频误用：把"共享状态"放错了地方

看这个错误想法："我想在一个请求里让多个依赖共享一个计数器/一条数据库连接，用模块级变量行不行？"

模块级变量 = **所有请求共享**（还有并发安全问题）。请求级共享的正确姿势是**一个依赖被其他依赖消费**——靠缓存天然实现：

```python
async def get_db_session():          # W7 会真的这么写
    ...

async def get_kb_repo(session = Depends(get_db_session)):
    return KBRepo(session)           # 同一请求里多个 repo 共享同一 session

async def get_doc_repo(session = Depends(get_db_session)):
    return DocRepo(session)          # 缓存保证这里拿到的是同一个 session
```

**`get_db_session` 在一个请求里只执行一次**（缓存），两个 repo 拿到同一个 session——这就是 FastAPI 版的"请求作用域容器"。W7 数据库周会把这个模式落地成真代码。

---

## 五、yield 依赖：带"善后"的依赖

到目前为止依赖都是"算出值 → 返回"。但有些资源需要**用完清理**：数据库连接要关、临时文件要删、锁要放。这就是 `yield` 依赖：

```python
def dep_yield():
    calls.append("setup")       # yield 之前的代码：解析阶段执行
    yield "resource"            # yield 出去的值，就是注入的值
    calls.append("teardown")    # yield 之后的代码：响应发出后执行
```

实测输出（§二 探针场景 3）：

```
调用顺序: ['setup', 'handler', 'teardown']   ← teardown 在响应之后
```

**执行时序**（记住这张图，W7 数据库会话管理直接用它）：

```
请求进入
  → [setup]     依赖 yield 前的部分（开连接）
  → handler     你的路由函数跑（用连接）
  → 响应发出
  → [teardown]  依赖 yield 后的部分（关连接）——即使 handler 抛异常也会执行
```

三个必须知道的边界（第 2 条是实测跑出来的，教材旧版漏了，很容易在 W7 踩）：

1. **异常会被送进 yield 点**，不只是"框架顺手帮你执行 teardown"。实测顺序：`setup → caught:ValueError → teardown`——`except` 能抓到 handler 抛的异常。这意味着 teardown 里可以写**回滚**（W7 事务要用到）。
2. ⚠️ **teardown 自己抛异常，客户端看不到**。同一份代码实测两次：

   | `scope` | 客户端收到 | 服务端 |
   |---|---|---|
   | 不写（默认，yield 依赖视为 `"request"`） | **200 + 正常响应体** | 异常只在日志里 |
   | `Depends(dep, scope="function")` | **500** | 正常错误响应 |

   原因：默认 scope 是 `"request"`，teardown 在**响应发出之后**才跑，那时状态码早已定死。想让 teardown 的失败影响状态码（提交事务失败必须返回 500），**必须显式写 `scope="function"`**。
3. **teardown 里不要发响应**：响应已经发出去了，teardown 只适合做清理（关连接、删临时文件、释放锁）。想改响应体，teardown 阶段已经晚了。

对照你已学过的知识：`yield` 依赖 ≈ **pytest 夹具的 `yield` 模式**（W4-D1 讲过：setup / yield / teardown）——FastAPI 把 pytest 的这个设计搬到了请求生命周期里。你面试可以直接说"这两个机制设计同源"。

---

## 六、测试的另一半：`dependency_overrides`

W4 你换依赖的方式：在 conftest 里构造 fake，然后**直接调 service 函数**传参。这对 service 层够用，但对**路由层**测试有个缺口：`TestClient` 打进来的是一个真实 HTTP 请求，路由内部 `Depends(get_current_user_id)` 解析的是真依赖——怎么换？

FastAPI 的官方答案：

```python
app.dependency_overrides[get_current_user_id] = lambda: UUID("00000000-0000-0000-0000-000000000001")
# 之后所有经过该 app 的请求，get_current_user_id 都返回这个假 UUID

app.dependency_overrides.clear()   # 测完清掉
```

实测输出（§二 探针场景 4）：

```
响应: {'b': 'b(FAKE)', 'c': 'c(FAKE)'}        ← override 生效，连子依赖都不调了
清掉 override 后: {'b': 'b(A)', 'c': 'c(A)'}   ← 原样恢复
```

三个要点：

1. **override 是"整个子树"级别的替换**：`dep_a` 被覆盖后，依赖它的 `dep_b`、`dep_c` 全部拿到假值——不用一个个替换。
2. **key 是函数对象本身**（不是名字、不是字符串）——所以 `from kb_service.api.deps import get_current_user_id` import 到的和路由里 `Depends(...)` 里的必须是**同一个对象**。这也是为什么 deps.py 里的依赖要"定义一次、到处 import"。
3. **它和 W5 的 `Protocol` 是绝配**：fake 返回的值如果本身也符合 `Protocol` 声明的形状，mypy 还能帮你检查 fake 写没写对——静态契约 + 运行时替换，两套机制各管一段。

### 6.1 它到底存了什么（源码两行 + 三条实测）

`app.dependency_overrides` 的类型声明就一行（`fastapi/applications.py:964`）：

```python
self.dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] = {}
```

**key = 注册依赖时用的那个 callable 对象；value = 你替上去的 callable 对象。**
不是函数名、不是字符串、不是 `Depends(...)` 实例。它就是个**普通 dict**，所以"塞任意值都不报错"。

查找也只有一行（`dependencies/utils.py:625-631`）：

```python
original_call = sub_dependant.call
call = getattr(provider, "dependency_overrides", {}).get(original_call, original_call)
```

`.get(key, 默认值)`——找不到就**原样返回自己**。所以 key 写错永远不报错，只是永远不命中（这就是"静默失效"的来源）。

⚠️ 还有一层容易漏：命中之后**不是直接调用替身**，而是拿替身重新 `get_dependant(call=替身, ...)` 建一棵新的依赖子树（`utils.py:632-638`）。三个实测后果：

| 你的写法 | 实测结果 | 为什么 |
|---|---|---|
| `Depends(functools.partial(dep, uid=7))`，然后 override `dep` | **不生效**，且静默 | 注册时的 `call` 是那个 partial 对象，不是 `dep`；两个对象不相等 |
| `Depends(repo.get)`，override 时用**另取一次**的 `repo.get` | **生效** | bound method 的相等性按（实例 + 函数）比较，不按对象身份——和普通函数不同 |
| 替身写成 `lambda uid: f"fake:{uid}"` | 必须带 `?uid=`，否则 **422** | 替身的**签名会被重新解析**，参数照常当 query / path / body 处理 |

顺带一个不在 override 里、但同源的坑：给依赖加装饰器时不用 `functools.wraps`，`wrapper(*a, **kw)` 的签名会被 FastAPI 当真——直接报 `missing query a / missing query kw`，422。**装饰器只保留 `wraps` 是不够的，被装饰的函数必须签名可解析。**

### 6.2 两张 dict 别混：overrides 的 key vs cache 的 key

学到这儿你手上其实有**两张 key 完全不同的 dict**，面试最容易在这里翻车：

| | `dependency_overrides` | `dependency_cache` |
|---|---|---|
| 挂在哪 | `app` 上（`applications.py:964`） | 每次请求**新建**（`utils.py:615-616`） |
| 类型 | `dict[Callable, Callable]` | `dict[DependencyCacheKey, Any]` |
| key | **单个 callable 对象** | **三元组** `(call, scopes, scope)`（`types.py:12`） |
| value | 替身 callable | 依赖**解析出来的值** |
| 谁写 | 你手写 | 框架自动写（`utils.py:679-680`） |
| 查找 | `.get(original, original)` | `if key in cache` |
| 生命周期 | app 级，测完必须 `clear()` | 一次请求，请求结束就丢 |

`DependencyCacheKey` 的定义就一行（`fastapi/types.py:12`）：

```python
DependencyCacheKey = tuple[Callable[..., Any] | None, tuple[str, ...], str]
```

实测打印出来长这样（`_get_cache_key` 直接算）：

```
Depends(f)                      -> (<function f at 0x...>, (), '')
Depends(f, scope="function")    -> (<function f at 0x...>, (), 'function')
```

三元组逐项：① 依赖 callable 对象 ② oauth scopes（没用到就是 `()`）③ scope 字符串（`"function"` / `"request"` / `""`）。

**实测验证第三项真的参与比较**：同一个 `f`，一个 `Depends(f)`、一个 `Depends(f, scope="function")`，同请求内 `f` 被调用了 **两次**——因为 key 只差第三项，没命中。

一个细节（源码读出）：override 生效时，缓存 key 仍按**原依赖** `sub_dependant` 算（`utils.py:656-657` 用的是 `sub_dependant`，不是替换后的 `use_sub_dependant`）。所以替身的结果会记在"原依赖"名下——同一请求内替身也只跑一次，缓存语义不会被 override 破坏。

**D1 动手任务里你会把 W4 的 conftest 注入方式改造成 overrides 版**，然后写一段对比笔记（两种方式的适用边界）。

---

## 七、读源码任务（今天的主菜，约 40 分钟）

> 目的：不是读懂 FastAPI 全部，是**亲手确认"§三、§四 讲的机制在源码里长什么样"**。
> 笔记格式固定三列：行号 + 那行做什么 + 为什么这么设计。**不抄大段代码。**

### 7.1 热身：`Depends` 类本体（20 行不到）

文件：`.venv/Lib/site-packages/fastapi/params.py`，从 **746 行**开始。

```powershell
# Windows PowerShell —— 直接用行号范围看
Get-Content .\.venv\Lib\site-packages\fastapi\params.py | Select-Object -Skip 745 -First 25
```

```bash
# Git Bash / Linux / macOS
sed -n '746,770p' ./.venv/Lib/site-packages/fastapi/params.py
```

看的时候回答三个问题（写进笔记）：
1. `Depends.__init__` 的 `dependency` 参数存到哪了？（提示：`self.dependency`）
2. `use_cache` 默认值是什么？在源码哪一行？（748）
3. `Depends` 有没有任何"执行"逻辑？（没有——它只是个**声明载体**，执行全在 solve 阶段）

### 7.2 主菜：`solve_dependencies` 的缓存段（约 60 行）

文件：`.venv/Lib/site-packages/fastapi/dependencies/utils.py`（共 1102 行），看 **583–730 行**。

```powershell
# Windows PowerShell
Get-Content .\.venv\Lib\site-packages\fastapi\dependencies\utils.py | Select-Object -Skip 582 -First 150
```

```bash
# Git Bash / Linux / macOS
sed -n '583,730p' ./.venv/Lib/site-packages/fastapi/dependencies/utils.py
```

按行号抓重点（别陷进 1102 行的细节，只看这几处）：

| 行号 | 看什么 |
|---|---|
| 583 / 594 | `dependency_cache` 参数的声明——注意它是个 `dict`，且默认 `None` |
| 615-616 | 缓存为 `None` 时新建空 dict → **证明缓存是请求级的** |
| 660-661 | 缓存命中分支 → §四 4.1 引用的就是这里 |
| 679-680 | 缓存写入分支 |
| 730 | 递归调用自己时把 `dependency_cache` 传下去 → **同一个 dict 贯穿整棵树** |

**验收式的问题**（读完后必须能答）：`dependency_cache` 是怎么"贯穿整棵依赖树"的？（答：递归时作为参数逐层传下去，整棵树共享同一个 dict——这就是为什么菱形的两个分支能互相命中。）

### 7.3 记录产出

写 `progress/week6/D1-源码笔记.md`：两张三列表（Depends 类 + 缓存段）+ 上面所有验收问题的答案。**50 行以内**，长了说明你在抄而不是在读。

---

## 八、易错点表

| 坑 | 症状 | 正解 |
|---|---|---|
| 把 `Depends(...)` 当默认值理解 | 以为"不传参就用自己的默认"，或手动调用 `dep_b()` 期望它自己解析依赖 | `Depends` 是声明标记，只在框架解析时生效；依赖函数**永远不要手动调用** |
| 以为依赖缓存是全局的 | 模块级可变对象当"请求内共享"，出现跨请求数据串门 / 并发错乱 | 请求级共享 = 依赖互相 `Depends` 消费（§4.3）；全局可变状态要加锁且三思 |
| 在 teardown 段写业务逻辑 | 想在 yield 后面改响应 / 记录"请求结果"，发现拿不到 | teardown 只做清理；响应在它之前已发出 |
| 以为 teardown 出错会让请求失败 | 客户端拿到 **200 + 完整响应**，异常只在服务端日志（默认 `scope="request"`，响应已发出） | 要 teardown 影响状态码 → `Depends(dep, scope="function")`（实测 500） |
| override 的 key 写成字符串 | **不报错，也不生效**：override 躺在 dict 里没人查，请求照走真实依赖 | key 是 **callable 对象**；查找是 `dict.get(original_call, original_call)`，找不到就用原函数（`utils.py:625-631`） |
| 用 `functools.partial` / 不带 `wraps` 的装饰器包了依赖，再 override 原函数 | 不生效，且零报错 | 注册时的 `call` 已经是那个新对象，两个对象不相等 |
| `use_cache=False` 当性能开关用 | 以为关缓存能"刷新数据"，实际是重复执行副作用（重复查库/重复鉴权） | 同函数要拿不同的值 → 必须显式 `use_cache=False`。**光改参数没用**——key 是 `(call, scopes, scope)`，不含实参 |
| 在依赖里做耗时操作且到处挂 | 每个接口都 `Depends(get_heavy_thing)`，接口全变慢 | 依赖 = 每请求至少执行一次；重的动作要么放缓存友好的位置，要么按需挂载 |

---

## 九、命令速查

```powershell
# Windows PowerShell ==============================

# 跑今天的探针（确认缓存/顺序/yield/override 四个行为）
& .\.venv\Scripts\python.exe C:\tmp\probe_depends.py

# 看源码片段（行号区间）
Get-Content .\.venv\Lib\site-packages\fastapi\params.py | Select-Object -Skip 745 -First 25
Get-Content .\.venv\Lib\site-packages\fastapi\dependencies\utils.py | Select-Object -Skip 582 -First 150

# 起 dev server 手动打 /docs 试依赖
& .\.venv\Scripts\uvicorn.exe kb_service.main:app --reload --port 8000
```

```bash
# Git Bash / Linux / macOS =========================

./.venv/Scripts/python.exe /tmp/probe_depends.py

sed -n '746,770p' ./.venv/Lib/site-packages/fastapi/params.py
sed -n '583,730p' ./.venv/Lib/site-packages/fastapi/dependencies/utils.py

./.venv/Scripts/uvicorn.exe kb_service.main:app --reload --port 8000
```

> 注意：Windows 的 venv 在 `Scripts/`，真 Linux 是 `bin/`——这是同一个 venv 结构差异，不是命令不同。

---

## 十、动手实验（每题跑之前先猜，猜错才值钱）

**实验 1（缓存 key 的粒度）**：定义 `def dep(x: int = 0)`。⚠️ 旧版这题写的是 `Depends(dep, x=1)`——**在 0.150.0 跑不起来**（`Depends` 只接受 `dependency` / `use_cache` / `scope`，传 `x=1` 直接 `TypeError`）。想给依赖"换参数"，只能换一个 callable 对象。两组各跑一次：

- A 组：`Depends(dep)` + `Depends(functools.partial(dep, x=1))`
- B 组：`Depends(dep)` + `Depends(dep, scope="function")`

同一请求里 dep 各被调用几次？**先猜再跑**。（A 组考 key 第一项，B 组考第三项）

**实验 2（yield + 异常）**：`dep_yield` 的 handler 里 `raise RuntimeError("boom")`。teardown 会执行吗？响应状态码是什么？**先猜再跑**。

**实验 3（类依赖）**：写一个 `class Auth:` 有 `__call__(self, credentials=Depends(_bearer_scheme))`，用它替换 `get_current_user_id`。行不行？`Depends(Auth())` 和 `Depends(Auth)` 有什么区别？（一个用实例一个用类——实例的状态是共享的吗？）

**实验 4（override 的子树性）**：只 override `dep_a`（§二的菱形图），`dep_b`、`dep_c` 不动。它们的返回值变吗？——验证 §六 要点 1。

**实验 5（自选）**：把你最近真实犯过的一个依赖相关错误（或直觉猜错的点）做成探针注进去。门禁/行为和你想的一样吗？**这个实验的产出进 D6 反脆弱清单。**

---

## 十一、面试问法

**30 秒版**：

> FastAPI 的 `Depends` 是框架级依赖注入：注册期把路由签名扫成一棵依赖树，请求期由 `solve_dependencies` 深度优先递归解析，先算叶子再算根。缓存是**请求级**的——每个请求新建一个 cache dict，随递归逐层传递贯穿整棵树，所以菱形依赖（多个依赖共享同一个上游）只执行一次上游。需要清理的资源用 yield 依赖，teardown 在响应之后、异常安全。测试用 `dependency_overrides` 按函数对象整体替换子树。

**追问链**：

| 层 | 问法 | 答到什么算过 |
|---|---|---|
| 一层（机制） | 缓存是怎么实现"贯穿整棵树"的？ | 每请求新建 dict，递归 `solve_dependencies` 时作为参数逐层传下去（源码 utils.py:615-730） |
| 二层（边界/故障） | 什么场景必须 `use_cache=False`？误用会怎样？ | 同一依赖不同语义（不同参数）；误用 = 重复副作用。**反方向**：以为缓存是全局的、用模块级变量共享状态 → 跨请求串门 |
| 三层（场景落地） | W7 接 MySQL 时，怎么保证一个请求里所有 repo 共享一个事务连接？ | `get_db_session` 用 yield 依赖（teardown 关连接），repo 依赖 `Depends(get_db_session)` 靠缓存拿同一连接——说出这个架构就赢了 |

**和已有项目故事的接缝**：W5 的 `Protocol` + W4 的 fake + 今天的 `dependency_overrides`，串成一句话进面试："**我的分层测试是静态契约（Protocol）+ 运行时替换（overrides）的组合，fake 不是靠 mock 打补丁，是实现了同一契约的另一实现。**"

---

## 十二、闭卷自测（先答后翻）

<details>
<summary>1. 依赖树解析的遍历顺序是什么？为什么 `calls` 是 ['a','b','c']？</summary>

深度优先、后序：先递归解析子依赖（叶子），拿到值后才能调用当前依赖（父节点），最后调用 endpoint。`dep_b` 需要先有 `dep_a` 的值才能执行，所以 a 在 b 前。
</details>

<details>
<summary>2. 菱形依赖里 dep_a 为什么只执行一次？缓存的 key 和生命周期分别是什么？</summary>

`solve_dependencies` 维护一个 `dependency_cache` dict，递归解析时同一个 dict 逐层传递贯穿整棵树；先查缓存（utils.py:660），没命中才调用并写入（:679）。key 是依赖的身份（callable + 参数配置），生命周期是**单个请求**——每请求新建，请求结束即废弃。
</details>

<details>
<summary>3. yield 依赖的三段各在什么时刻执行？handler 抛异常时 teardown 还跑吗？</summary>

yield 前 = 解析阶段（响应前）、yield 值 = 注入给 handler、yield 后 = 响应发出后。异常时 teardown **依然执行**（生成器被框架包裹，finally 语义），所以清理代码放这里是可靠的；但 teardown 里拿不到/改不了响应。
</details>

<details>
<summary>4. `dependency_overrides` 的 key 用字符串为什么会失败？正确写法是什么？</summary>

key 必须是依赖的**函数对象本身**，不是名字。`dependency_overrides[get_current_user_id] = fake`。字符串 key 查不到对应依赖，静默不生效。深层原因：依赖注册存的是对象引用，路由里 `Depends(get_current_user_id)` 和 import 到的是同一对象。
</details>

<details>
<summary>5. 为什么说"请求级共享状态的正确姿势是一个依赖被其他依赖消费"？模块级变量差在哪？</summary>

依赖消费 + 缓存 = 同一请求内天然拿到同一实例（如同一 DB session），且请求结束自动释放；模块级变量是**跨请求**共享的——多 worker/多并发下数据串门、竞态，还需要手动管理生命周期。一句话：缓存的边界是请求，模块变量的边界是进程。
</details>

---

## 十三、今日任务单（按顺序做）

1. ✅ 读教材 + 跑 §二 探针（把猜测写下再跑）
2. ✅ §七 读源码 → 写 `progress/week6/D1-源码笔记.md`（三列格式，≤50 行）
3. ✅ §十 实验 1–4（实验 5 可留到 D6）
4. ✅ **动手任务（已修正）**：项目里 11 个路由**已经全部挂好** `Depends(get_current_user_id)` 了，所以任务不是"去挂一遍"，而是**两种注入方式对打**：
   - 现在 `tests/conftest.py` 用 `auth_headers` 夹具签**真 token**（走完整鉴权链）；`tests/test_rag_async.py:134` 用了一段 `dependency_overrides[get_current_user_id]`
   - 把后者抽成 conftest 里的 `auth_override` 夹具（带 `try/finally` 清理，否则会污染其他测试）
   - 在 `D1-总结.md` 里写清三种方式的取舍：**真 token / override / 直接调 service 传 fake**——各自证明了什么、漏掉了什么
5. ✅ 画依赖解析树：把 `deps.py` 的树 + 探针菱形树画进总结（纸上拍照片贴 md 也行）
6. ✅ 跑门禁确认没弄坏：`& .\.venv\Scripts\python.exe scripts\check.py`
7. 日课清账（见周计划"滚动日课"节）：LC 283 闭卷手写 + Protocol/幂等/Any/累计勾

明天 D2：中间件与异常处理器的执行顺序——今天学的"解析发生在 handler 之前"是明天"异常谁先接住"的前置知识。
