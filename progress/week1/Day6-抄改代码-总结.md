# Day6 · 抄改代码（mini_kb / json_log / mini_api）【面试参考版】

> 日期：2026-10-22 ｜ 任务 A/B/C 全部验收通过（mini_kb 8/8、json_log 10/10、mini_api 8 项全绿）｜ 第四档 #01 3/4
> 这一天是"把前五天知识合成为可运行项目"的关卡，产出的 7 个坑**每一个都能当面试故事讲**。

---

## 1. 交付物与结构（面试讲故事用）

| 任务 | 文件 | 验收 | 内容 |
|---|---|---|---|
| A · 分层最小版 | `mini_kb.py`（~137 行） | 8/8 | repo/service/api 三层 + 异常族 + DTO |
| B · 日志 + ContextVar | `json_log.py`（~73 行） | 10/10 | JSON 格式化 + trace_id 上下文 |
| C · FastAPI 串联 | `mini_api.py`（~116 行） | 8 项全绿 | 路由 + 依赖注入 + 异常处理器 + 中间件 |

**方法论（值得写进简历/面试）**：上午手写卡死 → 改成"三档阶梯"（照着敲 → 讲顺 → 偷看计数 ≤3），产出参考实现后进度起飞。
> **跨度太大不是能力问题，是台阶密度问题**。这条对以后带人、对自己学新东西都成立。

---

## 2. 七个知识点（面试可说）

### 2.1 Python 3.11 Windows 时钟粒度 15.6ms（最值钱的坑）

```python
>>> import time
>>> time.get_clock_info("time").resolution
0.015625   # 15.6ms！
```

- Windows 上 `datetime.now()` 在 **3.11 精度只有 15.6ms**（3.13 是 1µs）。连续两次 `now()` **100% 相同**。
- 两次 create 实际只隔 ~27µs → 时间戳必然相等 → `sort(key=created_at)` 是**稳定排序，保持插入顺序** → 排序断言**静默通过**：你以为测到了，其实什么都没测。
- **防退化断言**（写排序/去重测试的标准动作）：

```python
assert kb2.created_at > kb.created_at   # 先证明"输入分得开"
assert items[0].id == kb2.id            # 再测排序本身
```

- **教训**：AI 参考代码先在 3.13 全绿、到 3.11 就挂。**凡涉及时间/浮点/哈希/dict 顺序的结论，一律用项目锁定的 3.11 实测。**

**面试话术**："Windows 上 Python 3.11 的 time 精度只有 15.6 毫秒，两次 datetime.now() 大概率相等。我的排序测试因此静默失效——排序是稳定的，时间戳相等就保持插入顺序，断言永远通过。后来我在测试里先断言两个时间戳确实不同，再断言排序结果，这叫防退化断言：先证明测试能区分，再验证行为。"

### 2.2 字符串驻留 → `id()` 不能当唯一 ID

`id('/api/users') == id('/api/users')` 为 **True**（CPython 驻留相同字面量，同一对象）。用 `id(path)` 当 trace_id，两个**相同路径**的并发请求会拿到同一个"唯一"ID → 串号。

**唯一 ID 必须 `uuid4()`**——这是运行时看输出永远看不出来的坑，只有并发同 path 才炸。

**追问**：还有什么"看起来唯一其实不唯一"？→ `id(obj)`（复用）、`hash(str)`（可能碰撞）、`time.time()`（精度不够/回拨）、`random` 未播种（多进程同种子）。

### 2.3 类型注解的三种命运（FastAPI 特有）

| 场景 | 注解是什么 | 拼错了会怎样 |
|---|---|---|
| 纯 Python | 字符串（惰性） | **静默**，运行时不检查 |
| `get_type_hints()` | 强制求值 | NameError，能抓到 |
| **FastAPI 返回注解** | **运行时校验器** | 结构不符 → `ResponseValidationError` → **500** |

所以 `-> dict[str, str]` 但实际含 `doc_count: int` 不是"文档写错了"，是**线上 500**。注解即契约：返回注解写 `dict[str, Any]`，除非你真的想约束结构。

**面试话术**："FastAPI 把返回注解当 response model 做运行时校验，所以注解不只是 IDE 提示，是线上契约。我踩过一次：注解写 dict[str, str]，实际返回里有个 int 字段，本地不报错，一请求就 ResponseValidationError 变 500。要么写准类型，要么用 Any 放宽，要么定义真正的响应模型。"

### 2.4 `ContextVar` 的 Token 是"回到过去"的凭证

```python
token = trace_id_ctx.set(value)
try:
    ...
finally:
    trace_id_ctx.reset(token)     # 精确回滚到该次 set 之前
```

- `reset()` 不传 token 只是"清掉"；传 token 是**精确回滚**（嵌套 set 时不误伤外层）。
- **try/finally 保证**：请求抛异常也要还原，否则协程复用脏数据泄漏。
- **对照实验实锤**：全局变量方案串号 9/10，ContextVar 0/10。

### 2.5 `record.created` ≠ `datetime.now()`

`LogRecord.created` 是**事件发生时刻**（logging 内部记录）；`datetime.now()` 在 Formatter 里调用是**格式化时刻**。QueueHandler / 异步日志 / 重放场景下两者差几秒，时间线全错。**日志时间戳一律用 `record.created`。**

### 2.6 `exc_info` 的后半句

`record.exc_info` 在 except 块外是 `(None, None, None)`——**bool 为 True 但 `formatException` 产出 `'NoneType: None'` 垃圾**。

正确写法：`record.exc_info and record.exc_info[0] is not None`。
（"差半句"条件和"忘记 `= None`"是同构错误：**判断条件不完整，静默走错分支**。）

### 2.7 service 出口一律 DTO

repo 的 row dict 是**内部方言**，service 出口必须 `KBOut.from_row(row)` 统一。否则 `get_or_403` 返回裸 dict，上层 `resp.name` 直接 AttributeError。

**接口边界（谁抛异常、谁翻译成 HTTP、谁转 DTO）就是必须手写的部分。**

### 2.8 AI 时代的瓶颈：从"写"移到"验证"

- METR 2025 RCT：允许用 AI 的开发者完成任务**反而慢 19%**，且主观感知与实测相反；接受率 <44%。
- GitClear：AI 介入后代码库**重复代码涨 8 倍**。
- **结论：没验证过的 AI 代码 = 负资产。核心能力不是写更多，而是长出"能看出 AI 错在哪"的眼睛**——第四档存在的意义（本次 AI 参考代码自己就错了 3.11 时钟这一处，铁证）。

**面试话术**（可以聊，很多团队爱问）："我用 AI 写代码但不会直接采信。有个随机对照实验显示用 AI 的开发者主观觉得快了，实测反而慢 19%，因为时间转移到了审查和返工上。所以我的做法是：AI 产出的代码必须跑、必须看 diff、关键路径自己写。我自己就遇到过 AI 给的参考实现只在 Python 3.13 正确、在项目锁定的 3.11 上断言失效的情况。"

---

## 3. 今天踩的坑（6 + 1）

| # | 坑 | 一句话教训 |
|---|---|---|
| 1 | `status` 未导入 → 401 变 500 | 500 先看服务端 traceback，别猜 |
| 2 | 返回注解 `dict[str, str]` 撞 doc_count(int) → 500 | 注解在 FastAPI 是运行时契约 |
| 3 | `get_or_403` 返回裸 dict → 上层 AttributeError | 出 service 一律 DTO |
| 4 | `id(path)` 当 trace_id，驻留致串号 | 唯一 ID 必须 uuid4 |
| 5 | `uuid4` 未导入（F821） | ruff 抓 import，交前必跑 |
| 6 | 验收器第 7 项契约过时 → 9/9 假绿 | 验收器也要随契约升级 |
| 7 | **AI 参考代码在 3.11 下排序断言失效** | 实测必须用项目锁定版本，AI 也不例外 |

## 4. 30 秒答案集

1. **15.6ms 时钟** → 3.11 Windows time 精度低，排序断言会静默失效；先写防退化断言。
2. **id() 当唯一 ID** → 字符串驻留导致相同字面量同 id，并发同 path 串号；用 uuid4。
3. **FastAPI 返回注解** → 运行时校验，类型不符 500；注解即契约。
4. **ContextVar Token** → `reset(token)` 精确回滚；必须 finally。
5. **日志时间戳** → 用 `record.created`（事件时刻），不用 `datetime.now()`（格式化时刻）。
6. **exc_info 判空** → `record.exc_info and record.exc_info[0] is not None`。
7. **DTO 口径** → 出 service 一律转换，别把内部方言漏给上层。
8. **AI 代码** → 未验证即负资产；瓶颈在审查不在生成。

## 5. 追问链（面试深挖预演）

| 起点 | 追问 | 你要能答 |
|---|---|---|
| 时钟精度 | 为什么测耗时用 perf_counter？ | 单调时钟、高精度、不受 NTP 影响 |
| 唯一 ID | uuid4 会碰撞吗？ | 概率极低（122 位随机）；分布式无需协调 |
| 注解 | 运行时怎么拿到注解？ | `get_type_hints()` / `inspect.signature()`；字符串注解会被求值 |
| ContextVar | 线程池里怎么传播？ | `copy_context().run(fn)` 或显式传参 |
| 日志 | 为什么异步日志会差几秒？ | 事件时刻 vs 格式化/落盘时刻分离（QueueHandler） |
| 异常日志 | `exc_info=True` 和传异常对象的区别？ | True 取当前正在处理的异常；传对象可记录非当前异常 |
| DTO | 什么时候用 dataclass / pydantic？ | 内部结构用 dataclass；边界校验用 pydantic |
| AI 协作 | 怎么保证质量？ | 跑测试 + 读 diff + 关键路径自己写 + 用项目版本实测 |

## 6. 与项目的衔接

| 今天练的 | 项目里的位置 | 何时用 |
|---|---|---|
| ContextVar + trace 中间件 | `core/logging.py` | 就是它的原理 |
| exception_handler 404/403 | `core/exceptions.py` + api 层 | mini_api 复刻了同构设计 |
| `KBOut.from_row` | `schemas/` + `services/` 口径 | W7 换 SQLAlchemy 的 from_orm 同思想 |
| 防退化断言 | pytest 写法 | W4 测试驱动直接用 |
| FastAPI 返回注解=契约 | 所有 router 签名 | 对照真项目的返回模型 |

## 7. 闭卷自测

1. 为什么 Windows 3.11 下两次 `datetime.now()` 常相等？导致排序测试什么静默失效？防退化断言怎么写？
2. `ContextVar.set()` 返回什么？`reset()` 传与不传 token 区别？为什么必须 finally？
3. FastAPI 里 `-> dict[str, str]` 但返回含 int 字段会怎样？说明注解什么性质？
4. Formatter 里该用 `record.created` 还是 `datetime.now()`？什么场景差几秒？
5. 为什么 `id('/api/users') == id('/api/users')` 是 True？当 trace_id 怎么炸？
6. 第四档为什么要求"至少 1 个坑运行时零症状"？

<details><summary>答案</summary>
1. `time.get_clock_info("time").resolution = 0.015625`（15.6ms），间隔 27µs 拿到同一时刻；稳定排序保持插入顺序 → 断言恒真。先断言 `b.created_at > a.created_at` 证明输入可分辨。
2. Token；`reset(token)` 精确回滚（嵌套不误伤），不传只清当前值；finally 保证异常路径也还原，防串号。
3. ResponseValidationError → 500；注解在 FastAPI 是运行时契约，不只是文档。
4. `record.created`；QueueHandler/异步/重放时"事件时刻"与"格式化时刻"分离，可能差几秒。
5. CPython 字符串驻留：相同字面量同一对象；并发同 path 请求拿到同一个"唯一"ID，日志无法区分。
6. 否则"找坑"退化成"跑一遍"；零症状坑模拟的正是"看起来对但埋雷"——AI 代码的真实风险。
</details>
