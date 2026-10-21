# Day5 · 标准库速通（下）总结

> **日期**：2026-10-21
> **投入**：约 3h（含卡壳排查）
> **结果**：**ex01–ex12 共 12 道全部 `[PASS]`**，`ruff check` All checks passed
> **提交**：由用户手动推送（新约定：推送三连自己练）
> **文件**：`progress/week1/stdlib_practice.py`（W1 代码任务至此全部完成）

---

## 一、完成情况

| 练习 | 模块 | 核心 API | 状态 |
|---|---|---|---|
| ex07 | `typing.Protocol` | 结构化子类型 | ✅ PASS |
| ex08 | `asyncio` | `Semaphore` / `gather` | ✅ PASS |
| ex09 | `argparse` | `store_true` / `type=` / `choices=` | ✅ PASS |
| ex10 | `contextlib` | `@contextmanager` / `try-finally` | ✅ PASS（实测 10.26 ms） |
| ex11 | `functools` | `lru_cache` / `cache_info()` | ✅ PASS（hits 8→9 实证） |
| ex12 | `enum` + `collections` | `StrEnum` / `defaultdict(list)` | ✅ PASS |

**过程记录**：ex08、ex11 其实一次写对了，卡住的原因是**忘了导入 `functools`，脚本在模块加载时 `NameError`**。教训见"三、坑"。

---

## 二、六个知识点（面试可直接说）

### 1. `Protocol` —— 看形状，不看血统

```python
class Storable(Protocol):
    def to_dict(self) -> dict[str, str]: ...

def ex07_flush_all(docs: list[Storable]) -> None:
    for d in docs:
        print(d.to_dict())
```

`UserDoc` 和 `NoteDoc` **没有任何继承关系**，却都能传进 `list[Storable]`——因为 Protocol 只检查"有没有 `to_dict()`、签名对不对"，这叫**结构化子类型**。

三个关键认知：

| 问题 | 答案 |
|---|---|
| 运行时会检查吗？ | **不会**。纯鸭子类型，缺方法照样到调用时才炸 |
| 那 Protocol 有什么用？ | **给 mypy / IDE 看的**。传错类型编辑器直接红线，不用等运行时 |
| 第三方类没继承我的接口能用吗？ | **能，零侵入**。这正是它比 ABC 强的地方 |

**Protocol vs ABC（高频面试题）**：

| | `Protocol` | `ABC` |
|---|---|---|
| 建立关系的方式 | 隐式（形状匹配） | 显式（必须继承） |
| 能约束第三方类吗 | 能 | 不能（人家不继承你） |
| 运行时强制 | 无 | 可用 `@abstractmethod` 强制子类实现 |
| 适用 | "只要能 do X 就行" | "必须是我家族的一员" |

### 2. `asyncio.Semaphore` + `gather` —— 限流与保序

```python
sem = asyncio.Semaphore(concurrency)

async def fetch_one(url: str) -> str:
    async with sem:                # 计数器归零时，后续协程在此挂起
        await asyncio.sleep(0.1)
        return url

return await asyncio.gather(*(fetch_one(url) for url in urls))
```

两个机制分开记：

- **限流**：`Semaphore(2)` 是计数器。`async with` 进入时 -1，**减到 0 后再进就挂起**；退出时 +1，唤醒一个排队者。所以 N 个任务同时最多 2 个在跑
- **保序**：**gather 返回列表的第 i 个 = 第 i 个传入协程的返回值**，与完成时间无关。u4 先完成也不影响 `[u0, u1, ...]` 的顺序

**`*` 解包的细节**：`gather(*(gen))` 把生成器展开成 5 个独立协程参数。如果写成 `gather(gen)`，gather 会把整个生成器当成**一个**任务。

**gather vs TaskGroup（必背）**：

| | `gather` | `TaskGroup`（3.11+） |
|---|---|---|
| 一个任务失败 | 默认立刻抛异常，**其余任务继续跑**（变孤儿） | **自动取消其余全部**，聚合异常一起抛 |
| 语义 | "把结果收集齐" | **结构化并发**：块结束 = 所有任务都结束 |
| 生产推荐 | 收集结果且想容忍失败（配 `return_exceptions=True`） | 默认首选 |

### 3. `argparse` —— CLI 三件套

```python
parser = argparse.ArgumentParser(description="...")
parser.add_argument("--verbose", action="store_true")            # 开关
parser.add_argument("--count", type=int, default=1)              # 类型
parser.add_argument("--mode", choices=["fast", "slow"])          # 枚举
```

| 参数 | 不写的后果 |
|---|---|
| `type=int` | 拿到字符串 `"3"`，`args.count + 1` 直接 `TypeError` |
| `choices=` | 任何垃圾值都接受，错误在深处才暴露 |
| `action="store_true"` | 没有"开关"语义，得用 `--verbose 1` 这种丑写法 |

**属性名规则**：`--verbose` → `args.verbose`（去 `--`，`-` 转 `_`）。

**和 kb-service 的联系**：FastAPI 的 `Query(ge=1, le=100)` 做的事和 `type=` / `choices=` 一模一样——**在入口处把非法值挡掉**。CLI 和 API 的参数校验是同一个思想。

### 4. `@contextlib.contextmanager` —— 用生成器写 with

```python
@contextlib.contextmanager
def ex10_timer(label: str = "elapsed"):
    start = time.perf_counter()   # ← __enter__（进入 with 时）
    try:
        yield                     # ← 控制权交给 with 块
    finally:
        ...                       # ← __exit__（离开 with 时，异常也保证执行）
```

**三条铁律**：

1. `yield` **之前** = 进入逻辑，**之后** = 退出逻辑
2. **必须且只能 yield 一次**，否则 `RuntimeError: generator didn't yield`
3. 清理逻辑放 `try/finally`——**with 块里抛异常也保证清理执行**

**面试问法**：不用装饰器怎么写？→ 手写一个类实现 `__enter__` / `__exit__`。装饰器版本是用生成器换掉类样板，等价但少写 10 行。

### 5. `functools.lru_cache` —— 缓存与它的作用域

```python
@lru_cache(maxsize=None)  # noqa: UP033 —— 生产等价写法是 @functools.cache
def _fib(n: int) -> int:
    if n < 2:
        return n
    return _fib(n - 1) + _fib(n - 2)
```

**本日最值钱的一个认知：缓存跟着函数对象走**。

- `_fib` 定义在**模块级** → 整个进程共享一个缓存，第二次调用 `fib(10)` 直接命中
- 如果定义在**另一个函数内部** → 每次调用外层函数都会重新执行装饰器、**重建一个全新缓存**，缓存形同虚设
- 自检输出实证了这一点：两次调用，`hits` 从 8 跳到 9，`misses` 停在 11 不变

**ex11 的 before/after 对比技巧**（自己想出来的）：

```python
before = _fib.cache_info()
result = _fib(n)
after = _fib.cache_info()
if after.hits > before.hits:   # 这次调用到底命中没有，一眼可判
```

**cache_info 五个字段**：`hits`（命中）/ `misses`（未命中）/ `maxsize` / `currsize`（当前缓存条数）/ `maxsize=None` 时无淘汰。

**什么时候不能用**：参数不可哈希（如 list）；函数有副作用（缓存会吞掉副作用）；参数空间无限增长（缓存撑爆内存）。

### 6. `StrEnum` + `defaultdict` —— 分组的最短路径

```python
grouped: dict[DocStatus, list[str]] = defaultdict(list)
for row in rows:
    grouped[DocStatus(row["status"])].append(row["id"])
```

- `defaultdict(list)`：访问不存在的键**自动创建空列表**，省掉 `if key not in grouped` 分支
- `DocStatus("ready")`：StrEnum **按值查找**成员；因为值就是 `"ready"`，字符串直接映射成枚举
- 反向也成立：`DocStatus.READY == "ready"` 为 True（成员是 str 子类），所以它能无缝进 JSON、能当 dict 的 str 键用

**这和 kb-service 的关系**：`schemas/doc.py` 的 `DocStatus(StrEnum)` 就是这个写法——文档状态机 `pending → processing → ready / failed`，API 返回的 `"ready"` 字符串就是它。

---

## 三、今天踩的坑

### 坑 1 · `NameError: name 'lru_cache' is not defined`（本日主坑）

**现象**：脚本一行都没跑就崩，12 道题看起来"全坏了"。

**根因**：`@lru_cache` 是**模块级装饰器**，import 时立即执行；`functools` 没导入 → 加载即 `NameError`。对比：`argparse` 也没导入但没炸，因为它只在 ex09 **函数体内**用，函数不执行就不检查。

**读报错三要素又立功**：`in <module>`（模块加载时）+ `not defined`（名字不存在）→ 直接指向"忘 import"。

**一般规律**：**装饰器用到的名字必须在 import 区可见**，因为装饰发生在模块加载时，比任何函数调用都早。

### 坑 2 · 写完代码顺手删了 docstring

ex08 实现时把函数的 docstring 三行删掉了。docstring 是 API 文档的来源（`help()`、IDE 悬浮提示都读它），**写实现不等于可以删说明**。已恢复。

### 坑 3 · 布局细节

`_fib` 和 `ex11_fib_cached` 之间只有一个空行（PEP8 要求顶层定义间隔两个空行）；import 后的分节注释前多了空行。`ruff` 全部抓出来了——**这就是为什么格式交给工具管，不靠肉眼**。

---

## 四、自测 6 问（闭卷）

1. `Protocol` 和 `ABC` 都能定义接口，什么时候必须用 ABC？
2. `asyncio.gather` 的返回顺序由什么决定？一个任务抛异常时其余任务会怎样？
3. `argparse` 里 `--count` 不写 `type=int`，`args.count` 是什么类型？会引发什么具体错误？
4. `@contextmanager` 装饰的函数里 `yield` 写了两次会怎样？`try/finally` 防的是什么？
5. 为什么 `_fib` 必须定义在模块级？定义在函数内部会发生什么？
6. `defaultdict(list)` 访问不存在的键时发生什么？和 `dict.setdefault(k, [])` 的区别？

<details>
<summary>答案</summary>

1. 需要**运行时强制**时：ABC + `@abstractmethod` 能在子类实例化时立刻报错（漏实现就炸），Protocol 运行时不检查。另外要给第三方类"官方血统"（isinstance 判断、注册回调）时也用 ABC。
2. 由**传入顺序**决定，与完成时间无关。默认 `return_exceptions=False` 时第一个异常直接抛出，**其余任务不会被取消**、继续跑成孤儿；TaskGroup 则会取消全部并聚合异常。
3. 字符串 `"3"`。典型错误：`args.count + 1` 抛 `TypeError: can only concatenate str (not "int") to str`——错误发生在使用处而非解析处，难定位。
4. `RuntimeError: generator didn't stop`（或 didn't yield 相关报错）。`try/finally` 防的是 with 块内抛异常时清理逻辑不执行——比如文件没关、锁没释放。
5. 装饰器在**函数定义时**执行并创建缓存。定义在函数内部，每次调用外层函数都会重新装饰、生成新函数对象和新缓存——之前缓存的结果全部丢失，等于没缓存。
6. 自动调用 `default_factory`（即 `list()`）创建空列表并插入，然后正常返回它。`setdefault` 每次都要**构造一个默认值对象**（哪怕键已存在，`[]` 也白建一次），且写起来是两步；`defaultdict` 把"缺键自动补"内置到 `__missing__` 里。

</details>

---

## 五、与项目的衔接

| 今天练的 | 项目里的位置 | 什么时候用到 |
|---|---|---|
| `Protocol` | `repositories/` 的隐式接口 | W7 换 SQLAlchemy 时定义 Repository 协议 |
| `Semaphore` | 并发爬取 / 批量 embedding | W12 批量向量化限流 |
| `TaskGroup` | FastAPI 并发调用下游 | W9 异步与并发 |
| `contextmanager` | `core/logging.py` 的 trace 上下文 | 已在用（思路同源） |
| `lru_cache` | `core/config.py` 的 `get_settings()` | **现在就在用**（配置缓存） |
| `StrEnum` | `schemas/doc.py` 的 `DocStatus` | **现在就在用**（文档状态机） |
| `defaultdict` | W13 可观测聚合 | 按维度统计指标 |

特别注意：**你 Day1 就见过的 `@lru_cache` 装饰 `get_settings()`，今天亲手写了一遍才真正懂它**。这也是"练习 → 回头看项目"的价值：项目里所有"当时看不懂"的代码，现在都该能看懂了。

---

## 六、W1 剩余安排

| 天 | 内容 | 性质 |
|---|---|---|
| Day6（周六 5h） | 抄改 300 行 + 跑通全部接口 | **检验"能不能独立写完整代码"** |
| Day7（周日 5h） | 12 道闭卷自测 + 周复盘 + 打 tag | 检验"能不能讲出来" |

Day6 的抄改规则提前说：**看 20 行 → 关掉 → 自己敲 → 对比差异**。不是复制粘贴。推荐顺序：`services/kb_service.py` → `core/logging.py`（ContextVar 是硬骨头，看不懂正常）。
