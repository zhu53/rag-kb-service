# D2 总结 · monkeypatch 与配置测试（面试参考版）

> 详细教材见 `D2-monkeypatch与配置测试-教材.md`（零基础版，含逐层机制讲解）。本篇是压缩的面试手册：速答 → 追问链 → 易错 → 白板靶。

## 知识点 1 · monkeypatch

**一句话定义**：pytest 内置 fixture，临时改变环境（环境变量/对象属性/dict 项/工作目录），测试结束**自动还原**。

**为什么存在**：环境变量是进程级全局状态，手动 `os.environ[...] = ...` 会泄漏到后续测试——尤其 assert 失败时清理代码执行不到。手动 try/finally 会忘、会漏；monkeypatch 把还原挂进 fixture teardown，**机制保证执行**，与测试成败无关。

**怎么用**：

```python
def test_x(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")            # 设环境变量
    monkeypatch.delenv("LOG_LEVEL", raising=False)      # 删（容忍不存在）
    monkeypatch.setattr(模块, "函数名", fake)            # 换属性/函数
    monkeypatch.setitem(some_dict, "key", value)        # 改 dict 项
    monkeypatch.chdir(tmp_path)                         # 切工作目录
```

**底层机制**：function 级 fixture；每次 set 先记账原值，teardown 倒序逐条恢复（影分身账本）。teardown 由 pytest fixture 机制保证，即使测试中途炸也执行——与 `try/finally`、`ContextVar.reset(token)`、conftest yield 同构（洋葱模型）。

**面试问法**：*"monkeypatch 原理？为什么断言失败也能还原？"*
30 秒答案：它是 function 级 fixture，set 时先记录原值，teardown 阶段照账本恢复；teardown 由 pytest 保证执行，不依赖测试成功与否。

**追问链**：
1. *和直接 `os.environ` 赋值差别？* → 泄漏 vs 自动还原；失败路径 vs 全路径覆盖。
2. *mock 完被调用的还是原函数吗？* → setattr 换的是名字指向，原函数不再执行——**测 stub = 测假货**（#07 漏坑教训）。判据：patch 后被调链路里必须还包含被测逻辑。
3. *pytest 为什么在测试里能随便用 fixture 不 import？* → conftest.py 自动加载当插件 + fixture 按参数名注入。

## 知识点 2 · tmp_path

**一句话定义**：function 级内置 fixture，每个测试（每组参数）独享一个 `pathlib.Path` 临时目录，自动清理（保留最近 3 次运行）。

**为什么存在**：测文件逻辑不能碰真实文件（真实 .env 有密钥、值会被改）；共享临时目录会撞名。测试应 self-contained——**全部输入自带，测完即毁**。

**怎么用**：

```python
def test_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=xxx\nLOG_LEVEL=WARNING\n", encoding="utf-8")
    s = Settings(_env_file=env)
```

**对比**：`tmp_path_factory` 是 session 级工厂，给全测试共享的贵资源（如共享假数据库目录）。今天用不到，认识即可。

**追问链**：*Windows 编码坑？* → 默认 GBK，写文件永远显式 `encoding="utf-8"`（W1 老规矩）。

## 知识点 3 · 测配置三级优先链（实战综合）

**链**：环境变量 > .env 文件 > 代码默认值。字段名无前缀 → 环境变量 = 字段名全大写。

**两个关键武器**：

1. `Settings(_env_file=None)`——关掉 .env 层，把三级链人为砍成两级，测试才能对准靶心。**代价**：必填字段（`secret_key` 无默认值）失去来源 → `Field required`。**修法是测试喂饱必填项（setenv），不是给字段加默认值**——没有默认值是安全 fail-fast：宁可启动崩，不许弱密钥悄悄签 JWT。
2. autouse 清缓存 fixture——`@lru_cache` 的缓存生命周期 = 进程生命周期，是**天然跨测试共享状态**。进出各 `get_settings.cache_clear()` 一次。

```python
@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

**为什么 lru_cache 是测试杀手**：无参函数 → 缓存键恒定 → 第一次后所有调用直接返回旧引用，**函数体不再执行**，环境变量变没变根本不看。`s1 is s2` 判"同一对象"是 `is` 的正当用途（判身份非比值）。

**追问链（高频区，背熟）**：
1. *"测试互相污染什么症状？怎么排查？"* → 单跑绿全跑红、顺序敏感。排查：确认非顺序问题 → `--setup-show` 看 fixture 生命周期 → 查全局状态（缓存/单例/模块级变量/真实 IO）→ autouse 清场兜底。
2. *"为什么不用真实 .env 测？"* → 环境依赖（不同机器结果不同）+ 密钥进测试。假 .env 由 tmp_path 造，self-contained。
3. *"lru_cache 在测试里还有什么坑？"* → mock `get_settings` 前想想别处是否还握着旧引用；`cache_clear` 是唯一官方清理口。

## 知识点 4 · 测试的杀伤力（#07 核心收获）

**覆盖率 ≠ 杀伤力**：覆盖率说明"代码被执行过"，不说明"行为被验证过"。四种摆设测试（全绿但抓不住任何 bug）：

| 类型 | 形状 | 为什么废 |
|---|---|---|
| 永真断言 | `assert r is not None` / `len(r) >= 0` | 任何实现都成立 |
| 镜像断言 | `expected = f(x); assert f(x) == expected` | 期望值是被测函数自己算的 |
| mock 掉被测逻辑 | `setattr` 换掉函数后断言 stub 的返回 | 测的是假货，真函数对错不知 |
| try/except 吞断言 | `except AssertionError: pass` | 失败信号永远到不了 pytest（零症状） |

**面试问法**：*"怎么保证测试真的能抓住 bug？"*
30 秒答案：看断言有没有区分度——期望值不能来自被测函数自己，mock 不能换掉被测逻辑，失败信号不能被吞。终极检验是变异测试思维：故意改坏一行代码，看有没有测试变红；全绿 = 测试没杀伤力。

**追问链**：*"什么该 mock 什么不该？"* → 明天 D3 主菜：依赖边界（外部 IO/时间/随机）该 mock，被测逻辑本身绝不 mock；Protocol 契约让 fake repo 成为正规解法。

## 30 秒答案集

- **monkeypatch 原理**：function 级 fixture，set 记账 → teardown 逐条恢复；失败也还原。
- **tmp_path**：每测试独立临时目录，自动清，self-contained 的载体。
- **测配置**：setenv/delenv 测环境层、tmp_path 假 .env 测文件层、`_env_file=None` 隔离、必填项喂饱、autouse 清 lru_cache。
- **lru_cache 与测试**：进程级共享状态，进出 cache_clear；无参函数缓存键恒定，setenv 后拿旧引用是缓存不是 bug。
- **测试杀伤力**：断言要有区分度；变异测试思维验杀伤力。

## 白板手写靶

1. **monkeypatch 配置测试**（必默）：

```python
def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-0123456789")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"
```

2. **清缓存 autouse**（必默）：yield 前后各 `get_settings.cache_clear()`。

3. **四种摆设测试的形状**（能认出，不必默）。

## 今日踩坑实录

| 坑 | 现象 | 根源 |
|---|---|---|
| `_env_file=None` 后 `Field required` | ValidationError: secret_key | 教材漏讲必填字段（AI 的锅，已修正教材）；必填项必须测试内喂饱 |
| `match="error"` 太弱 | 任何 ValidationError 都匹配 | 断言无区分度 = 没测到位 |
| ⑥ 测了 `Settings()` 没测 `get_settings()` | 缓存测试反而证明"每次读新环境" | lru_cache 挂在函数上不在类上；测缓存必须调带缓存的那个 |
| #07 漏"stub 换掉被测函数" | monkeypatch 用了一整天却没识别 setattr 换名 | "会用"≠"知道它换了什么"；D3 mock 边界预热 |

## 闭卷自测（6 题，折叠答案见教材 §10）

环境变量还原时机 / `_env_file=None` 关了什么 / cache_clear 为何进出各一次 / tmp_path vs tmp_path_factory / delenv 何时 KeyError / 必填字段缺失的正确修法方向。
