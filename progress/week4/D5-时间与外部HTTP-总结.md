# W4-D5 总结：时间与外部 HTTP 的测试（面试参考版）

> 用途：面试前直接翻。每个知识点按固定骨架写全——定义 → 为什么 → 怎么用 → 机制 → 面试问法 + 30 秒答案 → 追问链 → 易错表 → 关联。
> 日期：2026-10-31　状态：D5 ✅　第四档 #10 判定：1/4（详见文末）

---

## 0. 一句话主线

> **时间与外部世界是测试的两大不确定性来源：一个要能"拨表"，一个要能"编排"。**
> 工具（freezegun / respx）只是手段，判据仍是 D3 那句——被测逻辑别替换，外部世界才隔离。

---

## 1. 时间测试的三条路线

### 1.1 三条路线的取舍

| 路线 | 写法 | 速度 | 稳定性 | 适用 |
|---|---|---|---|---|
| 真实等待（错） | `await asyncio.sleep(0.15)` 赌过期 | 慢（硬吃时长） | 脆（CI 抖动翻红） | 只在极短窗口、无他法时 |
| 注入时钟 | `Cache(now=callable)`，测试传真时钟 | 快 | 稳 | **自己写的类**（推荐） |
| 全局冻结 | `freeze_time(...)` + `tick()` | 快 | 稳 | 时间藏在**第三方库内部**（jose 校验 exp、requests 超时计算） |

### 1.2 决策规则（一句话）

**自己能改设计的 → 注入时钟；够不着的 → freezegun 大锤。** 这与 D3 的 mock 边界判据同源：能改代码结构的，别用全局补丁；只有第三方的黑盒才值得大锤。

### 1.3 freezegun 怎么用

```python
# 两段式：签发与验证各冻一段（关键！冻在同一时刻 token 永不过期）
with freeze_time("2026-01-01 00:00:00"):
    token = create_access_token("u1")
with freeze_time("2026-01-01 13:01:00"):
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)

# 一段式 + 快进（等价于"睡了 61 分钟但不花时间"）
with freeze_time("2026-01-01 00:00:00") as ft:
    token = create_access_token("u1")
    ft.tick(timedelta(minutes=61))
```

### 1.4 机制：freezegun 补丁了什么

进入时替换 `datetime.datetime.now/utcnow`、`time.time`、`time.monotonic`、`time.perf_counter` 等一整族函数为虚拟时钟；出 with 自动还原（undo 机制）。

**本机实测（freezegun 1.5.5）**：`ft.tick(120)` 后 `time.monotonic()` 也前进 120 秒——**monotonic 同样被伪造**。所以写 TTL 缓存（内部用 `time.monotonic`）也能被 freezegun 控制，这是个容易搞反的点（很多人以为 monotonic 不受影响）。

### 1.5 实测发现：jose 的过期边界

| 验证时刻 | 结果 |
|---|---|
| 签发后 +59 分钟 | 有效 |
| **恰好 +60 分钟（exp == now）** | **仍然有效**（实测） |
| +61 分钟 | `UnauthorizedError` |

python-jose 的判定是 `exp` **严格小于**当前时刻才过期。写测试时把这种"非理所当然"的边界**钉成行为记录型测试**，升级依赖时行为一变立刻红。

### 1.6 面试问法

**Q：怎么测"token 一小时后过期"？**
> 30 秒：绝不真睡。自己的类注入时钟，测试拨假钟；时间在第三方库内部（jose 校验 exp）就用 freezegun 全局冻结——签发和验证各冻一段，中间 tick 快进。顺带把边界钉进测试：我们实测 jose 在 exp 恰好等于当前时刻时仍认为有效，+1 分钟才拒。

**追问链**：①"freezegun 会不会影响别的测试" → 出 with 即还原，但全局补丁影响面大，自己的类优先注入；②"monotonic 会被冻结吗" → 实测会（1.5.5）；③"为什么不干脆用超短 TTL 真等" → 慢 + 抖 + 测不了分钟级 TTL。

---

## 2. 外部 HTTP：respx

### 2.1 定义与机制

respx 在 **httpx 的 Transport 层**（请求发出前的最后一站）拦截：请求进来先查你注册的路由表，命中返回编排响应/异常；**没命中直接报 `AllMockedAssertionError`——默认所有真实出网被拦死**，测试想真联网必须显式 `real_http=True`。

### 2.2 三件套

```python
@respx.mock
async def test_x():
    route = respx.post("https://api.test/v1/chat/completions").respond(json={...})  # 200 + JSON
    route.respond(status_code=503)                              # 任意状态码
    route.mock(side_effect=httpx.ConnectTimeout("boom"))        # 抛异常
    assert route.called
    req = respx.calls.last.request                              # 账本：实际发出的请求
    assert req.headers["authorization"] == "Bearer sk-test"
```

**关于 `side_effect=httpx.ConnectTimeout` 的常见误解（#10 暴露的）**：这不是"取巧"，而是 respx 的**标准**用法。respx 根本不产生网络 I/O，没有"真实超时"可等——`side_effect` 抛出的异常与真实 I/O 超时**在调用方看来完全等价**（同一个异常类型、同一段 except 分支）。想测"超时被正确翻译/降级"，这就是唯一正确的写法。（真等 10 秒超时既慢又不稳，属于 #09 坑 3 的同类错误。）

### 2.3 路由精度：宽路由 = 什么都不验（#10 坑 1）

```python
respx.route(host="api.test")            # ← 匹配任何路径/方法：任何错路径都命中
respx.post("https://api.test/v1/chat/completions")   # ← 精确：路径错就 AllMockedAssertionError
```

实测教训：被测代码把路径写成 `/v1/chat`（少了 `/completions`，线上必然 404），**宽路由下 5 条测试全绿**——零症状。两条对策：①路由写精确 URL；②补路径断言 `assert req.url.path == "/v1/chat/completions"`。

**本质**：测试替身匹配得越宽，测试就越接近"什么都没验"。这和 D3 的"断言太宽"（`raises(AppError)`）、#08 的"选例不分叉"是同一族的三个变体——**宽松的入口 = 无效的测试**。

### 2.4 面试问法

**Q：外部 API 调用怎么测？**
> 30 秒：respx 在 httpx 传输层拦截，注册路由返回编排的响应或异常，默认拦死所有出网。断言重点是我方代码的处理——鉴权头、请求体拼装、错误翻译、降级——用 `route.called` 和 `respx.calls.last.request` 查账本。路由要写精确 URL，宽匹配会让错路径也通过。

**追问链**：①"模拟超时怎么弄" → `side_effect=httpx.ConnectTimeout`，与真实 I/O 超时在调用方等价；②"没匹配到路由" → `AllMockedAssertionError`；③"为什么不真调一次" → 花钱、CI 不稳、输出不确定不可断言。

---

## 3. 测试关注点分离（#10 的三个"伪坑"换来的）

### 3.1 一个测试只验一件事

| 测试 | 该断言什么 | 不该断言什么 |
|---|---|---|
| `test_request_carries_model_and_key` | 请求形状：路径、鉴权头、body 字段 | 返回值（由成功路径测试负责） |
| `test_ask_returns_answer` | 返回值与解析链 | 请求细节 |
| `test_degraded_on_timeout` | 降级文案**且**"降级不入缓存" | — |

**"这条测试没断言返回值"不等于缺陷**——如果另一条测试已经覆盖返回值，重复断言只会让失败信息变模糊（红了两条，不知道是拼装错还是解析错）。判断标准是**整个套件的覆盖率**，不是单条测试的完整度。

### 3.2 缺副作用断言才是真缺陷（#10 坑 4）

`Gateway.ask` 在 `except` 分支后无条件写缓存——**降级文案被缓存 60 秒**。实测：服务恢复后再问同一问题，仍返回兜底文案、`call_count` 停在 1（根本没重试）。原测试只断言 `== DEGRADED` 就结束了，绿。

**教训**：异常/降级分支的副作用（写缓存、改状态、发通知）比正常分支更需要断言，因为没人会盯着看。**"降级之后能不能恢复"是这类代码的头号线上问题。**

### 3.3 设计讨论 vs bug（判卷时的边界）

| 现象 | 是 bug 吗 | 说明 |
|---|---|---|
| 降级结果被缓存 | **是** | 服务恢复后用户拿不到真实答案，且无法自愈 |
| 缓存命中不刷新 TTL（绝对 TTL vs 滑动 TTL） | **不是** | 产品语义选择：绝对 TTL（固定过期）与滑动 TTL（访问续期）都是合法设计。要改是需求变更，不是测试坑 |
| `side_effect` 模拟超时 | **不是** | respx 标准用法，与真实 I/O 超时在调用方等价 |
| 请求形状测试未断言返回值 | **不是** | 关注点分离，返回值另有测试覆盖 |

**这条边界是工程判断力的核心**：能区分"我不同意这个设计"和"这是个 bug"，比能找出 bug 更难。

---

## 4. 易错点表

| # | 错误 | 正确 |
|---|---|---|
| 1 | 用 `sleep` 等时间窗口 | 注入时钟 / freezegun `tick` |
| 2 | 只冻"签发"或只冻"验证" | 两段式冻结 |
| 3 | 以为 `time.monotonic` 不受 freezegun 影响 | 实测会伪造（1.5.5） |
| 4 | 以为 `exp == now` 会拒绝 | 实测 jose 仍有效 |
| 5 | 路由写成 `host=` 宽匹配 | 精确 URL + 路径断言 |
| 6 | 以为 respx 会报"路由没被调用" | 自己 `assert route.called` |
| 7 | 以为 `side_effect` 模拟超时是取巧 | 这就是标准做法 |
| 8 | 异常分支不验副作用 | 降级不缓存、恢复后重试 |
| 9 | 断言私有字段/结构 | 断言行为（call_count、返回值） |
| 10 | 单条测试追求"什么都验" | 关注点分离，看套件整体覆盖 |

---

## 5. 30 秒答案集

1. **怎么测过期** → 注入时钟或 freezegun 两段式冻结 + tick。
2. **freezegun 补丁范围** → datetime 族 + time.time/monotonic/perf_counter。
3. **jose 边界** → exp 严格小于 now 才过期，恰好相等仍有效（实测）。
4. **怎么 mock 外部 HTTP** → respx 在 Transport 层拦截，默认拦死出网。
5. **怎么模拟超时** → `side_effect=httpx.ConnectTimeout`，与真实等价。
6. **路由写多宽** → 精确 URL；宽匹配让错路径也通过。
7. **断言请求发出没** → `route.called` / `respx.calls.last.request`。
8. **降级怎么测** → 断言文案 + 断言"未被缓存、恢复后重试成功"。
9. **私有字段能断言吗** → 不能，重构即碎；断言行为。
10. **一个测试验几件事** → 一件；整体覆盖靠套件。

---

## 6. 白板手写靶

1. 两段式冻结测 JWT 过期（含 `pytest.raises`）。
2. respx 成功路径 + 账本断言（鉴权头、body 字段、路径）。
3. `side_effect` 测超时 + 降级断言。
4. 注入时钟的构造函数签名（`now: Callable[[], float] = time.monotonic`）。

---

## 7. 今日踩坑实录

| # | 现象 | 处理 |
|---|---|---|
| 1 | `test_llm_client.py` 里 `import json` 排在 respx 后 | ruff I001 修复（import 排序统一由工具管） |
| 2 | `llm_client.py` 触发 ASYNC109（async 函数带 timeout） | 语义不同（httpx 连接超时 ≠ asyncio 超时域），`noqa` + 注释说明 |
| 3 | 我出 #10 时自检红了：`assert not gateway._cache` 失败 | 缓存过期淘汰是**惰性**的（下次 ask 才清），断言"空闲时缓存为空"必然红——改成"过期后再 ask 会重新请求"（`call_count == 2`）。**出题人也要跑自己的题** |

---

## 8. 第四档轨迹 #05 → #10

| 卷 | 主题 | 判定 | 一句话 |
|---|---|---|---|
| #05 | D1 验收 | 4/4 | — |
| #06 | D2 验收 | 3/4 | 漏 monkeypatch stub 坑 |
| #07 | 假测试套件 | 3/4 | 漏 stub 换被测函数 |
| #08 | 测试为什么没红 | 2/4 | 位置全对但答的是 bug 不是"测试为何放过" |
| #09 | 慢与脆 | 2.5/4 | 隔离✓、零症状时钟✓；漏 await 指错行、sleep 脆没找到 |
| #10 | 绿得可疑 | **1/4** | 只命中"降级被缓存"（且说的是代码 bug 不是测试缺口）；漏宽路由/路径错、sleep、私有断言；另有 3 条误判 |

**#10 详情与规律**：
- **命中 1/4**：`Gateway.ask` 降级结果被缓存 —— 这是 4 个坑里唯一被找到的（坑 4 的代码侧），但没有回答"测试为何绿"（缺副作用断言）。
- **漏掉的 3 个**：①宽路由掩盖 `/v1/chat` 路径错（**本卷头号坑，零症状，需要读 API 契约**）；②`sleep(0.12)` 真等（上一卷刚考过的同一个坑）；③断言私有 `_cache`。
- **误判 3 条**：①"命中不刷新 TTL"—— 绝对 TTL vs 滑动 TTL 是设计选择不是 bug；②"请求形状测试未断言返回值"—— 关注点分离，返回值另有测试；③"`side_effect` 模拟超时是取巧"—— 这是 respx 标准用法，与真实超时在调用方等价。
- **规律（第三次同型）**：**一直在用"代码 review"的视角回答，而不是"测试设计"的视角**。#08/#09/#10 三次都是如此。而误判的三条恰好都是"把设计选择当成 bug"——说明判断标准还没建立。改进动作：答题前先问三句——**这条测试能杀死哪种 bug？它搬到 CI 上还稳吗？这个断言绑的是行为还是实现？**

---

## 9. 闭卷自测（先自己答，再展开）

<details><summary>Q1：为什么"sleep 等过期"是错的？给出两个独立理由，并说出替代方案。</summary>

①慢：硬吃真实时长，分钟级 TTL 不可行；②脆：CI 调度抖动让窗口不稳，flaky。替代：注入时钟（自己的类）或 freezegun 两段式冻结 + tick（第三方内部）。

</details>

<details><summary>Q2：freezegun 会伪造 time.monotonic 吗？这对 TTL 缓存测试意味着什么？</summary>

实测 1.5.5：会（tick 后 monotonic 同步前进）。意味着用 monotonic 计算 deadline 的缓存也能被 freezegun 控制，可放心用冻结测 TTL，不必为此改成注入时钟。

</details>

<details><summary>Q3：respx 路由写 `host=` 有什么风险？怎么补救？</summary>

匹配任意路径/方法，被测代码把路径写错（如 `/v1/chat` 少了 `/completions`）测试仍全绿——零症状。补救：路由写精确 URL，或加 `assert req.url.path == "..."` 断言。

</details>

<details><summary>Q4：`side_effect=httpx.ConnectTimeout` 算"真实模拟超时"吗？为什么？</summary>

算。respx 不产生网络 I/O，没有真实超时可等；抛出的异常与真实 I/O 超时在调用方完全等价（同类型、同 except 分支）。这是标准做法，不是取巧。

</details>

<details><summary>Q5：降级/异常分支最容易被漏掉的断言是什么？举本项目例子。</summary>

副作用断言。`Gateway.ask` 在 except 后仍写缓存，导致降级文案被缓存 60 秒、服务恢复后仍返回兜底且不重试。要断言"降级不入缓存、恢复后重试成功"（`call_count == 2`）。

</details>

<details><summary>Q6：断言 `gateway._cache["q5"]` 有什么问题？换成什么？</summary>

绑死私有字段名、key 形式、value 结构，重构即碎（行为没变测试却红）。换成行为断言：`route.call_count == 1`（第二次没发请求）、返回值正确。

</details>

<details><summary>Q7：绝对 TTL 和滑动 TTL 哪个对？测试该怎么写？</summary>

都不是 bug，是产品语义选择：绝对 TTL（创建即固定过期）利于控制内存与新鲜度；滑动 TTL（访问续期）利于热数据。测试按选定的语义写，改语义是需求变更。能分清"设计分歧"与"缺陷"是工程判断力。

</details>
