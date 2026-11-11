# W6-D5 教材 · OpenAPI 定制 + BackgroundTasks（零基础版）

> ⚠️ **本文件已拆分为两份独立教材（11-11 用户反馈"从头到尾模糊"后重写）**：
> - 上午读 → `D5a-OpenAPI文档定制-教材.md`（主线：**一份 JSON 的一生**）
> - 下午读 → `D5b-BackgroundTasks-教材.md`（主线：**一次请求的生命线**）
>
> 拆分病因：① 强行用一根时间轴统一两个不同主语（业务请求 vs `/openapi.json` 请求），是模糊的主因；② 术语零锚点前置；③ 先贴源码后讲用法。
> **本文件保留作"源码级参考"**：探针 15 节实测输出、Starlette 36 行源码逐行、面试三层追问，D5a/D5b 里已抽取主线，细节查这里。

> 读者假设：你对这两个主题**完全不会**。本篇从"没有它会怎样"讲起，每个断言都有本机实测输出（FastAPI 0.150.0 / Starlette 1.9.0 / Python 3.11）。
> 配套探针：`D5-探针-OpenAPI与BackgroundTasks.py`（十节）、`D5-探针2-时序与文档化.py`（五节）。所有输出都可自己重跑。

## 零、主线：一张时间轴（先记住这个，再看细节）

D5 的两个主题看着毫不相干——一个是"文档"，一个是"任务"——但它们被同一根时间轴分开：

```
请求进来
   ↓  依赖解析 / 参数校验（错了 → 422，请求到此为止）
   ↓  handler 跑业务
handler 返回 ←────────── 你写的代码到这里就结束了
   ↓  response_model 校验 + 序列化（错了 → 500）
   ↓  http.response.start / body 发出去  ★ 客户端这一刻已经拿到响应
   ↓  后台任务开始跑            ★ 从这一刻起，出什么事客户端都不知道
   ↓  日志收尾 / 中间件收尾
```

**分界线只有一句**：**响应发出之前是契约（必须准、必须快），之后是副作用（可以慢、错了也不影响用户）**。

- OpenAPI 定制全部发生在**响应发出之前**那一半——它不改变运行时行为，只改变"别人看到你长什么样"。
- `BackgroundTasks` 全部发生在**响应发出之后**那一半——它不改变响应内容，只把"不该让用户等的事"挪到后面。

### 每节的位置自查

| 节 | 在时间轴上的位置 | 读完要能回答 |
|---|---|---|
| §三 OpenAPI 定制 | 构建期（应用启动时算好，`/openapi.json` 只是发出来） | 文档是什么时候生成的？拼错了谁会报错？ |
| §四 BackgroundTasks | 响应 body 发出**之后** | 任务什么时候跑？它炸了客户端知道吗？ |
| §五 易错点 | 两侧都有 | 哪几条是"零症状"的？ |
| §八 面试 | — | 能不能一句话说清两侧的分界线 |

## 一、痛点场景：没有它们的世界

### 1.1 没有 OpenAPI 定制：文档是"能跑就行"的样子

FastAPI 不用你写文档，`/docs` 自动就有。但**自动生成 ≠ 可用**：

- 所有接口的 tag 是 `default`，一屏 20 个接口平铺，前端找不到自己想调的那个；
- 每个接口只有 `summary` 是函数名（`create_kb`），说明栏空的；
- **错误响应文档里只有 200 和 422**——你的 `code=40100`、`40400` 这套统一壳，前端在文档上一个字都看不到，只能来问你；
- 生产环境的 `/docs` 还开着——等于把内部接口清单挂在公网。

前端对接时会问的五个问题：这个接口是干什么的？哪些字段必填？出错返回什么？哪些接口废弃了？有没有测试环境地址？——**OpenAPI 定制的全部工作，就是让 `/docs` 能自己回答这五个问题**。

### 1.2 没有后台任务：用户替你等

假设文档上传后要"切块 + 向量化"，耗时 3 秒。没有后台任务时只有三种写法，全是坑：

| 写法 | 问题 |
|---|---|
| 在 handler 里 `await` 完再返回 | 用户等 3 秒，超时/重试/流失；上传接口的 P99 直接崩 |
| 起个裸线程 `threading.Thread(target=...)` | 线程不受管：请求量一上来线程爆掉，异常没人接，进程退出任务丢 |
| `asyncio.create_task(...)` | 比线程好，但**任务随请求生命周期走**，响应发完事件循环如果没别的活它照跑——可一旦部署多进程/重启就丢，且没有统一入口观察 |

`BackgroundTasks` 是框架给的**最小可用方案**：任务挂在**响应对象**上，响应发完由框架按顺序执行；同步函数自动进线程池（不堵事件循环）；异常落进服务端日志。它不是"任务队列"，但足够覆盖"响应之后顺手做一件事"这一大类。

## 二、最小可跑示例（5 分钟亲手跑）

```powershell
# Windows PowerShell（kb-service 目录）
& .\.venv\Scripts\python.exe ..\progress\week6\D5-探针-OpenAPI与BackgroundTasks.py
```

只看两段输出：

```
六、BackgroundTasks 行为
响应状态=200 body={'ok': '1'} 客户端总耗时=0.205s
事件顺序: ['handler 返回', 'sync start', 'sync end', 'async start(async)', 'async end(async)']
同步任务的线程: ['线程名=AnyIO worker thread']
```

和

```
四、自定义 openapi() 与 app.openapi_schema 缓存
custom_openapi 调用次数（3 次请求后）: 3
servers: [{'url': 'https://api.example.com', 'description': '生产'}]
```

**跑之前先猜**：`事件顺序` 里 `handler 返回` 为什么排第一？`sync start` 和 `async start` 谁先？客户端 0.205s 是"收到了响应还在等"还是"根本没收到"？

（答案在 §四 4.2——先猜再翻。）

## 三、OpenAPI 定制（文档面）

### 3.1 先认识 `/openapi.json` 这张表

FastAPI 启动时把路由表**翻译**成一份 JSON（OpenAPI 3.1 规范），`/docs`（Swagger UI）只是这份 JSON 的渲染器。所以定制文档 = 定制这份 JSON。五个顶层键：

| 键 | 内容 | 你改它的入口 |
|---|---|---|
| `info` | title / version / description / contact / license | `FastAPI(title=..., version=...)` |
| `paths` | 每个路径 × 每个方法：summary / description / parameters / responses | 路由装饰器 |
| `components.schemas` | 所有 Pydantic 模型的 JSON Schema（`$ref` 指向这里） | 模型定义 + `response_model` |
| `tags` | 分组名 + 说明 + 顺序 | `openapi_tags=[...]` |
| `servers` | 环境地址列表 | `FastAPI(servers=[...])` 或自定义 openapi |

一条命令看全表：

```powershell
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; s=app.openapi(); print(json.dumps({'tags':s.get('tags'),'paths':list(s['paths'])}, ensure_ascii=False, indent=2))"
```

### 3.2 `openapi_tags`：拼错**不报错**，只在 /docs 里露馅

这是今天第一个坑，实测（探针一）：

```
tags 段（按 openapi_tags 声明顺序）:
  name='knowledge-bases'    desc=知识库的增删改查
  name='documents'          desc=文档上传与解析
  name='share'              desc=分享（故意写错：真实 tag 是 shares）

每个路径实际用的 tag:
  GET    /kbs                   tags=['knowledge-bases']
  GET    /kbs/{kb_id}/docs      tags=['documents']
  GET    /shares                tags=['shares']
```

三条规则：

1. `openapi_tags` 只负责**给 tag 配说明 + 定顺序**；它不是白名单，不会拦任何路由。
2. 声明了 `share` 但没路由用 → tags 里仍然出现，前端看到**一个没有任何接口的分组**。
3. 路由用了 `shares` 但没声明 → 自动出现在 tags 里，**没有 description，排到最后**。

**两侧都不报错、测试也不挂**——它只影响人类阅读。这是典型的"零症状坑"：`/docs` 打开一眼就能看出来，但没有任何自动化会提醒你。

### 3.3 路由级文档字段：写在装饰器上，进 OpenAPI

```python
@router.post(
    "",
    tags=["knowledge-bases"],
    summary="创建知识库（一行摘要）",
    description="多行说明，支持 **Markdown**：\n\n- 列表项一\n- 列表项二",
    response_description="创建成功，返回知识库本体",
    deprecated=True,          # 标废弃，/docs 里划灰线
    status_code=201,
)
```

实测进 JSON 的样子：

```
summary: 创建知识库（一行摘要）
description: 多行说明，支持 **Markdown**： - 列表项一 - 列表项二
responses: {'201': {'description': '创建成功，返回知识库本体', ...}}
GET /old deprecated 字段: True
```

要点：

- `summary` 是一行（列表页显示），`description` 是多行（详情页显示，支持 Markdown），`response_description` 只改**成功响应**那一行的说明。
- `deprecated=False` 时 JSON 里**不出现** `deprecated` 键（实测 `None`）；只有 `True` 才写进去。
- 函数的 docstring 也会自动成为 `description`——但显式参数优先，两者都写容易不一致，选一个。

### 3.4 把**统一响应壳**写进文档：`responses=`

D4 那套 `{"code","message","data"}`，默认在文档里完全看不到。修法（实测输出）：

```python
@router.get(
    "/items/{item_id}",
    responses={
        401: {"model": ApiResponse, "description": "未认证（code=40100）"},
        404: {"model": ApiResponse, "description": "资源不存在（code=40400）"},
    },
)
```

```
401: desc='未认证（code=40100）' schema={'$ref': '#/components/schemas/ApiResponse'}
404: desc='资源不存在（code=40400）' schema={'$ref': '#/components/schemas/ApiResponse'}
components 里的模型名: ['ApiResponse', 'HTTPValidationError', 'ValidationError']
```

注意两件事：

1. `model=` 会被注册进 `components.schemas`，用 `$ref` 复用——不是每个错误码复制一份 schema。
2. **这里只写"文档"，不写"行为"**：`responses=` 不会让接口真的返回 401，也不会校验你的错误体。真行为在 D4 的 handler 里，这里只是把契约补全。**文档和实现是两条独立的路**，写歪了不会有任何报错——这是 OpenAPI 定制最容易"自己骗自己"的地方。

### 3.5 `include_in_schema=False`：藏起来，但还能调

```
路径表里有 /internal/stats 吗: False
实际能调通吗: 200 {'qps': 0}
```

用于内部运维接口（不想让前端看见、但网关要能打）。**注意它不是权限控制**——只是从文档里消失，谁猜到路径都能调。真要保护得靠鉴权/网络层。

### 3.6 自定义 `openapi()`：加 servers、安全声明、公司统一字段

```python
base_openapi = app.openapi          # ① 必须先把原方法存下来

def custom_openapi() -> dict:
    if app.openapi_schema:           # ② 命中缓存直接返回
        return app.openapi_schema
    schema = base_openapi()          # ③ 用存下来的原方法，不能写 app.openapi()
    schema.setdefault("servers", []).append({"url": "https://api.example.com"})
    app.openapi_schema = schema      # ④ 写回缓存
    return schema

app.openapi = custom_openapi
```

**①③ 是今天第二个坑，而且是最凶的一个**：`app.openapi = custom_openapi` 之后，`app.openapi()` 已经是**你自己**了。函数体里再写 `app.openapi()` → 无限自我调用。本机实测：

```
RecursionError: maximum recursion depth exceeded
  File ".../D5-探针-OpenAPI与BackgroundTasks.py", line 130, in custom_openapi
    schema = app2.openapi()
  [Previous line repeated 966 more times]
```

它不报"命名冲突"，只报 966 层递归——第一次遇到根本想不到原因。规则一句话：**替换一个方法之前，先把原方法存成变量**。

缓存语义要分清（实测）：

```
custom 函数被调用 3 次（3 次请求）
schema 真正构建 1 次
自定义字段生效: kb-service
```

- `custom_openapi` **每次请求 `/openapi.json` 都被调用**（它是路由处理函数）；
- 真正的构建（遍历所有路由、生成 JSON Schema）**只发生 1 次**，之后走 `app.openapi_schema` 缓存。

**推论（写代码时最容易踩）**：你在 `custom_openapi` 里改了 `app.openapi_schema` 之后，**开发模式改了路由也不会自动重建**——得先 `app.openapi_schema = None`。FastAPI 在 `--reload` 重启进程时自然清掉，但同一进程里动态加路由时不会。

### 3.7 生产环境关文档

```python
app = FastAPI(
    docs_url="/docs" if settings.env != "prod" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.env != "prod" else None,
)
```

实测三个都设 `None` 后：`docs: 404 | openapi: 404`。

**只关 `docs_url` 是假关门**：`/openapi.json` 还在，任何人直接读 JSON 就能拿到全量接口清单。要关就三个一起关，或者根本不配网关白名单。

### 3.8 `FastAPI()` 构造参数速查（本项目用得到的）

| 参数 | 作用 | 本项目怎么用 |
|---|---|---|
| `title` / `version` | `info` 段 | `settings.app_name` / `"0.1.0"` |
| `description` | 文档首页大段说明（支持 Markdown） | 建议补：一句话说清服务是干什么的 |
| `openapi_tags` | 分组说明 + 顺序 | D5 任务 1 |
| `docs_url` / `redoc_url` / `openapi_url` | 三个文档入口 | prod 全 `None` |
| `servers` | 环境地址下拉 | 或走自定义 openapi |
| `contact` / `license_info` | 团队/协议 | 内部服务可省 |
| `root_path` | 网关前缀（`/api` 这类剥离场景） | 反代时用 |
| `openapi_url=None` | 连 JSON 都不生成 | 内部服务 |

## 四、`BackgroundTasks` 机制

### 4.1 源码只有 36 行（Starlette 1.9.0，全文实测抓取）

```python
class BackgroundTask:
    def __init__(self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.is_async = is_async_callable(func)   # ① 构造时就判断同步/异步

    async def __call__(self) -> None:
        if self.is_async:
            await self.func(*self.args, **self.kwargs)
        else:
            await run_in_threadpool(self.func, *self.args, **self.kwargs)   # ② 同步进线程池


class BackgroundTasks(BackgroundTask):
    def __init__(self, tasks: Sequence[BackgroundTask] | None = None):
        self.tasks = list(tasks) if tasks else []

    def add_task(self, func, *args, **kwargs) -> None:
        task = BackgroundTask(func, *args, **kwargs)
        self.tasks.append(task)

    async def __call__(self) -> None:
        for task in self.tasks:      # ③ 顺序执行，不是并发
            await task()
```

三个结论直接读出来：

1. **它只是个袋子**。`BackgroundTasks` 不调度、不排队、不重试，就是 `list[BackgroundTask]` + 一个 `for await`。
2. **判断同步/异步发生在 `add_task` 那一刻**（构造 `BackgroundTask` 时），不是执行时——所以传进去的必须是**函数对象**，不能是协程对象（`add_task(job())` 是错的，`job()` 当场就跑完了）。
3. **`run_in_threadpool`** 是同步函数的安全通道：不堵事件循环，但受线程池上限约束（默认 40 线程）。

### 4.2 时序：响应先发，任务后跑（带时间戳实测）

探针二在纯 ASGI 中间件里给 `http.response.body` 打时间戳：

```
handler 返回前  +   0.00 ms
body 已发送     +   0.44 ms     ★ 客户端这一刻已经拿到完整响应
任务启动         +   1.20 ms
任务结束         +  51.28 ms
```

**这是本日最该记住的一张表**。它证明了两件事：

- 任务启动在 body 发出**之后**（0.44 vs 1.20）——所以"响应慢"绝不是后台任务导致的（除非它堵了事件循环，见 4.3）；
- 任务结束在 51ms，但客户端的响应在 0.44ms 就已经完整了。

源码位置对应：`Response.__call__` 里 `await send(...)` 发完 body 之后才 `if self.background is not None: await self.background()`。**`background` 是挂在 Response 对象上的属性**，这也是"handler 抛异常任务就不跑"的原因（见 4.6）。

### 4.3 同步任务进线程池，异步任务回事件循环

```
同步任务的线程: ['线程名=AnyIO worker thread']
```

实测线程名 `AnyIO worker thread` 证明：`def job()` 被 `run_in_threadpool` 丢进 worker 线程执行，不占事件循环。

**推论（重要）**：`async def job()` 里**绝不能**写 `time.sleep()`——它跑在事件循环上，会堵住**所有**请求。同步任务可以随便 `sleep`（占一个线程），异步任务必须用 `await asyncio.sleep()`。

### 4.4 顺序执行，不并行

```
事件顺序: ['handler 返回', 'sync start', 'sync end', 'async start(async)', 'async end(async)']
```

`for task in self.tasks: await task()` —— 前一个跑完才跑下一个。**想并行得自己 `asyncio.gather` 或开线程**，`BackgroundTasks` 不提供。

顺序与 `add_task` 的调用顺序**一致**（FIFO），这也是它比"裸线程"好的地方之一：可预测。

### 4.5 任务抛异常：响应已发，客户端一无所知

```
客户端看到的状态码: 200 body: {'ok': '响应先发出'}
→ 响应已发出，异常发生在发送之后：客户端无法得知，只在服务端日志里留 traceback。

raise_server_exceptions=True（TestClient 默认）会直接抛出: 后台任务炸了
```

三层含义：

1. **客户端视角**：200 已到手，任务失败它不知道——所以"上传成功但没索引"这类问题，必须靠**任务自身的状态/日志/对账**暴露，不能靠 HTTP 状态码。
2. **服务端视角**：异常进日志（`ServerErrorMiddleware` 不在链上了，此时是 uvicorn 的错误日志/异常处理器），但**不会**变成 500。
3. **测试视角**：`TestClient` 默认会把异常抛给你（`raise_server_exceptions=True`）；要模拟真实行为得 `TestClient(app, raise_server_exceptions=False)`——这条直接影响你怎么写测试（见任务单）。

### 4.6 handler 抛异常 → 已注册的任务不跑

```
响应: 400 {'error': 'handled'} | 任务执行记录: （空）——没跑
```

原因在 4.2 结尾：任务挂在**handler 返回的那个 Response 对象**上。handler 抛异常后，响应是 `exception_handler` **新建**的 `JSONResponse`，那个对象上没有 `background` 属性 → 任务丢失。

**这条对业务有真实影响**：如果你在 handler 里先 `add_task(发通知)` 再抛业务异常，通知**不会**发。要"失败也通知"，得在异常路径里也 `add_task`，或者干脆用真正的任务队列。

### 4.7 依赖里也能注入同一个 `BackgroundTasks`

```
依赖里加的任务执行了吗: ['来自依赖']
```

在 `Depends` 函数里 `background_tasks.add_task(...)`，任务同样会跑——因为**同一次请求内 `BackgroundTasks` 是同一个实例**（FastAPI 的特殊依赖，按请求缓存）。这让"横切逻辑"（审计日志、指标上报）可以放进依赖，而不是每个 handler 都写一遍。

### 4.8 204 + 后台任务**可以**共存（和 `response_model` 相反）

```
状态码: 204 | 响应体: b'' | 任务执行: ['204 之后']
```

对照 D4 的铁律：**204 与任何 `response_model` 互斥（启动即 AssertionError）**，但 `204` + `background_tasks` 完全合法——因为后者根本不参与响应体构造。同一条时间轴，一个在 body 之前（校验），一个在 body 之后（副作用）。

### 4.9 中间件记的耗时**不含**后台任务

```
[中间件] call_next 前后耗时 = 1.13 ms（任务里 sleep 300ms）
[客户端] 总耗时 = 305.17 ms
```

两个数字差 300ms，各自都对，含义完全不同：

- **中间件 1.13ms**：`call_next` 返回时 body 已发完、任务还没跑（或刚起步）。所以**你的 `request` 日志里的耗时不含后台任务**——后台任务慢不会让 request 耗时变难看，但也意味着"接口很快"不代表"事办完了"。
- **客户端 305ms**：这是 `TestClient` 的行为——它等**整个 ASGI 调用周期**结束才返回（含任务）。真实 uvicorn 下客户端在 body 收到时就返回了，不会等这 300ms。**测试里的耗时不能直接当线上耗时看**。

### 4.10 `BackgroundTasks` vs 其他三种"异步干活"

| 方案 | 谁执行 | 响应影响 | 可靠性 | 适用 |
|---|---|---|---|---|
| `BackgroundTasks` | 框架，响应后顺序执行 | 无（不堵响应） | 进程崩/重启即丢，无重试 | 发通知、写审计、更新缓存、轻量索引 |
| `asyncio.create_task` | 事件循环 | 无 | 同上，且异常易被静默吞 | 不推荐（难以观测） |
| 线程/进程池 | 自己 | 无 | 无持久化 | 短时 CPU/IO，需自己管并发 |
| 消息队列（Celery/RQ/Kafka） | 独立 worker | 无 | 有持久化、重试、死信 | 长任务、必须成功、要削峰 |

**面试一句话**：`BackgroundTasks` 是"响应之后的尽力而为"，不是任务队列——它保证"不拖慢响应"，不保证"一定成功"。

## 五、易错点表（D5）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | `openapi_tags` 名字拼错 | 零症状，`/docs` 出现空分组 + 无说明分组 | 用常量统一定义 tag 名，路由和 tags 表引用同一常量 |
| 2 | 函数体里 `app.openapi()` | `RecursionError` 966 层 | 先 `base = app.openapi` 存原方法 |
| 3 | 以为改路由文档会立即生效 | 同一进程里旧文档不变 | `app.openapi_schema = None` 清缓存 |
| 4 | 只关 `docs_url= None` | `/openapi.json` 仍暴露全量接口 | 三个入口一起关 |
| 5 | 以为 `responses=` 会改行为 | 文档写了 401，实际不返回 401 | 它只写文档；行为在 handler |
| 6 | `add_task(job())` 传了调用结果 | 任务在 `add_task` 那行就同步跑完 | 传函数对象 + 参数：`add_task(job, x)` |
| 7 | `async def` 任务里 `time.sleep` | 全体请求卡住 | 用 `await asyncio.sleep`，或写成同步函数进线程池 |
| 8 | 以为后台任务异常会 500 | 客户端拿到 200 | 任务状态自己记；用 `raise_server_exceptions=False` 写测试 |
| 9 | handler 抛异常还指望任务跑 | 任务静默丢失 | 异常路径也 `add_task`，或用队列 |
| 10 | 拿 TestClient 耗时当线上耗时 | 数字偏大（含任务） | 线上耗时看中间件/访问日志（不含任务） |

## 六、命令速查

```powershell
# Windows PowerShell（kb-service 下）==================================
# 看当前 openapi 的 tags 与路径
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; s=app.openapi(); print(json.dumps({'tags':s.get('tags'),'paths':list(s['paths'])}, ensure_ascii=False, indent=2))"

# 只看某个接口的文档片段
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; print(json.dumps(app.openapi()['paths']['/api/v1/kbs'], ensure_ascii=False, indent=2)[:1500])"

# 跑两个探针
& .\.venv\Scripts\python.exe ..\progress\week6\D5-探针-OpenAPI与BackgroundTasks.py
& .\.venv\Scripts\python.exe ..\progress\week6\D5-探针2-时序与文档化.py

# 起服务看 /docs（另开终端）
& .\.venv\Scripts\python.exe -m uvicorn kb_service.main:app --reload --port 8000
```

```bash
# Git Bash / Linux / macOS ============================================
./.venv/Scripts/python.exe -c "from kb_service.main import app; print(list(app.openapi()['paths']))"   # Windows Git Bash
.venv/bin/python -c "from kb_service.main import app; print(list(app.openapi()['paths']))"            # Linux/macOS
```

## 七、动手实验（每题**先在纸上写答案**，再跑，猜错才值钱）

**实验 1**：把 `openapi_tags` 里 `"documents"` 改成 `"document"`（少个 s），路由不动。`/docs` 会长什么样？跑 `app.openapi()["tags"]` 看结果，并回答：**有没有任何测试会挂？**

**实验 2**：在 `custom_openapi` 里把 `base_openapi()` 改回 `app.openapi()`，把递归深度限制调低（`sys.setrecursionlimit(60)`）让报错快点出来。你看到的第一行 traceback 指向哪个文件？

**实验 3**：写一个 `async def` 后台任务，里面 `time.sleep(1)`，同时开两个并发请求打不同接口，量一下第二个请求的耗时。再换成同步 `def` 版本对比。结论写一句话。

**实验 4**：把某个接口的 `responses={404: {...}}` 写上，然后用 `client.get` 打一个不存在的 id，看实际返回的**响应体形状**和文档里写的是否一致。如果不一致，是文档错了还是实现错了？

## 八、面试问法

### 8.1 高频题 30 秒版

**Q：FastAPI 的 `BackgroundTasks` 是怎么工作的？适合什么场景？**

> 它把任务挂在响应对象上，框架在响应**发出去之后**按 `add_task` 顺序依次执行；同步函数自动扔进线程池，不堵事件循环。所以它保证"不拖慢响应"，但**不保证成功**——进程重启就丢、异常只进日志、客户端完全不知道。适合发通知、写审计、刷新缓存这类"尽力而为"的副作用；长任务或必须成功的用消息队列。

**Q：为什么后台任务的异常不会让接口返回 500？**

> 因为执行时响应已经发出去了——HTTP 状态码和响应体早就在客户端手里，协议上没有任何机制能"撤回"。异常只能落进服务端日志。这也意味着后台任务失败必须靠自己的状态记录/对账暴露，不能指望 HTTP 层。

**Q：OpenAPI 文档是运行时生成的吗？能不能改？**

> 是。应用启动时把路由表翻译成 OpenAPI JSON，`/docs` 只是它的渲染器。定制有三种粒度：构造参数（title/version/tags）、路由装饰器（summary/description/responses/deprecated）、替换 `app.openapi`（加 servers、统一字段）。注意 `app.openapi_schema` 有缓存，替换方法前要先存下原方法，否则自己调自己会无限递归。

### 8.2 追问链（三层递进）

**第一层（机制）**：`BackgroundTasks` 凭什么知道什么时候跑？

> 因为它不是"全局后台线程"，而是**响应对象的属性**：`Response.__call__` 里 `await send(body)` 之后才 `await self.background()`。FastAPI 在构造响应时把注入的 `BackgroundTasks` 实例挂到 `response.background` 上——所以是"跟着这次响应走"，不是"跟着进程走"。同一请求内多个依赖拿到的 `BackgroundTasks` 是同一个实例（按请求缓存），所以依赖里 `add_task` 也生效。

**第二层（边界/故障）**：这套机制在哪些情况下会失手？

> 四条，沿时间轴排：① **响应没发成**（handler 抛异常，响应被异常处理器重建，`background` 没了 → 任务丢失）；② **进程在任务执行前退出**（部署重启、OOM，任务无持久化 → 直接丢）；③ **同步任务塞满线程池**（默认 40 线程，全部阻塞 → 新任务排队，响应不受影响但任务延迟飙高）；④ **`async def` 任务里有同步阻塞调用**（`time.sleep`、同步 DB 驱动 → 堵死事件循环，所有请求一起卡）。这四条的共同点：**它们都不出现在 HTTP 状态码里**。

**第三层（场景落地）**：如果文档上传后要向量化，耗时 10 秒且必须成功，你怎么设计？

> 不能用 `BackgroundTasks`——它不保证成功。设计：① 上传接口只做"存文件 + 建 doc 记录（status=pending）"，立刻 202 返回 doc_id；② 投一条消息进队列（Redis Stream / Celery / Kafka），worker 消费做切块+向量化；③ worker 完成后把 `status` 改 `ready`，失败重试 N 次后 `failed` 并记原因；④ 前端轮询或 SSE 拿状态。`BackgroundTasks` 只留给"失败也无所谓"的活（更新热度、打点）。**判断标准不是"要不要异步"，是"失败能不能接受"。**

## 九、闭卷自测（先答，再展开）

<details>
<summary>1. `openapi_tags` 里写错一个 tag 名，谁会报错？</summary>

没人报错。声明了但没路由用 → tags 里出现一个空分组；路由用了但没声明 → 自动出现、无 description、排最后。只有人打开 `/docs` 才看得出。

</details>

<details>
<summary>2. 自定义 `openapi()` 为什么要先 `base = app.openapi`？</summary>

因为赋值后 `app.openapi` 已指向 `custom_openapi` 自己，函数体里再调它就是无限递归（实测 966 层 `RecursionError`）。先把原方法存成变量，才能拿到框架原始构建逻辑。

</details>

<details>
<summary>3. 后台任务的时序，用一句话说清（含谁先谁后）。</summary>

handler 返回 → `response_model` 校验 → body 发出（客户端此刻已拿到响应）→ 后台任务按 `add_task` 顺序依次执行 → 中间件收尾。实测时间戳：body 0.44ms、任务启动 1.20ms。

</details>

<details>
<summary>4. 后台任务抛异常，客户端看到什么？</summary>

完整的成功响应（如 200 + body），什么异常都看不到。异常只进服务端日志。测试里 `TestClient` 默认会把它抛给测试代码（`raise_server_exceptions=True`）。

</details>

<details>
<summary>5. 为什么 handler 抛异常后，之前 `add_task` 的任务不执行？</summary>

任务挂在 **handler 返回的那个 Response 对象**上。handler 抛异常 → 响应由 `exception_handler` 新建 → 新对象没有 `background` 属性 → 任务丢失。

</details>

<details>
<summary>6. 中间件记的接口耗时包含后台任务吗？为什么？</summary>

不包含。`call_next` 返回时 body 已发完、任务刚开始或还没开始（实测 1.13ms vs 任务 300ms）。但 `TestClient` 的耗时**包含**任务（它等整个 ASGI 周期，305ms）——所以测试耗时不能当线上耗时。

</details>

<details>
<summary>7. `add_task(job())` 和 `add_task(job)` 差在哪？</summary>

前者传的是**调用结果**（`None`）：`job()` 在那一行就同步执行完了，`add_task` 收到 `None` 会在执行时炸（`NoneType is not callable`）。后者传函数对象，由框架决定何时执行。参数要一起传：`add_task(job, arg1, key=val)`。

</details>

<details>
<summary>8. 生产环境怎么"关掉文档"才算真关？</summary>

`docs_url`、`redoc_url`、`openapi_url` 三个都设 `None`。只关 `/docs` 的话，`/openapi.json` 仍返回全量接口清单（实测三个全关后都是 404）。

</details>

## 十、今日任务单（4h 主线 + 35min 日课）

### 主线任务（今天只做一个，做透）

**任务 1：OpenAPI 定制落地**

1. `main.py` 加 `openapi_tags`（三个分组：`knowledge-bases` / `documents` / `chat`），说明写清各自管什么；tag 名用**常量**定义（避免 §五 坑 1）。
2. `FastAPI(...)` 补 `description`（一句话说清服务是什么）+ 生产环境三个文档入口全关（现在是只关了 `redoc_url`）。
3. 挑 `create_kb` 补 `summary` / `description` / `response_description`，`responses={401: {"model": ApiResponse, ...}}`。
4. 用 `app.openapi()` 打出来的 JSON 验证四处改动（不看 `/docs`，看 JSON——那是唯一权威）。

**任务 2（任务 1 门禁绿后再做）：`BackgroundTasks` 落地**

`POST /kbs/{kb_id}/documents` 创建成功后，后台跑一个"模拟索引"任务（写日志 + 打一个模块级计数器即可，不引入新依赖）。要求：同步函数（走线程池）、记录 doc_id、异常必须被捕获后记 error 日志（否则只进 uvicorn 日志）。

### 日课（35 分钟，先清逾期）

| 项 | 今天做什么 | 判据 |
|---|---|---|
| 算法 20m | **LC 15 三数之和**（双指针，接 LC 11） | 真敲、提交通过、说清复杂度 + 为什么排序后能去重（不加 AI、不看题解超 15 分钟） |
| 八股 5m | 新条目 `response_model 是出口校验器` 30 秒版复述（昨天 +1 到期） | 不看稿一口气说完 ≤3 句 |
| 面试 5m | 同条目追问一层：为什么它"只验不包"？ | 答到机制层（`serialize_response` 拿返回值校验，不构造） |

### 今日纸笔靶（三行，别省）

1. **画**：§零 那张时间轴（五段：校验 → handler → 校验序列化 → body 发出 → 后台任务），在"body 发出"处画一条竖线，左边标"契约"、右边标"尽力而为"。
2. **写**（闭卷三句）：① `BackgroundTasks` 什么时候跑、跑了客户端知道吗；② 为什么 `add_task` 的任务在 handler 抛异常后不跑；③ 自定义 `openapi()` 为什么必须先存原方法。
3. **手写**（10 分钟）：`BackgroundTask` 类骨架（`__init__` 存 func/args/kwargs + `is_async`；`__call__` 里 async 走 await、sync 走 `run_in_threadpool`）——就 12 行，白板靶。
