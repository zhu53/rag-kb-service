# D2 教材 · monkeypatch 与配置测试（零基础版）

> 本篇默认你**没写过任何"碰真实世界"的测试**。环境变量、文件系统这些东西本身不难，难的是"测试怎么不污染它们、也不被它们污染"。读完你会亲手测掉 `core/config.py` 的三级优先链——你上周在 kbcli 里亲手验证过的那条链，这次要让它被测试钉死。

---

## §0 痛点：测试要碰"真实世界"，而真实世界是全局的

D1 你写的测试都是"纯内存"的：fixture 建个 app、发个请求、断言返回。整个过程不碰任何**进程外的状态**。

但 D2 你要测配置。配置测试必须回答三个问题，而每个问题的朴素做法都是灾难：

**问题①：环境变量怎么设？**

环境变量是**进程级全局变量**——`os.environ` 这一个 dict，整个进程共享。朴素做法：

```python
import os

def test_log_level():
    os.environ["LOG_LEVEL"] = "DEBUG"
    assert Settings().log_level == "DEBUG"
```

能跑，但**测试结束后 `LOG_LEVEL=DEBUG` 留在进程里了**。同进程后面跑的任何测试（哪怕别的文件里的）都会看见这个 DEBUG。这就是**测试污染**。

你**亲身踩过这个坑**——10 月 27 号，kbcli 那天，你的 PowerShell 会话里残留着 `$env:KBCLI_DATA_FILE = "E:/tmp/other.json"`，导致"测默认值"的那条命令打出来的是环境变量的值。当时的解法是**手动清场**：`Remove-Item Env:KBCLI_DATA_FILE`。

手动清场的问题是：**人会忘**。十个测试里有一个人忘了清，就是一次"时好时坏"的 flaky 测试——世界上最难查的测试 bug。而且如果测试**中途 assert 失败**，清场代码根本执行不到：

```python
def test_log_level():
    os.environ["LOG_LEVEL"] = "DEBUG"
    assert Settings().log_level == "DEBUG"   # ← 如果这行失败…
    os.environ.pop("LOG_LEVEL")              # ← …这行永远不执行，环境变量泄漏
```

**问题②：临时文件怎么造？**

测配置还要测".env 文件"这一层。你总不能往真实项目的 `.env` 里乱写吧——那是含真实 SECRET_KEY 的文件。往系统临时目录（`C:\Users\...\Temp`）写？谁清理？怎么保证两个测试不撞名？

**问题③：`get_settings()` 有 `@lru_cache`，测它怎么办？**

D3（W3）你学过：`lru_cache` 让配置在进程内**只读一次**。这对生产是好事，对测试是杀手——你刚 `setenv` 完去调 `get_settings()`，它根本不看新环境变量，直接把**缓存的旧对象**还给你。不处理这个，你的测试会"神秘失效"。

pytest 对这三个问题各给了一件武器：**monkeypatch**（问题①）、**tmp_path**（问题②）、**`cache_clear()` + autouse 清场 fixture**（问题③）。今天三件全吃透。

---

## §1 最小可跑示例（5 分钟）

在 `kb-service/tests/` 下新建 `test_mp_demo.py`（实验品，今天用完就删）：

```python
import os


def test_setenv(monkeypatch):
    """setenv 设环境变量，断言能读到。"""
    monkeypatch.setenv("DEMO_KEY", "hello")
    assert os.environ["DEMO_KEY"] == "hello"


def test_leak_check():
    """证明上一个测试的环境变量没有泄漏到这个测试。"""
    assert os.environ.get("DEMO_KEY") is None
```

跑：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_mp_demo.py -v
```

**跑之前先猜**：两个测试，过几个？

答案：**两个全过**。关键在第二个——`DEMO_KEY` 在 `test_leak_check` 里是 `None`。如果是 30 秒前那个 `os.environ[...] = ...` 的写法，这里就会读到 `"hello"`，证明泄漏。而 `monkeypatch` 在 `test_setenv` 的 teardown 阶段**自动把环境变量恢复原样**，你一行清理代码都没写。

注意一个细节：`test_setenv` 里我们没有显式请求"清理"，**还原是 monkeypatch fixture 自带的**——它的实现里内置了 teardown（D1 学的 yield 模式，pytest 把它封装好了）。

---

## §2 monkeypatch 全家桶

`monkeypatch` 是 pytest 内置 fixture，功能是"**临时改变环境，测试结束自动恢复**"。它有一套方法，每个对应一类"临时改变"：

| 方法 | 干什么 | 恢复什么 |
|---|---|---|
| `monkeypatch.setenv(name, value)` | 设环境变量 | 删掉它或恢复原值 |
| `monkeypatch.delenv(name, raising=False)` | 删环境变量（默认不存在会报错，`raising=False` 容忍不存在） | 恢复原值 |
| `monkeypatch.setattr(对象, "属性", 新值)` | 改对象的属性/函数 | 恢复原属性 |
| `monkeypatch.setitem(dict, key, value)` | 改某个 dict 的某项 | 恢复原项 |
| `monkeypatch.chdir(path)` | 切换当前工作目录 | 恢复原目录 |
| `monkeypatch.syspath_prepend(path)` | 往 `sys.path` 头部插路径 | 移除 |

**两条心法：**

**① monkeypatch 是"影分身账本"**。每次你调用 set/setenv，它先在账本上记下"原来是什么"，再动手改。测试结束（无论过没过、哪怕中途炸了），teardown 阶段照着账本**逐条恢复**。这就是为什么"中途 assert 失败"也不会泄漏——teardown 是 fixture 机制保证的，不是你代码顺序保证的。

**② 只 patch"你测试需要的最小范围"**。`setenv("LOG_LEVEL", "DEBUG")` 只影响 LOG_LEVEL 一个变量，测试的其他环境保持真实。宁可多设几个具体变量，不要图省事把整个环境换掉——那会让测试脱离现实。

一个真实用例对比感受 `setattr`（D5 测 JWT 过期时会大量用到）：

```python
def test_something(monkeypatch):
    monkeypatch.setattr("kb_service.core.config.get_settings", fake_settings)
    # 之后 import 它的模块拿到的是 fake……（细节 D5 讲，今天认识方法即可）
```

---

## §3 tmp_path：每个测试的专属临时目录

`tmp_path` 也是 pytest 内置 fixture，类型是 `pathlib.Path`，指向一个**这个测试专属的临时目录**：

```python
def test_write_env_file(tmp_path):
    assert tmp_path.exists()          # 目录已经建好了
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")

    from kb_service.core.config import Settings
    s = Settings(_env_file=env_file)  # ← 关键：显式指定 .env 的位置
    assert s.log_level == "WARNING"
```

三个特性记住：

1. **每个测试（包括参数化的每组参数）拿到的目录都不一样**——天然隔离，不存在"两个测试写同一个文件"的冲突
2. **自动清理**：pytest 只保留最近 3 次测试运行的临时目录（方便你调试时翻看），更早的自动删。你不用管清理
3. **可以造嵌套结构**：`tmp_path / "sub" / "deep.txt"`，中间目录 pytest 会自动创建（`write_text` 前用 `mkdir(parents=True)` 更稳）

**别和 `tmp_path_factory` 搞混**：`tmp_path` 是 function 级的（每个测试一个）；`tmp_path_factory` 是 **session 级**的工厂（整个测试进程共享一批目录），给"全测试共用的贵资源"用——比如建一个所有测试共享的假数据库目录。今天用不到它，认识名字就行。

---

## §4 实战核心：测 config.py 的三级优先链

现在看靶子。`kb-service/src/kb_service/core/config.py` 的规则：

```
环境变量  >  .env 文件  >  代码里的默认值
```

具体到代码：`Settings` 有 `model_config = SettingsConfigDict(env_file=".env", ...)`——**默认从当前工作目录找 `.env`**。字段没有 env_prefix，所以环境变量名就是**字段名全大写**（`log_level` → `LOG_LEVEL`）。

### 4.1 两个关键武器（不懂这两个，测试必错）

**武器①：`Settings(_env_file=None)` 关掉 .env**

kb-service 目录下**真有一个 `.env`**（里面有 LOG_LEVEL、SECRET_KEY）。你在测试里裸写 `Settings()`，它会从当前工作目录把真实 `.env` 读进来——你的"默认值测试"测的其实是 .env 的值。

解法：pydantic-settings 支持运行时覆盖配置来源：

```python
s = Settings(_env_file=None)   # 明确说：这次不许读任何 .env
```

这样三级优先链就被你**人为砍掉中间一层**，只剩"环境变量 > 默认值"，测试才能对准靶心。同理，想单独测 .env 这一层，就 `Settings(_env_file=tmp_path / ".env")` 指向**你造的假 .env**（§3 学的）。

**⚠️ 关掉 .env 之后必踩的一个坑：必填字段没了来源。**

`config.py` 里 `secret_key: str = Field(min_length=16)` **没有默认值**——它是必填项，值只能来自环境变量 `SECRET_KEY` 或 `.env`。你写 `_env_file=None` 等于切断 .env 这条来源，环境里又没有 `SECRET_KEY`，结果：

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
secret_key
  Field required [type=missing, input_value={}, input_type=dict]
```

这不是 bug，**是设计在正常工作**：密钥没有默认值是安全上的 fail-fast——如果服务能在没有密钥的情况下悄悄启动，它就会用某个弱默认密钥签 JWT，是生产事故级漏洞。宁可启动即崩，也不许默默降级。

所以**修法不是给 secret_key 加默认值，而是测试把必需字段喂饱**。这就是"测试必须自包含（self-contained）"的落地：任何必填字段都在测试内部备齐，不许指望外部环境恰好提供。

```python
MINIMAL_SECRET = "test-secret-key-0123456789"   # ≥16 位，满足 min_length
monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)
```

一条可复用的检查流程：**① 这个类哪些字段没默认值？② 必需的先喂饱；③ 再断言其他字段的默认值。**

**武器②：`get_settings.cache_clear()` 清缓存**

`get_settings()` 挂着 `@lru_cache`——第一次调用后，结果被缓存在函数对象上，**进程内所有后续调用都拿同一个对象**，不再读环境变量。

测试它的正确姿势：

```python
from kb_service.core.config import get_settings

get_settings.cache_clear()      # 先清缓存
try:
    # ... 设环境变量、调用 get_settings()、断言 ...
finally:
    get_settings.cache_clear()  # 测完再清，把"干净状态"还给别的测试
```

为什么测完还要清一次？因为你的测试可能已经把**某个环境变量状态**下的配置对象留在了缓存里。下一个测试（比如 health 接口的测试）调 `get_settings()` 会拿到它——**又一次跨测试污染**。

更工程化的写法是把它做成 **autouse fixture**（只在本文件生效）：

```python
import pytest
from kb_service.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """进测试前清缓存，出测试也清——保证缓存状态不跨测试泄漏。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

回想 D1 的规矩：**autouse 只用于清场，不用于提供数据**——这就是标准清场 fixture。

### 4.2 测试用例表（照此写，共 6 个）

新建 `kb-service/tests/test_config.py`：

| # | 测试名 | 验证什么 | 手段 |
|---|---|---|---|
| 1 | `test_defaults` | 剩余字段取默认值（**先喂饱必填的 SECRET_KEY**） | `delenv` 清 LOG_LEVEL + `setenv` SECRET_KEY + `_env_file=None` |
| 2 | `test_env_var_overrides_default` | 环境变量 > 默认值 | `setenv` SECRET_KEY + `setenv("LOG_LEVEL", "DEBUG")` |
| 3 | `test_env_file_provides_value` | .env 能提供值 | tmp_path 写假 .env（**必须含 SECRET_KEY 行**）+ `_env_file=` 指向它 |
| 4 | `test_env_var_beats_env_file` | **环境变量 > .env**（优先链关键位） | setenv 和假 .env 都给 LOG_LEVEL |
| 5 | `test_secret_key_too_short_raises` | secret_key 少于 16 位必须报错 | 假 .env 提供其他项 + `setenv("SECRET_KEY", "short")` + `pytest.raises` |
| 6 | `test_get_settings_cached` | `get_settings()` 有缓存、`cache_clear()` 生效 | 清缓存 → setenv → 调两次对比 |

**骨架（①②给你打样，③–⑥自己写）：**

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from kb_service.core.config import Settings, get_settings

MINIMAL_SECRET = "test-secret-key-0123456789"   # 必填字段的最小合法值（≥16 位）


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults(monkeypatch):
    """喂饱必需字段后，其余全取代码默认值。"""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)   # 必填项必须先喂饱
    s = Settings(_env_file=None)          # 关掉真实 .env
    assert s.log_level == "INFO"          # config.py 里的默认值
    assert s.env == "dev"


def test_env_var_overrides_default(monkeypatch):
    """环境变量 > 默认值。"""
    monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)   # 同样要喂
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"
```

**③ 的提示**：`tmp_path / ".env"` 的内容格式就是 `KEY=VALUE` 每行一条，注意 `encoding="utf-8"`。**这个假 .env 里必须同时写 SECRET_KEY 和 LOG_LEVEL 两行**——少写 SECRET_KEY 就会 `Field required`（因为 `_env_file` 一指过去，真实 .env 就不读了）。

**④ 的提示**：假 .env 里给 `LOG_LEVEL=WARNING`，再 `setenv("LOG_LEVEL", "ERROR")`，断言拿到 `"ERROR"`——环境变量赢。这组的对比价值在：**同一份输入，只改来源，看谁说话算数**。

**⑤ 的提示**：W3 你在 `test_split_text.py` 里写过 `pytest.raises(ValueError, match="...")`——同款。这个用例里 SECRET_KEY **要设、且要设成短的**，否则报的会是“Field required”而不是“太短”，两种失败原因测的完全是两件事。真实报错文本（我已实测）：

```
ValidationError: 1 validation error for Settings
secret_key
  String should have at least 16 characters [type=string_too_short, input_value='short', input_type=str]
```

所以 `match="at least 16 characters"`。

**⑥ 的提示**：流程是 `cache_clear()` → `setenv` → `第一次 get_settings()` 记下 `log_level` → **再 setenv 一个不同的值** → `第二次 get_settings()` → 断言两次相同（证明缓存挡住了新值）→ `cache_clear()` → 第三次调用 → 断言这次是新值。用 `s1 is s2` 判断“同一个对象”——**这是 `is` 的正当用途**（判身份，不是比值）。

写完跑：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_config.py -v
```

**自查红线**（D1 的纪律延续）：

```powershell
# 全量回归必须仍然绿
./.venv/Scripts/python.exe -m pytest -q

# 偷偷验证"自动还原"真的在工作：跑完你的测试后单独跑 health，正常就说明没泄漏
./.venv/Scripts/python.exe -m pytest tests/test_health.py tests/test_config.py -q
```

---

## §5 机制：monkeypatch 凭什么"测完自动还原"

D1 你看过 fixture 的五步生命周期。monkeypatch 就是一个 **function 级 fixture**，它的 teardown 干的事：照账本逐条恢复。

```
SETUP:    建一个空账本（ MonkeyPatch 对象），交给你
测试中:   每次 setenv/delenv/setattr → 先记账"原值是什么" → 再改
TEARDOWN: 倒序遍历账本 → 逐条恢复原值 → 账本作废
```

两个推论，都能从机制推出来：

1. **测试中途炸也会还原**——teardown 不看你测试的成败，fixture 机制保证执行（和 `try/finally`、D5 的 `reset(token)`、conftest 的 yield teardown 是同一个洋葱模型：**谁申请的资源，谁负责收拾，且收拾必然发生**）。
2. **跨测试必然干净**——monkeypatch 是 function 级，每个测试一份新账本。A 测试的改动在 A 的 teardown 已恢复，B 测试从零开始。这就是 §1 里 `test_leak_check` 能过的原因。

**`@lru_cache` 为什么是"测试杀手"**（机制级理解，面试常问）：

`lru_cache` 把"函数参数 → 返回值"存在**函数对象的属性**里。`get_settings()` 无参数，所以第一次调用后，进程里任何地方再调它都直接命中缓存。这意味着：

- **缓存的生命周期 = 进程生命周期**，比任何测试都长 → 它是天然的跨测试共享状态
- 缓存里存的是**对象引用**：就算你 `setenv` 了新值，测试拿到的还是旧对象，看起来"代码坏了"，其实是"配置没重新读"
- 唯一的官方清理口就是 `cache_clear()`——没有它，任何"改环境变量再验证"的测试都是**测了个寂寞**（永远拿缓存）

---

## §6 易错点表（今天会踩的，提前打疫苗）

| # | 错误写法/想法 | 后果 | 正确姿势 |
|---|---|---|---|
| 1 | 测试里直接 `os.environ["X"] = ...` | 泄漏到后续所有测试，flaky | `monkeypatch.setenv` |
| 2 | 只测"设了能读到"，没测"删掉会怎样" | 半个真相 | `delenv` 也要测（本次 §4.2 的 ① 就覆盖了） |
| 3 | 裸写 `Settings()` 测默认值 | 真实 `.env` 被读进来，测的是 .env 不是默认值 | `Settings(_env_file=None)` |
| 4 | `setenv` 后直接调 `get_settings()` | 拿到缓存旧对象，断言"神秘失败" | 先 `cache_clear()`，autouse fixture 全程兜底 |
| 5 | 清缓存只清"进"不清"出" | 你污染的缓存留给别的测试 | autouse 的 yield 前后各 `cache_clear()` |
| 6 | `delenv("X")` 不加 `raising=False` | 本机恰好没设这个变量时 `KeyError` | 统一 `raising=False` |
| 7 | tmp_path 里写文件忘 `encoding="utf-8"` | Windows 默认 GBK，中文内容炸或乱码 | 永远显式 utf-8（W1 老规矩） |
| 8 | 把 `_env_file=None` 写成 `_env_file=""` | pydantic 报路径错误 | 用 `None` |
| 9 | 断言错误信息用整段 `match`（含正则特殊字符） | 正则误匹配或不匹配 | match 只放关键短语，特殊字符转义 |
| 10 | `_env_file=None` 却忘了喂 `SECRET_KEY` | `ValidationError: secret_key Field required`，以为是 pydantic 坏了 | 必填字段在测试里先 `setenv` 喂饱（不是给它加默认值） |
| 11 | 假 .env 里只写要测的那一项 | 想测 LOG_LEVEL，结果被 SECRET_KEY 缺失拦住 | 假 .env 也要满足“最小合法输入”，必需项全写上 |

---

## §7 命令速查

```powershell
# 只跑配置测试，看每条用例名
./.venv/Scripts/python.exe -m pytest tests/test_config.py -v

# 跑配置 + 全量回归
./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_health.py -q
./.venv/Scripts/python.exe -m pytest -q

# 看某个 fixture 的 setup/teardown 过程（D1 学的）
./.venv/Scripts/python.exe -m pytest tests/test_config.py --setup-show -q

# 看 monkeypatch 的还原证据：跑完 config 再跑 health，顺序对调各跑一次
./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_health.py -q
./.venv/Scripts/python.exe -m pytest tests/test_health.py tests/test_config.py -q
```

---

## §8 动手实验（跑之前先猜）

**实验 A**：把 §1 的 `test_mp_demo.py` 跑了，猜对了吗？然后把 `test_setenv` 里的 `monkeypatch.setenv` 换成 `os.environ["DEMO_KEY"] = "hello"`，再猜 `test_leak_check` 会怎样？（改完必须改回来或删文件——这个版本是故意泄漏的，不能留）

**实验 B**：在 `test_config.py` 里临时加一个：

```python
def test_cache_visible(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s1 = get_settings()
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    s2 = get_settings()
    print(s1 is s2, s1.log_level, s2.log_level)
```

猜输出是什么（`-s` 跑）。想明白"为什么是这个"再删掉。

---

## §9 面试问法

**Q：你们项目的配置怎么测试的？**

> 30 秒版：配置是三级优先链（环境变量 > .env > 默认值），我们用 pytest 的 monkeypatch 测每一级——setenv/delenv 控制环境变量层，tmp_path 造假 .env 测文件层，`Settings(_env_file=None)` 隔离真实 .env。因为 `get_settings()` 挂了 `lru_cache`，还有个 autouse fixture 在每个测试前后调 `cache_clear()`，保证缓存状态不跨测试泄漏。所有环境修改都走 monkeypatch，测试结束自动还原。

**追问链（面试官往下挖什么）：**

1. **"monkeypatch 原理是什么？为什么断言失败也能还原？"** → 它是 function 级 fixture，set 时先记账原值，teardown 阶段逐条恢复；teardown 由 fixture 机制保证，与测试成败无关。
2. **"lru_cache 在测试里还有什么坑？"** → 缓存生命周期 = 进程生命周期，是天然跨测试共享状态；mock 掉 `get_settings` 之前要想想别处是不是还握着旧引用。清理只有 `cache_clear()` 一条路。
3. **"为什么不用真 .env 测？"** → 两个原因：真实 .env 含密钥且值会被人改，测试依赖它是**环境依赖**（不同机器结果不同）；测试应该自带全部输入（self-contained），假 .env 由 tmp_path 造，测完即毁。
4. **"测试互相污染有什么症状？怎么排查？"** → 单跑绿、全跑红（或反过来），顺序敏感。排查：`-p no:randomly` 先确认不是顺序问题 → 用 `--setup-show` 看 fixture 生命周期 → 查全局状态（缓存/单例/模块级变量/真实 IO）。终极解法：autouse 清场 fixture 把全局状态进出各清一次。

---

## §10 闭卷自测（做完再展开答案）

1. monkeypatch 的还原发生在生命周期的哪一步？为什么 assert 失败也挡不住它？
2. `Settings(_env_file=None)` 关掉的是什么？不关会发生什么？
3. 为什么测 `get_settings()` 前后都要 `cache_clear()`？只清"进"不清"出"的后果是什么？
4. `tmp_path` 和 `tmp_path_factory` 的作用域区别？
5. `delenv("X")` 什么时候会抛 KeyError？怎么避免？
6. `Settings(_env_file=None)` 之后为什么会 `secret_key Field required`？正确的处理方向是"给字段加默认值"还是别的？为什么？

<details>
<summary>答案</summary>

1. TEARDOWN 阶段。monkeypatch 是 function 级 fixture，set 时记账原值，teardown 照账本恢复；teardown 由 pytest 的 fixture 机制保证执行，不依赖测试体是否成功（与 try/finally 同构）。
2. 关掉 `.env` 文件读取这一层。不关的话，裸 `Settings()` 会从当前工作目录读真实 `.env`（里面有 LOG_LEVEL、SECRET_KEY），你的"默认值测试"实际测到的是 .env 的值——测试结果依赖机器上恰好有什么文件。
3. 进测试前清：防止拿到别的测试（或上次运行）留下的缓存对象；出测试再清：防止**自己**污染的缓存对象被后续测试拿到。只清"进"不清"出"= 清掉了别人，留下了自己——跨测试污染方向反过来而已。
4. `tmp_path` 是 function 级，每个测试（每组参数）一个独立目录；`tmp_path_factory` 是 session 级工厂，供全测试进程共享的昂贵资源（如共享假数据库目录）。
5. 变量不存在且默认 `raising=True` 时。统一写 `delenv("X", raising=False)`。
6. 因为 `secret_key: str = Field(min_length=16)` 没有默认值，值只能来自环境变量或 `.env`；`_env_file=None` 切断了后者，环境里又没有前者 → 必填字段缺失。**正确方向是测试里把必需字段喂饱**（`setenv("SECRET_KEY", ...)`），不是给字段加默认值——没有默认值是安全上的 fail-fast：宁可启动即崩，也不许用弱默认密钥悄悄签 JWT。

</details>
