# W3-D5 教材：trace_id 贯穿全链路

> 靶子：kb-service 里"一个请求进来，middleware→service→repo 的日志全带同一个 trace_id"。
> W1-Day6 你抄改过 json_log.py（ContextVar + JsonFormatter）——**这次不抄改，自己从零搭**。

## 1. 问题：为什么需要 trace_id

服务器同时处理多个请求，日志是**混着流出来**的：

```
创建知识库 测试库
查询知识库 kb1
创建知识库 购物车      ← 哪行是谁的请求？没法定责
```

排查线上问题第一步永远是"把一次请求的所有日志捞出来"。做法：每个请求进门时发一个身份证（trace_id），本次请求打的每条日志都盖上这个章。

## 2. 三个候选方案（面试高频）

| 方案 | 做法 | 为什么不行/行 |
|------|------|--------------|
| A. 参数传递 | 每个函数都加 `trace_id` 参数 | **签名污染**：repo、工具函数全被迫改签名；业务逻辑被横切关注点入侵 |
| B. `threading.local` | 线程隔离的 storage | 同步线程没问题；但 **asyncio 里整个事件循环跑在一个线程上**，所有请求共享同一份 → 串号（W1 实测 9/10 串号） |
| C. `contextvars.ContextVar` ✅ | 按"上下文"隔离，线程和 Task 各有一份 | 官方为 async 设计；同步线程同样适用（一个线程=一个上下文） |

**核心认知：trace_id 是"横切关注点"**——它不属于任何一层业务逻辑，所以不该出现在任何业务函数签名里。

## 3. ContextVar 三要点

```python
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")

token = trace_id_var.set("abc123")   # set() 返回 Token（回程票）
trace_id_var.get()                   # 本上下文内读 → "abc123"
trace_id_var.reset(token)            # 恢复原值——防泄漏的保险
```

1. **隔离**：谁 set 只影响谁自己的上下文；别的线程/Task 看不见（default 值除外）。
2. **Token**：`set()` 的返回值是"回程票"。`reset(token)` 把值恢复成 set 之前的模样。
3. **为什么必须 reset**：线程池里线程是**复用**的。请求 A 用完不 reset，线程还回去接请求 B——B 还没 set 之前读到的就是 A 的残留 id。生产事故级 bug。

## 4. logging 注入链路（今天的魔术所在）

```
中间件: trace_id_var.set(new_trace_id())
   ↓
service / repo: logger.info("创建知识库 %s", name)     ← 全程不知道 trace_id 存在
   ↓
每条日志流出 handler 前: Filter.filter(record) 被调用
   → record.trace_id = trace_id_var.get()              ← 魔术在这里：日志记录上路前被盖章
   ↓
Formatter: "... [%(trace_id)s] %(message)s"            ← 盖好的章印到输出上
```

关键 API：

| API | 作用 | 注意 |
|-----|------|------|
| `logging.getLogger(__name__)` | 每模块一个 logger | 用 `__name__` 而不是 root，日志前缀能看出出处 |
| `logging.Filter.filter(record)` | 每条 record 过路检查 | 返回 `True`=放行，`False`=**丢弃这条日志**；顺手可以改 record 属性 |
| `record.trace_id = ...` | 给 record 动态挂属性 | Formatter 里就能用 `%(trace_id)s` 引用 |
| `logging.basicConfig(force=True)` | 幂等初始化 | 3.8+；不加 force，重复调用不生效（已有 handler 就跳过） |
| `logger.info("xx %s", val)` | 惰性格式化 | 传参数而不是 f-string：日志被过滤掉时不花格式化的钱 |

## 5. 任务书（三步）

### 第一步：`kb/tracing.py`（填空骨架）

```python
"""trace_id 上下文 + 日志注入。业务层只管 logger.info，盖章在这里自动完成。"""
import logging
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    """生成 8 位短 id。全链路唯一性够用，人眼好认。"""
    ...


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # ① 从 ContextVar 读出当前 trace_id，挂到 record.trace_id 上
        # ② 记得 return True（返回 False = 把这条日志扔掉！）
        ...


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(trace_id)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    handler.addFilter(TraceIdFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
```

### 第二步：业务层埋日志（零感知验收的靶子）

- `service.py`：模块头加 `logger = logging.getLogger(__name__)`；create_kb 成功后、get_kb 命中后、delete_kb 成功后各来一条 `logger.info`（用惰性格式化传参）。
- `json_repo.py`：`_save` 里来一条 debug/info。
- **红线：service / repo / memory_repo 里不许出现 `trace_id` 这个词**——grep 得到就算违章，因为业务层根本不该知道它的存在。

### 第三步：`kb/__main__.py` 并发实验

模拟中间件 + 两个线程并发请求：

```python
import threading
from kb.tracing import new_trace_id, trace_id_var

def handle_request(owner_id: str, name: str) -> None:
    """模拟 FastAPI 中间件：进门发 id，出门 reset。"""
    token = ________                    # set 新 id，接住 Token
    try:
        svc.create_kb(owner_id, name)   # 业务照常跑，日志自动盖章
    finally:
        ________                        # reset，防线程复用泄漏

t1 = threading.Thread(target=..., args=("alice", "线程1的库"))
t2 = threading.Thread(target=..., args=("bob", "线程2的库"))
```

## 6. 验收清单（四条硬性）

- [ ] `grep -r "trace_id" kb/service.py kb/memory_repo.py kb/json_repo.py` → **零命中**
- [ ] 两线程并发跑，日志交错流出，但**同一请求的行共享同一个 id，绝不串**
- [ ] 不在 handle_request 里直接调 svc（裸调一次），日志显示 `[--------]`（default 值）——证明"没进请求的日志拿不到 id"而不是拿错 id
- [ ] `python -m kb` 反复跑，输出稳定（basicConfig force 生效）

## 7. 易错点（出题人视角）

1. `filter()` 忘了 `return True` → 返回 None 被当 False → **所有日志凭空消失**，且无任何报错（"不炸但错"套餐）。
2. `reset()` 忘了放 `finally` → 中途抛异常就漏 reset → 线程池复用时串号。
3. Filter 只挂在 handler 上才生效——挂错到 logger 上，子 logger 的日志走的是 handler 的过滤器链，行为不一样。
4. `basicConfig` 不加 `force=True`，第二次运行 handler 已经存在，新 Formatter 静默不生效。

## 8. 面试问法

1. "异步服务里为什么不能用 threading.local 存请求上下文？" → 事件循环单线程，所有请求共享；ContextVar 按 Task 隔离（W9 异步周会实测）。
2. "trace_id 为什么不做成函数参数一层层传？" → 横切关注点不该入侵业务签名；这叫"基础设施与业务解耦"。
3. "logging.Filter 和 Formatter 各干什么？" → Filter 是每条日志的安检口（能放行/丢弃/顺手盖戳），Formatter 决定输出长相。

## 9. 闭卷自测（先答后翻）

1. `Filter.filter()` 返回 `False` 会发生什么？
2. `ContextVar.set()` 的返回值叫什么，干什么用？
3. 为什么 reset 必须放 finally？
4. 业务层（service/repo）的代码里应该能 grep 到 `trace_id` 吗？为什么？

<details>
<summary>答案</summary>

1. 这条日志被**静默丢弃**——不报错，日志直接消失，是"不炸但错"的典型。
2. Token（回程票），传给 `reset(token)` 把变量恢复成 set 之前的值。
3. 业务代码中途抛异常时也要恢复现场；否则复用该线程/上下文的下一个请求读到残留 id（串号）。
4. 不能。trace_id 是横切关注点，由日志基础设施（Filter）在日志流出处注入；业务层出现它 = 签名污染的同族病。
</details>
