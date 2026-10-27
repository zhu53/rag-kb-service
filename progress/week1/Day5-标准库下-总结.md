# Day5 · 标准库速通（下）【面试参考版】

> 日期：2026-10-21 ｜ **ex01–ex12 共 12 道全部 PASS**，ruff All checks passed ｜ 文件：`progress/week1/stdlib_practice.py`
> 用法：§2 的 gather vs TaskGroup、§5 的 lru_cache 作用域是高频题；§8 追问链覆盖并发与缓存。

---

## 1. `Protocol` —— 看形状，不看血统

```python
class Storable(Protocol):
    def to_dict(self) -> dict[str, str]: ...

def ex07_flush_all(docs: list[Storable]) -> None:
    for d in docs:
        print(d.to_dict())
```

`UserDoc` 和 `NoteDoc` **没有任何继承关系**，却都能传进 `list[Storable]`——因为 Protocol 只检查"有没有 `to_dict()`、签名对不对"，这叫**结构化子类型**。

| 问题 | 答案 |
|---|---|
| 运行时会检查吗？ | **不会**。纯鸭子类型，缺方法到调用时才炸 |
| 那它有什么用？ | **给 mypy / IDE 看**：传错类型编辑器直接红线，不用等运行时 |
| 第三方类没继承能用吗？ | **能，零侵入**（这正是它比 ABC 强的地方） |

### Protocol vs ABC（高频面试题，D4 会再展开）

| | `Protocol` | `ABC` |
|---|---|---|
| 建立关系 | 隐式（形状匹配） | 显式（必须继承） |
| 约束第三方类 | 能 | 不能（人家不继承你） |
| 运行时强制 | 无 | `@abstractmethod` 可在实例化时报错 |
| 适用 | "只要能 do X 就行" | "必须是我家族一员"、"需要共享实现" |

**什么时候必须用 ABC**：需要**运行时强制**（漏实现就炸）、需要基类提供共享实现/模板方法、需要 `isinstance` 判断血统。

---

## 2. `asyncio.Semaphore` + `gather` —— 限流与保序

```python
sem = asyncio.Semaphore(concurrency)

async def fetch_one(url: str) -> str:
    async with sem:                # 计数器归零时，后续协程在此挂起
        await asyncio.sleep(0.1)
        return url

return await asyncio.gather(*(fetch_one(url) for url in urls))
```

两个机制分开记：

- **限流**：`Semaphore(2)` 是计数器。`async with` 进入 -1，**减到 0 后再进就挂起**；退出 +1 唤醒一个排队者。N 个任务同时最多 2 个在跑。
- **保序**：**gather 返回列表第 i 个 = 第 i 个传入协程的返回值**，与完成时间无关。

**`*` 解包细节**：`gather(*(gen))` 把生成器展开成 N 个独立协程参数；写成 `gather(gen)` 会把整个生成器当成**一个**任务。

### gather vs TaskGroup（必背）

| | `gather` | `TaskGroup`（3.11+） |
|---|---|---|
| 一个任务失败 | 默认立刻抛异常，**其余任务继续跑**（变孤儿） | **自动取消其余全部**，聚合为 ExceptionGroup |
| 语义 | "把结果收集齐" | **结构化并发**：块结束 = 所有任务都结束 |
| 生产推荐 | 想容忍失败时配 `return_exceptions=True` | 默认首选 |

**孤儿为什么危险**：请求已经 500 返回给用户了，后台"写数据库/调第三方"的协程还在跑——浪费资源 + 可能写脏数据。

### 面试问法："并发请求下游，怎么控制并发数并保证结果顺序？"

**30 秒答案**："用 Semaphore 控制并发、gather 保证顺序。Semaphore 是计数器，进 async with 时减一，减到零后续协程就在原地挂起，退出时加一并唤醒一个等待者，这样同时最多 N 个在跑。gather 返回的列表按传入顺序排，跟谁先完成无关，所以天然保序。要注意两点：一是任务生成要用 `*` 解包，否则整个生成器会被当一个任务；二是 gather 在某个任务失败时不会取消其他任务，会留下孤儿协程继续跑，生产上更推荐 3.11 的 TaskGroup——一个失败自动取消全部，失败被聚合在 ExceptionGroup 里。"

**追问链**：
- 追问①："Semaphore 和信号量/连接池什么关系？" → 同一个思想：计数资源许可；数据库连接池本质也是限流。
- 追问②："为什么 asyncio 要 `async with` 而不是 `with`？" → `__aenter__`/`__aexit__` 是异步协议，`with` 只能调同步方法。
- 追问③："gather 的 return_exceptions 语义？" → True 时异常作为结果返回（不抛出），适合"部分失败也要全量结果"的批处理。
- 追问④："TaskGroup 的异常怎么处理？" → `except* ValueError`（PEP 654），按类型分组处理，还能拿到 `.exceptions`。

---

## 3. `argparse` —— CLI 三件套

```python
parser = argparse.ArgumentParser(description="...")
parser.add_argument("--verbose", action="store_true")            # 开关
parser.add_argument("--count", type=int, default=1)              # 类型
parser.add_argument("--mode", choices=["fast", "slow"])          # 枚举
```

| 参数 | 不写的后果 |
|---|---|
| `type=int` | 拿到字符串 `"3"`，`args.count + 1` → `TypeError` |
| `choices=` | 垃圾值都接受，错误在深处才暴露 |
| `action="store_true"` | 没有开关语义，得写 `--verbose 1` |

**属性名规则**：`--verbose` → `args.verbose`（去 `--`，`-` 转 `_`）。

**与 FastAPI 的联系**：`Query(ge=1, le=100)` 与 `type=`/`choices=` 是同一个思想——**在入口处把非法值挡掉**。

### 面试问法："CLI 和 HTTP 接口有什么共同点？"

**30 秒答案**："都是接口层：解析外部输入、校验、调用 service、把结果或错误翻译成协议。CLI 用 argparse 做类型和枚举校验、退出码表达成败；HTTP 用 Pydantic 校验请求体、状态码表达结果。业务逻辑不该知道自己被谁调用——这也是为什么 service 只抛领域异常，由最外层翻译成退出码或 HTTP 状态码。"

---

## 4. `@contextlib.contextmanager` —— 用生成器写 with

```python
@contextlib.contextmanager
def ex10_timer(label: str = "elapsed"):
    start = time.perf_counter()   # ← __enter__
    try:
        yield                     # ← 控制权交给 with 块
    finally:
        ...                       # ← __exit__（异常也保证执行）
```

**三条铁律**：
1. `yield` **之前** = 进入逻辑，**之后** = 退出逻辑。
2. **必须且只能 yield 一次**，否则 `RuntimeError: generator didn't yield`。
3. 清理逻辑放 `try/finally`——**with 块里抛异常也保证清理执行**。

手写类版本：

```python
class Timer:
    def __enter__(self):
        self.start = time.perf_counter(); return self
    def __exit__(self, exc_type, exc, tb):
        print(f"耗时 {time.perf_counter() - self.start:.4f}s")
        return False        # False = 不吞异常
```

### 面试问法："contextmanager 装饰器的原理？"

**30 秒答案**："它把生成器包装成上下文管理器：yield 之前是 `__enter__`，yield 之后是 `__exit__`，yield 的值就是 as 后面拿到的对象。所以清理逻辑必须放在 try/finally 里，否则 with 块抛异常时不会执行。要注意只能 yield 一次；`__exit__` 返回 True 会吞掉异常，默认返回 False 让它继续抛——吞异常是很多隐蔽 bug 的来源。"

---

## 5. `functools.lru_cache` —— 缓存跟着函数对象走

```python
@functools.lru_cache(maxsize=None)   # 生产等价写法：@functools.cache
def _fib(n: int) -> int:
    if n < 2:
        return n
    return _fib(n - 1) + _fib(n - 2)
```

**本日最值钱的认知：缓存跟着函数对象走。**

- 定义在**模块级** → 整个进程共享一个缓存，第二次 `fib(10)` 直接命中。
- 定义在**另一个函数内部** → 每次调用外层函数都重新执行装饰器、**重建一个全新缓存**，缓存形同虚设。
- 实证：两次调用，`hits` 从 8 跳到 9，`misses` 停在 11 不变。

**before/after 对比技巧**（自己想出来的）：

```python
before = _fib.cache_info()
result = _fib(n)
after = _fib.cache_info()
if after.hits > before.hits:   # 这次调用到底命中没有，一眼可判
```

**cache_info 五字段**：`hits` / `misses` / `maxsize` / `currsize` / （maxsize=None 时无淘汰）。

**什么时候不能用**：参数不可哈希（list/dict）；函数有副作用（缓存会吞掉副作用）；参数空间无限增长（撑爆内存）。

### 面试问法："lru_cache 有什么用？有什么坑？"

**30 秒答案**："它是进程内的 LRU 缓存装饰器，按参数做 key 缓存返回值，适合纯函数、重复调用、计算昂贵的场景，比如递归、配置读取、纯计算。坑有三个：一是参数必须可哈希，list/dict 不行；二是有副作用的函数不能缓存，副作用会被吞掉；三是缓存跟着函数对象走——如果装饰的函数定义在另一个函数内部，每次外层调用都会重建缓存，等于没缓存。另外在方法上用要小心 self 被当成 key 的一部分，实例不释放会导致内存泄漏。"

**追问链**：
- 追问①："maxsize=None 和给数字的区别？" → None 不淘汰（可能无限增长）；数字是 LRU 容量。`functools.cache` 等价于 `maxsize=None`。
- 追问②："多线程安全吗？" → CPython 下内部有锁保护字典，但并发 miss 时会重复计算（没有单一飞行去重）；要严格去重得自己做锁。
- 追问③："怎么手动失效？" → `cache_clear()`（测试换血）、`cache_info()` 观察命中；没有单 key 失效 API（`cache_parameters` 只读）。
- 追问④："和 Redis 缓存的区别？" → 进程内、无网络开销、随进程消亡、不跨实例共享；Redis 跨进程共享但有网络与序列化成本。

---

## 6. `StrEnum` + `defaultdict` —— 分组的最短路径

```python
grouped: dict[DocStatus, list[str]] = defaultdict(list)
for row in rows:
    grouped[DocStatus(row["status"])].append(row["id"])
```

- `defaultdict(list)`：访问不存在的键**自动创建空列表**，省掉 `if key not in grouped`。
- `DocStatus("ready")`：StrEnum **按值查找**成员；值就是 `"ready"`，字符串直接映射成枚举。
- 反向成立：`DocStatus.READY == "ready"` 为 True（成员是 str 子类），能无缝进 JSON、能当 dict 的 str 键。

**与项目的关系**：`schemas/doc.py` 的 `DocStatus(StrEnum)` 就是这个写法——文档状态机 `pending → processing → ready / failed`，API 返回的 `"ready"` 就是它。

### 面试问法："枚举和字符串常量怎么选？"

**30 秒答案**："枚举有类型约束和自动补全，非法值在构造时就报错，比裸字符串安全；StrEnum 因为成员本身就是 str 子类，可以直接序列化成 JSON、能当字典键，兼顾了安全性和兼容性。它还能配状态机用——文档从 pending 到 processing 到 ready，用枚举比散落的字符串常量更容易做静态检查和穷举处理。"

---

## 7. 今天踩的坑

### 坑 1 · `NameError: name 'lru_cache' is not defined`（主坑）

**现象**：脚本一行没跑就崩，12 道题看起来"全坏了"。
**根因**：`@lru_cache` 是**模块级装饰器**，import 时立即执行；`functools` 没导入 → 加载即 NameError。对比 `argparse` 也没导入但没炸，因为它只在 ex09 **函数体内**用，函数不执行就不检查。
**一般规律**：**装饰器用到的名字必须在 import 区可见**，装饰发生在模块加载时，比任何函数调用都早。

### 坑 2 · 写完代码顺手删了 docstring

docstring 是 API 文档来源（`help()`、IDE 悬浮都读它）。**写实现不等于可以删说明。**

### 坑 3 · 布局细节

顶层定义间只留一个空行（PEP8 要两个）；import 后多空行。ruff 全抓出来——**格式交给工具，不靠肉眼**。

## 8. 追问链总表

| 起点 | 追问 | 你要能答 |
|---|---|---|
| Protocol | 运行时检查吗？ | 不检查，静态契约；`runtime_checkable` 只查方法名 |
| Semaphore | 底层是什么？ | 计数器 + 等待队列（asyncio 的 Future 队列） |
| gather | 为什么保序？ | 按传入顺序收集 result，与完成顺序无关 |
| TaskGroup | 异常怎么捕获？ | `except*` 分组；`.exceptions` 拿全部 |
| contextmanager | 能 yield 两次吗？ | 不能，RuntimeError |
| lru_cache | 为什么在方法上危险？ | self 进 key，实例无法释放 → 泄漏 |
| StrEnum | 和 Enum 区别？ | 成员是 str 子类，可 JSON 序列化、可与字符串比较 |
| defaultdict | 和 setdefault 区别？ | 缺键自动补（`__missing__`）；setdefault 每次构造默认值 |

## 9. 30 秒答案集

1. **Protocol** → 结构化子类型，零侵入，静态检查不运行期强制。
2. **ABC 何时必须** → 需要运行期强制/共享实现/血统判断。
3. **Semaphore** → 计数许可，控制并发数。
4. **gather 保序** → 按传入顺序返回，与完成时间无关。
5. **gather vs TaskGroup** → 孤儿任务 vs 自动取消 + 异常聚合。
6. **contextmanager** → yield 前 `__enter__`、后 `__exit__`，清理放 finally。
7. **lru_cache 作用域** → 缓存跟函数对象走；函数内定义等于没缓存。
8. **StrEnum** → str 子类枚举，可序列化、可比较。

## 10. 白板靶

1. 用 `@contextmanager` 写一个计时器（含 try/finally）。
2. 用 Semaphore + gather 写限并发批处理（5 行核心）。
3. `defaultdict(list)` 分组 + `StrEnum` 状态转换。

## 11. 闭卷自测

1. Protocol 和 ABC 都能定义接口，什么时候必须用 ABC？
2. `gather` 返回顺序由什么决定？一个任务抛异常其余会怎样？
3. `--count` 不写 `type=int`，`args.count` 什么类型？引发什么错误？
4. `@contextmanager` 里 yield 两次会怎样？`try/finally` 防什么？
5. 为什么 `_fib` 必须定义在模块级？定义在函数内部会怎样？
6. `defaultdict(list)` 与 `dict.setdefault(k, [])` 的区别？

<details><summary>答案</summary>
1. 需要运行期强制（漏实现即炸）、需要共享实现/模板方法、需要 isinstance 血统判断时。
2. 传入顺序（与完成时间无关）；默认第一个异常直接抛，其余任务不被取消继续跑成孤儿。
3. 字符串 "3"；`args.count + 1` → TypeError（错误发生在使用处）。
4. RuntimeError（generator didn't yield/stop）；try/finally 保证异常时清理执行（文件关闭、锁释放）。
5. 装饰器在定义时执行并建缓存；定义在函数内则每次外层调用重建缓存，等于没缓存。
6. defaultdict 缺键自动创建（`__missing__`）；setdefault 每次会构造默认值对象，哪怕键已存在。
</details>
