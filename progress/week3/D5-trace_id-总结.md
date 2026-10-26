# W3-D5 总结：trace_id 贯穿全链路

> 日期：2026-10-26
> 靶子：一个请求从中间件进来到 repo 落盘，日志全带同一个 trace_id——**业务代码零感知**。

## 交付物

| 文件 | 内容 |
|------|------|
| `kb/tracing.py` | `trace_id_var`(ContextVar) + `new_trace_id()` + `TraceIdFilter` + `setup_logging()` |
| `kb/service.py` | 3 条 `logger.info`（create 查重后 / get 命中后 / delete 后），**不含 trace_id** |
| `kb/json_repo.py` | `_save` 写盘日志，**不含 trace_id** |
| `kb/__main__.py` | `handle_request` 模拟中间件（set → try/finally reset）+ 双线程并发 + 裸调对照 |
| `review_02_audit.py` | 第四档 #05 埋坑物（4 个静默坑） |

## 验收输出（关键三现象）

```
15:01:44 INFO  [-] kb.service: 创建知识库 name=没进请求的库 owner=carol      ← 裸调：默认值
15:01:44 INFO  [a7ac1088] kb.service: 创建知识库 name=线程1的库 owner=alice
15:01:44 INFO  [f03137d0] kb.service: 创建知识库 name=线程2的库 owner=bob      ← 零串号
```

四条硬验收：业务层 grep 零命中 ✓ / 并发各归各 ✓ / 裸调拿默认值 ✓ / 复跑稳定 ✓；ruff 全绿（7 文件统一排版）。

## 必须记住的四条

1. **trace_id 是横切关注点**——不属于任何一层业务逻辑，所以不该出现在任何业务函数签名里。参数传递方案 = 签名污染。
2. **ContextVar 而不是 threading.local**——`threading.local` 按线程隔离，但 asyncio 的事件循环跑在单线程上，所有请求共享一份 → 串号（W1 实测 9/10 串号，W9 会用真协程再验一遍）。
3. **Filter 是盖章员，不是保安**——`record.trace_id = var.get(); return True`。`return False` 的语义是**静默丢弃日志**（无报错），今天亲手写过一次这个 bug。
4. **Token + reset 是防泄漏保险**——`set()` 返回 Token，`reset(token)` 恢复原值；必须放 `finally`，否则线程池复用时下一个请求会读到残留 id。

## 今天踩过的坑

| 坑 | 症状 | 教训 |
|----|------|------|
| `trace_var.get("trace")` | 上下文外的日志被盖字面量章 | `get()` 参数是**缺省值**，不是变量名 |
| `if id == "-": return False` | 请求外日志凭空消失 | Filter 的职责是盖章，不是过滤；`False`=丢日志 |
| `record.trace_id` 忘挂 | 每条日志触发 `--- Logging error ---` | 读出来要挂上去；Formatter 靠 `%(trace_id)s` 取属性 |
| `trace_id_var.set()` 漏参数 | TypeError | `set()` 必须传值 |
| `setup_logging()` 没调 | INFO 日志全部蒸发（无 handler 时 lastResort 只管 WARNING+） | 日志基建必须显式初始化，`force=True` 保证幂等 |
| `kb = self.get_kb(...)` 接了不用 | ruff F841 | 复用只为副作用时直接裸调 |
| `except Exception` 被 BLE001 拦 | — | 重试器兜一切异常是正当的 → `# noqa` 且写明理由 |

## 第四档 #05 战报

`review_02_audit.py`：**4/4 全对**（`get()` 缺省值 / 注解 list / 缺 return / predicate 只返 True）。
→ 昨天的“静默坑雷达”缺口已补；**W1-Q12 欠分正式收回**。

## 面试三问

1. "异步服务里为什么不能用 threading.local 存请求上下文？" → 事件循环单线程，全请求共享；ContextVar 按上下文（线程/Task）隔离。
2. "trace_id 为什么不逐层传参？" → 横切关注点不入侵业务签名，基础设施与业务解耦。
3. "logging.Filter 和 Formatter 各干什么？" → Filter 是每条日志的安检口（放行/丢弃/顺手挂属性），Formatter 决定输出长相。

## 闭卷自测

1. `Filter.filter()` 返回 `False` 会怎样？
2. `ContextVar.set()` 的返回值叫什么，干什么用？
3. 为什么 reset 必须放 finally？
4. 业务层代码里应该能 grep 到 `trace_id` 吗？为什么？

<details>
<summary>答案</summary>

1. 这条日志被静默丢弃——不报错、不留痕。
2. Token（回程票），交给 `reset(token)` 恢复 set 之前的值。
3. 中途抛异常也要恢复现场，否则复用该上下文的下一请求读到残留 id（串号）。
4. 不能。横切关注点由日志基础设施注入；业务层出现它 = 签名污染同族病。
</details>
