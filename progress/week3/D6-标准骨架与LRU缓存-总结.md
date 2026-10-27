# D6 总结：标准骨架与 LRU 缓存（W3 压轴）【面试参考版】

> 日期：2026-10-26 ｜ 用时：约 2.5h ｜ 第四档 #06：3/4（真懂档）
> 用法：秋招前把"30 秒答案集"背熟；追问链按面试官深挖方向预演；白板手写靶考前必须默写一遍。

---

## 0. 今天的项目全景（面试开场可用）

> 面试官："你做过什么 Python 工程化的实践？"

**30 秒版**："我按社区标准从零搭过一个 CLI 项目：src 布局 + pyproject.toml 声明元数据和入口、uv 管依赖锁版本、分层架构（CLI 接口层 → service 业务层 → repo 存取层）、pydantic-settings 管配置、手写了 O(1) 的 LRU 缓存接进业务层。整个过程我刻意复刻了后端 Web 项目的结构——CLI 只是接口层不同，分层、配置、异常翻译、缓存策略和 FastAPI 项目是同一套思想。"

**为什么用 CLI 练而不是直接写 Web**：接口层越薄，越能看清分层本质——把 HTTP 换成命令行，剩下的（service/repo/契约/缓存）一字不改。这个"换接口层验证分层"本身就是面试故事。

---

## 1. 概念 A：src 布局（src layout）

| 层次 | 内容 |
|------|------|
| 一句话定义 | 把包源码放进 `src/` 目录的项目结构，强制"必须安装后才能 import" |
| 为什么存在 | 平铺布局（包目录在根下）会让 `import kbcli` 命中**当前目录的源码**——你测试的和用户 pip install 到 site-packages 的**不是同一份**，"在我机器上是好的"经典事故 |
| 怎么用 | `pyproject.toml` 里 `[tool.hatch.build.targets.wheel] packages = ["src/kbcli"]`；开发时装为 **editable install**（`uv sync` 默认） |
| 底层机制 | editable 安装往 site-packages 放一个 `.pth`/finder 重定向，`__file__` 仍指向 src 源码 → 改源码立即生效、无需重装；同时 import 只会走 site-packages 这一条路，测装一致 |

**面试问法**："src 布局和平铺布局的区别？为什么主流项目都用 src？"

**30 秒答案**："src 布局让包必须安装后才能 import。平铺布局下当前目录在 sys.path 里，测试时 import 到的是工作目录的源码而不是安装的那份，测试结果不能代表用户拿到的行为。src 布局逼你走安装流程，配合 editable install 开发体验不变，但保证'测的和装的是同一份'。"

**追问链**：
- 追问①："editable install 的原理？" → site-packages 里放重定向 finder/`.pth`，import 转发到 src 源码目录；所以改源码不用重装。
- 追问②："那 sys.path 里还有什么？" → 脚本所在目录、PYTHONPATH、site-packages；这就是为什么"从 src/kbcli 目录里跑命令"会出诡异行为——当前目录混进 sys.path。
- 追问③（深）："pyproject.toml 出现前用什么？" → setup.py/setup.cfg；pyproject 是 PEP 518/621 定的统一声明格式，[project] 表是元数据的单一事实来源。

**易错点**：站在 `src/kbcli` 里跑 uv 命令 → 相对路径（数据文件、.env）以当前目录为基准，换目录就"神秘失效"。**所有命令在项目根跑**。

---

## 2. 概念 B：`[project.scripts]` 与入口链

| 层次 | 内容 |
|------|------|
| 一句话定义 | pyproject 里的入口声明：安装时生成可执行包装脚本，把命令名映射到 `模块:函数` |
| 为什么存在 | 让 `pip install` 后用户直接敲 `kbcli` 而不是 `python -m kbcli.cli`；命令行工具分发的标准机制 |
| 怎么用 | `[project.scripts] kbcli = "kbcli.cli:main"`；`main()` 返回 int（退出码），`__main__.py` 里 `raise SystemExit(main())` |
| 底层机制 | 安装时在虚拟环境 `Scripts/`（Windows）生成 `kbcli.exe`，内容是"import kbcli.cli; sys.exit(main())"；**退出码是进程与 shell/CI 的通信协议**：0 成功，非 0 失败 |

**面试问法**："你的 CLI 出错时怎么让调用方知道失败了？"

**30 秒答案**："分层翻译：service 层抛业务异常（NotFound/Forbidden/Conflict，都继承 AppError），CLI 接口层统一 `except AppError`，打印到 stderr 并 return 2。main() 的返回值经 SystemExit 变成进程退出码，shell 的 `$LASTEXITCODE`、CI 的 errorlevel 都能拿到。这和 FastAPI 里异常处理器把异常翻译成 404/403 是同一个模式——接口层负责把业务异常翻译成协议，业务层只管抛。"

**追问链**：
- 追问①："为什么不直接 print 错误然后不返回码？" → CI/脚本链没法判断成败；退出码是自动化世界的通用协议。
- 追问②："异常为什么在接口层翻译而不是 service 里？" → service 的调用方可能是 CLI、API、定时任务，各自翻译成各自的协议；service 只抛领域异常，保持接口无关。
- 追问③："stdout 和 stderr 的分工？" → 结果走 stdout（可被管道消费），错误/日志走 stderr（D5 的 logging StreamHandler 默认 stderr，所以日志和 print 输出顺序会因缓冲交错）。

**易错点**：`main()` 忘了 return / return None → 退出码永远 0，CI 永远绿——静默假成功。

---

## 3. 概念 C：手写 LRU 缓存（白板高频题 ⭐）

| 层次 | 内容 |
|------|------|
| 一句话定义 | 容量受限的缓存；命中保鲜、满时淘汰最久未使用的条目；get/put 都要 O(1) |
| 为什么存在 | 热点数据重复读盘/读库是性能杀手；LRU 用"最近用过的大概率还用"的假设做淘汰 |
| 怎么用 | `OrderedDict`：`move_to_end(key)` 命中后挪到最新端；`popitem(last=False)` 从最旧端弹出；两个都是 O(1)（底层双向链表 + 哈希表） |
| 底层机制 | OrderedDict = 哈希表 + 双向链表：dict 给 O(1) 查找，链表维护插入/访问顺序，move/pop 只改指针 |

**白板标准实现（必须能默写，15 行）**：

```python
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self.cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)          # 保鲜
        return self.cache[key]

    def put(self, key: str, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value               # ← 赋值必须无条件！
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)    # 淘汰最旧
```

**面试问法**："设计一个 LRU 缓存，get/put O(1)。"

**30 秒答案**："哈希表 + 双向链表。Python 里 OrderedDict 就是这个结构的现成实现：get 命中后 move_to_end 保鲜，put 后检查容量、popitem(last=False) 从最旧端淘汰，两个操作都是 O(1)。三个易错点我会主动提：①覆盖写时赋值必须无条件执行，条件只负责 move_to_end——不然只挪位置不更新值，静默脏数据；②popitem 的 last=False 方向写反就变成淘汰最新的，语义全错；③get 未命中也要计数（hit/miss 统计），可观测性是缓存的一部分。"

**追问链**：
- 追问①："不用 OrderedDict 纯手写呢？" → 哈希表存 key→node，node 是双向链表节点（key/value/prev/next），dummy head/tail 哨兵简化边界；get/put 就是链表摘除+头插，O(1)。
- 追问②："Python 有没有现成的？" → `functools.lru_cache(maxsize=N)`，但只缓存**函数返回值**（按参数做 key）；要求参数可哈希；业务级缓存（可失效、可统计）还是自己封装。
- 追问③："lru_cache 的坑？" → ①方法上用 lru_cache，self 被当 key 之一 → 实例不死缓存不放，内存泄漏；②参数可哈希才行（dict/list 不行）；③`cache_clear()` 是测试换血阀门（D3 学过）。
- 追问④（深）："为什么不用 list/普通 dict？" → list 删除/挪位 O(n)；普通 dict 3.7+ 保插入序但 move_to_end 要 del+再插（两次哈希操作，近似可行但语义和 API 都不如 OrderedDict 清晰，且无 popitem(last=False) 方向控制）。
- 追问⑤（系统设计向）："单机 LRU 和 Redis 的淘汰策略？" → Redis 提供 LRU 近似实现（采样淘汰，省内存）和 LFU；分布式下还有一致性哈希/本地缓存与远端缓存的分层问题（W8+ 会学到）。

---

## 4. 概念 D：缓存接入业务层——一致性与安全（今天的主线）

### 4.1 命中路径必须过同样的业务规则 ⭐（今天亲手踩的安全坑）

**问题**：`get_kb` 里缓存命中直接 `return cached`，**跳过了 owner 校验** → bob 拿 alice 的 kb_id 直接读到别人的库。缓存越热，越权越常态化——生产级漏洞形状。

**修法对比**：

| 方案 | 写法 | 评价 |
|------|------|------|
| A：命中后校验 | `if cached is not None and cached["owner_id"] == owner_id: return cached` | 简单直接；owner 不匹配时多读一次盘，正确性优先 |
| B：复合键 | `put((owner_id, kb_id), kb)` | 各 owner 各一份，隔离彻底但浪费内存（同一记录 N 份） |
| C：先鉴权再查缓存 | 门禁挪到缓存查询前 | 语义最清晰；代价是每次都过一遍校验逻辑 |

今天选了 A。**核心原则：缓存是加速器，不是旁路——它不能 bypass 任何业务规则。**

### 4.2 写操作必须失效缓存（脏读防线）

```python
def delete_kb(self, owner_id: str, kb_id: str) -> None:
    self.get_kb(owner_id, kb_id)      # 复用鉴权
    self._repo.delete(kb_id)
    self._cache.delete(kb_id)         # ← 漏了这行 = 幽灵数据：删了还能"查到"
```

**面试问法**："缓存和数据库的一致性怎么保证？"（后端高频深水区，先给入门版）

**30 秒答案**："最常用的策略是 Cache Aside：读——先查缓存，miss 才查库并回填；写——先更新库，再删缓存（不是更新缓存）。删除而不是更新，是因为更新可能把中间态写进去，且并发写会互相覆盖；删除后下次读自然回填最新值。今天我在 CLI 里做的就是这个最小闭环：delete_kb 先删库再失效缓存条目，漏了失效就会出现'删了还能查到'的幽灵数据。更进阶的延迟双删、订阅 binlog 异步失效我知道存在，等学到 W8 缓存专题再深入。"

**追问链**：
- 追问①："为什么删缓存不是更新缓存？" → ①写多读少时更新是白干；②并发下 A 写库、B 写库、A 更新缓存、B 更新缓存的交错会把旧值留在缓存（时序问题）；删除是幂等的、无中间态。
- 追问②："先更新库再删缓存，也有不一致窗口吧？" → 有：删缓存失败就脏了。工程解法：删除重试/消息队列兜底/订阅 binlog（Canal 类）异步删，以及给缓存加 TTL 兜底。
- 追问③："TTL 和主动失效的关系？" → TTL 是兜底（脏数据最多活到过期），主动失效是主力；两者叠加把不一致窗口压到秒级以下。
- 追问④："缓存穿透/击穿/雪崩？"（面试必考三连）→ 穿透=查不存在的 key，缓存永远 miss 打到库（解：空值缓存/布隆过滤器）；击穿=热点 key 过期瞬间大量请求打到库（解：互斥重建/逻辑过期）；雪崩=大批 key 同时过期（解：TTL 加随机抖动）。

### 4.3 缓存寿命 = 进程寿命（今天实测拍到的）

CLI 每次调用都是**新进程**，LRUCache 活在内存里随进程消亡——所以"CLI 里 show 两次第二次命中"**永远不可能发生**。命中证据只能在同一进程内连调两次才拍得到。

**面试问法**："你的缓存进程重启后就没了，怎么办？"

**30 秒答案**："进程内缓存本来就是易失的，这是特性不是缺陷——它换的是速度不是持久性。要跨进程/跨实例共享就得外置：Redis 这类远端缓存。工程上常见两级：本地缓存（进程内，微秒级）挡热点 + 远端缓存（毫秒级）共享，各自有失效策略。我的 CLI 场景单进程就够，如果做成常驻服务，这层 LRU 直接有用。"

---

## 5. 概念 E：config.py 的三级优先链（D3 复认，面试常问）

环境变量 > `.env` 文件 > 代码默认值。`pydantic-settings` 的 `env_prefix="KBCLI_"` 实现"字段名 ↔ 环境变量"自动映射（大小写不敏感）。`@lru_cache` 包住 `get_settings()` 做进程级单例——**副作用要能说出口**：同一进程内改环境变量再调不会变（缓存住了），测试里要 `get_settings.cache_clear()` 换血。

**面试问法**："十二要素应用（12-Factor）第三条是什么？" → 配置存环境：同一份代码部署到 dev/test/prod，差异全在环境变量里，配置和代码严格分离。

---

## 6. 30 秒答案集（考前速背）

1. **src 布局解决什么** → 强制安装后 import，保证测装一致。
2. **退出码是什么** → 进程与 shell/CI 的通信协议；main() return 0/2，接口层翻译异常。
3. **LRU 三个动作** → move_to_end 保鲜 / popitem(last=False) 淘汰 / 覆盖写无条件赋值。
4. **OrderedDict 为什么 O(1)** → 哈希表查 + 双向链表挪，都是指针操作。
5. **缓存一致性最小闭环** → Cache Aside：读 miss 回填，写先更库再删缓存。
6. **缓存命中绕过鉴权** → 缓存是加速器不是旁路，命中路径也要过业务规则。
7. **CLI 缓存为什么测不出命中** → 进程死缓存亡，证据须同进程拍。
8. **配置三级链** → 环境变量 > .env > 默认值；get_settings 用 lru_cache 做单例。

## 7. 白板手写靶（考前必须默写）

1. **LRUCache 三方法**（§3 的 15 行）——200% 会考。
2. **`main()` 的 try/except AppError → return 2 骨架**（5 行）。
3. **`delete_kb` 三行**：复用鉴权 → 删库 → 失效缓存（顺序不能乱）。

## 8. 踩坑记录（复习时重点扫这）

| 坑 | 教训 |
|----|------|
| `put` 覆盖写把赋值关进 else | 只挪位不更新值 → 脏数据；赋值无条件，条件只管 move_to_end |
| 空 `__init__.py` 忘 Ctrl+S | PyCharm 编辑器和磁盘不是一回事；"写好了"先 cat 确认 |
| 测试被残留环境变量污染 | 上次实验的 `KBCLI_DATA_FILE` 没清 → 测"默认值"测了个寂寞；实验前先清场 |
| PowerShell 把 `<id>` 占位符当重定向 | 占位符要换成真值，别连尖括号一起抄 |
| "缺 return"三连漏（retry→rename→build_report） | 规矩：写完函数核对**签名承诺 vs 每条出口路径**；mypy（W5）能抓 |
| 第四档误报"put 缺写入" | 无条件赋值在 if 块外——把修复后的正确形状认成 bug，说明读代码要跟全控制流 |

## 9. 闭卷自测（不看上文答）

1. src 布局的核心收益是哪两个字？（提示：测 X 一致）
2. `main()` 返回 2，谁消费这个数字？举两个消费方。
3. LRU 覆盖写时，条件判断负责什么、赋值为什么必须无条件？
4. Cache Aside 写路径为什么"删缓存"而不是"更新缓存"？
5. 缓存穿透/击穿/雪崩分别是什么，一句话解法各是什么？
6. 为什么 `get_settings()` 要套 lru_cache？测试里怎么重置？

<details><summary>答案</summary>
1. 测装一致。 2. shell（$LASTEXITCODE）和 CI 流水线（决定 job 成败）。 3. 条件只管 move_to_end；赋值无条件，否则覆盖写静默丢新值。 4. 更新有并发时序问题且写多读少时白干；删除幂等、无中间态，下次读自然回填。 5. 穿透=查不存在的 key（空值缓存/布隆过滤器）；击穿=热点 key 过期瞬间（互斥重建/逻辑过期）；雪崩=大批同时过期（TTL 加抖动）。 6. 进程级单例避免重复读环境/文件；测试里 get_settings.cache_clear() 换血。
</details>

## 明天：D7 闭卷 12 题 + W3 复盘 + tag w03-done
