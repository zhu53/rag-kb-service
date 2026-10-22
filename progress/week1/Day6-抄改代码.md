# Day6 · 抄改代码 + 跑通服务（5h）

> **今天的本质**：前 5 天你一直在"看懂别人写的"，今天检验"能不能自己写出来"。  
> **产出**：`progress/week1/day6_copy/` 下的三个文件 + 跑通全部接口 + 三个必答问题。

---

## ⭐ 学习方法：三档阶梯（2026-10-22 调整）

> **调整原因**：直接"看 20 行关掉默写"跨度太大，导致"能看懂但写不出来"。
> 改成语言学习的通用阶梯，每一档都可验收。

| 档 | 做什么 | 练的是 | 验收 |
|---|---|---|---|
| **1 档 · 照着敲** | 打开 `mini_kb_reference.py`，一行一行抄到 `mini_kb.py`。每抄一小段，**用嘴念一遍它在干什么** | **手感**：`def __init__(self) -> None:` 这种行敲 20 遍就是肌肉记忆 | `python mini_kb.py` 打印 `ALL OK` |
| **2 档 · 背诵** | 合上参考文件，只看自己敲的 `mini_kb.py`，把每个方法的作用讲一遍 | **结构感**：知道这一层该有什么，比记具体的字重要 | 能不看参考讲完 6 个方法 |
| **3 档 · 默写** | 清空 `mini_kb.py`，凭记忆重写。**卡住最多偷看 3 次**，每次记一笔"忘了哪个方法" | **回忆能力**：这才是面试和真实开发的状态 | `ALL OK` 且偷看 ≤ 3 次 |

**为什么三档都要走**：只走 1 档 = 眼睛会了手不会；只走 3 档 = 2026-10-22 早上卡住的那个状态。**1→2→3 是逐步撤掉拐杖。**

**参考实现**：`progress/week1/day6_copy/mini_kb_reference.py`（已验证 `ALL OK` + ruff 全过）。任务 B/C 的参考实现做到再给。

---

## 1 档 · 照着敲（分 6 段，每段必须念 + 跑一次）

> 直接抄 260 行，手会酸，脑子不会进东西。**切成 6 段，每段抄完立刻跑一次。**
> "跑"不是验收，是**低成本自检**：语法错了立刻炸，不会攒到最后一起炸。

### 起手动作（1 分钟）

```powershell
cd progress\week1\day6_copy
# 把现在这份半成品留个档，三档走完拿它对比，你会看到进步
copy mini_kb.py mini_kb_v0_手写版.py
# 然后清空 mini_kb.py，从第 1 行开始抄
```

### 六段拆解

| 段 | 参考文件行号 | 内容 | **嘴里念这句**（念不出来就停下来想） | 抄完自问 |
|---|---|---|---|---|
| 1 | 1–41 | 文件 docstring + import + `NotFoundError` / `ForbiddenError` | "两个业务异常类，`status_code` 挂在**类属性**上，API 层靠它翻译成 HTTP 码" | 为什么不继承 `ValueError` 而继承 `Exception`？ |
| 2 | 43–64 | `InMemoryStore` + 模块级 `store` 单例 | "这是假数据库。`kbs` 是 dict，key 是 UUID，value 是一行数据" | 为什么 `now()` 返回 `datetime.now(UTC)` 而不是 `datetime.now()`？ |
| 3 | 67–102 | `KBOut` + `to_dict` + `from_row` | "`from_row` 是 pydantic `model_validate` 的手工版：dict 进，对象出" | `to_dict` 为什么全转 `str`？不转会怎样？ |
| 4 | 105–153 | `KBRepository` 六个方法 | "数据层只存取，不做判断。查不到返回 `None` 或 `False`，**不抛异常**" | `list_by_owner` 的 `total` 为什么是**切片前**的 `len(rows)`？ |
| 5 | 156–203 | `KBService` 六个方法 | "业务层只做规则判断和对象转换。**这一层出现 `fastapi` 就说明分层破了**" | `get_or_403` 两个 `if` 顺序反了会怎样？ |
| 6 | 206–254 | `if __name__ == "__main__":` 自测 6 条 | "六条断言从上到下：建 → 别人的权限 → 不存在 → 列表 → 改名 → 删除" | 第 4 条为什么能断言 `items[0].name == "第二个库"`？ |

### 每段抄完都跑这一句

```powershell
python mini_kb.py
```

**看到什么算正常**：

| 段 | 正常输出 | 如果报错，大概率是 |
|---|---|---|
| 1 | 什么都没打印，退出码 0 | 导入少了 → `NameError: name 'Any' is not defined`（你今早卡在这里） |
| 2–5 | 还是什么都没打印 | 缩进错、`def` 少了冒号、上一段复制时漏了行 |
| 6 | `mini_kb: ALL OK` | 才真正开始看业务逻辑的问题，报错信息会直接指向行号 |

> **"什么都没打印"不是失败**，是"这一段语法正确且没有可执行语句"。这是最安静的绿灯。

### 抄写时的三条纪律

1. **抄错不要回退重抄整段**——抄错就抄错，跑一次让报错指给你看，然后只改那一行。这才是真实开发时的循环（写 → 跑 → 看报错 → 改）。
2. **不许在抄的时候"顺便优化"**。想 `list_by_owner` 加缓存？抄完 6 段全绿之后再说。掺着改，报错时你分不清是抄错了还是改错了。
3. **念出来才算抄完一段**。念不出来说明这段是"手的动作"不是"脑的理解"，停下来把那行读懂再往下。

---

## 为什么抄到独立目录，而不是抄进 kb-service

1. 抄进 `kb-service/src/` 就是死代码，永远不会被运行
2. 独立小项目可以**随便删随便改**，没有心理负担
3. **从零把分层拼一遍**，比读十遍更能理解"层与层为什么这么接"

目标结构（今天结束时）：

```
progress/week1/day6_copy/
├── mini_kb_reference.py  ← 任务 A 参考实现（只读，照着它敲）
├── mini_kb.py            ← 你自己敲的（三档都在这个文件上迭代）
├── check_mini_kb.py      ← 任务 A 自动验收器（8 项，只判对错不给答案）
├── json_log.py           ← 任务 B：ContextVar + JSON 日志
├── mini_api.py           ← 任务 C：FastAPI 把 A+B 接起来
└── day6-抄改记录.md       ← 默写偷看记录 + 三个必答问题
```

**任务 A 的验收命令**（必须用项目 3.11，用 3.13 结论会失真）：

```powershell
cd progress\week1\day6_copy
..\..\..\kb-service\.venv\Scripts\python.exe check_mini_kb.py
# 想拿参考实现对照：末尾加 mini_kb_reference
```

**为什么不能只靠 `python mini_kb.py` 打印 `ALL OK`**：2026-10-22 实测，Windows + Python 3.11
的 `datetime.now()` 精度只有 15.6ms，两次 `create()` 拿到同一时间戳 → `list.sort` 退化成
插入顺序 → 断言"绿得毫无意义"。**自测通过 ≠ 逻辑正确**，验收器查的是性质不是打印结果。

**依赖关系**：C import A 和 B——**先做 A，再做 B，最后 C**。这本身就是"分层"的体验：先有地基再盖楼。

---

## 任务 A · mini_kb.py：分层复现（约 120 行，2h）

**看什么**：`kb-service/src/kb_service/repositories/base.py`、`kb_repo.py`、`services/kb_service.py`、`schemas/kb.py`——**看完关掉**。

**要实现的东西**（不 import kb_service 的任何代码，全部手写）：

| 层   | 内容                                                                               | 要点                                  |
| --- | -------------------------------------------------------------------------------- | ----------------------------------- |
| 存储  | `InMemoryStore`：`kbs: dict[UUID, dict]` + `new_id()` + `now()`                   | 为什么 datetime 用 `datetime.now(UTC)`？ |
| 数据层 | `KBRepository`：`create / get / list_by_owner / update / delete / count_by_owner` | **方法签名和 kb_repo.py 一样**——接口稳定才能换实现  |
| 业务层 | `KBService`：`create / get_or_403 / list / update / delete / count_owned`         | **禁止 import fastapi**，禁止直接碰 store   |
| 输出层 | `@dataclass class KBOut`：`id / name / owner_id / doc_count / created_at`         | 用 Day4 学的 dataclass                 |

**提示阶梯**（卡住按顺序看）：

1. `Page` 分页结构今天可以简化成 `list[KBOut]` + `total`，想挑战就写个泛型 `Page[T]`
2. `get_or_403` 的两个分支顺序**不能反**：先查存在（404）再查归属（403）——想想为什么顺序反了信息泄露
3. `list_by_owner` 记得 `sort(key=created_at, reverse=True)` 再切片
4. 异常自己定义两个：`NotFoundError` / `ForbiddenError`（继承 `Exception`，带 `status_code` 属性）——**别 import kb_service 的**
5. **`store.now()` 要加单调兜底**（2026-10-22 踩坑）：Windows + Python 3.11 的 `datetime.now()` 精度只有 **15.6 毫秒**，两次 `create()` 只隔 27µs → 必然拿到同一个时间戳 → `list.sort` 稳定排序 → 排序退化成插入顺序。加 `_last_ts` 保证严格递增，否则"后创建的在前"这条断言永远测不出来

**写完必须跑**：在文件末尾加 `if __name__ == "__main__":` 自测块，依次验证：

```python
# 1. 创建 → 能查到
# 2. 别的 user_id 查 → ForbiddenError
# 3. 不存在的 id 查 → NotFoundError
# 4. list 只返回自己的，且按时间倒序
# 5. update 后字段变了
# 6. delete 后 get 返回 None，count 变 0
```

每个断言用 `assert`，全过打印 `mini_kb: ALL OK`。

**抄改记录（写进 day6-抄改记录.md）**：对比 kb_repo.py，你漏了什么？我预测是 `update` 里的 `model_dump(exclude_unset=True)` 对应物（只更新用户传了的字段）——想想 dict 版本怎么实现"部分更新"。

---

## 任务 B · json_log.py：ContextVar 日志（约 90 行，1.5h）

**看什么**：`kb-service/src/kb_service/core/logging.py`——**看完关掉**。

**要实现的东西**：

| 部分   | 内容                                                                       | 要点                              |
| ---- | ------------------------------------------------------------------------ | ------------------------------- |
| 上下文  | `trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")`    | 为什么不用全局变量？（想想两个请求并发）            |
| 格式化  | `JsonFormatter(logging.Formatter)`：输出一行 JSON                             | `ensure_ascii=False`；时间戳 ISO 格式 |
| 安装   | `setup_logging()`：清空 root handlers → 挂 StreamHandler                     | 为什么先 `clear()`？不清会重复打印          |
| 模拟请求 | `handle_request(path: str)` 函数：set trace_id → 干活（log 两次）→ `reset(token)` | **set 返回的 token 必须用完 reset**    |

**提示阶梯**：

1. `extra={"key": value}` 传的字段会出现在 `record.__dict__` 里——你要把它们合并进 JSON，但要**跳过 logging 自己的保留字段**（`levelname`、`msg`、`exc_info` 等）。保留字段名单不用背全，先过滤你见过的这几个，跑起来看输出里混进了什么再补
2. `record.exc_info` 存在时用 `self.formatException()` 加一个 `exc` 字段
3. **为什么用 ContextVar 而不是全局变量**：写个实验——两个线程/两个 asyncio task 同时 `handle_request`，全局变量的 trace_id 会互相覆盖，ContextVar 各归各。**这个实验是今天的精髓，必做**：

```python
import asyncio
# 用你的 json_log 写：两个 task 并发跑 handle_request，
# 验证每行日志的 trace_id 互不串扰（全局变量版本会串）
```

**验收**：跑 `python json_log.py`，输出是合法 JSON（贴到浏览器 JSON 校验器或 `json.loads` 一下），并发实验里 trace_id 不串。

### 先跑实验，再写代码（必做，2 分钟）

```powershell
cd progress\week1\day6_copy
..\..\..\kb-service\.venv\Scripts\python.exe exp_trace_id.py
```

`exp_trace_id.py` 是**观察实验**，不是作业。它让 10 个"请求"并发跑：每个进门 set 自己的
trace_id → `await` 一下 → 再读回来。实测输出：

```
=== 方案 1：全局变量 ===      串号 9 / 10
=== 方案 2：ContextVar ===    串号 0 / 10
```

**看懂这个再动手**，否则 `json_log.py` 只是抄了个 API。

两个必须注意的点：
1. **串号只在 `await` 之后才发生**。如果 set 完立刻读，全局变量看起来也是对的——
   真实服务一定有 IO 等待，所以问题必然暴露。
2. 全局变量是"一人写，全楼看"；ContextVar 是"每人一份，跟着执行流走"
   （`asyncio` task 和线程各自独立）。

### 分五步写，每步都能单独验收

| 步 | 写什么 | 关键 API | 这一步做完该看到 |
|---|---|---|---|
| B1 | `trace_id_ctx` + `set_trace_id()` + `get_trace_id()` | `ContextVar("trace_id", default="-")`、`.set()` 返回 token、`.reset(token)` | 交互式里 set 完 get 得到新值 |
| B2 | `JsonFormatter.format(record) -> str` | `record.getMessage()`、`record.__dict__`、`self.formatException(record.exc_info)` | 返回一行合法 JSON |
| B3 | `setup_logging()` | `logging.getLogger()`、`.handlers.clear()`、`logging.StreamHandler` | 重复调用不出现两行重复日志 |
| B4 | `handle_request(path)` | B1 的 set/reset + 两次 `logger.info` | 两行日志的 trace_id 相同 |
| B5 | `__main__` 里的并发实验 | `asyncio.gather` | 每行 JSON 的 trace_id 与请求编号一致 |

**B2 的三个坑**（先自己撞，撞不出来再回来看）：
1. `extra={"path": ...}` 传的字段在 `record.__dict__` 里，但同一个 dict 里还混着
   logging 自己的保留字段（`levelname` / `msg` / `args` / `exc_info` / `stack_info` /
   `name` / `filename` / `lineno` / `created` / `msecs` / `process` …）。
   **先不过滤，跑一次看输出里混进了什么，再补名单**——比背名单有效。
2. `ensure_ascii=False`，否则中文会变成 `\u4e2d\u6587`。
3. `record.exc_info` 有值时，`record.getMessage()` 拿不到堆栈，得 `self.formatException()`。

**B3 的坑**：`logging.getLogger()` 拿到的是 root，`handlers` 是**全局共享**的。
测试里反复 `setup_logging()` 会一层层往上加 handler → 同一条日志打印 N 次。
所以入口先 `.handlers.clear()`。

**B4 的坑（今天的重点）**：`set()` 返回的 token **必须在 `finally` 里 reset**，
否则这个 trace_id 会顺着上下文漏给后续代码：

```python
token = trace_id_ctx.set(trace_id)
try:
    ...干活...
finally:
    trace_id_ctx.reset(token)      # 恢复上一个值，不是清空
```

`reset(token)` 是**回到 set 之前的那个值**，不是设为默认值。想清楚这个差别。

---

## 任务 C · mini_api.py：FastAPI 串起来（约 100 行，1h）

**看什么**：`kb-service/src/kb_service/api/v1/knowledge_bases.py`、`api/deps.py`、`main.py`——看完关掉。

**要实现的东西**：

| 部分   | 内容                                                                                     |
| ---- | -------------------------------------------------------------------------------------- |
| 中间件  | 把 B 的 `trace_id_ctx` 接进真的 `BaseHTTPMiddleware`，写回 `X-Trace-Id` 响应头                     |
| 路由   | `POST /kbs`、`GET /kbs`、`GET /kbs/{kb_id}`、`DELETE /kbs/{kb_id}`、`GET /kbs/stats/count` |
| 鉴权   | 简化版：`X-User-Id` 请求头当 user_id（**不搞 JWT**，今天重点不是安全）                                      |
| 异常翻译 | `NotFoundError → 404`、`ForbiddenError → 403`（用 `@app.exception_handler`）               |
| 接线   | 路由里 `KBService().xxx(...)`，然后 dataclass 转 dict 返回                                      |

**提示阶梯**：

1. dataclass 转 dict：`dataclasses.asdict(obj)`，UUID/datetime 要转 str——写个 `to_dict()` 方法更直观
2. 异常处理器写法：
   ```python
   @app.exception_handler(NotFoundError)
   async def not_found_handler(request, exc):
       return JSONResponse(status_code=exc.status_code, content={"message": str(exc)})
   ```
3. 中间件里 `trace_id_ctx.set()` 拿 token，`finally` 里 reset——**和 B 里的 handle_request 是同一个模式**，只是套了 async

**验收**：`uvicorn mini_api:app --reload`（在 day6_copy 目录下跑，注意 mini_api 要能 import 到 mini_kb/json_log——同目录直接 import 即可），去 `/docs` 手点 5 个接口，确认：

- [ ] 每个响应头都有 `X-Trace-Id`
- [ ] 不带 `X-User-Id` 请求头 → 422 或 400（你自己的设计，能讲清就行）
- [ ] 访问别人的 kb → 403
- [ ] 不存在的 kb → 404
- [ ] `/kbs/stats/count` 数对了

**⚠️ 别忘了**：路由 `/stats/count` 必须注册在 `/{kb_id}` **之前**——Day3 踩过的坑，看看这次能不能主动想起来。

---

## 任务 D · 跑通 kb-service 全部接口（1h）

这回跑的是**真项目**：

```powershell
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\kb-service
./.venv/Scripts/python.exe -m uvicorn kb_service.main:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs`，按顺序手点：

1. `GET /api/v1/health` —— 看响应头 `X-Trace-Id`（这就是你 B 里抄的机制的成品）
2. 生成 token：PyCharm Python Console 里
   ```python
   from kb_service.core.security import create_access_token
   print(create_access_token("11111111-1111-4111-8111-111111111111"))
   ```
3. 右上角 Authorize 粘贴 token → 建库 → 传文档 → 提问（`stream: false`）→ 提问（`stream: true` 观察 SSE 逐字返回）
4. 把 Console 里的 JSON 日志看一眼：`ts / level / msg / trace_id / method / path / duration_ms` 都在吗？

---

## 三个必答问题（写进 day6-抄改记录.md，抄完凭理解答）

### Q1：为什么 `stream=true` 时响应头要加 `X-Accel-Buffering: no`？

提示：SSE 是"来一段发一段"。想想 Nginx 这类反向代理的默认行为是什么，如果它攒着会发生什么。

### Q2：文档入库后 `status` 为什么直接是 `ready`？哪一步做的切分？

提示：看 `doc_service.py` 的 `create` → `_parse_sync`。这个设计在什么量级会出问题？W11 用什么方案解决？

### Q3：越权访问别人的 kb，返回 403 还是 404？为什么？

提示：`kb_service.py:30` 有注释。两个选择各保护什么、各暴露什么？（关键词：信息枚举攻击）

---

## 时间预算（5h）

| 时段        | 任务                          |
| --------- | --------------------------- |
| 0:00–2:00 | 任务 A（分层，最重）                 |
| 2:00–3:30 | 任务 B（ContextVar + 并发实验）     |
| 3:30–4:30 | 任务 C（FastAPI 串联 + /docs 验证） |
| 4:30–5:00 | 任务 D（跑真项目）+ 三个必答问题 + 抄改记录   |

---

## 今日验收清单（10 条）

- [ ] `day6_copy/` 三个文件全部存在且能独立运行
- [ ] A 的 6 个自测断言全过
- [ ] A 的 service 层没有 import fastapi
- [ ] B 的日志输出是合法 JSON，含 ts/level/msg/trace_id
- [ ] **B 的并发实验跑过，trace_id 不串**（或亲眼看到全局变量版会串）
- [ ] C 的 5 个接口在 /docs 里全部手点过
- [ ] 每个响应有 X-Trace-Id；403/404 行为正确
- [ ] `/stats/count` 路由顺序这次主动放对了
- [ ] kb-service 真项目全接口跑通（含 SSE）
- [ ] 三个必答问题写完（写不出来说明要回看，正常）
