# W6-D5b 教材 · `BackgroundTasks`（只讲一件事）

> 本篇只有一个主语：**一次请求**。它从进来到结束，后台任务被插在哪个位置、为什么插在那里、插在那里会带来什么后果。
> 全部断言本机实测（Starlette 1.9.0 / FastAPI 0.150.0 / Python 3.11）。读法：§一 先跑，看见顺序再往下。

## 零、主线：一次请求的五段

```
① 解析参数 / 校验        错了 → 422，请求到此为止
② handler 跑业务          ← 你写的代码到这里结束
③ 序列化 / 校验出参      错了 → 500
④ body 发出去          ★ 客户端的活干完了
⑤ 后台任务按顺序执行      ★ 这一刻起，出什么事客户端都不知道
```

**后台任务被插在 ④ 之后**，这是全部结论的源头：它慢不拖响应、它错不影响状态码、handler 在 ② 就炸的话它根本不存在。

一句话记住：**后台任务是"客户走了以后的事"，不是"客户等着的事"。**

## 一、先看见它（10 行，跑一次就懂）

存成 `bg_demo.py`，跑：

```python
import time
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
log: list[str] = []

def job(name: str) -> None:                      # 普通同步函数
    log.append(f"{name} 开始")
    time.sleep(0.2)
    log.append(f"{name} 结束")

@app.get("/bg")
def bg(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(job, "任务A")       # 只登记，不执行
    log.append("handler 返回")
    return {"ok": "1"}

print(TestClient(app).get("/bg").json())         # 响应体
print(log)                                        # 事件顺序
```

实测输出：

```
{'ok': '1'}
['handler 返回', '任务A 开始', '任务A 结束']
```

**先猜再往下看**：为什么 `handler 返回` 排第一？客户端拿到 `{'ok':'1'}` 的时候，任务是已经跑完了、还是还没开始？

再跑第二个（证明"慢任务不拖响应"）：

```python
@app.get("/bg2")
def bg2(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(job, "只在这里跑")
    # 注意：handler 里写 job(...) 是同步执行；add_task 只是登记
    return {"ok": "1"}
```

把 `/bg2` 换成"任务 sleep 3 秒"，会发现：**`TestClient` 的耗时是 3 秒多，但真实 uvicorn 下客户端在几毫秒内就拿到响应了**——因为 `TestClient` 等的是整个 ASGI 调用周期（含任务），不是"客户端收到响应"。这条差别后面 §四.4 会讲透。

## 二、银行柜台类比（把 §零 那张图变成画面）

| 时间轴上的位置 | 银行里的对应 |
|---|---|
| ② handler | 柜员给你办业务 |
| ④ body 发出 | **你拿着回单走出大门** |
| ⑤ 后台任务 | 柜员往"待办筐"里放的条子，你走后由后台同事按顺序处理 |
| ③ 出参校验失败 → 500 | 回单打印出错，业务没办成（你还在柜台） |
| ② handler 抛异常 | 业务中途失败，回单作废——**作废的回单上的条子也就没了** |
| 任务抛异常 | 后台同事处理条子时出错，**你已经走了，没人通知你** |

三条推论直接从类比里掉出来：

1. 条子挂在**这一次业务的回单**上，不是挂在"银行"上 → 回单换了（异常处理器新建响应），条子丢了。
2. 后台同事一次处理一张条子（顺序），不是同时开十个人。
3. 你收不到"条子办砸了"的消息 → 失败必须靠**事后对账**（查状态、看日志），不能靠 HTTP。

## 三、它是怎么做到的：36 行源码

用上之后再回头看实现，才看得懂。Starlette 的 `background.py` 全文只有 36 行：

```python
class BackgroundTask:
    def __init__(self, func, *args, **kwargs) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.is_async = is_async_callable(func)     # ① 登记时就判断同步还是异步

    async def __call__(self) -> None:
        if self.is_async:
            await self.func(*self.args, **self.kwargs)
        else:
            await run_in_threadpool(self.func, *self.args, **self.kwargs)   # ② 同步进线程池


class BackgroundTasks(BackgroundTask):
    def __init__(self, tasks=None):
        self.tasks = list(tasks) if tasks else []

    def add_task(self, func, *args, **kwargs) -> None:
        task = BackgroundTask(func, *args, **kwargs)   # ③ add_task 只是"造一张条子"塞进列表
        self.tasks.append(task)

    async def __call__(self) -> None:
        for task in self.tasks:                        # ④ 顺序执行，一个跑完再下一个
            await task()
```

四个结论：

1. **它就是个袋子**：`list[BackgroundTask]` + 一个 `for await`。不排队、不重试、不持久化。
2. **①③ 说明 `add_task` 只登记、不执行**——所以 `add_task(job, "A")` 传的是**函数对象 + 参数**。写成 `add_task(job("A"))` 会让 `job` 当场同步跑完，然后把 `None` 塞进袋子，执行时报 `NoneType is not callable`。
3. **② 同步函数走线程池**（实测线程名 `AnyIO worker thread`）：不堵事件循环，但受线程池上限（默认 40）约束。
4. **④ 顺序执行**：实测 `['任务A 开始', '任务A 结束', '任务B 开始', ...]`——前一个跑完才下一个，与 `add_task` 顺序一致。

**它挂在响应对象上**——这是"什么时候跑"的最后一块拼图。`Response.__call__` 里的顺序是：先 `send`（发 body），再 `if self.background: await self.background()`。所以时间戳实测出来是：

```
handler 返回前  +  0.00 ms
body 已发送     +  0.44 ms     ★ 客户端这一刻已经拿到完整响应
任务启动         +  1.20 ms
任务结束         + 51.28 ms
```

## 四、六个必须知道的边界（都实测过）

### 4.1 任务抛异常：客户端永远不知道

```
客户端看到的状态码: 200 body: {'ok': '响应先发出'}
```

任务在 body 发出后才跑，HTTP 协议里没有任何机制能"撤回一个已经发出的响应"。所以：

- **客户端**：拿到 200，任务失败它不知道；
- **服务端**：异常进日志（这时的 uvicorn 错误日志，不是你的 `request` 日志）；
- **测试**：`TestClient` 默认 `raise_server_exceptions=True`，会把异常直接抛给测试代码。要测真实行为用 `TestClient(app, raise_server_exceptions=False)`。

**业务含义**：后台任务失败必须靠"任务自己记状态/对账"暴露，不能指望状态码。

### 4.2 handler 抛异常 → 已登记的任务不执行

```
响应: 400 {'error': 'handled'} | 任务执行记录: （空）——没跑
```

原因在 §三 结尾：任务挂在 **handler 返回的那个 Response 对象**上。handler 抛异常后，响应由 `exception_handler` **新建**，新对象上没有 `background` → 任务丢失。

**真实影响**：`add_task(发通知)` 之后再抛业务异常，通知不会发。要"失败也通知"，得在异常路径里再 `add_task`，或者用任务队列。

### 4.3 依赖里也能登记任务

```
依赖里加的任务执行了吗: ['来自依赖']
```

同一次请求内 `BackgroundTasks` 是**同一个实例**（FastAPI 按请求缓存），所以在 `Depends` 函数里 `add_task` 同样生效。这让审计日志、指标上报这类横切逻辑可以放进依赖，不用每个 handler 写一遍。

### 4.4 中间件的耗时**不含**后台任务

```
[中间件] call_next 前后耗时 = 1.13 ms（任务里 sleep 300ms）
[客户端] 总耗时 = 305.17 ms
```

两个数字都对，含义完全不同：

- **中间件 1.13ms** = 接口本身的耗时，**不含**任务。所以你的 `request` 日志里"接口很快"不代表"事办完了"。
- **305ms** = `TestClient` 等整个 ASGI 周期（含任务）。真实 uvicorn 下客户端在 body 收到时就返回，不会等这 300ms。**测试耗时 ≠ 线上耗时。**

### 4.5 `async def` 任务里绝不能写同步阻塞

```python
async def bad() -> None:
    time.sleep(1)      # ❌ 堵死事件循环，所有请求一起卡
```

同步函数（`def`）走线程池，随便 sleep；异步函数（`async def`）跑在事件循环上，必须 `await asyncio.sleep()`。判断标准：**你写的是 `def` 还是 `async def`**。

### 4.6 204 可以和它共存（和 `response_model` 相反）

```
状态码: 204 | 响应体: b'' | 任务执行: ['204 之后']
```

对照 D4 的铁律：**204 与任何 `response_model` 互斥（启动即 AssertionError）**，但 204 + 后台任务完全合法——因为后台任务根本不参与响应体构造。一个在 body 之前（校验），一个在 body 之后（副作用）。

## 五、什么时候**不该**用它（第三层追问的素材）

| 方案 | 谁执行 | 可靠性 | 适用 |
|---|---|---|---|
| `BackgroundTasks` | 框架，响应后顺序执行 | 进程崩/重启即丢，无重试 | 发通知、写审计、刷缓存、轻量索引 |
| `asyncio.create_task` | 事件循环 | 同上，异常易被静默吞 | 不推荐（难观测） |
| 线程/进程池 | 自己 | 无持久化 | 短时 CPU/IO，需自己管并发 |
| 消息队列（Celery / RQ / Kafka） | 独立 worker | 持久化、重试、死信 | 长任务、必须成功、要削峰 |

**判断标准不是"要不要异步"，是"失败能不能接受"**。文档向量化 10 秒必须成功 → 队列；更新热度、打个点 → `BackgroundTasks`。

## 六、易错点表

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | `add_task(job())` 传了调用结果 | 任务当场同步跑完，执行时报 `NoneType is not callable` | `add_task(job, 参数)` |
| 2 | `async def` 任务里 `time.sleep` | 所有请求一起卡住 | `await asyncio.sleep`，或写成 `def` 进线程池 |
| 3 | 以为任务异常会 500 | 客户端拿到 200 | 任务状态自己记；测试用 `raise_server_exceptions=False` |
| 4 | handler 抛异常还指望任务跑 | 任务静默丢失 | 异常路径也 `add_task`，或用队列 |
| 5 | 把 `TestClient` 耗时当线上耗时 | 数字偏大（含任务） | 线上看中间件/访问日志（不含任务） |
| 6 | 以为任务并行执行 | 一个慢任务拖住后面所有任务 | `for await` 是顺序的；要并行自己 `gather` |
| 7 | 用它在请求里等结果 | 拿不到（返回值被丢弃） | 要结果就不是后台任务，别用它 |

## 七、闭卷自测（先答，再展开）

<details>
<summary>1. 用一句话说清它什么时候跑。</summary>

响应 body 发出去之后。实测时间戳：body 0.44ms、任务启动 1.20ms——客户端那一刻已经拿到完整响应了。

</details>

<details>
<summary>2. 它会不会拖慢接口？什么情况下会？</summary>

正常不会（同步函数进线程池）。会拖慢只有一种常见情况：`async def` 任务里写了同步阻塞调用（`time.sleep`、同步 DB 驱动），把事件循环堵死，所有请求一起排队。

</details>

<details>
<summary>3. 任务失败了，客户端怎么知道？</summary>

不知道。响应早已发出，HTTP 没有"撤回"机制。失败只在服务端日志里，业务层要自己记状态、做对账。

</details>

<details>
<summary>4. 为什么 handler 抛异常后，任务不跑？</summary>

任务挂在 handler 返回的 Response 对象上；异常时响应由 `exception_handler` 新建，新对象没有 `background` 属性，任务丢失。

</details>

<details>
<summary>5. `add_task(job)` 和 `add_task(job())` 差在哪？</summary>

前者传函数对象（登记，之后执行）；后者传调用结果——`job()` 在那一行就同步跑完了，`add_task` 收到的是返回值（通常是 `None`），执行时报 `NoneType is not callable`。

</details>

<details>
<summary>6. 为什么测试里的耗时比线上大？</summary>

`TestClient` 等整个 ASGI 调用周期结束（含后台任务）才返回；真实 uvicorn 下客户端收到 body 就返回。实测：中间件 1.13ms，TestClient 305ms（任务 sleep 300ms）。

</details>

<details>
<summary>7. 什么情况下必须换成消息队列？</summary>

失败不能接受时（必须成功、要重试、要持久化）、任务时间长（几十秒以上）、要削峰、要多机分担。`BackgroundTasks` 是"尽力而为"，进程重启就丢。

</details>

## 八、今天下午的任务单（约 60 分钟，含第四档找坑）

**任务 2：给文档上传挂一个"模拟索引"后台任务**

位置：`POST /kbs/{kb_id}/documents`（`api/v1/documents.py`，`create_doc`）。

要求：

1. 用一个**同步函数** `fake_index(doc_id: UUID) -> None`（走线程池，能看见 `AnyIO worker thread` 的行为）：里面 `time.sleep(0.05)` 模拟耗时，然后 `logger.info("indexed doc %s", doc_id)`。
2. 在 `create_doc` 成功返回前 `background_tasks.add_task(fake_index, doc.id)`。
3. **异常必须自己捕获**：`fake_index` 里 `try/except Exception: logger.exception(...)`——否则异常只进 uvicorn 日志，你的应用日志里什么都没有。
4. 加一条测试：调接口拿 201 后，断言"任务确实执行了"（模块级计数器或 `caplog` 查那条日志）。注意 `TestClient` 会等任务跑完，所以断言可以直接写在 `client.post(...)` 之后。

**交付方式**：我按第四档交付**埋坑版**（能跑、门禁绿、不提交，里面埋 3 个坑），你按"先说层 → 再说症状 → 最后点行"找出来；修完、门禁复绿才允许提交。

### 今日纸笔靶（三行，配这一份就够）

1. **画**：§零 五段生命线，在 ④ 处画竖线，左边写"客户在等"，右边写"客户走了"。
2. **写**（闭卷三句）：① 任务什么时候跑、失败客户端知道吗；② handler 抛异常任务为什么丢；③ 中间件耗时为什么不含任务。
3. **手写**（10 分钟）：`BackgroundTask` 类骨架——`__init__` 存 `func/args/kwargs/is_async`，`__call__` 里 async 走 `await`、sync 走 `run_in_threadpool`。12 行，白板靶。
