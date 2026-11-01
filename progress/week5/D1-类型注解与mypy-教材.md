# D1 教材 · 类型注解与 mypy（零基础版）

> 假设你**没认真写过类型注解**，最多写过 `def f(x: int) -> str` 这种"看起来像那么回事"的表面功夫。  
> 读完本篇 + 做完 §6 的实验，你能做到两件事：**让你项目上的 mypy 从 58 个错误降到只剩 8 个**，  
> 并且**看懂它说的每一句话**——包括那 8 个你今天故意不修的。
>
> 本篇所有输出都是我在这台机器上**真跑出来的**（mypy 2.4.0 / Python 3.11 / 你的项目）。你可以逐条对照。
>
> **命令一律给两套写法**：上面是 **PowerShell**（你 PyCharm 终端默认的），下面是 **bash**（Git Bash / Linux / CI）。
> 两个相邻代码块就是这么回事，输出一致，跑哪套都行。翻译规律见 §8.4。

---

## §0 先看一个你上周亲手做过的事

W4 你写了 `FakeKBRepo`，用它替掉真的 `KBRepository` 跑单元测试，57 个测试全绿。

现在回答一个问题：

> **你凭什么认为 `FakeKBRepo` 的行为和 `KBRepository` 是一致的？**

你可能会说："我照着真 repo 的方法名写的，6 个方法，参数也抄对了。"

那就再问一层：

- 如果 fake 的 `update` 参数顺序写反了（`update(data, kb_id)`）——测试会红，因为传错了。
- 如果 fake 的 `get` 返回 `dict`，而真 repo 返回 `dict | None`——**你的测试会不会红？**  
  只有当某个用例恰好碰到"找不到"的分支才会红。碰不到就永远绿。
- 如果 fake 少了一个 `count_owned` 方法，但你所有的用例都没走到那条路径——**全绿**。

也就是说：**"57 个测试全绿"这件事，强度和"我肉眼比对过 6 个方法签名"差不多。**

这正是本周要解决的东西。类型检查器是那个**不需要你肉眼比对、且永远不会累**的读者。

---

## §1 五分钟：让 mypy 说第一句话

### 1.1 它在不在

```powershell
# Windows PowerShell
cd kb-service
& .\.venv\Scripts\python.exe -m mypy --version
```

```bash
# Git Bash（Windows）/ Linux / macOS
cd kb-service
./.venv/Scripts/python.exe -m mypy --version    # Windows 的 venv 在 Scripts\ 下
# 真·Linux 上是 .venv/bin/python；CI 里统一用 uv run mypy
```

真实输出：

```
mypy 2.4.0 (compiled: yes)
```

`mypy` 是 dev 依赖里的（`pyproject.toml` 的 `[dependency-groups] dev` 里有 `mypy>=1.13`），早就装好了，只是你从没用过。

### 1.2 第一个错误

在任意临时目录写一个 `demo.py`：

```python
def greet(name):
    return "hi " + name


def total(items: list) -> int:
    return sum(items)
```

跑：

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy --strict demo.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy --strict demo.py
```

真实输出：

```
demo.py:1: error: Function is missing a type annotation  [no-untyped-def]
demo.py:5: error: Missing type arguments for generic type "list"  [type-arg]
Found 2 errors in 1 file (checked 1 source file)
```

### 1.3 把这个输出拆开看

一条 mypy 错误有固定的五段结构：

```
demo.py : 1 : error: Function is missing a type annotation  [no-untyped-def]
   ↑      ↑     ↑              ↑                                  ↑
 哪个文件 哪一行 严重级别      人话描述                          错误码
```

**第五段（错误码）是最重要的**，因为：

1. 它可以被**精确忽略**：`# type: ignore[no-untyped-def]`
2. 它是你查文档的入口：搜索 `mypy no-untyped-def`
3. 同一种错误码，修法永远一样。**58 个错误往往只有 6 种错误码**——这是后面最省力的地方。

### 1.4 两个错误分别是什么意思

**第一个 `no-untyped-def`**：`def greet(name)` 没写 `name` 的类型，也没写返回值类型。

`--strict` 模式下，没注解的函数**整个函数体都不检查**。这是关键——mypy 不是"检查你的代码"，它是"检查**有注解的地方**，没注解就当你没说话"。

**第二个 `type-arg`**：`items: list` 里的 `list` 是个"泛型"（generic），意思是"某种东西的列表"，但你没说是什么东西。

修法是写 `list[int]`——`int` 就是"类型参数"（type argument）。裸写 `list` 等于 `list[Any]`，`Any` 会污染它流经的所有地方。

### 1.5 修好它，看它变绿

```python
def greet(name: str) -> str:
    return "hi " + name


def total(items: list[int]) -> int:
    return sum(items)
```

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy --strict demo.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy --strict demo.py
```

```
Success: no issues found in 1 source file
```

**第一课记住：mypy 不猜。你给它多少信息，它才检查多少东西。**

---

## §2 关键认知：注解在运行时会被丢掉

这是零基础最容易误解的地方，一定要亲手跑一遍。

```python
def add(a: int, b: int) -> int:
    return a + b


print("传入字符串:", add("1", "2"))
print("注解内容:", add.__annotations__)
```

真实输出：

```
传入字符串: 12
注解内容: {'a': <class 'int'>, 'b': <class 'int'>, 'return': <class 'int'>}
```

看仔细：**传了两个字符串进去，Python 一声没吭，还给你拼出了 `"12"`。**

为什么？

| 阶段    | 注解的命运                                                                   |
| ----- | ----------------------------------------------------------------------- |
| 函数定义时 | 被求值（或存成字符串，见 `from __future__ import annotations`），塞进 `__annotations__` |
| 函数调用时 | **完全不看**。Python 的调用机制里根本没有"检查注解"这一步                                     |

所以类型注解的本质是：**给"另一个读者"（mypy / IDE / 人）看的说明书，不是给 Python 运行时看的守门员。**

### 那为什么还要写？

因为**另一个读者在你要上线之前，会把所有说明书核对一遍**：

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src    # ← 这一步就是"核对说明书"
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src
```

如果上面那个 `add` 出现在你的项目里，mypy 会报：

```
error: Argument 1 to "add" has incompatible type "str"; expected "int"  [arg-type]
```

**你还没运行代码，它就已经知道你要炸了。** 这是单元测试做不到的——测试只能测你想到的输入，类型检查能覆盖你所有写出来的代码路径。

### 什么时候需要"运行时检查"

| 需求                                    | 用什么               |
| ------------------------------------- | ----------------- |
| 我写的调用别写错                              | mypy（静态）          |
| **外部传进来的**数据别是垃圾（HTTP 请求体、JSON、命令行参数） | **pydantic**（运行时） |

这也是为什么你项目里 `KBOut` / `KBCreate` 用 pydantic，而内部函数用注解 + mypy。**边界用运行时校验，内部用静态检查**——这句话可以直接当面试答案。

---

## §3 概念拆解（术语都得能解释）

### 3.1 静态检查 vs 动态检查

- **静态**：不运行代码，只看源码文本。mypy 就是静态的。
- **动态**：运行时判断。`if not isinstance(x, int): raise TypeError` 是动态的。

静态的优点是**能在代码跑起来之前发现问题**，缺点是需要你写注解，且它不知道运行时真值。

### 3.2 鸭子类型（duck typing）

"如果它走起来像鸭子、叫起来像鸭子，那它就是鸭子。"

Python 天生是鸭子类型：你调 `repo.get(id)`，Python 只关心 `repo` 有没有 `get` 方法，不关心它是什么类。

**这就是 `FakeKBRepo` 能绕过测试的原因**——运行时它确实有 `get`，所以能工作。

但鸭子类型有个致命弱点：**错误发现得太晚**。你只能在它真的被调用、且真的走错分支时才炸。

### 3.3 名义类型（nominal typing）vs 结构化类型（structural typing）

这两个词是理解 W3 那个 `Protocol` 伏笔的钥匙，务必搞清。

|           | 判断标准                   | 例子                                      |
| --------- | ---------------------- | --------------------------------------- |
| **名义类型**  | 你**声明**了你是它的子类才算       | `class Fake(KBRepository)` → 算；不继承 → 不算 |
| **结构化类型** | 你**长得**像它就算（方法齐全、签名匹配） | 只要 6 个方法签名都对，不继承也算                      |

- Java / C# 是名义类型
- TypeScript / Go(interface) 是结构化类型
- **Python 默认名义类型，但 `Protocol` 打开结构化类型**

现在看你项目里的 `KBRepository`（`src/kb_service/repositories/kb_repo.py:10`）：

```python
class KBRepository:            # ← 普通类，不是 Protocol
    def create(self, owner_id: UUID, data: KBCreate) -> dict[str, Any]: ...
    def get(self, kb_id: UUID) -> dict[str, Any] | None: ...
    ...
```

它是**具体类**。而 `KBService.__init__` 的签名是：

```python
def __init__(self, repo: KBRepository | None = None) -> None:
```

于是在 mypy 眼里：`FakeKBRepo` 没继承 `KBRepository` → **名义上不是它** → 类型不兼容。

**哪怕 6 个方法签名一模一样。** 这就是 §5 那 8 个 `arg-type` 的全部原因。今天先不修，D2 专门讲怎么用 `Protocol` 收这个线。

### 3.4 `--strict` 到底开了什么

`--strict` 不是一个开关，是**一整套开关的打包**。你项目 `pyproject.toml` 里写的就是 `strict = true`。

它主要打开这些（记住三个就够面试用）：

| 开关                      | 干了什么                                     |
| ----------------------- | ---------------------------------------- |
| `disallow_untyped_defs` | 没注解的函数直接报错（对应 `no-untyped-def`）          |
| `disallow_any_generics` | 裸 `list` / `dict` 报错（对应 `type-arg`）      |
| `warn_return_any`       | 返回 `Any` 但声明了具体类型时报错（对应 `no-any-return`） |

另外还有 `no_implicit_optional`（不能再用 `x: str = None` 这种老写法）等十几个。

**为什么要 strict？** 因为宽松模式下，mypy 碰到没注解的东西就静默跳过——你得到的是"虚假的绿色"。strict 会把"你没说"也当成问题。

---

## §4 在你的真项目上跑：从"安静"到 58 个错误

这一段是今天最重要的部分。你会看到一件事：**mypy 一开始根本没看你的代码，却假装很安静。**

### 4.1 先看 src：只有 3 个错误

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src
```

真实输出（省略相同前缀）：

```
src\kb_service\core\config.py:45: error: Unused "type: ignore" comment  [unused-ignore]
src\kb_service\core\security.py:33: error: Returning Any from function declared to return "str"  [no-any-return]
src\kb_service\services\llm_client.py:41: error: Returning Any from function declared to return "str"  [no-any-return]
Found 3 errors in 3 files (checked 28 source files)
```

28 个文件，只有 3 个错误。你可能会想："我的代码挺干净嘛。"

**记住这个感觉，§4.4 会打碎它。**

### 4.2 再看 tests：20 个错误，但没有一条在说你的代码

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy tests
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy tests
```

真实输出（截取）：

```
tests\conftest.py:9: error: Skipping analyzing "kb_service.core.security": module is installed, but missing library stubs or py.typed marker  [import-untyped]
tests\fakes.py:13: error: Skipping analyzing "kb_service.schemas.kb": ...  [import-untyped]
...
tests\fakes.py: error: Source file found twice under different module names: "fakes" and "tests.fakes"
Found 20 errors in 8 files (errors prevented further checking)
```

注意关键词：**`Skipping analyzing`（跳过分析）**。

mypy 在说："`kb_service` 在我眼里是**一个装好的第三方库**，而这个库没有告诉我它有类型信息，所以我不分析它。"

19 个 `import-untyped` 全是这一句。最后的 `errors prevented further checking` 意思是"错误太多，我后面不检查了"。

**所以：此刻 mypy 对你的 `FakeKBRepo`、对你的 service、对你的协议，一个字都没看过。**

### 4.3 `py.typed`：一个空文件解决 19 个错误

mypy 怎么判断一个已安装的包"有没有类型"？

靠 **PEP 561** 规定的一个约定：**包目录下存在一个名为 `py.typed` 的文件**（内容无关，空文件即可）。

你的项目是 `src` 布局 + editable 安装（`.venv\Lib\site-packages\_editable_impl_kb_service.pth`），对 mypy 来说 `kb_service` 就是"装好的包"，而 `src/kb_service/` 下没有 `py.typed` → 它拒绝分析。

```powershell
# Windows PowerShell
# 建一个空文件（-Force 让它在文件已存在时也不报错）
New-Item src\kb_service\py.typed -ItemType File -Force
& .\.venv\Scripts\python.exe -m mypy tests
```

```bash
# Git Bash / Linux / macOS
touch src/kb_service/py.typed
./.venv/Scripts/python.exe -m mypy tests
```

真实输出：

```
tests\fakes.py: error: Source file found twice under different module names: "fakes" and "tests.fakes"
Found 1 error in 1 file (errors prevented further checking)
```

19 个错误一次消失。**一个空文件，解决了 19 个"错误"——因为它们本来就不是错误，是门没开。**

> 这里有个重要的工程认知：**报错数量不是一个可靠的进步指标。** 同一个项目，门没开时 20 个错，门开了可能是 58 个错。数字变大，但你是真的在进步。

### 4.4 剩下那个 `duplicate module`，以及门彻底打开后的 58 个

`Source file found twice under different module names` 的意思是：同一个 `tests/fakes.py`，mypy 一会儿把它当模块 `fakes`，一会儿当 `tests.fakes`——因为 `tests/` 目录下没有 `__init__.py`，mypy 不确定包边界在哪。

修法不是加 `__init__.py`（那会影响 pytest 的导入行为），而是在配置里告诉 mypy **按什么规则切包**。两个设置配合使用：

```toml
# pyproject.toml 的 [tool.mypy] 段，加两行
mypy_path = "src"
explicit_package_bases = true
```

- `mypy_path = "src"`：告诉 mypy 去 `src/` 下面找包
- `explicit_package_bases = true`：让 mypy 按 `__init__.py` 的位置确定每个模块的"包根"，从而不再出现一个文件两个名字

加完直接跑（**不再需要任何命令行参数**）：

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
```

真实输出（末尾）：

```
Found 58 errors in 14 files (checked 46 source files)
```

**从 3 个到 58 个。** 46 个文件被真正检查了（之前 `src` 只查 28 个，`tests` 一个都没查）。

这就是今天真正要处理的东西。

---

## §5 读懂 58 个错误：其实只有六类

跑一条统计命令（后面 §8 有速查）。两种终端各一条，**输出完全一样**：

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py |
  Select-String '\[([a-z-]+)\]$' |
  ForEach-Object { $_.Matches[0].Groups[1].Value } |
  Group-Object | Sort-Object Count -Descending |
  Select-Object Count, Name
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep -oE "\[[a-z-]+\]$" | sort | uniq -c | sort -rn
```

> 注意两处细节：**mypy 把错误打到 stdout**（实测 stderr 为空），所以**不需要 `2>&1`**；
> PowerShell 里加 `2>&1` 反而会把每行变成 ErrorRecord、并把 `$?` 标成失败。

真实输出：

```
     40 [no-untyped-def]
      8 [arg-type]
      5 [type-arg]
      2 [no-any-return]
      2 [index]
      1 [unused-ignore]
```

**58 个错误 = 6 种病。** 这是类型工程里最省力的一课：不要一个一个改，要按错误码**批量**改。

### 5.1 `no-untyped-def` × 40 —— 便宜的机械活

真实例子：

```
tests\conftest.py:37: error: Function is missing a type annotation for one or more parameters
tests\test_respx_demo.py:5: error: Function is missing a return type annotation
tests\test_respx_demo.py:5: note: Use "-> None" if function does not return a value
```

**测试函数几乎都是"不返回值"的**，所以绝大多数就补一个 `-> None`。带参数的再给参数标类型。

这类错误**占了 40/58**，但它是纯体力活——修完你会发现它几乎不改变你对代码的理解。**先清掉它，是为了腾出脑子看后面那 8 个。**

### 5.2 `type-arg` × 5 —— 裸泛型

```
tests\test_unit_demo.py:14: error: Missing type arguments for generic type "dict"
tests\test_kb_service_unit.py:21: error: Missing type arguments for generic type "list"
tests\test_rag_async.py:22: error: Missing type arguments for generic type "dict"
```

`dict` → `dict[str, Any]`，`list` → `list[str]`（按实际内容写）。

**为什么要写？** 因为裸 `dict` 等于 `dict[Any, Any]`，而 `Any` 的特性是"和谁都能配"——它会一路传染下去，让下游所有的检查失效。

> **`Any` 是类型系统的黑洞：进去的东西出不来，出来的一切都不再被检查。**

### 5.3 `index` × 2 —— mypy 在逼你处理 `None`

真实代码（`tests/test_doc_service.py:126`）：

```python
assert world.kb_repo.get(world.kb_id)["doc_count"] == 1
```

真实报错：

```
tests\test_doc_service.py:126: error: Value of type "dict[str, Any] | None" is not indexable  [index]
```

|                                 |                                        |
| ------------------------------- | -------------------------------------- |
| `get()` 的返回类型是 \`dict[str, Any] | None`。**`None\` 不能下标取值\*\*，所以 mypy 拒绝。 |

运行时为什么没炸？因为那行之前你刚 `incr_doc_count`，数据一定存在——**但这是"你知道"，不是"类型系统知道"**。

修法是把这个"我知道"变成代码：

```python
row = world.kb_repo.get(world.kb_id)
assert row is not None        # ← 让类型系统也知道
assert row["doc_count"] == 1
```

**这不是给 mypy 让路的废话**：如果哪天有人改坏了 `incr_doc_count`，这里的 `assert` 会先炸，报错信息比 `TypeError: 'NoneType' object is not subscriptable` 清楚得多。


> 这一条和你 W4 学的"测试要有杀伤力"是同一个思路：**不要依赖"我知道"，要让机器也知道。**

### 5.4 `no-any-return` × 2 —— 别人没标类型，账算在你头上

```
src\kb_service\core\security.py:33: error: Returning Any from function declared to return "str"
src\kb_service\services\llm_client.py:41: error: Returning Any from function declared to return "str"
```

`security.py:33` 附近是这样：

```python
def create_access_token(...) -> str:
    ...
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
```

`jwt.encode` 来自 `python-jose`，这个库**没有类型标注**（`pyproject.toml` 里你写了 `module = ["passlib.*", "jose.*"] / ignore_missing_imports = true`，意思是"别管这个库"）。

于是 `jwt.encode(...)` 的返回类型被推断成 `Any`。而你的函数声明返回 `str`。**返回 `Any` 给一个声称返回 `str` 的函数，strict 下算错。**

两种修法，各有取舍：

```python
# 写法一：运行时真的转一下
return str(token)

# 写法二：向 mypy 断言"相信我，它就是 str"
from typing import cast
return cast(str, token)
```

- `str(token)`：有运行时开销（极小），但**真的保证**返回 str（万一库返回 bytes，会被转成字符串，不是崩）
- `cast(str, token)`：零运行时开销，本质是**你对 mypy 说"我知道我在干什么"**——说错了它不管你

**面试可以这么答**：`cast` 是"骗过检查器"，`str()` 是"真的转换"；对一个返回类型不确定的第三方库，我倾向 `cast` 加注释说明依据，因为它不改变运行时行为。

### 5.5 `unused-ignore` × 1 —— 过期的创可贴

```
src\kb_service\core\config.py:45: error: Unused "type: ignore" comment  [unused-ignore]
```

`config.py` 里：

```python
return Settings()  # type: ignore[call-arg]
```

这句 ignore 是当年"不加就报错"时贴上的。现在 `pydantic.mypy` 插件（`pyproject.toml` 里 `plugins = ["pydantic.mypy"]`）能理解 pydantic 模型的字段来自环境变量，不再报错——**创可贴过期了，撕掉**。

> 这就是 strict 里 `warn_unused_ignores` 的价值：**它让"临时妥协"无法悄悄变成永久垃圾。**

### 5.6 `arg-type` × 8 —— 今天不修，但必须看懂

真实输出（全部 8 条）：

```
tests\test_unit_demo.py:22: error: Argument "repo" to "KBService" has incompatible type "FakeRepo"; expected "KBRepository | None"  [arg-type]
tests\test_kb_service_unit.py:29: error: Argument "repo" to "KBService" has incompatible type "FakeKBRepo"; expected "KBRepository | None"  [arg-type]
tests\test_rag_async.py:61: error: Argument "doc_repo" to "RagService" has incompatible type "FakeDocRepo"; expected "DocRepository | None"  [arg-type]
...
```

翻译成人话：

> "你把 `FakeKBRepo` 传给了要求 `KBRepository` 的参数。在我（mypy）眼里，`FakeKBRepo` **不是** `KBRepository`。"

可是它的 6 个方法签名**真的**和真 repo 一模一样。为什么不算？

回到 §3.3：`KBRepository` 是**普通类**，Python 默认**名义类型**——不继承就不算。所以这不是"你写错了"，而是"设计上还没允许 fake 顶替真货"。

**这 8 条就是 W3 那个 `Protocol` 伏笔的收线点。** D2 会用 `Protocol` 把 `KBRepository` 改成"结构化契约"，这 8 条会一次性消失——而且从此以后，**只要你改了真 repo 的方法签名，fake 不跟着改就立刻红**。这才是"契约"的真正含义。

> 今天请**故意留着这 8 条**。让你亲手体验一次：**类型错误是分层的**——便宜的那 50 个是"你没写注解"，贵的这 8 个是"你的设计还没表达出来"。

---

## §6 动手实验（今天的任务）

**目标：把 58 个错误降到只剩 8 个 `arg-type`。**

前提：先做完 §4 的配置（`py.typed` + `mypy_path` + `explicit_package_bases`），否则你连 58 个都看不到。

### 任务清单

| # | 任务 | 涉及 |
|---|---|---|
| 1 | 建 `src/kb_service/py.typed`（空文件） | PEP 561 |
| 2 | `pyproject.toml` 的 `[tool.mypy]` 加 `mypy_path` + `explicit_package_bases` | 包边界 |
| 3 | 清 40 个 `no-untyped-def`：测试函数补 `-> None`，带参数的补参数类型 | 体力活 |
| 4 | 清 5 个 `type-arg`：裸 `dict`/`list` 补类型参数 | 泛型 |
| 5 | 清 2 个 `index`：先用 `assert row is not None` 收窄 | `Optional` 收窄 |
| 6 | 清 2 个 `no-any-return` | `cast` vs `str()` |
| 7 | 清 1 个 `unused-ignore` | 过期创可贴 |

**不要动那 8 个 `arg-type`。**

### 验收

```powershell
# Windows PowerShell
cd kb-service
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py |
  Select-String '\[([a-z-]+)\]$' |
  ForEach-Object { $_.Matches[0].Groups[1].Value } |
  Group-Object | Sort-Object Count -Descending |
  Select-Object Count, Name
```

```bash
# Git Bash / Linux / macOS
cd kb-service
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep -oE "\[[a-z-]+\]$" | sort | uniq -c | sort -rn
```

**合格标准**：统计结果只剩 `8 [arg-type]`。

如果多出别的错误码，别急着问——**先自己读那一行**：多半是你补注解时写宽了（比如该 `list[str]` 写成 `list[Any]`），或者写窄了（比如实际可能为 `None` 却标成 `str`）。**加注解暴露新问题，是好事。**

### 另外两条兜底要求

1. **测试必须仍然全绿**：`pytest -q` → `57 passed`。注解不该改变任何运行时行为；如果红了，说明你顺手改坏了逻辑。

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests scripts conftest.py
```

### 卡住了？按这个顺序看提示（一次只看一层）

**第 1 层（只告诉你在哪几类里）**
> 40 个 `no-untyped-def` **全都在 tests 里**，一个都不在 src。分布是：`test_kb_service_unit.py` 8 个、`test_rag_async.py` 7 个、`test_config.py` 7 个，其余四个文件各 1–4 个。从最多的那个文件开始，几乎全是"缺 `-> None`"。

**第 2 层（如果你分不清"参数注解"和"返回注解"）**
> `def test_x(world: World) -> None:` —— 形参在名字后面加 `: 类型`，返回值在括号后面加 `-> 类型`。测试函数不 `return` 东西，所以一律 `-> None`。

**第 3 层（如果 `index` 那条不知道 assert 写哪）**
> 报错在 `[...]` 那个位置。把那一行拆成两行：先 `row = ...get(...)`，下一行 `assert row is not None`，再 `row["doc_count"]`。

**第 4 层（如果 `no-any-return` 拿不准选哪种）**
> 先用 `cast`，写一行注释说明为什么安全（比如"jose 的 encode 实际返回 str"）。跑测试确认没坏。

**第 5 层（如果改完 pytest 红了）**
> `git diff` 看自己改了哪些**非测试文件**——注解不该改逻辑，红了说明你顺手动了实现。

---

## §7 易错点表

| 坑 | 症状 | 正确做法 |
|---|---|---|
| 以为注解会拦住运行时 | `add("1","2")` 照样算出 `"12"` | 注解只给静态检查器看；边界校验用 pydantic |
| 裸 `list` / `dict` | `[type-arg]` 而且 `Any` 往下游传染 | 一律写全 `list[int]` / `dict[str, Any]` |
| `dict \| None` 直接下标 | `[index]`，运行时可能 `TypeError` | 先 `assert row is not None` 收窄 |
| `# type: ignore` 不带错误码 | 以后这个文件所有错误都被吞 | 写 `# type: ignore[错误码]` |
| 创可贴过期 | `[unused-ignore]` | strict 会替你发现，删掉 |
| 只跑 `mypy src` | 以为很干净，其实 tests 一个都没查 | 永远跑全量 `src tests scripts conftest.py` |
| 没有 `py.typed` | 一堆 `import-untyped`，看着像"缺库" | 包根目录放空文件 `py.typed` |
| 拿"错误数变多"当退步 | 20 → 58 就慌 | 门开了才会看见屋子有多乱 |
| 在 PowerShell 里抄 `grep`/`sort`/`uniq` | `无法将"grep"项识别为 cmdlet…` | 用 §8 的 PowerShell 版；`Select-String` 对应 `grep`，`Group-Object` 对应 `sort \| uniq -c` |
| 在 PowerShell 里给 native 命令加 `2>&1` | `$?` 变 `$false`、管道里混进 ErrorRecord | mypy 的错误本来就在 stdout，**不加** |

---

## §8 命令速查

> **每条命令都给两套写法**，输出**完全一样**。
> - **PowerShell**：你的 PyCharm 终端默认就是它。
> - **bash**：Git Bash / Linux / macOS / GitHub Actions（CI 跑在 Ubuntu 上）。
>
> 唯一实质差异是"怎么调用 venv 里的 Python"：Windows 的 venv 在 `.venv\Scripts\python.exe`，
> Linux 在 `.venv/bin/python`。下面 bash 版写的是 **Windows 上 Git Bash** 的路径（你在这个项目里最常用）；
> 真·Linux 上把 `Scripts/python.exe` 换成 `bin/python`，CI 里更省事的是 `uv run mypy ...`。

### 8.1 日常三条

**① 全量类型检查**（最常用）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py
```

**② 跑测试**（注解不该改变任何运行时行为）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m pytest -q
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m pytest -q
```

**③ 代码风格检查**

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m ruff check src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m ruff check src tests scripts conftest.py
```

### 8.2 统计类（看清"还剩哪几类"）

**① 按错误码统计**（日常体检，最常用）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py |
  Select-String '\[([a-z-]+)\]$' |
  ForEach-Object { $_.Matches[0].Groups[1].Value } |
  Group-Object | Sort-Object Count -Descending |
  Select-Object Count, Name
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep -oE "\[[a-z-]+\]$" | sort | uniq -c | sort -rn
```

**② 按文件统计**（找重灾区）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py |
  Select-String ': error: ' |
  ForEach-Object { ($_ -split ':')[0] } |
  Group-Object | Sort-Object Count -Descending |
  Select-Object Count, Name
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep "error:" | cut -d: -f1 | sort | uniq -c | sort -rn
```

**③ 只看某一类**（验收时确认只剩 arg-type）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy src tests scripts conftest.py | Select-String '\[arg-type\]'
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy src tests scripts conftest.py | grep "\[arg-type\]"
```

### 8.3 排查类

**① 忽略缓存、强制全量重算**（改过配置后用）

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy --no-incremental src tests scripts conftest.py
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy --no-incremental src tests scripts conftest.py
```

**② 看某个文件为什么被跳过**

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe -m mypy -v tests | Select-String -Pattern 'skip'
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/python.exe -m mypy -v tests | grep -i "skip"
```

### 8.4 两套写法的翻译表

记住这张表，以后自己能翻译：

| 要做的事 | PowerShell | bash |
|---|---|---|
| 按正则筛行 | `Select-String '\[arg-type\]'` | `grep "\[arg-type\]"` |
| 提取行内匹配的那一段 | `$_.Matches[0].Groups[1].Value` | `grep -oE` |
| 取每行第一个 `:` 前的部分 | `($_ -split ':')[0]` | `cut -d: -f1` |
| 分组计数 | `Group-Object` | `sort \| uniq -c` |
| 按计数倒序 | `Sort-Object Count -Descending` | `sort -rn` |
| 只看前 / 后几行 | `Select-Object -First 5` / `-Last 5` | `head -5` / `tail -5` |
| 建空文件 | `New-Item x -ItemType File -Force` | `touch x` |
| 调 venv 里的 Python | `& .\.venv\Scripts\python.exe` | `./.venv/Scripts/python.exe` |

### 8.5 为什么不写 `2>&1`

实测过：`mypy src` 的 stderr 是**空的**，所有错误都在 stdout。

- bash 里 `2>&1` 加不加都行；
- **PowerShell 里不要加**——它会先把 native 命令的 stderr 行包成 `ErrorRecord` 塞进管道，并把 `$?` 标成 `$false`（即使 mypy 正常退出）。后续 `Select-String` 拿到的不再是纯字符串，正则行为也会变。

### 8.6 如果你懒得记管道

`mypy` 自己会给你最后一行汇总（两种终端一样）：

```
Found 58 errors in 14 files (checked 46 source files)
```

**改完前后对比这个数字 + `git diff` 看改了哪些文件**，就够验收了。管道统计只是让你看清"还剩哪几类"，不是必须的。

---

## §9 面试问法

### Q1：Python 有类型注解，运行时会不会检查？

> **30 秒版**：不会。注解在函数定义时被存进 `__annotations__`（或者用 `from __future__ import annotations` 存成字符串），调用时完全不看。所以 `add("1","2")` 声明的是 `int,int`，运行时照样执行、返回 `"12"`。它的价值是给静态检查器（mypy）和 IDE 看，属于"编译期"约束，不是运行时守卫。真要运行时校验，得用 pydantic——比如我项目里 HTTP 的入参出参都用 pydantic 模型，内部函数之间用注解 + mypy。

**追问链：**
→ *"那注解到底还有什么用？"* 三个：① mypy 静态查错 ② IDE 补全和跳转 ③ 团队协作时的"可执行文档"（注释会过期，注解会被检查）。
→ *"`from __future__ import annotations` 干什么的？"* 把注解变成字符串延迟求值，解决前向引用（类里引用自己）和启动开销，`typing.get_type_hints()` 才能还原。
→ *"pydantic 和 mypy 冲突吗？"* 不冲突，层次不同：pydantic 管"边界进来的数据是垃圾吗"，mypy 管"我自己的代码有没有接错线"。

### Q2：`Protocol` 和继承（ABC）有什么区别？为什么依赖倒置要用 Protocol？

> **30 秒版**：继承是**名义类型**——你得显式声明 `class Fake(KBRepo)`，等于让 fake 依赖真实现，还白拿一堆真实方法。`Protocol` 是**结构化类型**——只要方法签名匹配就算，被实现方完全不知道协议存在。这正是依赖倒置想要的效果：高层模块定义"我需要什么形状"，底层模块自己长成那个形状，双方不互相 import。

**追问链：**
→ *"不继承，怎么保证 fake 和真的一样？"* 靠类型检查器比对：把 `repo: KBRepository = FakeKBRepo()` 写在测试里，签名差一个参数名都会红。
→ *"参数名算不算签名的一部分？"* mypy 算。`get(self, kb_id)` 和 `get(self, id)` 在 Protocol 下不兼容（关键字调用会炸）。
→ *"那 `runtime_checkable` 呢？"* 加装饰器后可以 `isinstance()` 检查，但只检查方法**存在**，不检查签名——比静态检查弱得多，别拿它当契约测试。

### Q3：`--strict` 打开了什么？为什么团队要用它？

> **30 秒版**：`--strict` 是一组开关的打包，核心三条：禁止无注解函数（`disallow_untyped_defs`）、禁止裸泛型（`disallow_any_generics`）、禁止返回 `Any`（`warn_return_any`）。为什么要用：宽松模式下 mypy 遇到没注解的东西就静默跳过，你会得到"虚假的绿色"；而 `Any` 会传染，一个没标注的函数能让下游几十行检查全部失效。strict 的原则是**"你没说，也算问题"**。

**追问链：**
→ *"全量开了会不会太多错误，团队推不动？"* 通常是**按目录渐进**：新代码 strict，老代码用 `[[tool.mypy.overrides]]` 单独放宽，再逐个目录收紧。
→ *"`Any` 和 `object` 有什么区别？"* `object` 是"任何东西"但**不能用**（调用前必须收窄）；`Any` 是"任何东西而且随便用"——所以 `Any` 才危险，它静默通过一切检查。
→ *"怎么让第三方无类型库不报错？"* `ignore_missing_imports = true` 按模块白名单，但代价是那个库的返回值全是 `Any`——这也是 `no-any-return` 的来源。

### Q4：为什么测试代码也要过类型检查？

> **30 秒版**：因为测试是**替身**。我项目里 `FakeKBRepo` 替掉了真的 `KBRepository`，如果两者签名有差异，测试全绿也没意义——它验证的是一个不存在的对象。类型检查器是唯一能自动比对"替身和真货契约是否一致"的工具。我这次跑 mypy，它直接报出 8 条 `arg-type`：fake 结构上匹配但没声明继承，正因为这个报错我才发现 `KBRepository` 该改成 `Protocol`。

**追问链：**
→ *"测试全绿但类型报错，是不是说明测试没用？"* 不，说明测试覆盖的是**行为**，类型检查覆盖的是**契约**。两者互补：类型查不出的逻辑错误（比如 `offset = page * size`）要靠测试，测试覆盖不到的签名漂移要靠类型。
→ *"那能不能靠类型检查代替测试？"* 不能。类型只能证明"接得对"，不能证明"算得对"——把 `(page-1)*size` 写成 `page*size` 类型完全正确。这正是 W4 变异测试要杀的东西。

---

## §10 闭卷自测（先写答案，再展开）

**1.** 下面这段代码，mypy `--strict` 会报几条？哪几条？

```python
def greet(name):
    return "hi " + name
```

<details><summary>答案</summary>

1 条：`[no-untyped-def]`。因为 `name` 没注解、返回值也没注解，strict 下整个函数**不检查函数体**。

补充：如果你把 `greet` 改成 `def greet(name: str) -> str`，它才会开始检查函数体里的 `return` 是否真的返回 `str`。
</details>

**2.** `def f(x: int) -> int: return x`，调用 `f("abc")` 会发生什么？为什么？

<details><summary>答案</summary>

**什么都不会发生**——正常执行，返回 `"abc"`。注解不参与运行时。

会报错的是 mypy：`Argument 1 to "f" has incompatible type "str"; expected "int"`。区别在于：mypy 在**你运行之前**报，Python 在**你写错时也不报**。
</details>

**3.** 为什么加了 `py.typed` 之后，`mypy tests` 的错误从 20 个变成 1 个？

<details><summary>答案</summary>

因为那 19 个 `import-untyped` 不是"类型错误"，是"mypy 拒绝分析"。`kb_service` 是 editable 安装的包，没有 `py.typed` 时 mypy 把它当"无类型的第三方库"，直接跳过。

`py.typed` 是 PEP 561 的标记：一个空文件，声明"我这个包自带类型信息"。加上之后 mypy 才真正开始看你的代码——**代价是错误数会从 1 涨到 58**。
</details>

**4.** `KBRepository` 是普通类，`FakeKBRepo` 六个方法签名完全一致，为什么 mypy 还报 `arg-type`？

<details><summary>答案</summary>

因为 Python 默认**名义类型**：`FakeKBRepo` 没有声明继承 `KBRepository`，在 mypy 眼里就不是它的子类型。方法长得一样不够。

修法是把 `KBRepository` 改成 `Protocol`（结构化类型），或者让 fake 显式继承它。前者才是依赖倒置——后者会让 fake 白拿真实实现，测试就不再是"替身"了。
</details>

**5.** 下面两行，哪一行会被 mypy 拒绝？为什么？

```python
row = repo.get(kb_id)          # 返回 dict[str, Any] | None
print(row["doc_count"])
```

<details><summary>答案</summary>

|  |  |
| --- | --- |
第二行，报 `[index]`：`Value of type "dict[str, Any] | None" is not indexable`。

`None` 不能下标。修法是先收窄：

```python
row = repo.get(kb_id)
assert row is not None
print(row["doc_count"])
```

注意：运行时可能一直没炸（因为数据确实存在），**但"你知道"不等于"类型系统知道"**，而这个 assert 在数据真缺失时给出的报错比 `TypeError` 清楚得多。
</details>

**6.** `no-any-return` 为什么会出现？`cast(str, x)` 和 `str(x)` 你选哪个？

<details><summary>答案</summary>

出现原因：第三方库（这里是 `python-jose`）没有类型标注，它的函数返回值被推断为 `Any`；你的函数声明返回 `str`，strict 下报"返回 Any"。

- `cast(str, x)`：零运行时开销，本质是对 mypy 说"相信我"——说错了它不管
- `str(x)`：真的做转换，有极小开销，但保证类型正确

我选 `cast` + 一行注释说明依据（例如"jose 的 encode 实际返回 str"），因为它不改变运行时行为；如果这个库的返回类型真的不确定（有时 str 有时 bytes），就选 `str()`。
</details>

**7.** 为什么"错误数从 20 涨到 58"可能是在进步？

<details><summary>答案</summary>

因为 20 个里有 19 个是"mypy 根本没看我的代码"（`Skipping analyzing`），只有 1 个是配置冲突。加了 `py.typed` + 包基址配置后，46 个文件被真正检查，58 个才是**真实的类型债**。

**指标要看"被检查的代码量"，不是"错误数"。** 从"没检查"到"查出 58 个"，是从虚假的安静走向真实的清单。
</details>

---

## 今日交付清单

- [ ] `src/kb_service/py.typed` 已建（空文件）
- [ ] `pyproject.toml` 的 `[tool.mypy]` 已加 `mypy_path` / `explicit_package_bases`
- [ ] 全量 mypy：只剩 `8 [arg-type]`
- [ ] `pytest -q` 仍然 `57 passed`
- [ ] `ruff check` 仍然通过
- [ ] 能口述：注解为什么不拦运行时、`Any` 为什么危险、`index` 那条为什么必须 `assert`

> 做完之后来找我验收。**今天的第四档会拿这 8 个 `arg-type` 出题**——因为它正好考"你是真的理解名义类型/结构化类型的区别，还是只是把错误改没了"。
