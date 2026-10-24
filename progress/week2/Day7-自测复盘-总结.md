# W2-Day7 · 自测复盘 + 收官总结（2026-10-24）

> 本文是 W2 的收官材料：自测成绩单 + 三条概念纠错 + 两次补课 + 收官数据。

## 一、自测成绩单：18 / 24（一轮压线过，及格线 18）

| 轮次 | 题号 | 得分 | 丢分点 |
|---|---|---|---|
| 一 迭代器/生成器 | Q1-Q4 | 6/8 | Q1 缺"为什么不能返回 None"；Q4 list 适用场景说错 |
| 二 装饰器/异常 | Q5-Q8 | 7/8 | Q5 FastAPI 后果没答（只说"丢失元信息"） |
| 三 魔术方法/工程 | Q9-Q12 | 5/8 | Q9 回退方向说反；Q10 答错默认 `==`；Q11 混淆 |

**对比 W1**：14 → 17（补测）→ **18（一次到位）**。丢分从"没内化设计意图"变成"概念精确性"——进步可见。

## 二、三条概念纠错（今天最值钱的部分）

### 1. `print` 的回退方向

```
print(obj) → 先找 __str__ → 没有才退回 __repr__
```
**方向是 str 优先**。"只写 repr 也够用"是因为 str 缺失时会退回 repr，不是 repr 优先。

### 2. `==` 与 `is`（补课 2）

| | `==` | `is` |
|---|---|---|
| 问的问题 | 相等吗？（语义由类型 `__eq__` 定义） | 同一个对象吗？（恒比 id，不可重载） |
| 内置类型 | 比值（list/str/int 都定义了 `__eq__`） | 通常 False |
| 自定义类未定义 `__eq__` | **退回身份比较** → 两个内容相同的对象 False | False |
| 正当用途 | 比值 | **只有 `x is None` / 哨兵** |

**小整数缓存陷阱**（实测三轮才复现）：`-5~256` 被 CPython 预建，区间内 `is` 碰巧 True；且同脚本的相同字面量会**编译期合并**、`256+1` 会被**常量折叠**——想让 257 分家必须 `int("257")` 运行时产生。结论：**判断值永远用 `==`**。

### 3. 三个"不"字辈（Q11 的混淆）

| 名字 | 意思 | 谁用 |
|---|---|---|
| `return NotImplemented` | 协商失败信号，"你去问别人"（无括号！） | `__eq__` 等双目运算 |
| `raise NotImplementedError` | 此方法必须由子类实现 | 抽象基类/骨架代码 |
| `raise StopIteration` | 迭代到头了 | `__next__` |

## 三、其他补强

- **Q1 补**：结束信号不能返回 None——数据里合法的 None 会和结束信号撞车，异常走独立通道
- **Q4 补**：该用 list 的场景 = 遍历多次 / 随机访问 / 要 len()；实测 200 万元素 list ≈77MB vs 生成器 ≈0MB
- **Q5 补**：忘加 `@wraps` → FastAPI 把 `*args/**kwargs` 当必填 query 参数 → **全部接口 422**
- **`__hash__` 联动**（补课 1）：定义 `__eq__` 后 Python 自动 `__hash__ = None`——因为相等语义变了，默认按地址的 hash 会让"相等的对象 hash 不同"，破坏 dict/set 根基；**故意禁用是保护**。补救：`__hash__` 与 `__eq__` 用同一批字段（如 `hash(tuple(self._items))`）。延伸：`@dataclass` 默认不可哈希，`frozen=True` 才生成 `__hash__`
- **Q12 满分**：`f.read()` 内存炸弹小文件零症状 → **smoke 全绿 ≠ 代码正确**，测试数据量要模拟生产规模

## 四、第四档 #03 战报

`review_03_stream.py`（ingest 批处理工具集）：**3/4 真懂档**
- ✅ P1 全量 `f.read()` 内存炸弹 / P2 `__iter__` 返 self / P4 `except Exception` 吞炸弹
- ❌ P3 定义 `__eq__` 未定义 `__hash__`（零症状，唯一漏网）——上面补课 1 已完整讲过

**三次轨迹**：#01 3/4 → #02 4/4 满分 → #03 3/4。

## 五、D6 阶段任务数据

- `stream_utils.py` 10/10：read_chunks（边读边吐）/ paginate（无限生成器不卡死）/ Cursor（可反复遍历 + 5 个魔术方法）
- 首版 3 个坑：`Cursor.__new__()` 遮蔽类名、`__eq__` 条件装反、`__next__` `>` 差等号（被验收器第 8 项挡住的潜伏雷）——全部自己修复

## 六、闭卷快问（睡前扫一眼，答案折叠）

<details><summary>1. print(obj) 的查找顺序？</summary>先 __str__，缺失退回 __repr__。</details>
<details><summary>2. 两个内容相同的自定义类对象 == 是 False，为什么？</summary>没定义 __eq__，退回身份比较（比 id/地址）。</details>
<details><summary>3. 定义 __eq__ 后为什么 __hash__ 变 None？</summary>相等语义变了，默认按地址 hash 会违反"相等对象必须同 hash"，Python 不敢猜就禁用。</details>
<details><summary>4. x is 256 为什么危险？</summary>小整数缓存 + 常量合并让它碰巧 True，不可依赖；比值永远用 ==。</details>
<details><summary>5. NotImplementedError 和 StopIteration 谁报"没元素"？</summary>StopIteration；NotImplementedError 是"子类必须实现"。</details>
