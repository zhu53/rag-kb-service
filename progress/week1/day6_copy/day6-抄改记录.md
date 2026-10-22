# Day6 抄改记录

> 这份文件只记三件事：**1 档抄到哪了**、**3 档偷看了几次**、**三个必答问题的答案**。
> 别写日记，只留能复用的东西。

---

## 1 档 · 照着敲（打卡）

起手：`copy mini_kb.py mini_kb_v0_手写版.py`，然后清空 `mini_kb.py`。

| 段 | 内容 | 抄完打勾 | 跑出来是什么 | 备注（哪里卡了） |
|---|---|---|---|---|
| 1 | docstring + import + 两个异常类 | [ ] | | |
| 2 | `InMemoryStore` + `store` 单例 | [ ] | | |
| 3 | `KBOut` + `to_dict` + `from_row` | [ ] | | |
| 4 | `KBRepository` 六个方法 | [ ] | | |
| 5 | `KBService` 六个方法 | [ ] | | |
| 6 | 自测 6 条 | [ ] | | |

**6 段全绿 = 1 档完成。** 中间抄错的次数不用记，那不是指标。

---

## 2 档 · 背诵（合上参考，只看自己敲的）

按顺序讲这 6 个东西，讲完一个打一个勾。**讲不清的那个就是 3 档会卡的地方，先圈出来。**

| 要讲的东西 | 一句话说清它是干什么的 | 讲顺了 |
|---|---|---|
| `InMemoryStore` | | [ ] |
| `KBOut.from_row` | | [ ] |
| `KBRepository` 和数据层的职责边界 | | [ ] |
| `get_or_403` 两个 if 的顺序 | | [ ] |
| `list_by_owner` 的 total 为什么是切片前 | | [ ] |
| `KBService` 为什么不能 import fastapi | | [ ] |

---

## 3 档 · 默写（偷看计数，上限 3 次）

> 清空 `mini_kb.py`，凭记忆重写。卡住超过 30 秒才准偷看，看**只准看那一个方法**，不要滚回去重读全文。

| 第几次偷看 | 卡在哪个方法 / 哪一行 | 忘了什么（用一个词概括） |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

**偷看 3 次以内且 `ALL OK` = 3 档通过。** 超过 3 次也不用焦虑，说明该进 Day7 的复习清单，明天早上先重默一遍。

### 默写通过后

```powershell
# 留个档，一周后回来重默时对比
copy mini_kb.py mini_kb_v3_默写版.py
```

---

## v0 → v3 对比（走完三档再填）

翻出 `mini_kb_v0_手写版.py`（今早那份），和 `mini_kb_v3_默写版.py` 并排看：

| 维度 | v0（今早） | v3（默写） |
|---|---|---|
| 能跑通吗 | 半成品，自测 4/5/6 被注释 | |
| `KBOut` 字段命名 | `owner` / `created`（和数据库行不一致） | |
| `list_by_owner` | 只有 `rows.sort` 没写完 | |
| `count_by_owner` | `len(store.doc_count)`（int 取 len） | |
| 报错时的第一反应 | 不知从何下手 | |

**这一栏才是今天真正的成绩单**，不是行数。

---

## 三个必答问题（任务 D 跑完真项目后填）

题目在 `../Day6-抄改代码.md` 的 Q1–Q3。

### Q1：`stream=true` 时为什么响应头要加 `X-Accel-Buffering: no`？

（答）

### Q2：文档入库后 `status` 为什么直接是 `ready`？哪一步做的切分？

（答）

### Q3：越权访问别人的 kb，返回 403 还是 404？为什么？

（答）

---

---

## 3 档 review（2026-10-22 10:10，结论已修正）

> **过程记录**：第一版复核写成"用户记反了"，是**错的**。原因是 AI 只在自己的 Python 3.13
> 里测出"2000 轮 0 次时间戳相同"，没在项目锁定的 3.11 里测。用户指出后重查，根因见下。

### 现象对照（同一份代码，只换解释器）

| 文件 | 断言 | Python 3.13 | Python 3.11（项目 `.venv`） |
|---|---|---|---|
| `mini_kb_reference.py` | `items[0]` | `ALL OK` | **`AssertionError`** |
| `mini_kb.py`（手改） | `items[1]` | **`AssertionError`** | `mini_kb: ALL OK` |

### 根因：Windows + Python 3.11 的 `datetime.now()` 精度只有 15.6 毫秒

```
Python 3.11.17
连续两次 datetime.now() 相同: 19995/19999 = 100.0%
time.get_clock_info("time").resolution = 0.015625     ← 15.625 ms

Python 3.13.12
连续两次 datetime.now() 相同: 82.5%   （粒度 1 µs）
```

两次 `create()` 只隔约 **27 µs** → 在 15.6ms 的格子里**必然撞在一起** → 两个
`created_at` 完全相同 → `list.sort` 是**稳定排序** → 保持插入顺序 →
**"测试库" 排到了 `items[0]`**。

这就是为什么 `items[0]` 在 3.11 下会挂、`items[1]` 反而过。**不是谁记反了，
是排序在时间戳相等时根本没发生。**

### 真正的坑：那条断言在 3.11 下"绿得毫无意义"

改成 `items[1]` 后测试确实绿了，但它验证的已经不是"按时间倒序"，而是
**"dict 的插入顺序"**——测了个同义反复。**比失败更危险：它假装测过了。**

### 修法：让 `now()` 严格单调递增

```python
class InMemoryStore:
    def __init__(self) -> None:
        self.kbs: dict[UUID, dict[str, Any]] = {}
        self._last_ts: datetime | None = None      # 新增

    def now(self) -> datetime:
        ts = datetime.now(UTC)
        # 时间戳撞车时手动 +1µs，保证严格递增
        if self._last_ts is not None and ts <= self._last_ts:
            ts = self._last_ts + timedelta(microseconds=1)
        self._last_ts = ts
        return ts
```

需要 `from datetime import UTC, datetime, timedelta`。

**这同时也是真实工程做法**：数据库排列表时用 `ORDER BY created_at DESC, id DESC`，
就是拿自增 id 当第二排序键兜底；很多系统直接用序列号排序，不信任时间戳。

### 再加一条"防退化"断言

```python
kb2 = svc.create(me, "第二个库")
# 先证明两个时间戳真的分得开，否则下面的排序断言在测插入顺序
assert kb2.created_at > kb.created_at, "两次创建拿到同一时间戳，排序断言失效"
items, total = svc.list(me)
assert items[0].name == "第二个库"
```

**教训：测试要能区分"测到了"和"没测到"。** 一个永远为真的断言，和一个正确的断言，
在 CI 里长得一模一样。

### 复盘：这次的错在哪

| 环节 | 怎么错的 |
|---|---|
| 实测 | 只用了 `binaries/python/3.13.12`，没碰项目 `kb-service/.venv` 的 3.11 |
| 推论 | 由"3.13 下 2000 轮不撞"直接推出"断言可靠"，忽略了**时钟精度是解释器/平台属性** |
| 表达 | 直接说"你记反了"，而不是"我这边跑出来是反的，你那边跑出来是什么" |

**规则补充**：涉及时间、浮点、哈希、`dict` 顺序、正则、编码的断言，**必须在项目锁定的
Python 版本下实测**，不能只在自己的解释器里测。

---

## 任务 A 验收：`check_mini_kb.py`（2026-10-22 10:20 首次跑）

**为什么要有它**：`python mini_kb.py` 打印 `ALL OK` 不代表对。当前 `mini_kb.py` 在 3.11 下
确实打印 `ALL OK`，但验收器只给 **2/8** —— 因为 `items[1]` 在 15.6ms 时钟精度下恰好过，
属于**假绿**。手改过没过，不能靠眼睛看。

跑法：
```powershell
cd progress\week1\day6_copy
..\..\..\kb-service\.venv\Scripts\python.exe check_mini_kb.py
```

| # | 检查项 | 现状 | 改哪里 |
|---|---|---|---|
| 1 | `KBService()` 能无参构造 | ❌ | 100 行 `repo: KBRepository` 后面补 `= None` |
| 2 | `now()` 严格递增 | ❌ | `__init__` 加 `self._last_ts`；`now()` 加 `+1µs` 兜底；import `timedelta` |
| 3 | `list()` 真按时间倒序 | ❌ | 依赖第 2 项；另把 168 行断言改回 `items[0]` |
| 4 | 只返回自己的 + total 是切片前 | ✅ | — |
| 5 | 类型注解可求值 | ❌ | 49 / 115 行 `KBout` → `KBOut` |
| 6 | 行 id 是 UUID 不是 str | ❌ | 63 行 `str(uuid4())` → `uuid4()` |
| 7 | `to_dict()` 可直接 `json.dumps` | ❌ | 44 行 `(self.owner_id)` → `str(self.owner_id)` |
| 8 | 权限语义 404 / 403 | ✅ | — |

**两条 PASS 说明什么**：`list` 的过滤与 `total` 逻辑、`get_or_403` 的检查顺序，你默写时就对了。
这两个是这道题的**核心业务逻辑**，你已经掌握。剩下 6 条全是细节精度问题（默认值、注解、
类型转换），不是"不会写分层"。

**方法**：改一条跑一次，别一口气改完再跑。一次改 6 处，跑挂了不知道是谁挂的。

---

## 任务 B · B1+B2 review（2026-10-22 11:00）

用户写完 `json_log.py` 的 B1 + B2。验收器 `check_json_log.py`：**6 / 9**（对照版 9/9，已交叉验证不误报）。

### 写对的部分（值得记）

**`and record.exc_info[0] is not None` 这半个判断是对的。** AI 一开始以为是冗余，实测发现不是：

```
exc_info=(None, None, None)  →  bool(exc_info) == True
                            →  formatException 返回 'NoneType: None'
```

`exc_info=True` 在 except 块外调用时，`sys.exc_info()` 就返回 `(None, None, None)`。
所以 `if record.exc_info` 单独不够，会往 JSON 里塞 `"exception": "NoneType: None"`。
用户这半个判断正好挡住它。

另：`ensure_ascii=False` 用对了，中文可读；`json.loads` 能直接解析。

### 三个问题

| # | 位置 | 问题 | 后果 |
|---|---|---|---|
| 1 | 53 行 | `if __name__ == "__&#8203;main__":` —— 混进 HTML 实体 | 字符串长 15 字符，**永不等 `"__main__"`，`main()` 永不执行** |
| 2 | 15 行 | `set_trace_id(...) -> None` 把 `set()` 返回值丢了 | B4 `reset(None)` → `TypeError: expected an instance of Token, got None` |
| 3 | 26 行 | `time` 用 `datetime.now(UTC)` | 记录的是**格式化时刻**，不是**事件发生时刻**。日志进队列/批量写/重放时时间全错 |

排查记录：

```
# 1 号
'__&#8203;main__' 长度 15，逐字符 ['_','_','&','#','8','2','0','3',';','m','a','i','n','_','_']
ruff: All checks passed!   ← 完全查不出来，字符串字面量合法
只用 AST 扫字符串常量才能发现

# 2 号
set_trace_id('abc')  →  返回 None
v.reset(None)        →  TypeError: expected an instance of Token, got None
v.set('xyz')         →  返回 <Token ...>，reset(token) 后值回到 'abc'

# 3 号
造 record.created = 1_700_000_000.0（2023-11-14T22:13:20Z）
formatter 输出 "time": "2026-10-22T02:58:57..."  ← 差了 3 年
```

### 第 2 条与昨天那次的同构

昨天：`repo: KBRepository | None` 丢了 `= None` → 调用处被迫写 `KBService(None)`。
今天：`set_trace_id(...) -> None` 丢了 `Token` → B4 里 `reset` 拿不到 token。

**同一类错误：函数签名丢了信息，调用方被迫绕路或根本走不通。**
信号：如果调用处要写 `KBService(None)`、或者要拿返回值却拿不到，先回头看签名。

### 第 3 条为什么不是"风格问题"

`record.created` 是 logging 在**创建 LogRecord 的那一刻**打的戳；
`datetime.now()` 是**format 执行的那一刻**。两者只在这条日志被立即同步输出时才相等。

一旦上 `QueueHandler` / `AsyncHandler` / 批量写日志，或者做日志重放（replay），
时间就会全部变成"写出时刻"——排查故障时你会看到 100 条日志挤在同一毫秒。

附带：3.11 下 `datetime.now()` 精度 15.6ms（今天早上踩过的坑），
所以即使同步输出，同一毫秒内的几条日志 `time` 也会完全相同。

### 白名单设计的取舍（WARN，不算错）

用户只挑了 `time/trace_id/level/message` 四个字段（白名单）。
好处：天然免疫 logging 保留字段混入（`levelname`/`args`/`created`/`pathname` …）。
代价：`extra={"path": ...}` 全部丢掉。

B4 要记录 `path`，届时需要：
```python
"path": getattr(record, "path", None),
```
或者改成黑名单：`{k: v for k, v in record.__dict__.items() if k not in RESERVED}`。

---

## 第四档 · 找出 AI 代码里的坑（2026-10-22 起，每次验收必做）

> **用户定的标准**（2026-10-22 11:35）：「我能找出来说明我真懂了，希望以后每一次验收都能有这个第四档。」

前三档检验「能不能写出来」，第四档检验「能不能看出错」。
真实工作里后者的频次高得多——读别人代码（包括 AI 的）的时间，远多于从空白开始写。

### 第 01 题：`review_01_logging.py`

一份 AI 写的 JSON 日志模块。**能跑、输出漂亮、ruff 全过、docstring 齐全。**
埋了 **4 个坑**，其中 1 个跑一遍根本发现不了。

跑法（在 `day6_copy` 目录下，用项目 3.11）：

```
<kb-service 的 .venv>/Scripts/python.exe review_01_logging.py
```

跑完你会看到两行合法 JSON，看起来完全没问题。**这就是这道题的目的：跑通不等于对。**

### 判定标准

| 找出几个 | 含义 |
|---|---|
| 1 个 | 及格（说明真的在读了） |
| 2 个 | 合格 |
| 3 个 | 真懂 |
| 4 个 | 全对。第 4 个最难——**跑不出来，只能靠读代码想到** |

### 提示阶梯（一次只看一层，卡住 10 分钟再往下）

1. 四个坑分别位于：**上下文层、输出层、安装层、异常处理**，各一个。
2. 有一个坑会让**同一段日志被打印两次**。
3. 你自己那份 `json_log.py` 里，`time` 那一行是怎么写的？对比一下。
4. 有一个坑会让 `exception` 字段出现字符串 `'NoneType: None'`。你在哪见过这个判断？

### 答案

<details>
<summary>点开看答案（先自己找完再看，别提前偷看）</summary>

**坑 1 · 上下文层 · `set_trace_id` 返回 None**

```python
def set_trace_id(trace_id: str) -> None:
    trace_id_ctx.set(trace_id)          # 返回值丢了
```

后果：B4 里 `reset(token)` 拿不到 token；`reset(None)` 抛
`TypeError: expected an instance of Token, got None`。
**这个坑你今天已经在自己代码里修过一次**，找不出来说明当时是照着改的。

**坑 2 · 输出层 · `time` 用了 `datetime.now(UTC)`**

```python
"time": datetime.now(UTC).isoformat(),          # 格式化时刻，不是事件时刻
```

应为 `datetime.fromtimestamp(record.created, UTC).isoformat()`。
症状：同一毫秒内多条日志的 `time` 完全相同（3.11 精度 15.6ms）。
判据很直接——**跑一遍看两行日志的 `time` 是不是一模一样**。

**坑 3 · 安装层 · `setup_logging` 不清 handlers**

```python
root.addHandler(handler)                # 少了 root.handlers.clear()
```

后果：调用两次就有两个 handler，**每条日志打印两遍**。
真实场景：测试里每个 case 都调一次 `setup_logging`，跑到第 50 个 case 时日志刷屏。
注意：跑一遍 `_demo()` **看不出来**，必须连续调两次才会暴露。

**坑 4 · 异常处理 · `if record.exc_info:` 少了后半句**

```python
if record.exc_info:                     # 应为 if record.exc_info and record.exc_info[0] is not None
```

后果：`exc_info=True` 在 `except` 块外调用时，`sys.exc_info()` 返回 `(None, None, None)`，
`bool()` 为 True，于是 `formatException` 往 JSON 里塞 `"exception": "NoneType: None"`。
**这个是你自己写对过的地方**，AI 版偷懒了。
**运行时零症状**，必须想到「exc_info 可能是空的」才会去验。

</details>

### 复盘要点

四个坑里有 **3 个是你今天自己踩过或写对过的**，所以这道题同时在测两件事：

1. 你真的记住了那三处，还是照着我的修改建议改的
2. 你能不能在「看起来专业」的代码面前保持怀疑

第 4 个坑最值钱：**它在运行时不产生任何症状**。真实项目里这类问题会潜伏到某天日志里冒出一堆 `NoneType: None`。

---

## 任务 B · B1+B2 二次验收（2026-10-22 16:50，9/10）

用户改完后第一次跑给的是 **9/9**，但那是**验收器自己的漏洞**造成的假绿。

### 用户这版写对了什么

1. `set_trace_id(...) -> Token` + `return trace_id_ctx.set(...)` ✅
2. `reset_trace_id(token)` —— **用户自创的封装**，教材没要求。把 reset 也收进工具函数，
   调用方（B4）不用直接碰 `trace_id_ctx`。这是好设计，保留。
3. `created = datetime.fromtimestamp(record.created, tz=UTC)` 然后 `created.isoformat()`
   —— 拆成两步，比嵌在一行里可读，也方便调试时单步看 `created` 的值。

### 但漏了一个 import

```python
from contextvars import ContextVar        # ← 少了 Token
def set_trace_id(trace_id: str) -> Token  # ← 这个名字不存在
```

**运行时完全不报错**，因为 `from __future__ import annotations` 把注解变成永不求值的字符串。
只有 `typing.get_type_hints()` 会抛 `NameError: name 'Token' is not defined`。

**这是昨天 `KBout` 小写 o 的同一个坑，第二次踩。** 两次都因为同一个机制静默通过。

### ⚠️ 验收器漏洞：9/9 是假绿

`check_mini_kb.py` 里有「类型注解可求值」这一项，但写 `check_json_log.py` 时**没移植过来**，
所以漏掉了 `Token` 未导入。

这跟用户早上把 `items[1]` 改成 `items[0]` 之后"测试绿了"是同一个形状：
**验收器覆盖不到的地方，会给出一个看起来通过的绿灯。**

已补第 9 项：

```python
for name, obj in vars(m).items():
    if getattr(obj, "__module__", None) != m.__name__:
        continue
    ...
    typing.get_type_hints(fn)      # 强制求值，拼写错误立刻现形
```

现在 9/10，补上 import 后 10/10（已验证）。

### 该记的两条

1. **写验收器时，要把上一个验收器里有效的检查项当作模板复用**，不要凭记忆重写。
   漏掉一项的代价是"假绿"，比写不出验收器更危险。
2. **`from __future__ import annotations` 的代价是复数级的**：每多一个跨模块的类型名，
   就多一处可能拼错而无人发现的地方。ruff 是唯一可靠的第一道防线（`F821`）。

### 待改

| 位置 | 改什么 |
|---|---|
| 8 行 | `from contextvars import ContextVar` → 加 `, Token` |
| 31 行 | `"trace_id": trace_id_ctx.get()` → `get_trace_id()`（定义了就该用，否则以后改默认值要改两处） |

---

## 任务 B · B3–B5 验收（2026-10-22 17:35）

**B1+B2：10/10**（上次漏的 `Token` import 已补）。**B3–B5 已写完并跑通**：

- 6 行 JSON 全部合法，每个请求两条日志 trace_id 一致
- 三个不同 path 的请求并发，trace_id 互不串号 —— **ContextVar 的核心目标达成**
- 输出里"收到"全部在"完成"前面：正常。`await asyncio.sleep(0.1)` 让出控制权，
  三个任务各打完"收到"再一起醒来打"完成"。想要交错输出可把 sleep 改成 0.01/0.02/0.03 不等
- 三行"收到"的 time 完全相同：又是 3.11 的 15.6ms 粒度（`time.time()` 同样受影响），不是 bug

### 发现的新坑：B4 用 `id(path)` 当 trace_id

```python
trace_id = f"req-{id(path):x}"     # ← 内存地址当唯一 ID
```

**实测（两个并发请求打到同一个 path `/api/users`）**：

```
req-1ad656c9830 | 收到 /api/users
req-1ad656c9830 | 收到 /api/users
req-1ad656c9830 | 完成 /api/users
req-1ad656c9830 | 完成 /api/users
```

四个请求级日志共享同一个 trace_id —— **和今天早上全局变量串号是同一种危害，只是触发条件不同**。

根因是**字符串驻留（interning）**：值相同的小字符串在 CPython 里是同一个对象，
`id()` 返回同一个内存地址。实测 `id('/api/users') == id('/api/users')` 为 True。

另一层问题：即便不驻留，对象被 GC 后内存地址会被复用，`id()` 本身就不该当唯一 ID。

**修法**：`trace_id = uuid4().hex[:8]`（或 `itertools.count` 计数器）。
唯一性必须来自"专门生成唯一值的机制"，不能从别的东西（地址、时间、哈希）上蹭。
