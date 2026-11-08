# W6-D3 教材 · Pydantic v2 深入：校验、序列化、Field 约束（零基础版）

> **前置**：D2 的六层洋葱。今天不碰中间件，只回答一个问题：
> **一个字段从 JSON 进来、到存库、再回到 JSON，中间被谁改过几次？**
>
> **本教材所有输出都是本机实测**：pydantic 2.14.1 / fastapi 0.150.0 / Python 3.11.17。
> 凡与网上文章冲突，以本文的输出为准（v1 和 v2 的 API 差异很大，网上大量文章还是 v1 的）。

---

## 零、先看主线：一个字段的四站

> 全篇地图，先扫 3 分钟。每读完一节回来对一次位置。

D3 的全部内容可以压成一句话：

> **进方向叫校验，出方向叫序列化。两个方向都可能"悄悄改数据"。**

```
【第 1 站】客户端发来 JSON
     {"name": "kb", "doc_count": "3"}
        ↓
【第 2 站】校验（validate）——发生在 ⑥ 依赖/参数解析，D2 说的 422 就在这
     · 缺字段？类型不对？超长？→ 收集错误 → ValidationError → 422
     · lax 模式下 "3" 会被换成 3，true/"yes" 会被换成 True
        ↓
【第 3 站】你的模型实例（BaseModel 对象）
     KB(name='kb', doc_count=3)   ← 到这里类型已经被"归一化"了
        ↓
【第 4 站】序列化（serialize）——响应回去时按 response_model 再走一遍
     · model_dump()：转成 dict，**只含模型声明的字段**（`extra="allow"` 时才会带额外的）
     · response_model：**只保留 schema 里声明的字段**，多余的静默丢弃
     · 声明成 A 却返回 B → ResponseValidationError → 500（不是 422）
```

### 这条双向箭头就是 D3 的骨架

| 知识点 | 挂在线上哪 |
|---|---|
| `Field` 约束（长度/范围） | 第 2 站：先过类型，再过约束 |
| lax / strict | 第 2 站：**要不要帮你猜类型** |
| 默认值不校验 | 第 2 站：没传的时候**根本不校验** |
| `alias` | 第 2 站与第 4 站：两头都可能换名字 |
| `field_validator` | 第 2 站：类型过了之后跑你的逻辑 |
| `model_config` | 第 2 站（extra/strict）与第 4 站（from_attributes） |
| `model_dump` 的开关 | 第 4 站：哪些字段出去、叫什么名字 |
| `response_model` | 第 4 站：**过滤 + 二次校验**，两个身份 |

### 每节的位置自查

读完一节问一句：**这一节讲的是"进"、"出"、还是"两头都管"？**

- `Field` / lax-strict / validator / alias → 进（第 2 站）
- `model_dump` / `response_model` / `from_attributes` → 出（第 4 站）
- `model_config` → 两头都有

**答不出来，那一节还没读进去。**

---

## 一、痛点场景：没有 pydantic 的世界

### 1.1 手写校验长什么样

```python
def create_kb(payload: dict):
    if "name" not in payload:
        return {"code": 400, "msg": "name 必填"}
    name = payload["name"]
    if not isinstance(name, str):
        return {"code": 400, "msg": "name 必须是字符串"}
    if len(name) == 0 or len(name) > 100:
        return {"code": 400, "msg": "name 长度 1-100"}
    if "doc_count" in payload and not isinstance(payload["doc_count"], int):
        return {"code": 400, "msg": "doc_count 必须是整数"}
    ...
```

四个问题，一个比一个贵：

| 问题 | 后果 |
|---|---|
| 每个接口抄一遍 | 40 个接口 = 40 份几乎一样的 if |
| 错误格式各写各的 | 前端要为每个接口写一套解析 |
| 校验散在业务里 | service 层没法单测（得先造 dict）、CLI 复用不了 |
| **改一处规则要改 N 处** | 名字上限从 100 改成 64，漏一个接口就是线上不一致 |

### 1.2 pydantic 把这件事挪到"类定义"上

```python
class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

KBCreate(name="kb")            # 成了 → 一个带类型的对象
KBCreate(name="")              # 不了 → ValidationError，一条一条列出来
```

**校验规则写在类型声明里，只写一遍。** FastAPI 拿这个类做两件事：请求进来时校验、生成 OpenAPI 文档时当 schema。

### 1.3 但"校验"只是它一半的活

大多数人只知道 pydantic 校验入参，于是踩下面这些坑：

- 数据库查出来的对象直接 `return`，结果**多返回了密码字段**
- 明明声明 `score: int`，实际返回字符串，客户端拿到 `null`
- `exclude_none=True` 一开，前端抱怨"我传的空字符串怎么没了"

**这些都发生在第 4 站（出方向）**，而第 4 站比第 2 站更容易被忽略——因为第 2 站会报错，第 4 站只会**静默地改**。

---

## 二、最小可跑示例（5 分钟亲手跑）

新建任意文件 `d3_demo.py`：

```python
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class KB(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=10)]
    doc_count: int = 0

    @field_validator("name")
    @classmethod
    def no_space_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name 不能全是空格")
        return v.strip()


print("1)", KB(name="  rag  "))
print("2)", KB(name="kb", doc_count="3").doc_count, type(KB(name="kb", doc_count="3").doc_count))

for bad in [{"name": ""}, {"name": "x" * 11}, {"name": "   "}, {"name": "kb", "oops": 1}]:
    try:
        KB(**bad)
    except ValidationError as e:
        err = e.errors()[0]
        print(f"3) {bad} -> type={err['type']}, loc={err['loc']}")
```

跑法：

```powershell
# Windows PowerShell（在 kb-service 下，用项目解释器）
& .\.venv\Scripts\python.exe C:\path\to\d3_demo.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe /tmp/d3_demo.py     # 真 Linux 上是 .venv/bin/python
```

**实际输出（本机实测，逐字）**：

```
1) name='rag' doc_count=0
2) 3 <class 'int'>
3) {'name': ''} -> type=string_too_short, loc=('name',)
3) {'name': 'xxxxxxxxxxx'} -> type=string_too_long, loc=('name',)
3) {'name': '   '} -> type=value_error, loc=('name',)
3) {'name': 'kb', 'oops': 1} -> type=extra_forbidden, loc=('oops',)
```

四个反直觉的地方，先记住，后面逐个解释：

1. **`"  rag  "` 变成 `"rag"`** —— validator 里 `strip()` 的返回值就是最终值。
2. **`doc_count="3"` 变成 `3`** —— lax 模式帮你转类型。
3. **四条错误各有 `type` 和 `loc`**，前端靠 `loc` 定位字段、靠 `type` 做多语言。
4. **`x` 11 个字符报 `string_too_long`**，但报错里**没有** value（只有 `ctx` 里的上限）。

---

## 三、概念逐层

### 3.1 `BaseModel` 到底是什么

```python
class KB(BaseModel):
    name: str
```

这 2 行在**类创建的那一刻**就做完了这些事：

1. 读 `__annotations__`，收集字段名和类型（`model_fields` 就是这张表）
2. 把字段声明编译成一份 **core schema**（一个 dict 描述"怎么校验这个类型"）
3. 交给 Rust 实现生成一个校验器 `__pydantic_validator__` 和一个序列化器 `__pydantic_serializer__`

所以**校验发生在 `KB(...)` 这一刻，而不是 import 的时候**；类只是一个"配方"，实例是"按配方校验过的结果"。

```python
KB.model_fields          # {'name': FieldInfo(annotation=str, required=True)}
KB(name=1)               # ValidationError（1 不会被悄悄当字符串）
```

> 术语：**core schema** 是一棵描述结构的树（`model` → `model-fields` → `str`），不是 Python 类。它才是真正被执的东西。

### 3.2 `Field` 约束：两种写法与报错的形状

两种写法等价，**推荐 `Annotated`**（可以把约束抽成类型别名复用）：

```python
# 写法 A：默认值位置塞 Field（老写法，项目现状）
name: str = Field(min_length=1, max_length=100)

# 写法 B：Annotated（推荐）
name: Annotated[str, Field(min_length=1, max_length=100)]
```

为什么推荐 B：`name: str` 这句话在 IDE / mypy 眼里就只是 `str`，而 A 里的 `Field(...)` 会被当成默认值——**默认值是 None 时就会撒谎**（见 3.4）。

常用约束（都实测过）：

| 类型 | 参数 | 不合规时的 `type` |
|---|---|---|
| `str` | `min_length` / `max_length` | `string_too_short` / `string_too_long` |
| `int` | `gt` / `ge` / `lt` / `le` | `greater_than` / `less_than` 等 |
| `int` / `str` | `strict=True`（单字段） | `int_type` |
| 任意 | `description`（只进 OpenAPI，不校验） | — |
| 任意 | `default_factory`（可变默认值） | — |

实测报错形状：

```
name=''          -> type=string_too_short, ctx={'min_length': 1}, msg=String should have at least 1 character
name='abcdefgh'  -> type=string_too_long, ctx={'max_length': 5}, msg=String should have at most 5 characters
```

> 注意 `ctx` 里是**约束值**，不是"你传的值"。你传的值在 `input` 里。前端要做"最长 100 字，当前 137 字"这种提示，得自己把 `input` 的长度和 `ctx.max_length` 拼起来。

`str | None` 上写 `max_length` 会怎样？实测：`None` 正常通过，字符串超长照样 `string_too_long`——约束只作用在字符串分支上。

### 3.3 lax vs strict：它到底帮不帮你猜

**lax（默认）**：尽力转。**strict**：只认原类型。

实测：

```
模型 A(n: int, flag: bool)
  A.model_validate({'n': '18', 'flag': 'yes'}) -> n=18 flag=True        ← 字符串转成了 int / bool

strict=True 的模型：
  {'n': '18'} -> type=int_type, msg=Input should be a valid integer
```

三种开法，粒度不同：

```python
# 1) 整模型
class S1(BaseModel):
    model_config = ConfigDict(strict=True)

# 2) 单个字段（最常用）
class S2(BaseModel):
    n: Annotated[int, Field(strict=True)]

# 3) 单次调用
S2.model_validate({"n": "18"}, strict=True)
```

**什么时候该用 strict**：给内部服务用的 API（"我不猜，你的 SDK 应该发对类型"）、幂等键/金额这类**不能被隐式转换**的字段。对外 API 保持 lax——前端 `"3"` 和 `3` 混着传是常态。

> `"yes"` → `True` 这件事要特别留意：它能转，就意味着**客户端传 `"no"` 也会被当成 `False`**，而传 `"maybe"` 会报错。lax 的边界是白名单，不是"随便转"。

### 3.4 默认值不参与校验（最会骗人的一条）

```python
class B(BaseModel):
    name: str = Field(default=None)      # 类型是 str，默认给了 None
```

实测三行：

```
B()                -> name=None          ← 构造成功，值就是 None
B(name=None)       -> string_type        ← 显式传 None 被拒
validate_default=True -> string_type     ← 连默认值也校验，构造就炸
```

这就是"默认值不校验"：**没传的时候 pydantic 直接把默认值塞进去，不走校验器**。于是：

- 类型注解说 `str`，运行时是 `None`
- 存进数据库就是 NULL
- 序列化出去前端拿到 `null`，而 OpenAPI 里写的是 `string` → **契约从第一天就是假的**

mypy 会报这个（实测）：

```
error: Incompatible types in assignment (expression has type "None", variable has type "str")  [assignment]
```

但 mypy 只在你写了这个类的地方报；**从 JSON 进 `model_validate` 那条路 mypy 管不到**，所以它是"静态拦得住、运行时拦不住"。

正解只有一条：**要可空就写 `str | None = None`；不可空就别给它 None 默认值**。想让默认值也被校验，才用 `validate_default=True`。

### 3.5 `alias`：前后端命名不一致怎么办

前端习惯 `userName`，Python 习惯 `user_name`。实测：

```python
class D(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_name: str = Field(alias="userName")
```

```
D(userName='x')                       -> user_name='x'       ← 用别名进来
D(user_name='y')                      -> user_name='y'       ← populate_by_name 允许用字段名
D(userName='x').model_dump()          -> {'user_name': 'x'}  ← 默认按字段名出去
D(userName='x').model_dump(by_alias=True) -> {'userName': 'x'} ← 出去也按别名
```

要点三条：

1. **不给 `populate_by_name`**，就只能用别名构造，测试里写字段名会直接报 `missing`。
2. **`model_dump` 默认用字段名**，要发给前端得 `by_alias=True`。
3. `FastAPI` 的 `response_model` 会用 `by_alias=True` 序列化（对外按别名），所以**接口契约看别名、代码里看字段名**，两边都成立。

需要的另一个开关是 `alias_generator`（全模型统一规则，如驼峰化）：

```python
from pydantic.alias_generators import to_camel

class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
```

### 3.6 `field_validator`：类型过了之后跑你的逻辑

```python
class E(BaseModel):
    x: int

    @field_validator("x")
    @classmethod
    def check(cls, v: int) -> int:      # 注意：类方法 + 返回值就是最终值
        if v > 10:
            raise ValueError("x 不能大于 10")
        return v
```

实测报错：

```
type=value_error | msg=Value error, x 不能大于 10 | ctx.error 的类型: ValueError
```

**注意最后一项**：`ctx.error` 是个**活的 `ValueError` 实例**。这就是 D2 那个 422→500 的坑的源头——`JSONResponse` 序列化它时会 `TypeError`。你已经在 `main.py` 用 `jsonable_encoder` 修过了，今天加第一个 validator 的时候，**这个坑会想再犯一次**，认出来。

几个必须记住的点：

| 点 | 说明 |
|---|---|
| 为什么加 `@classmethod` | pydantic 把它当类方法调用；忘了会得到 `TypeError: ... takes 2 positional arguments` |
| 返回值才算数 | 不 `return` 就是 `None`，字段值变 `None` |
| `mode="before"` | 类型转换**之前**跑（拿到原始输入，可能是字符串）；默认 `after` |
| 多个字段 | `@field_validator("a", "b")`，共用一个函数 |
| 报错的 `msg` 前缀 | pydantic 自动加 `Value error, `，你写什么它接在后面 |
| 别在这里查库 | validator 可能被调用多次（校验 + 赋值），有副作用会重复执行 |

### 3.7 `model_config`：模型级开关

```python
class KBOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
```

| 配置 | 作用 | 实测症状 |
|---|---|---|
| `from_attributes=True` | 允许从**对象属性**构造（ORM 行、dataclass） | 不加：`model_type` 错误（"Input should be a valid dictionary or instance of Out"） |
| `extra="forbid"` | 多传字段直接报错 | `extra_forbidden`，`loc=('oops',)` |
| `extra="ignore"` | **默认**，多传的字段静默丢弃 | 前端多传了字段，你以为会被记住，其实没有 |
| `strict=True` | 整模型 strict | 见 3.3 |
| `populate_by_name=True` | 允许用字段名代替别名 | 见 3.5 |
| `validate_default=True` | 默认值也校验 | 见 3.4 |

`from_attributes` 是**出方向的关键**：数据库查出来的是 ORM 对象，不是 dict：

```
Out.model_validate(Row(), from_attributes=True)  -> id=7 name='row'
Out.model_validate(Row())                        -> type=model_type 错误
```

项目里 `KBOut` 就带着这个开关，所以 service 层可以直接 `return orm_obj`。

### 3.8 `model_dump` 的四个开关

```python
class U(BaseModel):
    a: int
    b: str | None = None

u = U(a=1)
```

实测：

```
u.model_dump()                    -> {'a': 1, 'b': None}
u.model_dump(exclude_none=True)   -> {'a': 1}
u.model_dump(exclude_unset=True)  -> {'a': 1}      ← b 从来没被设过
```

`exclude_none` 和 `exclude_unset` 在**这个例子里结果一样**，差别在这里：

```python
u2 = U(a=1, b=None)               # b 被显式设成 None
u2.model_dump(exclude_none=True)  -> {'a': 1}      ← 去掉
u2.model_dump(exclude_unset=True) -> {'a': 1, 'b': None}   ← 保留，因为"设过"
```

所以 PATCH 语义要用 `exclude_unset`（"没传的字段别动"），展示用 `exclude_none`（"空的别给前端"）。**用错会导致"清空字段"这个操作永远失败**——这是 PATCH 接口的经典 bug。

还有两个常用参数：

- `mode="json"`：把 `UUID` / `datetime` / `Decimal` 转成字符串（要 `json.dumps` 时必加）
- `by_alias=True`：按别名输出（见 3.5）

### 3.9 `response_model` 的两个身份（今天最重要的一节）

`@app.get(..., response_model=Out)` 同时做两件事，**顺序是先校验再过滤**：

**身份一：过滤器**——多返回的字段静默消失。实测：

```python
@app.get("/leak", response_model=Out)      # Out 只有 id / name
def leak():
    return {"id": 1, "name": "a", "secret": "hunter2"}
```

```
客户端收到: {'id': 1, 'name': 'a'}          ← secret 被丢掉，没有任何报错
```

**身份二：校验器**——声明成 A 却返回 B，直接 500。实测：

```python
@app.get("/liar", response_model=StrictOut)   # score: int
def liar():
    return {"id": 1, "score": "not-a-number"}
```

```
fastapi.exceptions.ResponseValidationError: 1 validation error:
  {'type': 'int_parsing', 'loc': ('response', 'score'),
   'msg': 'Input should be a valid integer, unable to parse string as an integer',
   'input': 'not-a-number'}
```

注意三件事：

1. **`loc` 的第一个元素是 `('response',)`**，不是 `('body',)`——一眼能看出是出参的问题。
2. 它是**未捕获异常**，冒到最外层变 500（D2 的 ①）。测试里 `TestClient` 默认会把它直接抛给测试代码，所以你会看到 traceback 而不是 500 响应。
3. **这个 500 不经过你的 `AppError` handler**，所以日志里只有 `request_failed`。要统一格式，得单独注册 `ResponseValidationError` 的 handler（D4/D5 做统一响应体时一起处理）。

一条能直接用于面试的结论：

> **入参错了是 422，出参错了是 500。** 因为入参校验是"用户的问题"，出参校验是"我的 bug"——服务端自己返回了不符合自己契约的数据。

### 3.10 错误项的完整形状

一条错误长这样（`e.errors()` 的元素）：

```python
{'type': 'value_error', 'loc': ('body', 'x'),
 'msg': 'Value error, x 不能大于 10', 'input': 99,
 'ctx': {'error': ValueError('x 不能大于 10')}}
```

| 键 | 含义 | 谁在用 |
|---|---|---|
| `type` | 机器可读的错误码 | 前端做多语言、埋点统计 |
| `loc` | 出错位置元组（`body`/`query`/`path` + 字段名 + 下标） | 前端定位到具体输入框 |
| `msg` | 人类可读文案（英文） | 日志、兜底展示 |
| `input` | 你传进来的原值 | 错误提示里回显"你填的是 xxx" |
| `ctx` | 约束值或原始异常 | 拼"最多 100 字，当前 137 字" |

**pydantic 一次收集所有字段的错误**（实测两个字段都错时 `error_count()==2`，`loc` 分别是 `('a',)` 和 `('b',)`），不是碰到第一个就停——所以前端可以一次性把所有问题标红。

---

## 四、底层机制：为什么 v2 快，以及"编译"指什么

1. **v2 的校验器是 Rust 实现**（`pydantic-core`）。Python 只负责"声明"，真正的类型检查、字典遍历、错误收集在 Rust 里跑。
2. **类创建时编译**：`class KB(BaseModel)` 执行时，pydantic 把字段树翻译成 core schema，再生成 `__pydantic_validator__`（校验器）和 `__pydantic_serializer__`（序列化器）。所以**第一次构造有额外开销，之后每次构造都是"调一个已经编好的函数"**。
3. **`model_fields` 是声明表**，core schema 是执行表。两者不总是一一对应（比如 `Optional` 会变成 `nullable` 包装）。
4. **v1 → v2 的 API 改名**（网上文章十篇有八篇还是 v1，对照着看）：

| v1 | v2 |
|---|---|
| `parse_obj()` / `parse_raw()` | `model_validate()` / `model_validate_json()` |
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `@validator` | `@field_validator`（必须配 `@classmethod`） |
| `@root_validator` | `@model_validator(mode="after")` |
| `class Config` | `model_config = ConfigDict(...)` |
| `Optional[X]` 隐含默认 `None` | **必须显式 `= None`**（v1 的隐含默认在 v2 被取消） |

最后一行是升级时最容易炸的地方：v1 里 `x: Optional[int]` 可以不传，v2 里它是**必填且可为 None**。

---

## 五、易错点表

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 以为 `response_model` 只是文档 | 多返回的字段静默消失 / 类型不符直接 500 | 它是**过滤器 + 校验器**，出参也过一遍 |
| 2 | `Field(default=None)` 挂在非 Optional 类型上 | 构造成功、运行时是 `None`，契约撒谎 | 要可空写 `str \| None = None`；或 `validate_default=True` |
| 3 | 以为默认值也会被校验 | `min_length=1` 的字段能存成空串（默认给的） | 默认值不校验；靠 `validate_default` 或别给坏默认值 |
| 4 | `model_dump(exclude_none=True)` 用在 PATCH | "把字段清空"永远失败 | PATCH 用 `exclude_unset=True` |
| 5 | 以为 lax 只转数字 | `"yes"`/`"no"` 被转成 `True`/`False` | 金额、开关这类字段用 `Field(strict=True)` |
| 6 | `field_validator` 忘了 `@classmethod` | `TypeError: ... takes 2 positional arguments` | 两个装饰器都要写，顺序：validator 在上、classmethod 在下 |
| 7 | validator 里不 `return` | 字段值变 `None` | 返回值才是最终值 |
| 8 | 忘了 `populate_by_name` 却用字段名构造 | `missing` 错误，看着像字段没定义 | 加 `ConfigDict(populate_by_name=True)` |
| 9 | `model_dump` 直接 `json.dumps` 带 UUID/datetime | `TypeError: Object of type UUID is not JSON serializable` | `model_dump(mode="json")` |
| 10 | 以为出参校验失败是 422 | 客户端收到 500，日志只有 `request_failed` | 出参错是 500，要单独注册 handler 统一格式 |

---

## 六、项目现状：`schemas/kb.py` 逐行点评

```python
class KBBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="知识库名称")
    description: str | None = Field(default=None, max_length=500)
```

- 约束已经有（`min_length` / `max_length`），但用的是**写法 A**（默认值位置塞 Field），且没有 `Annotated` 类型别名复用。
- `description` 的 `str | None = Field(default=None, ...)` 是**正确写法**（类型也带 `| None`），这条没坑。
- 缺 `extra` 策略：默认 `ignore`，所以前端多传字段静默丢弃——D3 要不要改成 `forbid`，得看你要不要"严格契约"。

```python
class KBOut(KBBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_id: UUID
    doc_count: int = 0
    ...
```

- `from_attributes=True` 让 service 能直接 `return orm_obj`，正确。
- 但它**继承自 `KBBase`**，所以 `KBOut` 也继承了 `name` 的约束——出参也受入参约束，属于"耦合但不致命"。

**D3 的改造点（今天的动手任务）**

1. 把 `KBBase` / `KBUpdate` 的约束改成 `Annotated` 类型别名（如 `KbName = Annotated[str, Field(min_length=1, max_length=100)]`）
2. 给 `KBCreate` 加一个 `alias`（`kb_name` ← `kbName`）+ `populate_by_name`，验证两条路都能构造
3. 加**一个** `field_validator`：`name` 不能全是空白字符（`strip()` 后为空则 `ValueError`）
4. 给某个模型加 `extra="forbid"`，并**实测**多传字段的报错形状

⚠️ 第 3 条一落地，D2 修过的 422→500 坑就会重新出现一次（`ctx.error` 有 `ValueError`）——但你已经修过 handler 了，这次应该是"绿的"。**如果它红了，说明 D2 的修法有漏。**

---

## 七、命令速查

```powershell
# Windows PowerShell（在 kb-service 下）==================
& .\.venv\Scripts\python.exe scripts\check.py          # 门禁四步
& .\.venv\Scripts\python.exe -m pytest tests -q        # 只跑测试
& .\.venv\Scripts\python.exe -c "import pydantic; print(pydantic.VERSION)"
& .\.venv\Scripts\python.exe -m mypy src               # 类型检查
```

```bash
# Git Bash / Linux / macOS ==============================
./.venv/Scripts/python.exe scripts/check.py            # 真 Linux: .venv/bin/python
./.venv/Scripts/python.exe -m pytest tests -q
./.venv/Scripts/python.exe -c "import pydantic; print(pydantic.VERSION)"
./.venv/Scripts/python.exe -m mypy src
```

---

## 八、动手实验（每题**先在纸上写答案**，猜错才值钱）

**实验 1**：`class P(BaseModel): n: int` 上，`P.model_validate({"n": 3.7})` 得到什么？`{"n": "3.7"}` 呢？

**实验 2**：`name: str = Field(min_length=1, max_length=5, default="")`，`M()` 会不会报错？为什么？

**实验 3**：`response_model=Out`（`id/name`）的路由返回 `{"id": 1, "name": "a", "secret": "x"}`，客户端收到什么？如果把它改成 `response_model=None` 呢？

**实验 4**：`model_config = ConfigDict(extra="forbid")` 的模型，前端多传一个字段，`loc` 指向谁？（指向多出来的那个字段，还是模型根？）

**实验 5**：给 `name` 加 `@field_validator("name", mode="before")`，打印 `type(v)`。传 `123` 时打印出什么类型？和默认 `after` 模式有什么区别？

做完把 5 条答案写进 `D3-阅读笔记.md`（格式沿用 `week6/D1-阅读笔记.md`：只记"我原来想错的" + 还挂着的问号）。

---

## 九、面试问法

### 9.1 高频题 30 秒版

**Q：pydantic 在项目里起什么作用？**

> 两头都管。进方向把 JSON 校验成带类型的对象，规则写在类型声明里只写一遍，失败统一收集成 `ValidationError`，FastAPI 翻译成 422；出方向按 `response_model` 再走一遍，**声明了哪些字段就只输出哪些**，所以它同时是过滤器和出参校验器——入参错了是 422，出参错了是 500。

### 9.2 追问链（三层）

**第一层（机制）**：`Field` 的约束是什么时候生效的？
> 类创建时编译成 core schema，实例化时由 Rust 校验器执行。所以约束不是装饰器式的"运行时反射"，而是"编好的一次性函数"。

**第二层（边界/故障）**：`response_model` 声明 `score: int`，但返回的是字符串，客户端收到什么？
> 500。`serialize_response` 里抛 `ResponseValidationError`，`loc` 第一项是 `('response',)`；它是未捕获异常，冒到最外层生成 500，**不经过 `AppError` 的 handler**。测试里开 `raise_server_exceptions=False` 才能断言到这个 500。

**第二层（另一个方向）**：默认值会被校验吗？
> 不会。`name: str = Field(default=None)` 能构造成功，运行时真的是 `None`——存库就是 NULL，而 OpenAPI 写的是 string。要可空就得写 `str | None = None`，或者开 `validate_default=True`。

**第三层（场景落地）**：PATCH 接口"清空某个字段"为什么总是失败？
> 因为用了 `exclude_none=True`：显式传 `None` 被当成"没值"直接丢掉，服务端永远收不到"要清空"这个意图。PATCH 要用 `exclude_unset=True`——它区分"没传"和"传了 None"。

**第三层（AI 应用向）**：LLM 输出结构化数据，怎么保证不炸？
> 用 pydantic 模型做 schema，把 `model_json_schema()` 喂给模型的 function calling / structured output，拿回来先 `model_validate_json`；失败不要重试同一句 prompt，而是把 `ValidationError` 的 `loc` + `msg` 拼成"你上次漏了哪个字段、哪个字段类型错了"再让它修一次。这就是 pydantic 在 AI 应用里最核心的用法——**校验器同时是"给模型的反馈生成器"**。

### 9.3 一句话收尾

> 我们的 schema 分两层：`KBCreate` 管入参，`KBOut` 管出参并开 `from_attributes` 让 service 直接返回 ORM 对象；约束用 `Annotated` 抽成别名，避免"改一处漏一处"。

---

## 十、闭卷自测（先答，再展开）

<details>
<summary>Q1：lax 模式下 `{"doc_count": "3"}` 会怎样？`{"flag": "yes"}` 呢？</summary>

都会转换：`"3"` → `3`，`"yes"` → `True`。lax 是"尽力转"，白名单内的字符串会转成数字/布尔；strict 模式下两者都报 `int_type`。
</details>

<details>
<summary>Q2：`name: str = Field(min_length=1)`，`M()` 会不会报错？</summary>

不会。默认值不参与校验，`min_length` 只在"传了值"的时候检查。要让默认值也被校验，开 `validate_default=True`。
</details>

<details>
<summary>Q3：`response_model` 声明了 3 个字段，路由返回 5 个，额外 2 个去哪了？</summary>

被静默丢弃。`serialize_response` 按 schema 生成输出，多出来的键不报错也不输出。想防泄露（比如密码字段）靠的就是这个行为——但必须知道它在过滤，否则会以为"返回了就给出去了"。
</details>

<details>
<summary>Q4：出参类型不符为什么是 500 不是 422？</summary>

422 的语义是"客户端提交的数据不合法"；出参不符是"服务端自己违反了自己的契约"，属于服务端 bug，所以是 `ResponseValidationError` → 500。`loc` 首项是 `('response',)` 可以一眼分辨。
</details>

<details>
<summary>Q5：PATCH 接口该用 `exclude_none` 还是 `exclude_unset`？</summary>

`exclude_unset`。它区分"没传"和"传了 None"；`exclude_none` 会把"显式清空"也当成空值丢掉，导致清空操作永远失效。
</details>

<details>
<summary>Q6：`@field_validator` 为什么必须配 `@classmethod`？忘掉会怎样？</summary>

pydantic 以类方法方式调用校验器。忘掉 `@classmethod` 会得到 `TypeError: check() takes 2 positional arguments but 3 were given`（pydantic 传 cls 和 value 两个）。
</details>

<details>
<summary>Q7：`field_validator` 里 `raise ValueError` 之后，`ctx.error` 是什么？为什么 D2 要修那个 handler？</summary>

是原始的 `ValueError` 实例（实测 `type(...).__name__ == 'ValueError'`）。`JSONResponse` 遇到它会 `TypeError`，于是 422 变 500——所以要用 `jsonable_encoder(exc.errors())` 包一层。
</details>

<details>
<summary>Q8：`from_attributes=True` 解决什么问题？</summary>

允许从对象属性构造（ORM 行、dataclass、任意带属性的对象）。不加会报 `model_type` 错误（"Input should be a valid dictionary or instance of X"）。项目里 `KBOut` 就靠它直接接 ORM 对象。
</details>

---

## 十一、今日任务单（5h：主线 4h20m + 日课 35min）

| # | 任务 | 产出 | 时长 |
|---|---|---|---|
| 0 | 跑第二节 demo，把 4 行输出抄进 `D3-阅读笔记.md`（含"我原来以为…"） | demo 输出 + 2 条误判 | 20min |
| 1 | 第三节 3.1–3.4 精读 + 自己动手验证 `default` 不校验那条 | 纸笔：进/出两栏各自会改什么 | 40min |
| 2 | 3.5–3.8：alias / validator / config / dump 四个开关各写一个最小例子 | 4 段能跑的代码 | 60min |
| 3 | 3.9 `response_model` 两个身份，自己复现"静默丢字段"和"撒谎 500" | 两条实测输出 | 30min |
| 4 | **动手任务**：改 `schemas/`（Annotated 别名 + alias + 一个 validator + 一个 `extra="forbid"`），门禁全绿 | 改动 + `check.py` 全绿 | 90min |
| 5 | 第八节 5 个实验（先写答案） | 5 条答案 | 20min |
| 6 | 日课 35min | LC 20m + 八股/面试 15m | 35min |

**验收标准**

- [ ] 能不看资料说出"入参 422 / 出参 500"的原因
- [ ] 能说清"默认值不校验"和它的三种表现形式（构造成功 / 入库 NULL / 契约撒谎）
- [ ] `schemas/` 改造后门禁全绿，且新增至少一条 validator 相关测试
- [ ] 第八节 5 条答案里有 ≥1 条是猜错的（全对说明没在猜）

### 今日纸笔靶

1. **画**：一个字段的四站图（JSON → 校验 → 模型实例 → 序列化），在"校验"站标出 422、在"序列化"站标出"静默丢字段 / 500"
2. **写三句**：①默认值为什么能绕过校验 ②`response_model` 的两个身份分别是什么 ③为什么出参错是 500
3. **手写骨架**：一个带 `field_validator` + `Annotated` 约束的 `BaseModel`（10min，本周第 2 次白板靶）
