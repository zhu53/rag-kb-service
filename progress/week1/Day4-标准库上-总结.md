# Day4 · 标准库速通（上）【面试参考版】

> 日期：2026-10-21 ｜ ex01–ex06 全 PASS，ruff 通过 ｜ 文件：`progress/week1/stdlib_practice.py`
> 用法：§8 的"标准库选型速查"和 §9 追问链，是 Python 岗基础面的高频区。

---

## 1. `pathlib` —— 别再用 `os.path` 拼字符串

```python
for p in root.rglob("*.py"):
    if p.is_file():
        result.append((str(p), p.stat().st_size))
return sorted(result, key=lambda x: x[1], reverse=True)
```

| 需求 | 写法 |
|---|---|
| 递归找文件 | `root.rglob("*.py")` |
| 只找当前层 | `root.glob("*.py")` |
| 拼路径（不手动加 `/`） | `root / "sub" / "a.py"` |
| 建目录（父目录自动创建） | `Path("a/b/c").mkdir(parents=True, exist_ok=True)` |
| 文件大小 | `p.stat().st_size` |
| 读文本（**指定编码！**） | `p.read_text(encoding="utf-8")` |

**易错点**：
- **`rglob` 会返回目录**：实测建一个名叫 `a.py` 的目录，`rglob("*.py")` 会返回它且 `is_file=False`。所以 `if p.is_file()` 不是保险，是**必需**。
- `p.name` 只有文件名，`str(p)` 才是完整路径。第一版用了 `p.name` → 丢掉子目录信息，而测试只查条数和大小，**测不出这个错误**。
- Windows 不写 `encoding="utf-8"` 会用 GBK，中文直接 `UnicodeDecodeError`。

### 面试问法："pathlib 比 os.path 好在哪？"

**30 秒答案**："pathlib 把路径变成对象而不是字符串：拼接用 `/` 运算符，不会漏斜杠也不会双斜杠；读写直接 `.read_text()`、`.write_text()`，不用 `open()` 配 `os.path.join`；跨平台分隔符由库处理，Windows 反斜杠不用管；而且 `glob`/`rglob`/`stat` 都挂在对象上，代码读起来是链式的。os.path 是函数式字符串操作，容易在拼接和编码上出错。"

**追问**：`rglob` 和 `glob` 区别？→ 前者递归全部子目录；两者都可能返回**目录**，要 `is_file()` 过滤。

---

## 2. `json.dumps(default=)` —— 序列化不认识的类型

```python
def default(o: object) -> str:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"不可序列化的类型：{type(o).__name__}")

return json.dumps(obj, default=default)
```

**机制**：`json.dumps` 只认 `dict/list/str/int/float/bool/None`。遇到别的类型，把这个对象交给 `default` 函数，你返回什么就用什么替换。

| 参数 | 作用 | 为什么重要 |
|---|---|---|
| `ensure_ascii=False` | 中文不转成 `\u4e2d` | **不加这个，日志和接口响应里的中文全是转义** |
| `default=fn` | 处理不可序列化对象 | datetime / Decimal / UUID / set 都靠它 |
| `indent=2` | 美化 | 只用于调试，别用在 API 响应（体积翻倍） |

**易错点**：`default` 忘了兜底 `raise TypeError`，会**隐式返回 `None`** → JSON 里冒出 `null`，比直接报错更难查。

### 面试问法："接口返回里有 datetime，怎么序列化？"

**30 秒答案**："json 只认基础类型，遇到 datetime 会抛 TypeError。两种做法：序列化时用 default 回调把不认识的对象转成字符串，datetime 用 isoformat，其他类型抛 TypeError 兜底——不兜底会静默变成 null，特别难查；或者在模型层统一转换，比如 pydantic 的 model_dump(mode='json') 会按 JSON 规则序列化。另外中文一定要 ensure_ascii=False，否则响应里全是 \\u 转义，体积也变大。"

---

## 3. `dataclasses` —— 不可变配置类的标准写法

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

| 参数 | 得到什么 | 代价 |
|---|---|---|
| （默认） | 自动生成 `__init__` / `__repr__` / `__eq__` | — |
| `frozen=True` | 不可变（改字段抛 `FrozenInstanceError`）；**可哈希** | 方法里不能 `self.x = ...` |
| `slots=True` | 无 `__dict__`，省 30–50% 内存；**拼错属性名立刻报错** | 不能动态加属性 |

**`__post_init__` 时机**：`__init__` 末尾自动调用，**构造后唯一能跑校验的钩子**。

### 可变默认值陷阱（周计划点名的面试题）

```python
@dataclass
class Bad:
    items: list[int] = []      # ValueError: mutable default ...
```

原因：类属性**定义时求值一次**，所有实例共享同一个列表对象。正确写法：

```python
items: list[int] = field(default_factory=list)     # 每次实例化调用一次 list()
```

**实测澄清**：`field(default=[])` **也会报同样的错**——dataclasses 检查"默认值是否可变"，不看怎么包装。

| 写法 | 结果 |
|---|---|
| `items: list[int] = []` | ❌ ValueError |
| `items: list[int] = field(default=[])` | ❌ ValueError（一样被拦） |
| `items: list[int] = field(default_factory=list)` | ✅ 每实例独立列表 |

### 面试问法："为什么 dataclass 不允许可变默认值？"

**30 秒答案**："因为类属性在定义时求值一次，所有实例共享同一个对象——改一个实例的列表会影响全部。这是 Python 里经典的"可变默认参数"陷阱，函数默认参数 `def f(x=[])` 是同一个病。Python 在 dataclass 这里直接拦下来（ValueError），要求用 default_factory，每次实例化调用一次工厂拿到新对象。frozen=True 也不能豁免，只是 tuple 这类不可变默认值天然安全。"

**追问链**：
- 追问①："`frozen=True` 就完全不可变吗？" → 浅不可变：字段不能重新绑定，但字段指向的可变对象（list/dict）内容仍能改。要彻底不可变用 tuple/frozen 的嵌套结构。
- 追问②："`slots=True` 的收益和代价？" → 省 `__dict__` 内存、属性访问略快；代价是不能动态加属性、不能多重继承带 slots 的类（复杂）、pickle 需注意。
- 追问③："dataclass 和 pydantic 怎么选？" → dataclass 轻量、标准库、无运行时校验（除非自己写 `__post_init__`）；pydantic 有类型转换与校验，适合外部输入边界（API 请求体/配置）。内部数据结构用 dataclass，边界数据用 pydantic。

---

## 4. `Counter` —— 统计就该用它

```python
words = re.findall(r"[a-z']+", text.lower())
return Counter(words).most_common(n)
```

`Counter` 是 `dict` 的子类，值 = 计数。

| 操作 | 写法 | 说明 |
|---|---|---|
| 计数 | `Counter(可迭代对象)` | 一次遍历 |
| Top-N | `.most_common(n)` | 返回 `[(元素, 次数)]`，按次数降序 |
| 单个元素 | `c["a"]` | **不存在返回 0，不抛 KeyError**（与 dict 的关键差异） |
| 合并 | `c1 + c2` | 计数相加 |
| 取差 | `c1 - c2` | 只保留正数部分 |

**易错点**：`most_common()` 不传参数返回全部（不再是 Top-N 语义）；**次数相同的元素顺序不保证稳定**，别依赖。

---

## 5. `itertools.zip_longest` + 哨兵对象

```python
_MISSING = object()
pairs = zip_longest(a, b, fillvalue=_MISSING)
return [v for v in chain.from_iterable(pairs) if v is not _MISSING]
```

| | `zip` | `zip_longest` |
|---|---|---|
| 长度不等 | **截断到最短** | 用 `fillvalue` 补齐 |

**⭐ 用 `object()` 当哨兵**：

```python
_MISSING = object()      # 独一无二，谁都不可能等于它
```

写 `fillvalue=""` 时，列表里**本来就有空字符串**会被误删；`None` 也可能是合法值。`object()` 每次创建全新对象，`is` 比较永不为真——标准库自己也在用（`dataclasses.MISSING`、`inspect.Parameter.empty`）。

`chain.from_iterable(嵌套)` = 把 `[(a1,b1),(a2,b2)]` 摊平成 `a1,b1,a2,b2`。

### 面试问法："Python 里怎么表示'没有值'？"

**30 秒答案**："用独一无二的哨兵对象，通常是模块级 `_MISSING = object()`，然后用 `is` 比较。不能用 None，因为 None 常是合法业务值；也不能用空字符串或 0，会和真实数据撞车。is 比较的是身份，哨兵对象没有别人能拿到引用，所以绝不会误判。标准库就是这么做的——dataclasses.MISSING、inspect.Parameter.empty 都是 object() 哨兵。"

---

## 6. `deque` 单调队列（算法题，白板会考）

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

- **为什么 O(n)**：每个下标最多进队一次、出队一次 → 总操作 ≤ 2n。暴力 O(n·k)。
- **为什么 deque 不是 list**：`list.pop(0)` 是 O(n)（后面全部前移），`deque.popleft()` 是 O(1)（分块双向链表）。**队列/栈场景一律 deque**。
- **为什么存下标不存值**：要判断"队头是否滑出窗口"，必须知道位置。
- **边界自验**：`k=1`、`k=len(values)` 都实测正确。

### 面试问法："滑动窗口最大值的最优解？"

**30 秒答案**："单调队列，O(n)。维护一个存下标的双端队列，队列里的值从队头到队尾单调递减：新元素进来时把队尾所有比它小的弹掉（它们不可能再成为最大值），然后入队；再检查队头是否滑出窗口，滑出就 popleft；窗口成型后队头就是最大值。用 deque 是因为两端操作都要 O(1)，list 的 pop(0) 是 O(n)。也可以用大顶堆做到 O(n log n)，代码更简单但更慢。"

---

## 7. `logging` 的菜谱（今天只记配方）

```python
logger = logging.getLogger("stdlib_practice")
handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1024*1024,
                              backupCount=3, encoding="utf-8")
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

| 对象 | 职责 |
|---|---|
| `Logger` | 入口，按名字分层（`a.b` 是 `a` 的子 logger，向父冒泡） |
| `Handler` | 输出到哪（文件/控制台/网络）；`RotatingFileHandler` 是文件轮转 |
| `Formatter` | 长什么样 |
| `Filter` | 要不要放行（比级别更细的规则） |
| `Level` | 门槛（DEBUG < INFO < WARNING < ERROR） |

**轮转参数**：`maxBytes=1MB` + `backupCount=3` → `app.log` 满了改名 `app.log.1`，最多留 3 个，更老的删掉。**生产必备**，否则日志写满磁盘。
**易错点**：`RotatingFileHandler` 在 `logging.handlers` 里，**不在 `logging` 顶层**。

---

## 8. 标准库选型速查（面试"你会用什么"）

| 需求 | 首选 | 别用 |
|---|---|---|
| 路径操作 | `pathlib.Path` | `os.path` 字符串拼接 |
| 计数统计 | `collections.Counter` | 手写 dict + if |
| 队列/栈 | `collections.deque` | `list` 的 `pop(0)` / `insert(0)` |
| 分组 | `defaultdict(list)` | 手写 `if k not in d` |
| 长度不等配对 | `zip_longest(fillvalue=哨兵)` | 手写索引 |
| 扁平化 | `chain.from_iterable` | 双层循环 + extend |
| 不可变数据类 | `@dataclass(frozen=True)` | 手写 `__init__`/`__eq__` |
| 序列化 | `json.dumps(default=...)` | 手写拼字符串 |
| 日志 | `logging` + `RotatingFileHandler` | `print` |

## 9. 追问链（面试深挖预演）

| 起点 | 追问 | 你要能答 |
|---|---|---|
| pathlib | 怎么跨平台处理分隔符？ | `/` 运算符与 `Path` 内部处理；`as_posix()` 输出正斜杠 |
| json | 为什么不推荐 `indent` 用于生产？ | 体积成倍增长；调试在客户端格式化即可 |
| dataclass | frozen 真的不可变？ | 浅不可变；嵌套可变对象仍可改 |
| Counter | most_common 怎么实现？ | `heapq.nlargest`（n 给定）或全排序（n 为 None） |
| 哨兵 | 为什么用 `is` 不用 `==`？ | `==` 可被重载、可能相等；`is` 比身份，唯一可靠 |
| deque | 底层结构？ | 分块双向链表（block 数组 + 索引），两端 O(1)，中间 O(n) |
| 单调队列 | 为什么弹队尾？ | 更小且更早入队的元素永远竞争不过新元素（既小又新） |
| logging | 为什么用轮转？ | 磁盘写满、单文件过大不便检索 |

## 10. 30 秒答案集

1. **pathlib 优势** → 对象化、`/` 拼路径、自带读写、跨平台。
2. **json 中文** → `ensure_ascii=False`；`default=` 处理非基础类型。
3. **dataclass 可变默认** → 定义时求值共享；用 `default_factory`。
4. **Counter 缺键** → 返回 0 不抛 KeyError。
5. **哨兵** → `object()` + `is` 比较，避免与真实值撞车。
6. **deque vs list** → 两端 O(1) vs `pop(0)` O(n)。
7. **滑动窗口最大值** → 单调队列 O(n)，队头即最大。
8. **日志轮转** → maxBytes + backupCount，防磁盘写满。

## 11. 闭卷自测

1. `rglob` 和 `glob` 区别？为什么结果要 `is_file()`？
2. `json.dumps` 不加 `ensure_ascii=False` 会怎样？`default=` 何时调用？
3. `items: list[int] = []` 为什么报错？`field(default=[])` 与 `default_factory=list` 区别？
4. `Counter["不存在"]` 返回什么？
5. `fillvalue` 为什么用 `object()`？
6. 滑动窗口最大值为什么 O(n)？为什么用 deque？

<details><summary>答案</summary>
1. glob 只看当前层，rglob 递归；rglob 会返回名字匹配的目录，需 is_file 过滤。
2. 中文变 \uXXXX 转义、体积变大；default 在遇到不认识的类型时被调用，参数是那个对象。
3. 类属性定义时求值一次、所有实例共享；field(default=[]) 同样报错，default_factory=list 每次新建。
4. 0，不抛 KeyError。
5. "" 与真实空串冲突、None 可能是合法值；object() 独一无二，is 永不误判。
6. 每个下标最多进出队一次（≤2n）；deque.popleft O(1)，list.pop(0) O(n)。
</details>
