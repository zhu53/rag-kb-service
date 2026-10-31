# W4-D5 教材：时间与外部 HTTP 的测试（零基础版）

> 假设你完全没写过时间相关的测试，也没 mock 过网络请求。所有命令与输出都来自你本机（Python 3.11 / freezegun 1.5.5 / respx 0.23.1 / pytest-asyncio 1.4.0），已实测。
> 依赖已装好：`uv add --dev freezegun respx`（已执行，pyproject 的 dev 组里多了这两行）。

---

## 1. 痛点场景：为什么需要这两个工具

### 痛点一：时间没法"快进"（#09 坑 3 的续集）

第四档 #09 里你见过这段测试：

```python
await cache.put("session:ttl", "gone", ttl=0.05)
await asyncio.sleep(0.15)          # ← 真睡 150ms
assert await cache.get("session:ttl") is None
```

它有三个死穴：

| 死穴 | 后果 |
|---|---|
| 慢 | 每个到期用例至少睡 150ms，测试套件被硬拖 |
| 脆 | CI 机器一忙，`sleep(0.15)` 可能实际只轮到 90ms，**测试随环境翻红翻绿**（flaky） |
| 测不了真实场景 | TTL 的真实取值是分钟/小时级——"30 分钟过期"你总不能真睡 30 分钟 |

**本质问题**：测试想控制"现在是几点"，但"现在"来自 `datetime.now()` / `time.time()`，你的代码控制不了它。

### 痛点二：外部 HTTP 没法真调

马上要写 LLM 客户端（调 `api.openai.com`）。测试时：

- 真调 → 要 API Key（花钱）、要网（CI 不稳定）、LLM 输出每次不同（**不可断言**）
- 不调 → 客户端的请求构造、鉴权头、错误翻译、超时处理**全都没被测过**

**本质问题**：外部世界（慢的、花钱的、不确定的）不能进测试——这正是 D3 mock 边界判据的"外部世界"一栏。

今天的两个工具，各解决一个痛点：

| 工具 | 解决 | 手段 |
|---|---|---|
| freezegun | 时间不可控 | **把全项目的钟拨到你指定的时刻** |
| respx | 外部 HTTP 不可控 | **在 httpx 的传输层拦截请求，返回你编排的假响应** |

---

## 2. 最小可跑示例（5 分钟，亲手跑）

不用项目代码，先感受两个工具的最小形态。

**示例 1：freezegun**——新建 `tests/test_freeze_demo.py`：

```python
from datetime import datetime, timedelta
from freezegun import freeze_time


def test_time_is_frozen():
    with freeze_time("2026-01-01 12:00:00"):
        assert datetime.now() == datetime(2026, 1, 1, 12, 0, 0)


def test_time_can_tick():
    with freeze_time("2026-01-01 12:00:00") as ft:
        ft.tick(timedelta(minutes=30))
        assert datetime.now() == datetime(2026, 1, 1, 12, 30, 0)
```

跑：`pytest tests/test_freeze_demo.py -v` → 2 passed。

**示例 2：respx**——新建 `tests/test_respx_demo.py`：

```python
import httpx
import respx


async def test_http_is_mocked():
    with respx.mock:
        respx.post("https://api.example.com/v1/chat").respond(
            json={"reply": "假的"}
        )
        async with httpx.AsyncClient(base_url="https://api.example.com") as client:
            resp = await client.post("/v1/chat", json={"q": "hi"})
        assert resp.json() == {"reply": "假的"}
```

跑 → 1 passed。**没有任何网络请求发生**——`https://api.example.com` 这个域名根本不存在。

跑通这两个，今天的思想就到位了：**时间被你拨，网络被你编排**。

---

## 3. freezegun 逐层展开（以你项目的 JWT 为例）

### 3.1 背景：你的 token 现在完全没被测过

`core/security.py` 签发 JWT 时写入 `exp`（过期时刻 = 签发时刻 + 60 分钟），`decode_access_token` 靠 python-jose 校验 `exp`。**"token 过期会被拒绝"这条安全关键行为，目前零测试覆盖**。为什么一直没测？因为没有 freezegun 时，你只能签一个"1 秒后过期"的 token 再 `sleep(2)`——#09 坑 3 的老路。

### 3.2 正确姿势：冻结 → 签发 → 快进 → 验证

```python
from freezegun import freeze_time


def test_expired_token_rejected():
    with freeze_time("2026-01-01 12:00:00"):       # 把钟拨到签发时刻
        token = create_access_token("u1")

    with freeze_time("2026-01-01 13:01:00"):       # 再把钟拨到过期后 1 分钟
        with pytest.raises(UnauthorizedError):
            decode_access_token(token)
```

实测输出（本机）：**passed**。

三种冻结方式一览：

| 写法 | 适用 |
|---|---|
| `@freeze_time("2026-01-01 12:00:00")` 装饰器 | 整个测试都在同一时刻 |
| `with freeze_time(...):` 上下文 | 只在块内冻结（上面的"签发/快进"两段式必须用这个） |
| `ft.tick(timedelta(minutes=30))` | 块内快进，等价于"睡 30 分钟但不花时间" |

### 3.3 两个实测发现（网上教程不会告诉你）

**发现 1：恰好 +60 分钟的 token 仍然有效。**

```python
with freeze_time("2026-01-01 12:00:00"):
    token = create_access_token("u1")
with freeze_time("2026-01-01 13:00:00"):   # 恰好过了 60 分钟
    decode_access_token(token)              # ← 实测：没抛异常！
```

本机实测：**13:00:00 解码成功，13:01:00 才拒绝**。python-jose 的过期判定是 `exp` **严格小于**当前时刻才算过期（`exp == now` 算还没到）。这是行为记录型测试的价值：**不是所有行为都是"理所当然"的，把它钉在测试里，升级 jose 版本时如果边界变了你会立刻知道**。

**发现 2：freezegun 对 async 测试同样有效**（它补丁的是 `datetime`/`time` 模块本身，和事件循环无关）。

### 3.4 机制：freezegun 到底干了什么

`freeze_time` 进入时，把 `datetime.datetime.now()`、`time.time()`、`time.monotonic()` 等一整族函数**替换成基于虚拟时钟的实现**——全进程生效。所以：

- 你项目代码里的 `datetime.now(UTC)`（签发 exp）和 jose 内部的过期比较，读的都是**同一台假钟** → 完美自洽
- 代价：影响面是全局的。冻结期间所有库的时间都假了，测试结束后 freezegun 自动还原（它有 undo 机制）

### 3.5 两条路线对比：全局冻结 vs 注入时钟

| | freezegun（全局冻结） | 注入时钟（构造函数传 `now`） |
|---|---|---|
| 写法 | 装饰器/上下文，零侵入 | `TTLCache(now=callable)` 之类的构造参数 |
| 影响面 | 全进程所有时间调用 | 只有被注入的那个类 |
| 适用 | 第三方库内部读时间（jose）→ **只能用这个** | 自己的代码 → 更推荐（显式、依赖清晰） |
| D3 语言的对应 | 全局 monkeypatch | 构造注入 |

**决策规则**：时间在**自己写的类**里 → 优先注入时钟（D3 的 mock 边界判据：自己能改设计的，别用大锤）；时间藏在**第三方库内部**（jose 校验 exp）→ freezegun 是唯一解。

---

## 4. respx 逐层展开（为 LLM 客户端铺路）

### 4.1 项目现状：配置已预留，客户端还没有

`core/config.py` 里已经躺了三个字段：

```python
llm_api_key: str | None = None
llm_base_url: str = "https://api.openai.com/v1"
llm_model: str = "gpt-4o-mini"
```

今天练习就写 `LLMClient`——W14 接真实 LLM 前的占位实现，`chat(prompt)` 发一次 HTTP 请求拿回文本。它给了 respx 一个**真实靶子**（有鉴权头、有请求体、有错误翻译，全是要测的东西）。

### 4.2 respx 三件套

```python
@respx.mock                                  # 装饰器形式（也有 with respx.mock: 形式）
async def test_chat_success():
    route = respx.post("https://llm.test/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "你好，世界"}}]}
    )
    client = LLMClient(base_url="https://llm.test/v1", api_key="sk-test")
    assert await client.chat("hi") == "你好，世界"

    assert route.called                      # 这条路由被调用过
    assert respx.calls.call_count == 1       # 总调用次数
    sent = respx.calls.last.request          # ← 拿到"实际发出的请求"
    assert sent.headers["Authorization"] == "Bearer sk-test"   # 鉴权头实测可断言
```

本机实测全过，`Authorization: Bearer sk-test` 确实被抓到了。**respx 不只给假响应，还把"你发了什么"记在账本上**——这就是 D3 spy 思想在网络层的化身。

编排响应的三种武器：

```python
route.respond(json={...})                          # 200 + JSON 体
route.respond(status_code=500)                     # 任意状态码
route.mock(side_effect=httpx.ConnectTimeout("x"))  # 抛异常（模拟超时/断连）
```

### 4.3 实测发现：respx 默认不检查"注册了却没调用"的路由

```python
@respx.mock(assert_all_called=True)
async def test_xxx():
    respx.post("...").respond(json={})
    # 从不调用这条路由
```

老教程说 `assert_all_called=True`（默认）会在路由没被调用时报错。**本机 respx 0.23.1 实测：显式传 `assert_all_called=True` 也 1 passed，不报错**。结论：**想断言"请求确实发出了"，自己写 `assert route.called`，别指望 respx 替你查**。又一次：教程结论必须实测，包括这条教材自己。

### 4.4 机制：respx 在哪一层拦截

httpx 的请求链：`AsyncClient` → **Transport（传输层）** → 真实网络。respx 做的事：冻结期间把 Transport 换成自己的**路由匹配器**——请求进来先查你注册的路由表，命中就返回编排的响应/抛编排的异常，没命中就报 `AllMockedAssertionError`（**默认所有真实出网请求都被拦死**，测试想真联网反而要显式声明 `respx.mock(real_http=True)`）。所以测试绝无可能意外打到真 API。

---

## 5. flaky 测试排查思路（今天知识的应用题）

面试常问："你们有没有测试时好时坏？怎么排查？"三大源头，今天各补一件武器：

| 源头 | 症状 | 武器 |
|---|---|---|
| **时间** | 跨午夜/月末挂、CI 慢机器上挂 | freezegun 拨表；绝不 `sleep` 等时间窗口（#09 坑 3） |
| **顺序/共享状态** | 单跑绿、全跑红（或反之） | D4 的"谁种谁收"；用 `-p no:randomly` 前先怀疑自己 |
| **网络/外部** | 依赖第三方可用性 | respx 拦截；外部世界不进测试（D3 判据） |

排查口诀：**先单跑复现 → 再对调顺序 → 最后看环境差异（时间/网络/机器速度）**。测试随机化工具（pytest-randomly）是主动暴露顺序依赖的手段——它能杀死的测试，本来就是脆的。

---

## 6. 易错点表

| # | 错误 | 正确 | 备注 |
|---|---|---|---|
| 1 | 用 `sleep` 等时间窗口 | freezegun 拨表 / 注入时钟 | #09 坑 3 正解 |
| 2 | `freeze_time` 只包了"签发"没包"验证" | 签发和验证各冻一段（两段式） | 冻在"未来"里签发，exp 就错了 |
| 3 | 以为 `exp == now` 会拒绝 | 实测 jose：`exp == now` 仍有效 | 行为钉进测试 |
| 4 | 以为 respx 会报"路由没调用" | 自己 `assert route.called` | 0.23.1 实测 |
| 5 | 忘记 respx 默认拦死所有出网 | 想放行真请求才用 `real_http=True` | 测试默认不该出网 |
| 6 | 用 freezegun 测自己类的时间逻辑 | 自己的类注入时钟，freezegun 留给第三方 | mock 边界判据 |
| 7 | 断言假响应内容 | 断言的应是**我方代码的处理**（翻译/拼装/头），不是假数据本身 | 别测假货 |

---

## 7. 命令速查

```python
# freezegun
with freeze_time("2026-01-01 12:00:00") as ft:   # 冻结
    ft.tick(timedelta(minutes=30))                # 块内快进
# 出了 with 自动还原

# respx
@respx.mock                                       # 装饰器
async def test_x():
    route = respx.post(url).respond(json={...})   # 注册路由 + 200
    route.respond(status_code=503)                # 改状态码
    route.mock(side_effect=httpx.ConnectTimeout())# 抛异常
    route.called                                  # 是否被调用
    respx.calls.last.request.headers["Auth"]      # 查实际请求
```

```powershell
pytest tests/test_jwt_expiry.py tests/test_llm_client.py -v -W error::RuntimeWarning
```

---

## 8. 动手实验（跑之前先猜，猜完再跑）

1. 把 `test_expired_token_rejected` 的第二个 freeze 改成 `13:00:00`（恰好 60 分钟），跑之前猜：抛不抛 `UnauthorizedError`？
2. 在 respx 测试里注册两条路由：`/chat/completions` 和 `/models`，但只调 chat，猜：测试挂不挂？`respx.calls.call_count` 是几？
3. 把 `LLMClient.chat` 里的 `await client.post(...)` 改成 `client.post(...)`（漏 await），跑 `pytest -W error::RuntimeWarning`，猜：绿还是红？哪一步红？
4. respx 路由写成 `respx.post("https://llm.test/v1/wrong/path")`，猜：报什么错？

（答案不写死在这里——全部自己跑一遍对答案，把"猜错的那条"记到当日总结里。）

---

## 9. 今日练习（任务书）

两个文件，验收标准：`pytest -W error::RuntimeWarning` 全绿 + 全量回归不破。

### 练习 A：`tests/test_jwt_expiry.py`（freezegun，4 测）

1. `test_fresh_token_roundtrip`——冻结时刻签发并解码，`sub` 能读回来
2. `test_expired_token_rejected`——两段式冻结，+61 分钟 → `pytest.raises(UnauthorizedError)`
3. `test_token_valid_at_59min`——+59 分钟仍能解码（**别只测坏的一侧**）
4. `test_boundary_exactly_60min_still_valid`——恰好 +60 分钟，断言**不抛异常**（把实测发现钉进测试，注释写明这是 jose 的行为记录）

### 练习 B：`src/kb_service/services/llm_client.py` + `tests/test_llm_client.py`（respx，4 测）

`LLMClient` 骨架（构造注入 base_url/api_key/model——构造注入主题再现）：

```python
"""极简 LLM 客户端占位（W14 换真实流式实现）。"""

from __future__ import annotations

import httpx


class LLMClient:
    """同步整段式问答：发一次请求，拿回完整文本。"""

    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(self, prompt: str, timeout: float = 10.0) -> str:
        """POST /chat/completions，返回 assistant 文本。"""
        # TODO(你写)：AsyncClient(base_url, headers 鉴权) → post → raise_for_status
        #  → 取 resp.json()["choices"][0]["message"]["content"]
        raise NotImplementedError
```

测试 4 条（全部 `@respx.mock` + 假域名，永不真出网）：

1. `test_chat_success`——假响应 `choices[0].message.content`，断言返回值正确
2. `test_request_shape`——`route.called` + `respx.calls.last.request` 断言三件事：`Authorization` 头 = `Bearer <api_key>`、请求体里 `model` 字段、`messages[0].content` = prompt
3. `test_500_raises_status_error`——`respond(status_code=500)` → `pytest.raises(httpx.HTTPStatusError)`
4. `test_timeout_raises`——`mock(side_effect=httpx.ConnectTimeout("boom"))` → `pytest.raises(httpx.ConnectTimeout)`

提示：先写练习 A（更短），练 A 的"两段式冻结"手感；B 的断言 2 是 respx 账本的核心用法。卡住喊我，一次一层。

---

## 10. 面试问法

**Q：怎么测"token 一小时后过期"这种时间逻辑？**
> 30 秒：绝不真睡。分两条路：时间逻辑在自己类里，就构造注入一个时钟函数，测试里拨假时钟；时间藏在第三方库内部（如 jose 校验 JWT 的 exp），用 freezegun 全局冻结——签发和验证各冻一段，中间 tick 快进一小时。顺带能把边界行为钉进测试：我们实测过 jose 在 exp 恰好等于当前时刻时仍认为有效。

**Q：外部 API 调用怎么测？**
> 30 秒：respx 在 httpx 传输层拦截，注册路由返回编排的响应或异常，测试默认无法真出网。断言重点是"我方代码的处理"——鉴权头、请求体拼装、错误翻译——用 `route.called` 和 `respx.calls.last.request` 查账本，而不是复述假数据。

**追问链**：①"freezegun 会不会影响别的测试？" → 出 with 即还原；但全局补丁影响面大，自己的类优先注入时钟。②"respx 没匹配到路由会怎样？" → AllMockedAssertionError，默认绝不真出网。③"flaky 测试怎么排查？" → 单跑复现 → 对调顺序 → 看时间/网络/机器差异三大源。④"为什么不真调一次 LLM？" → 花钱、CI 不稳、输出不确定不可断言——外部世界的三宗罪。

---

## 11. 闭卷自测（先自己答，再展开）

<details><summary>Q1：为什么"睡 150ms 验证过期"是错的？说出两个独立的理由。</summary>

①慢：每个用例硬吃 150ms；②脆：CI 机器繁忙时 sleep 实际时长不定，窗口可能不够，测试随环境翻红翻绿（flaky）。根本解法是让"现在几点"可控：注入时钟或 freezegun。

</details>

<details><summary>Q2：freezegun 和注入时钟各适合什么场景？决策规则是什么？</summary>

时间在自己写的类里 → 注入时钟（显式、影响面小）；时间藏在第三方库内部（jose 校验 exp）→ freezegun 全局冻结是唯一解。规则：自己能改设计的用注入，够不着的用大锤。

</details>

<details><summary>Q3：respx 没匹配到路由时发生什么？怎么让测试允许真出网？</summary>

抛 AllMockedAssertionError——默认所有真实出网请求都被拦死。要放行需显式 `respx.mock(real_http=True)`。

</details>

<details><summary>Q4：respx 测试里怎么断言"请求确实发出了、头和体都正确"？</summary>

`assert route.called`；`respx.calls.last.request` 拿到实际请求对象，断言 `headers["Authorization"]`、`json()["model"]` 等。注意 0.23.1 实测不会自动报"注册了却没调用"，必须自己断言。

</details>

<details><summary>Q5：测 JWT 过期时，为什么"签发"和"验证"要各自冻一段，而不是冻在一个时刻里？</summary>

签发时刻决定 exp（iat + 60min），验证时刻决定"现在"。冻在同一点 token 永远不过期。正确姿势：冻在 T 签发 → 出 with → 冻在 T+61min 验证；或冻一段内用 ft.tick 快进。

</details>

<details><summary>Q6：LLM 输出每次都不一样，为什么假响应反而让测试"更有意义"？</summary>

测试断言的从来不是 LLM 的答案，而是我方代码的处理链：请求拼装对不对、鉴权头对不对、错误翻译对不对、返回值提取对不对。假响应把"输出不确定"钉成确定，这些处理链才可断言——这就是 mock 边界判据的"外部世界才隔离"。

</details>
