# Day6 · 抄改代码 总结

> **日期**：2026-10-22
> **投入**：约 5.5h（上午 ~2h 任务 A 卡壳 + 策略调整，下午 ~3.5h 任务 B/C + 第四档）
> **结果**：**任务 A/B/C 全部完成并验收通过**——mini_kb 8/8、json_log 10/10、mini_api 终验 8 项全绿、ruff 全目录干净；第四档 #01 找出 3/4 + 1 题豁免
> **提交**：由用户手动推送（新约定：推送三连自己练）
> **文件**：`progress/week1/day6_copy/`（mini_kb.py / json_log.py / mini_api.py + 两个自建验收器 + 对照实验 + 第四档 #01）
> **待做**：任务 D（跑真 kb-service 全接口 + 三个必答问题）→ 顺延到下次；Day7 自测复盘不变

---

## 一、完成情况

| 任务 | 文件 | 验收 | 状态 |
|---|---|---|---|
| A · 分层最小版 | `mini_kb.py`（~137 行） | `check_mini_kb.py` **8/8** | ✅ |
| B · 日志 + ContextVar | `json_log.py`（~73 行） | `check_json_log.py` **10/10** | ✅ |
| C · FastAPI 串联 | `mini_api.py`（~116 行） | 终验 **8 项全绿**（POST 201 / stats 200 / GET 200 / 404 / 403 / 422 / list 回归 / X-Trace-Id 两次不同） | ✅ |
| 第四档 #01 | `review_01_logging.py`（4 坑） | **3/4 + 1 题豁免**（Q2 属歧义） | ✅ |
| 回归 | 三项全绿 | check_mini_kb 8/8、check_json_log 10/10、ruff 全目录 | ✅ |

**过程记录**：上午手写卡死 → 用户主动提出"三档阶梯"（照着敲 → 讲顺 → 偷看计数 ≤3），产出参考实现 `mini_kb_reference.py` 后进度立刻起飞。**这是本周最重要的方法论调整：跨度太大不是你的错，把台阶铺密一点就行。**

---

## 二、八个知识点（面试可直接说）

### 1. Python 3.11 Windows 时钟粒度 15.6ms（本日最大坑，AI 自己也踩了）

```python
>>> import time
>>> time.get_clock_info("time").resolution
0.015625   # 15.6ms！
```

- Windows 上 `datetime.now()` 在 **3.11 精度只有 15.6ms**（3.13 是 1µs）。连续两次 `now()` **100% 相同**
- 两次 create 实际只隔 ~27µs → 时间戳必然相等 → `sort(key=created_at)` 是**稳定排序，保持插入顺序** → 排序断言**静默通过**，你以为测到了其实什么都没测
- **防退化断言**（以后写排序/去重测试的标准动作）：

```python
assert kb2.created_at > kb.created_at   # 先证明"输入分得开"
assert items[0].id == kb2.id            # 再测排序本身
```

- **教训**：AI 参考代码先在 3.13 上全绿、到 3.11 就挂。**凡涉及时间 / 浮点 / 哈希 / dict 顺序的结论，一律用项目锁定的 3.11 实测**（`kb-service/.venv/Scripts/python.exe`）

### 2. 字符串驻留 → `id()` 不能当唯一 ID

`id('/api/users') == id('/api/users')` 为 **True**（CPython 会驻留相同字面量，同一对象）。用 `id(path)` 当 trace_id，两个**相同路径**的并发请求会拿到同一个"唯一"ID → 串号。**唯一 ID 必须 `uuid4()`**，这是运行时看输出永远看不出来的坑（只有并发同 path 才炸）。

### 3. 类型注解的三种命运（FastAPI 特有认知）

| 场景 | 注解是什么 | 拼错了会怎样 |
|---|---|---|
| 纯 Python | 字符串（惰性） | **静默**，运行时根本不检查 |
| `get_type_hints()` | 强制求值 | 报 NameError，能抓到 |
| **FastAPI 返回注解** | **运行时校验器** | 返回值结构不符 → `ResponseValidationError` → **500** |

所以 `-> dict[str, str]` 但实际含 `doc_count: int` 不是"文档写错了"，是**线上 500**。注解即契约，返回注解要写 `dict[str, Any]` 除非你真的想约束结构。

### 4. `ContextVar`：Token 是"回到过去"的凭证

```python
token = trace_id_ctx.set(value)   # set 返回 Token
try:
    ...
finally:
    trace_id_ctx.reset(token)     # reset(token) 回到 set 之前的状态
```

- `reset()` 不传 token 只是"清掉"，传 token 是**精确回滚**（嵌套 set 时不误伤外层）
- **try/finally 保证**：请求处理抛异常，trace 上下文也必须还原，否则协程复用时脏数据泄漏
- 对照实验实锤：全局变量方案串号 9/10，ContextVar 0/10

### 5. `record.created` ≠ `datetime.now()`

`LogRecord.created` 是**事件发生时刻**（logging 内部记录），`datetime.now()` 在 Formatter 里调用是**格式化时刻**。QueueHandler / 异步日志 / 重放场景下两者差几秒，全部时间线全错。日志时间戳一律用 `record.created`。

### 6. `exc_info` 的后半句

`record.exc_info` 在 except 块外是 `(None, None, None)`——**bool 为 True 但 `formatException` 产出 `'NoneType: None'` 垃圾**。正确写法：`record.exc_info and record.exc_info[0] is not None`。签名/条件"差半句"和昨天 `= None` 丢失是同构错误。

### 7. service 层口径：出 door 一律 DTO

repo 的 row dict 是**内部方言**，service 出口必须 `KBOut.from_row(row)` 统一。否则 `get_or_403` 返回裸 dict，上层 `resp.name` 直接 AttributeError。**接口边界（谁抛异常、谁翻译成 HTTP、谁负责转 DTO）就是必须手写的部分。**

### 8. AI 时代的瓶颈：从"写"移到"验证"（今天讨论的定论）

- METR 2025 RCT：允许用 AI 的开发者完成任务**反而慢 19%**，且主观感知与实测相反；接受率 <44%
- GitClear：AI 介入后代码库**重复代码涨 8 倍**
- **结论：没验证过的 AI 代码 = 负资产。你的重点不是写更多，而是长出"能看出 AI 错在哪"的眼睛**——这正是第四档存在的意义（本次 Day6 AI 参考代码自己就错了 3.11 时钟这一处，铁证）

---

## 三、今天踩的坑（6 + 1）

| # | 坑 | 一句话教训 |
|---|---|---|
| 1 | `status` 未导入 → 401 变 500 | 500 先看服务端 traceback，别猜 |
| 2 | 返回注解 `dict[str, str]` 撞 doc_count(int) → 500 | 注解在 FastAPI 是运行时契约 |
| 3 | get_or_403 返回裸 dict → 上层 AttributeError | 出 service 一律 KBOut |
| 4 | `id(path)` 当 trace_id，驻留致串号 | 唯一 ID 必须 uuid4 |
| 5 | `uuid4` 未导入（F821） | ruff 抓 import，交前必跑 |
| 6 | 验收器第 7 项契约过时 → 9/9 假绿 | 验收器也要随契约升级 |
| 7 | **AI 参考代码在 3.11 下排序断言失效** | 实测必须用项目锁定版本，AI 也不例外 |

---

## 四、自测 6 问（闭卷）

1. 为什么 Windows 3.11 下两次 `datetime.now()` 常相等？会导致排序测试出现什么**静默失效**？防退化断言怎么写？
2. `ContextVar.set()` 返回什么？`reset()` 传与不传 token 的区别？为什么必须放 `finally`？
3. FastAPI 里 `-> dict[str, str]` 但返回值含 int 字段，会发生什么？这说明了注解的什么性质？
4. 日志 Formatter 里该用 `record.created` 还是 `datetime.now()`？两者在什么场景下会差好几秒？
5. 为什么 `id('/api/users') == id('/api/users')` 是 True？它作为 trace_id 会怎么炸？
6. 第四档出题为什么要"至少 1 个坑运行时零症状"？（用 METR/GitClear 的结论回答）

<details>
<summary>答案</summary>

1. Windows `time.get_clock_info("time").resolution = 0.015625`（15.6ms），两次调用间隔 ~27µs 拿到同一时刻。`sort` 是稳定排序，key 相等保持插入顺序 → 断言永远通过但什么都没测。先写 `assert b.created_at > a.created_at` 证明输入分得开，再写排序断言。
2. 返回 **Token**。`reset(token)` 精确回滚到该次 set 之前（嵌套 set 不误伤外层）；不传只是清当前值。放 `finally` 是保证异常路径也还原上下文，否则协程复用脏数据泄漏。
3. FastAPI 把返回注解当 response model 做**运行时校验**，结构不符 → `ResponseValidationError` → 500。注解不只是文档/IDE 提示，在 FastAPI 里是运行时契约。
4. 用 `record.created`。QueueHandler/异步日志/重放场景下，"事件时刻"与"格式化时刻"（Formatter 执行 `datetime.now()` 的瞬间）会差几秒，日志时间线全错。
5. CPython 字符串驻留：相同字面量是**同一个对象**，id 相同。作为 trace_id 时两个相同 path 的并发请求拿到同一个"唯一"ID，日志无法区分请求——且单请求测试永远发现不了。
6. 如果所有坑跑一遍就能发现，"找出坑"就退化成"跑一遍"，检验不了读代码的能力。METR/GitClear 证明 AI 代码的真正风险是**看起来对**（慢 19%、重复 8 倍）——零症状的坑模拟的正是"看起来对但埋雷"的真实形态。

</details>

---

## 五、与项目的衔接

| 今天练的 | 项目里的位置 | 什么时候用到 |
|---|---|---|
| ContextVar + trace 中间件 | `core/logging.py` 的 trace 上下文 | **就是它的原理**，任务 D 跑真项目时对照看 |
| exception_handler 404/403 | `core/exceptions.py` + api 层 | **已经在 mini_api 里复刻了同构设计** |
| KBOut.from_row | `schemas/` + `services/` 口径 | W7 换 SQLAlchemy 时 from_orm 同一思想 |
| 防退化断言 | pytest 写法 | W4 测试驱动直接用 |
| FastAPI 返回注解=契约 | 所有 router 签名 | 任务 D 对照真项目的返回模型 |

---

## 六、下一步（不用现在做）

1. **任务 D**（顺延，~1h）：跑真 kb-service 全接口（含 SSE）+ 三个必答问题，把 mini_api 和真项目对照
2. **第四档 #02**：埋坑版 API（任务 D 后出题）
3. **Day7**：12 道闭卷自测 + 周复盘 + 打 tag（周日）
4. 推送由你自己执行，命令块见对话
