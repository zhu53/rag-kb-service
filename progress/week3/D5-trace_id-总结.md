# W3-D5 · trace_id 贯穿全链路【面试参考版】

> 日期：2026-10-26 ｜ 靶子：一个请求从"中间件"进来，到 repo 落盘，日志全带同一个 trace_id——**业务代码零感知**。
> 用法：§4 的两条"为什么"是高频考点；§7 追问链覆盖 asyncio 与分布式追踪。

---

## 1. 要解决的问题（先讲场景，面试开场用）

多请求并发时，日志是混在一起的行流：A 用户的"创建失败"和 B 用户的"创建成功"交错打印，**出错时无法把一次请求的所有日志串起来**。

解法：每个请求进门发一个**唯一身份证（trace_id）**，本次请求链路里的每条日志都自动带上它。排查时按 id 过滤，整条链路一次性还原。

### 面试问法："线上一个请求报错了，你怎么定位？"

**30 秒答案**："先拿 trace_id。每个请求进网关/中间件时生成一个 id 放进上下文，日志框架给每条日志自动盖上这个 id，链路里所有服务、所有层都带同一个值。报错时用户提供或从错误响应里拿到 id，按 id 过滤日志就能看到这次请求的完整路径：进了哪个接口、调了哪个下游、在哪一步卡住。如果跨服务，这个 id 会通过请求头透传下去，配合 OpenTelemetry 还能直接画出调用链。"

---

## 2. 三个方案对比（为什么不用前两个）

| 方案 | 做法 | 问题 |
|---|---|---|
| ① 逐层传参 | `def create_kb(owner_id, name, trace_id)` | **签名污染**：每层每个函数都要加参数，横切关注点入侵业务；漏传一层就断链 |
| ② `threading.local` | 线程本地存储 | 同步多线程 OK；**asyncio 下失效**——事件循环跑在单线程，所有协程共享同一份 local → 串号（W1 实测 9/10 串号） |
| ③ `contextvars.ContextVar` | 按执行上下文隔离 | 线程/Task 各自一份；`asyncio.create_task` 自动拷贝上下文；推荐 |

### 核心认知：trace_id 是横切关注点

它不属于任何一层的业务逻辑——不属于 API、不属于 service、不属于 repo。**横切关注点不能进业务签名**，否则每加一个（trace_id、用户身份、租户、语言）都要改全项目签名。

**验收红线**：`grep trace_id` 在 service/repo 里**零命中**。出现即污染。

---

## 3. 实现（今天的代码）

```python
# kb/tracing.py
import logging
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:8]


class TraceIdFilter(logging.Filter):
    """盖章员：给每条日志挂上当前上下文的 trace_id，永远放行。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()      # get() 的参数是缺省值，不是变量名！
        return True                                # 永不放行 = 静默丢日志


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(
        logging.Formatter("[%(trace_id)s] %(levelname)-7s %(name)s: %(message)s")
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)
```

**中间件模拟（Kbcli 里在 `__main__.py`）**：

```python
def handle_request(owner_id: str, name: str) -> None:
    token = trace_id_var.set(new_trace_id())   # ① 进门发 id，接住 Token
    try:
        svc.create_kb(owner_id, name)          # ② 业务照常跑，日志自动盖章
    finally:
        trace_id_var.reset(token)              # ③ 必须 finally：防上下文复用泄漏
```

**验收输出**：

```
INFO  [-]        kb.service: 创建知识库 name=没进请求的库 owner=carol     ← 裸调：默认值
INFO  [a7ac1088] kb.service: 创建知识库 name=线程1的库 owner=alice
INFO  [f03137d0] kb.service: 创建知识库 name=线程2的库 owner=bob           ← 零串号
```

---

## 4. 两个"为什么"（必背）

### 4.1 为什么 Filter 不能 `return False`

`Filter.filter()` 返回 `False` 的语义是**这条日志被静默丢弃**——不报错、不留痕。我第一版写成 `if trace_id == "-": return False`，等于"所有请求外的日志凭空消失"。

**Filter 是盖章员，不是保安。** `return False` 的正经用途是"屏蔽某个第三方库的刷屏日志"。

### 4.2 为什么 reset 必须在 finally

`set()` 返回一个 **Token（回程票）**，`reset(token)` 恢复 set 之前的值。不放 finally 的话，中途抛异常就跳过 reset，上下文里残留旧 id——线程池/协程池复用时，**下一个请求会读到上一个请求的 id**（串号），而且日志看起来"有 id"，非常难发现。

**和数据库连接、文件句柄一样：凡是"获取-使用-归还"的模式，归还必须在 finally。**

---

## 5. logging 的四个角色（面试常问结构）

```
Logger（按 __name__ 分层，logger = logging.getLogger(__name__)）
  └─ 日志记录 → 级别判断 → 传给 Handler
        Handler（决定输出到哪：Stream/File/RotatingFile/HTTP）
          ├─ Filter（决定放行与否，可顺手给 record 挂属性 ← 今天的用法）
          └─ Formatter（决定输出长相，%(trace_id)s 从这里取值）
```

- **Logger 有层级**：`kb.service` 的日志会向父 logger `kb` 冒泡，根 logger 兜底——所以只在根上配一次 handler，全项目都生效。
- **`__name__` 做 logger 名**：日志前缀自动带模块路径，一眼看出哪层打的。
- **惰性格式化**：`logger.info("name=%s", name)` 而不是 f-string——字符串拼接推迟到"确认要输出"时才做；级别过滤掉时省掉格式化开销。
- **没有 handler 时**：INFO 及以下直接蒸发（只有 WARNING+ 走 lastResort 打到 stderr）——今天 `setup_logging()` 没调用就是这个症状，日志全灭而不报错。

### 面试问法："logging 的 Logger/Handler/Filter/Formatter 分别干什么？"

**30 秒答案**："Logger 是入口，按名字分层（通常用 `__name__`），负责级别判断和向父级冒泡；Handler 决定日志去哪（控制台、文件、网络）；Filter 是每条日志的关卡，可以过滤也可以给记录挂额外字段——我用它给每条日志盖上当前上下文的 trace_id；Formatter 决定最终文本长相。四者串起来是：Logger 产生记录 → 各级 Filter 处理 → Handler 输出 → Formatter 格式化。"

---

## 6. ContextVar 机制（为什么它能隔离）

- `ContextVar` 是**按执行上下文**存储的：每个线程有自己的 Context，每个 asyncio Task 在创建时**拷贝**当前上下文——所以 Task 里 `set` 的值不会泄漏回父上下文，兄弟 Task 之间也互不可见。
- `set()` 返回 Token，`reset(token)` 精确回滚（支持嵌套 set 的栈式恢复）。
- `asyncio.create_task()` 默认 `context=copy_context()`，**上下文自动继承**——这是 trace_id 在异步代码里能自然传递的原因；但用 `run_in_executor` 丢进线程池时，需要手动 `contextvars.copy_context().run(fn)`。
- 坑：**别用它存大对象或可变状态做业务数据**，它是"隐式参数"，滥用会重演 D3 的"多副本/不可预测"问题。

---

## 7. 追问链（面试深挖预演）

| 起点 | 追问 | 你要能答 |
|---|---|---|
| 为什么不用 threading.local | asyncio 下为什么失效？ | 事件循环单线程，所有协程共享同一线程的 local → 串号 |
| ContextVar 怎么隔离 | Task 之间怎么不串？ | Task 创建时拷贝上下文；子 Task 的 set 不影响父和兄弟 |
| 线程池怎么办 | `run_in_executor` 里怎么带上下文？ | `copy_context().run(fn)` 或显式传参；默认不继承 |
| 跨服务怎么串 | id 怎么传下去？ | HTTP header（如 `X-Trace-Id`/W3C `traceparent`）透传，下游继续用同一个 id |
| 分布式追踪 | trace_id 和 span_id 什么关系？ | trace 是一次请求的全链路，span 是链路里的单段调用（有父子关系、耗时）；OpenTelemetry 用 traceparent 头携带 |
| 可观测性三件套 | 日志/指标/链路区别？ | 日志=离散事件（细节）、指标=聚合数值（趋势告警）、链路=调用拓扑（定位慢在哪一段） |
| 采样 | 全量 trace 太贵怎么办？ | 头部采样（入口决定，简单但可能漏异常）/ 尾部采样（按结果决定，保留错误链路） |

---

## 8. 今天的坑（复习重点）

| 坑 | 症状 | 教训 |
|---|---|---|
| `trace_var.get("trace")` | 上下文外的日志被盖字面量章 | `get()` 参数是**缺省值**不是变量名 |
| `if id == "-": return False` | 请求外日志凭空消失 | Filter 盖章不放行丢弃；`False` = 静默丢日志 |
| `record.trace_id` 读完忘挂 | 每条日志 `--- Logging error ---` | 读出来要挂回 record；Formatter 靠属性取值 |
| `set()` 漏参数 | TypeError | `set()` 必须传值 |
| `setup_logging()` 没调 | INFO 全灭（无 handler 时只有 WARNING+ 走 lastResort） | 日志基建要显式初始化，`force=True` 保证幂等 |
| `kb = self.get_kb(...)` 接了不用 | ruff F841 | 只要副作用就裸调 |
| `except Exception` 触发 BLE001 | — | 重试器兜一切异常是正当的 → `# noqa` 写理由 |

## 9. 30 秒答案集（考前速背）

1. **trace_id 是什么** → 一次请求的身份证，串起该请求的全部日志。
2. **为什么不传参** → 横切关注点不入侵业务签名。
3. **为什么不用 threading.local** → asyncio 单线程共享，会串号；ContextVar 按上下文隔离。
4. **谁给日志盖章** → Handler 上的 Filter（`record.trace_id = var.get(); return True`）。
5. **Token/reset 干嘛** → 恢复 set 前的值；必须 finally，防上下文复用泄漏。
6. **`return False` 什么后果** → 静默丢弃该条日志。
7. **跨服务怎么传** → 请求头透传（W3C traceparent），配合 OpenTelemetry 形成 span 树。

## 10. 闭卷自测

1. `Filter.filter()` 返回 `False` 会怎样？
2. `ContextVar.set()` 的返回值叫什么，干什么用？
3. 为什么 reset 必须放 finally？
4. 业务层代码里应该能 grep 到 `trace_id` 吗？为什么？
5. `asyncio.create_task` 会继承上下文吗？线程池呢？

<details><summary>答案</summary>
1. 该条日志被静默丢弃——不报错、不留痕。
2. Token（回程票），交给 `reset(token)` 恢复 set 之前的值。
3. 中途抛异常也要恢复现场，否则复用的下一请求会读到残留 id（串号）。
4. 不能。横切关注点由日志基础设施注入；出现即签名污染。
5. create_task 默认拷贝上下文（继承）；线程池（run_in_executor）默认不继承，需 `copy_context().run(fn)` 或显式传参。
</details>
