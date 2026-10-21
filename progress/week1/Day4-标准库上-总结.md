# Day4 · 标准库速通（上）总结

> **日期**：2026-10-21
> **投入**：约 2.5h
> **结果**：`ex01`–`ex06` 全部 `[PASS]`，`ruff check` 通过
> **提交**：`c90c9eb feat(w1): 完成标准库练习 ex01-ex06`（+ `92d45b7` 看板）
> **文件**：`progress/week1/stdlib_practice.py`

---

## 一、完成情况

| 练习 | 模块 | 核心 API | 状态 |
|---|---|---|---|
| ex01 | `pathlib` | `rglob` / `stat().st_size` / `sorted(key=, reverse=)` | ✅ PASS |
| ex02 | `json` | `dumps(default=...)` | ✅ PASS |
| — | `dataclasses` | `frozen` / `slots` / `__post_init__` | ✅ 手测验证 |
| ex03 | `re` + `collections.Counter` | `findall` / `most_common(n)` | ✅ PASS |
| ex04 | `itertools` | `zip_longest(fillvalue=)` / `chain.from_iterable` | ✅ PASS |
| ex05 | `logging` | `RotatingFileHandler` / `Formatter` / `addHandler` | ✅ PASS |
| ex06 | `collections.deque` | 单调队列，O(n) | ✅ PASS |

**质量指标**：`ruff check` 仅剩 2 个 `F401`（`defaultdict`、`field` 留给 Day5）。

---

## 二、六个知识点（每个都能在面试里说两句）

### 1. `pathlib` —— 别再用 `os.path` 拼字符串

```python
for p in root.rglob("*.py"):
    if p.is_file():
        result.append((str(p), p.stat().st_size))
return sorted(result, key=lambda x: x[1], reverse=True)
```

**必须记住的四个 API**：

| 需求 | 写法 |
|---|---|
| 递归找文件 | `root.rglob("*.py")` |
| 只找当前层 | `root.glob("*.py")` |
| 拼路径（不手动加 `/`） | `root / "sub" / "a.py"` |
| 建目录（父目录自动创建） | `Path("a/b/c").mkdir(parents=True, exist_ok=True)` |
| 文件大小 | `p.stat().st_size` |
| 读文本（指定编码！） | `p.read_text(encoding="utf-8")` |

**易错点**：
- **`rglob` 会返回目录**：实测建一个名叫 `a.py` 的目录，`rglob("*.py")` 会把它返回且 `is_file=False`。所以 `if p.is_file()` 不是保险，是**必需**
- `p.name` 只有文件名，`str(p)` 才是完整路径。**我在第一版就用了 `p.name`，会丢掉子目录信息**——测试只查条数和大小，测不出这个错误
- Windows 上不写 `encoding="utf-8"` 会用 GBK，中文直接 `UnicodeDecodeError`

**面试问法**：`pathlib` 比 `os.path` 好在哪？→ 面向对象、路径就是个对象能直接 `.read_text()`、用 `/` 运算符拼路径不会漏斜杠、跨平台。

### 2. `json.dumps(default=)` —— 序列化不认识的类型

```python
def default(o: object) -> str:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"不可序列化的类型：{type(o).__name__}")

return json.dumps(obj, default=default)
```

**机制**：`json.dumps` 只认识 `dict/list/str/int/float/bool/None`。遇到别的类型，它会**把这个对象交给你提供的 `default` 函数**，你返回什么，就用什么替换。

**三个必须知道的参数**：

| 参数 | 作用 | 为什么重要 |
|---|---|---|
| `ensure_ascii=False` | 中文不转成 `\u4e2d` | **不加这个，日志和接口响应里的中文全是乱码转义** |
| `default=fn` | 处理不可序列化对象 | datetime / Decimal / UUID / set 都靠它 |
| `indent=2` | 美化输出 | 只用于调试，**别用在 API 响应里**（体积翻倍） |

**易错点**：`default` 忘了写兜底 `raise TypeError`，会**隐式返回 `None`**——结果 JSON 里突然冒出个 `null`，比直接报错还难查。

### 3. `dataclasses` —— 不可变配置类的标准写法

```python
@dataclass(frozen=True, slots=True)
class DbConfig:
    host: str
    port: int = 5432
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError(f"port 必须在 1-65535 之间，当前值 {self.port}")
```

**三个装饰参数的收益**：

| 参数 | 得到什么 | 代价 |
|---|---|---|
| （默认） | 自动生成 `__init__` / `__repr__` / `__eq__` | — |
| `frozen=True` | 不可变，改字段抛 `FrozenInstanceError`；**可哈希**（能当 dict key / 放 set） | 不能在方法里 `self.x = ...` |
| `slots=True` | 无 `__dict__`，内存省 30-50%，**拼错属性名会立刻报错** | 不能动态加属性 |

**`__post_init__` 的时机**：`__init__` 末尾自动调用，**是构造后唯一能跑校验的钩子**。

**经典陷阱（周计划点名的面试题）**：
```python
@dataclass
class Bad:
    items: list[int] = []      # ValueError: mutable default <class 'list'> for field items is not allowed
```
原因：类的属性在**定义时求值一次**，所有实例共享同一个列表对象，改一个会影响全部。正确写法：
```python
items: list[int] = field(default_factory=list)     # 每次实例化都调用一次 list()
```
`frozen=True` 时这个限制**部分放松**：`tuple` 不可变所以能用 `= ()`，但真要用列表还是得 `default_factory`。

**（实测澄清）** `field(default=[])` 写法**也会报同样的错**——dataclasses 检查的是"默认值是否可变"，不看你怎么包装：

| 写法 | 结果 |
|---|---|
| `items: list[int] = []` | ❌ `ValueError` |
| `items: list[int] = field(default=[])` | ❌ `ValueError`（一样被拦） |
| `items: list[int] = field(default_factory=list)` | ✅ 每个实例拿到**独立**的空列表 |

**面试问法**：为什么要 `default_factory`？→ 可变默认值在定义时求值一次、所有实例共享，会互相污染。

### 4. `Counter` —— 统计就该用它

```python
words = re.findall(r"[a-z']+", text.lower())
return Counter(words).most_common(n)
```

`Counter` 是 `dict` 的子类，值 = 计数。

| 操作 | 写法 | 说明 |
|---|---|---|
| 计数 | `Counter(可迭代对象)` | 一次遍历完成 |
| 取 Top-N | `.most_common(n)` | 返回 `[(元素, 次数)]`，按次数降序 |
| 单个元素次数 | `c["a"]` | **不存在时返回 0，不报 KeyError**（这是和 dict 的关键差异） |
| 加法合并 | `c1 + c2` | 计数相加 |
| 取差 | `c1 - c2` | 只保留正数部分 |

**易错点**：`most_common()` 不传参数会返回全部（有序但不再是 Top-N 语义）；次数相同的元素顺序取决于插入顺序，**不要依赖它的稳定性**。

### 5. `itertools.zip_longest` —— 长度不等也能配对

```python
_MISSING = object()
pairs = zip_longest(a, b, fillvalue=_MISSING)
return [v for v in chain.from_iterable(pairs) if v is not _MISSING]
```

**`zip` vs `zip_longest`**：

| | `zip` | `zip_longest` |
|---|---|---|
| 长度不等 | **截断到最短** | 用 `fillvalue` 补齐 |
| 适用 | 严格等长 | 允许不等长 |

**⭐ 这题你做得最好的地方：用 `object()` 当哨兵**

```python
_MISSING = object()      # 独一无二的对象，谁都不可能等于它
```

如果图省事写 `fillvalue=""`，当列表里**本来就有空字符串**时会被误删。`object()` 每次调用都创建全新对象，`is` 比较永不为真——这是标准库自己也在用的套路（`dataclasses.MISSING`、`inspect.Parameter.empty`、`None` 本身的语义化替代）。

`chain.from_iterable(嵌套列表)` = 把 `[(a1,b1),(a2,b2)]` 摊平成 `a1,b1,a2,b2`。

### 6. `deque` 单调队列 —— 今天的算法题

```python
dq: deque[int] = deque()          # 存下标，值从队头到队尾单调递减
for i, v in enumerate(values):
    while dq and values[dq[-1]] <= v:
        dq.pop()                  # 比我小的都不可能是最大值了
    dq.append(i)
    if dq[0] <= i - k:
        dq.popleft()              # 队头滑出窗口
    if i >= k - 1:
        result.append(values[dq[0]])
```

**为什么不是每个元素都比一次？** 因为**每个下标最多进队一次、出队一次**，所以总操作数 ≤ 2n → **O(n)**。暴力法是 O(n·k)。

**为什么 `deque` 而不是 `list`？** `list.pop(0)` 是 O(n)（后面全部元素要前移），`deque.popleft()` 是 O(1)（双向链表块结构）。**队列/栈场景一律用 deque**。

**为什么存下标不存值？** 需要判断“队头是否滑出窗口”，这要用下标做比较。存值就不知道它的位置了。

**边界要自己验**：`k=1`（每个元素单独一个窗口）、`k=len(values)`（只有一个输出）——我实测过都正确。

**面试问法**：滑动窗口最大值的最优解？→ 单调队列 O(n)，队头永远是当前窗口最大值；也可以用大顶堆 O(n log n)。

### 7. `logging` 的菜谱（没有"思考"，只有"记忆"）

```python
logger = logging.getLogger("stdlib_practice")
handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1024*1024,
                              backupCount=3, encoding="utf-8")
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

**五个对象必须分清**：

| 对象 | 职责 |
|---|---|
| `Logger` | 入口，`logger.info(...)` 调它；按名字分层级（`a.b` 是 `a` 的子 logger） |
| `Handler` | 输出到哪（文件 / 控制台 / 网络）；`RotatingFileHandler` 是文件轮转 |
| `Formatter` | 长什么样（时间、级别、消息的格式） |
| `Filter` | 要不要放行（比级别更细的规则） |
| `Level` | 门槛（DEBUG < INFO < WARNING < ERROR） |

**轮转参数**：`maxBytes=1MB` + `backupCount=3` → `app.log` 满了改名 `app.log.1`，最多留 3 个，再老的删掉。**生产环境必备**，否则日志把磁盘写满。

**易错点**：`RotatingFileHandler` 在 `logging.handlers` 里，**不在 `logging` 顶层**。

**学完这个再看项目里的 `kb-service/src/kb_service/core/logging.py`**——那是同一个菜谱 + ContextVar 传 `trace_id`。你会发现"能看懂"了。

---

## 三、今天踩的三个坑

### 坑 1 · `port=0` 漏过校验（真 bug）

```python
if self.port < 0 or self.port > 65535:      # ❌ 0 会通过
if not 1 <= self.port <= 65535:             # ✅ 符合需求
```

**但真正值得记的是**：自检器**根本没测 `DbConfig`**，所以 6 个 `[PASS]` 全绿时这个 bug 依然存在。

> **`[PASS]` 只说明“被测到的部分对了”，不说明“代码对了”。**
> 这和 Day2 的 Bug#1（接口传不出非法参数，所以测不出来）是同一个道理。

**已手测边界**：`0` / `65536` / `-1` 拒绝，`1` / `65535` 通过，`frozen` 改字段抛 `FrozenInstanceError`。

### 坑 2 · 又见 `F811` 重复导入

```python
from collections import Counter, defaultdict, deque   # 第 21 行
from collections import deque                          # 又导一遍 → F811
```

和 Day3 的 `test_count_kbs` 重复定义**是同一类错误**：同名符号重复引入，后者覆盖前者。

**防范**：写 import 时按字母序一次性写完，别想起来一个加一个。

### 坑 3 · `return` 后面的死代码

```python
return result
raise NotImplementedError("ex06")     # 永远执行不到
```

不影响运行，但读代码的人会困惑。**写完要把脚手架的 `raise NotImplementedError` 和 `# TODO` 一起清掉。**

---

## 四、自测 6 问（闭卷）

1. `Path.rglob("*.py")` 和 `Path.glob("*.py")` 有什么区别？为什么 `rglob` 的结果要判断 `is_file()`？
2. `json.dumps` 不加 `ensure_ascii=False` 会怎样？`default=` 参数在什么时机被调用？
3. `@dataclass` 里 `items: list[int] = []` 为什么直接报错？`field(default_factory=list)` 和 `field(default=[])` 有什么区别？
4. `Counter["不存在的键"]` 返回什么？和普通 `dict` 有什么不同？
5. `zip_longest` 的 `fillvalue` 为什么用 `object()` 而不是 `""` 或 `None`？
6. 滑动窗口最大值为什么能用 O(n)？为什么 `deque` 比 `list` 适合做队列？

<details>
<summary>答案</summary>

1. `glob` 只看当前层，`rglob` 递归所有子目录。`rglob` 会把**名字匹配的目录**也返回，所以要 `is_file()` 过滤。
2. 中文会被转成 `\u4e2d\u6587` 这样的 ASCII 转义，日志不可读、响应体积变大。`default=` 在 `dumps` 遇到**它不认识的类型**时被调用，参数是那个对象。
3. 因为类属性在定义时求值一次、**所有实例共享同一个列表**，改一个实例会影响全部。Python 直接拦住。`default_factory=list` 每次实例化都调用一次 `list()` 得到新列表；`field(default=[])` 同样会报错（它还是共享同一个对象）。
4. 返回 `0`，不抛 `KeyError`。这是 `Counter` 的核心便利——统计场景不用先 `in` 判断。
5. `""` 可能与真实数据冲突（列表里本来就有空字符串），`None` 也可能是合法值。`object()` 每次创建**独一无二**的对象，`is` 比较永远不会误判——这是标准库通用的哨兵模式。
6. 每个下标**最多进队一次、出队一次**，总操作数 ≤ 2n。`deque.popleft()` 是 O(1)，而 `list.pop(0)` 要移动后面所有元素是 O(n)。

</details>

---

## 五、与项目的衔接

今天练的每个模块，都在 `kb-service` 里有真实用途：

| 今天练的 | 项目里的位置 | 什么时候会用到 |
|---|---|---|
| `pathlib` | `ex01` 同款 | W11 扫描上传目录、读 PDF |
| `json` + `default=` | `core/logging.py` 的 JSON 日志 | 现在就在用 |
| `dataclasses` | `schemas/` 用的是 pydantic（更重） | 但配置类、内部数据结构会用 dataclass |
| `Counter` | W13 可观测统计 | 统计接口调用频次 |
| `logging` 轮转 | `core/logging.py` | 现在就在用 |
| `deque` | W10 限流（滑动窗口） | 令牌桶、滑动窗口限流 |

**特别说 W10**：限流算法里的“滑动窗口计数”和今天 ex06 的单调队列思路同源——都是用 `deque` 维护一个会过期的窗口。

---

## 六、明天（Day5）的六个点

| 练习 | 模块 | 难点预警 |
|---|---|---|
| ex07 | `Protocol` | 结构化子类型：不继承也能满足，`mypy` 认账 |
| ex08 | `asyncio` + `Semaphore` + `TaskGroup` | **今日最难**：限并发 + 保持返回顺序 |
| ex09 | `argparse` | `action="store_true"` / `type=int` / `choices=` |
| ex10 | `contextlib.contextmanager` | `try/finally` 保证异常时也能清理 |
| ex11 | `functools.lru_cache` | **坑**：`cache_info()` 挂在装饰后的函数上 |
| ex12 | `StrEnum` + `defaultdict` | `defaultdict(list)` 省掉 `if key not in d` |

**Day5 结束后 Day6 是抄改 300 行代码** —— 那才是检验"能不能独立写出完整代码"的关卡。今天已经证明：**思路拆开了你就能写出来**。
