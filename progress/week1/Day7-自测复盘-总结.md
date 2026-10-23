# Day7 · 自测 + 任务 D + 周复盘 总结

> **日期**：2026-10-23
> **投入**：约 3.5h（闭卷自测 3 轮 ~1.5h + 任务 D ~1h + 补测与复盘 ~1h）
> **结果**：**W1 全部 7 天完成**；自测 14/24 → 补测 **17/24**；任务 D 全链路手点顺利；S0 阶段 100%
> **文件**：`day7_evidence/` 三份实测证据脚本（ruff 全过，可复跑）
> **待办**：打 tag `w01-done`（命令已给）；第四档 #02 埋坑版 API → W2 开头补

---

## 一、自测成绩单

| 轮次 | 题号 | 得分 | 短板 |
|---|---|---|---|
| 第一轮（工具链/异步） | Q1–Q4 | 4/8 | Q4 wraps 不知道 |
| 第二轮（语言特性） | Q5–Q8 | **7/8** | 仅 Q7 孤儿对象说反 |
| 第三轮（项目/工程） | Q9–Q12 | 3/8 | Q11 答反、Q12 只答一半 |
| **首轮合计** | | **14/24**（线 18） | |
| 补测（Q9/Q11/Q12） | | +3 → **17/24** | Q12 "哪些不用改/为什么"仍欠 |

**分数分布说明话**：语言特性接近满分（这两周手写真长进去了），丢分全在**框架与工程的"为什么"**——代码写出来了，设计意图没内化。

---

## 二、六个知识点（面试可直接说）

### 1. `threading.local` 在 asyncio 下等于全局变量（实测：串号 9/10）

```
threading.local 串号 9/10   期望 u0 实际 u9（都是最后写入者的值）
ContextVar      串号 0/10
线程数 1，当前线程 MainThread
```

- asyncio **所有协程跑在同一个线程里** → `threading.local` 按线程隔离，同线程 10 个协程共用一份 → 谁最后写谁赢
- `ContextVar` 按**执行上下文（Task）**隔离，每个 task 有自己的副本
- 一句话：**隔离单位不同——线程 vs 协程任务**。证据：`day7_evidence/exp_local_vs_contextvar.py`

### 2. 不加 `@wraps`，FastAPI 全接口 422（实测，不是背书）

装饰器返回 `wrapper(*args, **kwargs)`，FastAPI 用 `inspect.signature` 扫描路由签名来识别参数和 `Depends`——现在签名只剩 `*args, **kwargs`，被当成**必填 query 参数**：

```
GET /a → {'detail': [{'loc': ['query', 'args'], 'msg': 'Field required'}, ...]}
__name__: wrapper / __doc__: None / __wrapped__: False
operationId='wrapper_a_get'，summary='Wrapper'，description=None
```

严重度排序：**接口不可用 > OpenAPI 全糊（/docs 一排同名接口）> traceback 全是 wrapper 定位不了**。证据：`day7_evidence/exp_wraps_fastapi.py`

### 3. gather 的孤儿 vs TaskGroup 的取消（实测）

```
gather：异常抛给调用方，其余协程【不被取消】→ 0.2s 后孤儿照样跑完
TaskGroup：一个失败 → 其余【全部取消】→ 抛 ExceptionGroup（3.11+ 用 except* 捕获）
```

孤儿为什么危险：请求已经 500 返回给用户了，后台"写数据库/调第三方"的协程还在跑——浪费资源 + 可能写脏数据。**TaskGroup 的自动取消传播 = 结构化并发的实际含义。** 证据：`day7_evidence/exp_dataclass_gather.py`

### 4. dataclass 可变默认值在**类定义时**就炸（fail-fast）

```
ValueError: mutable default <class 'list'> for field items is not allowed: use default_factory
```

import 时立刻报错，不可能上线才发现"两个实例共享同一个列表"。和 Day1 `SECRET_KEY` 太短启动即拦是同一设计哲学：**错误越早暴露越便宜**。

### 5. SSE 与 `X-Accel-Buffering: no`

流式响应 `media_type="text/event-stream"` + `Cache-Control: no-cache` + `X-Accel-Buffering: no`。这个头是给 **Nginx** 看的：代理默认会把上游响应攒进缓冲区，SSE 小片段被囤住 → 用户端"卡半天一次性蹦"，流式白做。

### 6. 403 vs 404 的权衡（防枚举攻击）

项目源码注释原文："这里返回 403 而不是 404，是产品决策。若担心枚举攻击可改 404。"越权一律 404 的好处：攻击者拿一万个 UUID 扫，**无法区分"不存在"和"存在但不是你的"**（GitHub 私有仓库策略）；403 则给正常用户明确提示。**两种都正当，面试说出权衡就赢。**

---

## 三、今天踩的坑（认知坑为主）

| # | 坑 | 教训 |
|---|---|---|
| 1 | Q11 答反：pydantic 配置校验明明 Day2 亲手测过（启动时），闭卷时答"请求时" | **亲手做过 ≠ 记得原理**，实测过的坑要当天写"面试可说版本" |
| 2 | Q12 只答"改 repo 层"，漏了灵魂："services/api/schemas 不用改，因为只依赖方法签名" | 分层 = 换实现不动契约；这分 W7 亲手换 SQLAlchemy 收回 |
| 3 | 任务 D 误以为"没有切分直接 ready 很奇怪"——实际 `_parse_sync` 同步切分后才标 ready | 判断"项目做了什么"要看源码，不能只凭对生产流程的想象 |
| 4 | 自测题 Q9 写的是 VS Code，用户用 PyCharm | 教材也会过时，做题先审题 |
| 5 | pre-commit `end-of-file-fixer` 改了文件导致提交被中断 | 钩子动了文件必须重新 `git add` 再 commit |

---

## 四、遗留与衔接

| 遗留项 | 何时收 |
|---|---|
| Q12 分数（分层契约） | W7 换 SQLAlchemy，亲手做一遍 |
| 第四档 #02（埋坑版 API） | W2 开头 |
| tag `w01-done` | 今天由用户自己打 |
| 12 题未覆盖 Day6 新知识（注解契约/时钟粒度） | 靠第四档 + Day6 总结的自测 6 问补位 |

## 五、闭卷快问（3 题自检）

1. asyncio 里 `threading.local` 为什么会串号？换成什么？隔离单位分别是什么？
2. 忘加 `@wraps` 的装饰器挂在 FastAPI 路由上，最严重的后果是什么？机制是什么？
3. 项目里文档为什么创建完就是 ready？W11/W12 会怎么改？

<details>
<summary>答案</summary>

1. 所有协程同线程，local 按线程隔离 → 共用一份，最后写入者通吃（9/10 串号）。换 `ContextVar`。隔离单位：线程 vs 协程任务。
2. 全部接口 422。FastAPI 靠 `inspect.signature` 扫路由签名，`wrapper(*args, **kwargs)` 被解析成两个必填 query 参数，依赖注入失效；另 operationId 全变 wrapper、docstring 丢失。
3. `create()` 里同步调 `_parse_sync(row)`：`split_text(chunk_size=400, overlap=50)` 切分后 `update_status("ready", chunk_count)`，做完才返回。W11 改异步任务队列（会出现 pending→processing→ready 状态机），W12 补 embedding+pgvector。

</details>
