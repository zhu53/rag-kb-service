# W3-D6 任务书：S1 标准骨架 + 手写 LRU 缓存

> 今天造一个**能装、能跑、能分层**的真实项目：`kbcli`。
> 交付判据不是"代码看起来对"，而是**`uv run kbcli --help` 能出四子命令**。
> 另一半是 W2 的欠账：手写 LRU（不许 `functools.lru_cache`）。

## 0. 最终形态

```
progress/week3/kbcli/
├── pyproject.toml            # [project] / [project.scripts] / [dependency-groups] / [tool.*]
├── .python-version           # 3.11
├── src/
│   └── kbcli/
│       ├── __init__.py       # __version__ = "0.1.0"
│       ├── __main__.py       # python -m kbcli 的入口（D1 学的机制）
│       ├── cli.py            # argparse 子命令 + main() → int 退出码
│       ├── config.py         # Settings：数据文件路径、日志级别（环境变量覆盖）
│       ├── logging_setup.py  # D5 那套 ContextVar + Filter 的复用版
│       ├── errors.py         # 异常族（D4 抄过来）
│       ├── caching.py        # ⭐ 手写 LRU（今天的主角）
│       ├── services.py       # KBService：repo + cache，写操作后失效缓存
│       └── repositories/
│           ├── __init__.py
│           └── json_repo.py  # D4 的 JSON repo（照搬，改 import）
└── verify.py                 # 验收器（脚手架，可最后写）
```

## 1. 概念精讲 A：为什么用 src 布局

```
❌ 平铺布局                     ✅ src 布局
kbcli/                         kbcli/
├── pyproject.toml             ├── pyproject.toml
└── kbcli/  ← 源码就在当前目录   └── src/kbcli/  ← 源码在 src 下
```

平铺布局的坑：你在项目根目录敲 `python`，`import kbcli` 找的是**当前目录那个文件夹**（因为 `''` 在 sys.path 里），而不是"安装好的包"。于是：

- 你测的是源码，用户装的是另一份，**行为和你想的不一样也发现不了**
- 忘了 `pip install -e .` 也能跑通，CI 里一装就崩

src 布局把"源码"和"导入路径"隔开：不安装就 `import kbcli` 找不到 → **强制你先安装**，保证测的就是用户拿到的东西。业界标准（PyPA 推荐），Django/Flask/pytest 都是这么放的。

## 2. 概念精讲 B：`[project.scripts]` 到底做了什么

```toml
[project.scripts]
kbcli = "kbcli.cli:main"
```

安装时，构建后端在 `Scripts/`（或 `.venv/bin/`）生成一个 `kbcli.exe`（Windows 上是 exe 包装器），内容等价于：

```python
import sys
from kbcli.cli import main
sys.exit(main())      # ← 你的 main() 返回值 = 进程退出码
```

三条必须懂：

1. **`main()` 必须返回 int**：`0` 成功，非 0 失败。返回 `None` → 退出码 0（脚本挂了也当成功）。返回字符串 → 退出码 1 + stderr 报错。
2. **命令行参数从 `sys.argv` 来**：`argparse.ArgumentParser().parse_args()` 默认读 `sys.argv[1:]`，不用你手动解析。
3. **`python -m kbcli` 和 `kbcli` 是两条路**：前者走 `__main__.py`，后者走 console script。两条都要通——`__main__.py` 内容就一行 `raise SystemExit(main())`。

## 3. 概念精讲 C：LRU 的三条实现路线

| 路线 | get | put | 问题 |
|------|-----|-----|------|
| list + dict | O(n) 查位置后 remove | O(n) | 淘汰找最久未用要扫全表 |
| **OrderedDict** ✅ | O(1) `move_to_end` | O(1) `popitem(last=False)` | 无（今天用这条） |
| dict + 手写双向链表 | O(1) | O(1) | 代码量 3 倍，面试手写才值 |

`OrderedDict` 是 dict + 双向链表的封装，`move_to_end()` 只改 4 个指针，所以 O(1)。

**LRU 语义就三句话**：

1. `get(key)` 命中 → 把 key 移到**最新**端；未命中 → 返回 None
2. `put(key, value)` → 放到最新端
3. 超容量 → 淘汰**最旧**端（`popitem(last=False)`）

## 4. 概念精讲 D：缓存一致性（今天的隐藏主线）

缓存是"副本"，副本就会**过期**。写操作（create/delete）之后，缓存里的旧数据必须失效，否则用户读到幽灵：

```
delete kb1 成功 → 缓存里还有 kb1 → show kb1 返回已删除的记录  ← 脏读
```

三种策略（能讲出取舍就够面试用）：

| 策略 | 做法 | 取舍 |
|------|------|------|
| Cache-Aside（今天用） | 读：cache→miss→repo→回填；写：**删缓存** + 写库 | 简单，业界默认；极端并发下有短暂不一致 |
| Write-Through | 写库同时写缓存 | 一致性好，写放大 |
| TTL 兜底 | 缓存带过期时间 | 不保证强一致，但能自愈（生产常和 Cache-Aside 叠加） |

## 5. 动手顺序（五步，每步可跑）

### 第 1 步：骨架 + pyproject（脚手架，照抄）

```toml
[project]
name = "kbcli"
version = "0.1.0"
description = "命令行知识库工具：分层 + 配置 + 日志 + 缓存"
requires-python = ">=3.11"
dependencies = ["pydantic-settings>=2.4"]

[project.scripts]
kbcli = "kbcli.cli:main"

[dependency-groups]
dev = ["ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

跑：`uv sync` → `uv run python -c "import kbcli; print(kbcli.__version__)"` → 能打印 0.1.0 说明 src 布局 + 安装链路通了。

### 第 2 步：config.py + logging_setup.py（小，但别省）

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KBCLI_", env_file=".env", extra="ignore")
    data_file: Path = Path("kbs.json")
    log_level: str = "INFO"
```

`KBCLI_DATA_FILE=E:/tmp/x.json` 环境变量应能覆盖默认值（D3 的三级优先链实战）。

### 第 3 步：`caching.py`（⭐ 手写，今天的核心）

```python
class LRUCache:
    """容量受限的最近最少使用缓存。get/put 均 O(1)。"""

    def __init__(self, capacity: int = 128) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须大于 0")
        self._capacity = capacity
        self._data: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        # 命中 → move_to_end(key)，hits+1，返回
        # 未命中 → misses+1，返回 None
        ...

    def put(self, key: str, value: Any) -> None:
        # 已存在先 move_to_end；写入；超容量 popitem(last=False)
        ...

    def invalidate(self, key: str) -> None:
        """删除单个 key（写操作后调用）。"""
        ...

    def clear(self) -> None:
        ...

    def __len__(self) -> int:
        ...

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
```

自测（写完立刻跑）：

```python
c = LRUCache(2)
c.put("a", 1); c.put("b", 2)
assert c.get("a") == 1          # a 变成最新
c.put("c", 3)                    # 容量溢出 → 淘汰最旧的 b
assert c.get("b") is None
assert len(c) == 2
assert c.get("a") == 1           # 命中
print("hit_rate:", c.hit_rate)
```

### 第 4 步：services.py 接缓存

```python
class KBService:
    def __init__(self, repo, cache: LRUCache) -> None:
        self._repo = repo
        self._cache = cache

    def get_kb(self, owner_id, kb_id):
        cached = self._cache.get(kb_id)
        if cached is not None:
            return cached          # ← 命中直接回
        kb = self._repo.get(kb_id)
        if kb is None:
            raise NotFoundError(...)
        if kb["owner_id"] != owner_id:
            raise ForbiddenError(...)
        self._cache.put(kb_id, kb)
        return kb

    def create_kb(...): ...        # 成功后清缓存（或者根本不用清——新 id 不在缓存里，想清原因）
    def delete_kb(...): ...        # ⚠️ 必须 invalidate(kb_id)，否则脏读
```

**红线**：`delete_kb` 不 invalidate = 今天的头号坑。create 要不要清？想清楚为什么（提示：新 id 是新的，缓存里不可能有；但如果你按 name 缓存就要清）。

### 第 5 步：cli.py + verify.py

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kbcli", description="命令行知识库")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create", help="新建知识库")
    p_create.add_argument("name")
    p_create.add_argument("--owner", default="local")
    p_list = sub.add_parser("list", help="列出我的知识库")
    p_list.add_argument("--owner", default="local")
    p_show = sub.add_parser("show", help="查看单个知识库")
    p_show.add_argument("kb_id")
    p_delete = sub.add_parser("delete", help="删除知识库")
    p_delete.add_argument("kb_id")

    args = parser.parse_args(argv)
    try:
        ...
        return 0
    except AppError as exc:       # D4 的异常族：统一在这里翻译成退出码
        print(f"错误: {exc.message}", file=sys.stderr)
        return 2
```

## 6. 验收清单（D7 前必须全绿）

- [ ] `uv run kbcli --help` 显示四个子命令；`uv run python -m kbcli --help` 同样通达（两入口）
- [ ] `uv run kbcli create "测试库" --owner alice` → 数据文件出现记录；`list` 能列出
- [ ] `KBCLI_DATA_FILE=/tmp/other.json uv run kbcli list` → 读的是另一个文件（环境变量覆盖生效）
- [ ] 缓存命中有证据：同一 id `show` 两次，第二次日志**没有** repo 的"读盘"日志
- [ ] `delete` 后 `show` → 返回 NotFound（**不是缓存的旧记录**）
- [ ] `LRUCache(2)` 塞 3 个，最久未用被淘汰；`hit_rate` 数值正确
- [ ] `grep -r "lru_cache" src/` → 零命中
- [ ] ruff check / format 全绿

## 7. 易错点（出题人视角）

1. `main()` 返回 None → 出错也退出码 0，CI 永远绿。
2. `except AppError` 漏了 `PermissionError` 之外的异常 → 用户看到裸 traceback。
3. `delete_kb` 忘 invalidate → 脏读（今天最想让你亲手踩一次的坑，踩完永远记住）。
4. 缓存了 `None`（miss 也回填）→ 新建的同 id 记录被"负缓存"挡死。要么不缓存 None，要么 create 后清缓存。
5. `OrderedDict` 忘了 import（用 `collections` 不是 `typing`）。
6. `popitem(last=False)` 参数写反 → 淘汰最新的，LRU 变"最不常用"错误语义。
7. `[project.scripts]` 写 `kbcli.cli.main`（带模块名）→ 入口报错；格式是 `模块:函数`。

## 8. 面试问法

1. "LRU 为什么用 OrderedDict/双向链表而不是 list？" → 淘汰需要"移到最新"和"取最旧"都 O(1)，list 是 O(n)。
2. "缓存和数据库怎么保证一致？" → Cache-Aside：读回填、写删缓存；极端并发用延迟双删/TTL 兜底。
3. "`console_scripts` 的原理？" → 安装期生成包装脚本，import 目标函数并 `sys.exit()` 其返回值。

## 9. 闭卷自测

1. src 布局相比平铺布局解决的核心问题是什么？
2. `popitem(last=False)` 淘汰的是哪一端？
3. delete 之后为什么必须 invalidate 缓存？不清会发生什么？
4. `main()` 返回 `None` 和返回 `2` 的区别？

<details>
<summary>答案</summary>

1. 强制"安装后才能 import"，保证测的包 = 用户装的包；避免当前目录遮蔽已安装版本。
2. 最旧（最久未使用）那一端——因为 put/move_to_end 都往尾部放，头部就是 LRU。
3. 不清则缓存里留着已删除记录，`show` 读缓存直接返回幽灵数据（脏读），且不报错。
4. `None` → 进程退出码 0（成功）；`2` → 非零（失败），CI/Shell 能据此判断。
</details>
