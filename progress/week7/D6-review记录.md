# W7-D6 代码 review 记录（2026-11-19）

> **方法就是 `progress/代码review检查单.md` 本身**：先跑契约三件套，再跑四种手段，再过十二问。  
> 下面每一步都是**空表**，你边读代码边填。AI 的标准答案在最后——对照用，不是替代。  
> 收口三问：这段代码假设了什么？谁在保证它？它失效时我会不会知道？

## 范围

今天的 diff：`kb_repo.py` / `kb_service.py` / `doc_repo.py` / `doc_service.py` / `models.py` / `main.py` / `dev.py` / `conftest.py` / `test_db_integration.py`。  
核心入口三个函数，契约三件套从这里开始；其余代码用手段扫，不逐行读。

---

## 第一步：契约三件套（§二）

对下面三个函数，逐条写：前条件 / 后条件 / 不变式，**每条后面写"谁在保证它"**（只允许三种答案：代码自己检查 / 调用方保证 / 外部系统保证）。说不出来处的，标 ⚠️——那就是 bug 温床。

### 示范（照这个粒度填，函数换成 A/B/C 的）

`KBService.delete(kb_id, user_id)`：

| 条件    | 内容                           | 谁在保证                                                        |
| ----- | ---------------------------- | ----------------------------------------------------------- |
| 前条件 ① | kb 存在                        | 代码自己——`get_or_403` 查不到就抛 `NotFoundError`                    |
| 前条件 ② | user 是 owner                 | 代码自己——`get_or_403` 比对 `owner_id`，不符抛 `ForbiddenError`       |
| 前条件 ③ | session 非 None、事务已开启         | 调用方——handler 的 `Depends(get_db)`；`KBService` 不检查 ⚠️         |
| 后条件 ① | 返回后 kb + docs + chunks 都不在库里 | 代码 + 级联——`session.delete(obj)` + models.py:36 的 ORM cascade |
| 后条件 ② | commit 已发生，别的会话可见            | 代码自己——`_commit()`（session 为 None 时静默跳过，承诺是空的 ⚠️）            |
| 不变式   | 无                            | 这个函数不维护跨行计数，写"无"也是合法答案                                      |

读表要点：**⚠️ = 说不出来处**，全部流进手段 1 的前提审计；"代码自己检查"（不满足就炸）≠"代码自己保证"（不满足也不响）；不变式硬凑不如写"无"。

### A. `KBService.update(kb_id, user_id, data)`（kb_service.py:54）

> 空行是槽位：能列出几条就写几行，不够就自己往下加。下面同。

| 条件    | 内容                   | 谁在保证                                                  |
| ----- | -------------------- | ----------------------------------------------------- |
| 前条件 ① | kb存在                 | 代码自己——`get_or_403` 查不到就抛 `NotFoundError`              |
| 前条件 ② | user 是 owner         | 代码自己——`get_or_403` 比对 `owner_id`，不符抛 `ForbiddenError` |
| 前条件 ③ | session 非 None、事务已开启 | 调用方——handler 的 `Depends(get_db)`；`KBService` 不检查 ⚠️   |
| 前条件 ④ | data有效               | 调用方——KBUpdate的入参校验                                    |
| 后条件 ① | 返回后的数据格式符合KBOut      | Fastapi——model_validate保证，不符合会抛异常                     |
| 后条件 ② | commit 已发生，别的会话可见    | 代码自己——`_commit()`（session 为 None 时静默跳过，承诺是空的 ⚠️）      |
| 不变式   | 无                    |                                                       |

> **AI 修正你的 A 表两处**：
> ① 后条件① 的出处写"FastAPI"不准确——`model_validate` 是 **KBService 代码自己调的**（kb_service.py:33），保证形状的是 Pydantic 库，触发者是业务代码。三选一里应选"代码自己"。
> ② 前条件④ "data 有效"漏了一个静默洞：`{}` 空 PATCH 合法（Pydantic 不要求至少一个字段）→ setattr 循环零次 → **静默 no-op 返回 200**（探针 2 实测）。"入参校验"保证的是形状，不是"有意义"。
> ③ 还漏了最毒的一条后条件：**"返回的 updated_at 是新值"**——保证不了！`to_row()` 在 flush 前取快照，`onupdate` 在 flush 时才生效（探针断言2 实测：to_row 里的 updated_at == 旧值 True）。客户端 PATCH 改名成功，拿回的时间戳是旧的——**静默错误**。
> ④ 不变式写"无"合法，但有一条值得知道：`owner_id` 永不被 PATCH 改（`KBUpdate` 没这个字段，schema 保证）。

### B. `DocService.create(kb_id, user_id, data)`（doc_service.py:45）

| 条件    | 内容                                           | 谁在保证         |
| ----- | -------------------------------------------- | ------------ |
| 前条件 ① | kb 存在且 user 是 owner                          | 代码自己——`get_or_403` |
| 前条件 ② | title/content 非空非全空白、长度上限                    | schema——`not_blank` + max_length（实测：全空白 → 422） |
| 前条件 ③ | session 或 repo 至少给一个                         | 代码自己——构造函数抛 `ValueError`（doc_service.py:27-34，入口炸，堆栈第一行就是答案） |
| 后条件 ① | 文档行 + chunks 行 + doc_count+1 **同生共死**        | 代码自己——五步一次 commit；中途炸 `get_db` rollback 全撤 |
| 后条件 ② | 返回的 status=ready、chunk_count=实际块数            | 代码自己——`{**row, ...}` 补快照（row 是 repo.create 时刻的快照） |
| 后条件 ③ | chunks 的 seq 唯一连续                            | 代码自己（enumerate）+ DB 兜底（`uq_chunk_doc_seq`） |
| 不变式   | `doc_count == 该 kb 下 documents 行数`           | **代码自己——两个写点**：create 里 +1（`incr_doc_count(kb,1)`）、delete 里 -1（doc_service.py:80） |

> **AI 修正你的不变式答案（"数据库——原子自增+行锁"）**：原子自增 + 行锁保证的是**这个加法本身不丢、不互相覆盖**（D4 的丢失更新），它保证不了**语义上该不该加**。DB 不知道"建了一篇文档该 +1"——`+1` 是 `doc_service.create` 的代码在做，`-1` 是 `delete` 的代码在做。所以不变式由**两个写点的代码**维护：正确但脆弱（未来批量导入第三个写点忘了同步，数据库不会拦你）。**原子性 ≠ 不变式成立**——这是这条 review 最值钱的一句。

### C. `KBService._commit()`（kb_service.py:24）

这个最小，也最毒：前条件是什么？谁保证 session 不是 None？"session 为 None 时静默跳过"算不算破坏了后条件？

| 条件  | 内容            | 谁在保证             |
| --- | ------------- | ---------------- |
| 前条件 | session不是None | 调用方——handler依赖注入 |
| 后条件 | commit成功执行    | 代码自己——`self._session.commit()` |

> **AI 修正你的后条件答案（"数据库"）**：数据库保证的是 commit **成功之后**的持久性（写入不丢）；"commit **会被调用**"这件事只能由代码保证。而且实测发现这个保证是空的：`session` 为 None 时静默 return——承诺存在，兑现无人。**判定：算破坏后条件**（承诺"提交"，实际"可能提交"）。更硬写法：session 必传 + 测试用 NullSession 桩，忘传变 mypy 编译期错误。

---

## 第二步：四种手段（§四）

### 手段 1：前提审计（对上面三个函数的 ⚠️ 条款）

每个 ⚠️ 前提问三连：**谁保证 → 不成立时报错还是算错值 → 算错值的话错给谁看**。  
"报错"安全；"算出一个错的值"是静默错误，最高优先。

| 前提 | 不成立时 | 静默 or 硬失败 |
| -- | ---- | --------- |
| session 非 None（A③ / C） | flush 成功、接口 201，**库里 0 行**（今早真实事故） | **静默** |
| `updated_at` onupdate 时机（A） | 客户端拿到旧时间戳，无报错 | **静默**（断言2 实测） |
| 空 PATCH `{}`（A④） | 200、无副作用、无提示 | **静默 no-op**（实测） |
| update 竞态：另一会话删了行 | identity map 返回缓存对象 → setattr → flush 抛 `StaleDataError` | **硬失败 500**（断言1 实测；AI 原预测"静默 200"被推翻） |
| delete 竞态：另一会话抢先删 | flush **不抛**，静默"成功"——但端状态两路收敛（行反正没了），实际无害 | **静默**（断言4 实测） |
| `doc_count` 两个写点手工维护（B 不变式） | 未来第三个写点（批量导入）漏同步 → 计数漂移 | **静默漂移**（负债，非现行 bug） |

### 手段 2：变异探测

今早已经做过一次（删 `_commit()` → 集成测试红），记下结果。再选一个变异自己设计：

> 把 `kb_repo.update` 里的 `setattr` 循环删掉 → 有测试会红吗？为什么红/不红？

| 变异                             | 有没有人喊 | 说明什么 |
| ------------------------------ | ----- | ---- |
| 删 `_commit()`（已做）              | ✅ 集成测试红（另一个会话看不到这行） | 漏 commit 有真防线 |
| 删 update 的 setattr 循环          | ✅ `test_kb_crud_flow` 红 | PATCH 有覆盖 |
| `incr_doc_count` 的 delta 改成 +2 | ✅ 3 个测试红（decrement / upload / twenty_increments） | 计数器防线最厚 |
| （用户变异）删 `if row is None`       | ✗ **无测试红** | 不可达分支——"装饰"；真防线在 `get_or_403` + flush 的 StaleDataError 校验 |

### 手段 3：反例构造

对着 `KBUpdate` 和 `DocCreate` 构造反例，预测每个的行为再验证：

| 反例                                                      | 预测行为 | 实际（可探针/测试） |
| ------------------------------------------------------- | ---- | ---------- |
| `PATCH {"name": null}`                                  | 200（repo 的 `if v is not None` 挡掉） | ✅ 200——静默忽略 = PATCH 语义"null 不改"，但客户端拼错字段也 200，边界该写进 API 文档 |
| `PATCH {"description": null}`（description 本来 nullable）   | 200，且"清空"做不到 | ✅ 200——`if v is not None` 把"清空描述"也挡了，**清空语义缺失**（行为债） |
| `POST doc content="   "`（全空白）                           | 422 | ✅ 422——schema 的 `not_blank` 兜住了 |
| 同名 KB 重复创建（同 owner）                                     | IntegrityError | ✅ 约束生效（`uq_kb_owner_name`）但**未翻译成 409** → 500（已知债） |
| 两个请求同时建同名 KB                                            | 后 commit 的那个失败 | 顺序重复已实测（同上）；并发未单独实测——机制上同一约束兜底，第二个事务在 flush/commit 时撞唯一索引 → 500 |

### 手段 4：时间轴推演（§四.4 的三个事件）

对 `DocService.create` 的五步（get_or_403 → repo.create → incr_doc_count → \_parse_sync → commit）：

| 事件插在哪                                   | 后果 |
| --------------------------------------- | -- |
| 进程在第 2 步和 commit 之间死掉                   | 五步全在一个事务里，`get_db` 的 `close()` 回滚 → 文档、chunks、计数全部不存在，用户重传即可 ✅ |
| 另一个实例同时给同一个 kb create 文档（doc_count 会怎样） | doc_count 用 `x = x + delta` 单条 UPDATE，原子不丢更新 ✅；chunks seq 每篇独立从 0 编，无冲突 |
| 同一请求被重试一次（网络层）                          | **建两篇文档**——create 不幂等，重试防护不在代码里（谁该管？调用方；API 文档没写 ⚠️。W11 异步化时用 client-generated id 解决） |
| 另一个实例同时 DELETE 这个 kb                    | `incr_doc_count` 的 UPDATE 影响 0 行 → `NotFoundError` → 404 ✅——这一步反而把竞态防住了 |

---

## 第三步：十二问（§五）——只勾命中的，逐问写一句

对今天 diff 里你扫过的代码，过一遍十二问。命中的写一句结论；没命中画 ✗。

1. 被调用两次会怎样？—— ✗ 主要写路径无此风险（delete 两次第二次 404，可接受）
2. 永远不被调用会怎样？—— ✅ 命中两次：今天删掉的 `base.py`（内存 store 死代码）；`if row is None` 不可达分支（变异探测无测试红）
3. 执行到一半崩掉，留下什么？—— ✅ DocService.create 五步一个事务，崩了全撤（时间轴已推演）
4. 两个实例同时跑，谁覆盖谁？—— ✅ doc_count 原子 ✅；update/delete 竞态见手段 1（StaleDataError 500 / delete 静默收敛）
5. 输入是它自己上一次的输出，会不会漂移？—— ✗ 未发现自输出回灌路径
6. 值是空/空集/超长时走哪条分支？—— ✅ 反例构造全覆盖：空白 422、空 PATCH 静默 no-op、同名 500（待修）
7. 谁读这个值？读的人需要什么保证？—— ✅ **命中要害**：`to_row()` 的快照被 service 直接 `model_validate`——读的人以为是库里的真相，其实是取快照那一刻的（updated_at 旧值就是这么漏出去的）
8. 这个常量明天要改，得改几处？—— ✗ `chunk_size=400/overlap=50` 各一处，OK
9. 这段删掉，谁会发现问题？—— ✅ `if row is None` 删了没人发现（死分支）；`_commit` 的 None 分支删掉 fake 单测会炸——它有真实用户，不能删
10. 出问题时，日志里能看到什么？—— ✗ TraceMiddleware 会记 request_failed（同名重复那次实测看到了完整 traceback），但 IntegrityError→500 的用户侧语义没有专门日志
11. 三个月后改这块的人需要知道什么，代码里写了吗？—— ✅ **两处过期 docstring**：`doc_repo.py:14`"W7 TODO：换成 SQLAlchemy"（已换完）、`kb_repo.py:17-21`"session 为 None 时沿用内存实现"（已必传）——过期注释让人不再相信任何注释
12. 这段代码假设了什么外部事实？谁在维护那个事实？—— ✅ `expire_on_commit=False`（core/db.py）是 `_commit` 后还能 `model_validate(row)` 的前提——两周前的决定在为今天的代码兜底

---

## 第四步：扫尾（§六 AI/生成代码的错分布）

今天的代码有相当一部分是 AI 给骨架、你填空的。检查单 §六 说的错分布是"外部系统真实行为、默认值求值时机、量级变化后的性能"。问自己：

- 今天哪几个 bug 正好落在这个分布里？（提示：1101、级联、onupdate 时机）
- 有没有哪段代码"看起来专业"，但你其实**判断不了**对错？——按 §七，两个合法动作：查文档 / 实测。别装审过。

> 我的答案：

**AI 代填**：今天落进 §六 分布的 bug 有三个——**1101**（TEXT 不许 DEFAULT：库的真实行为，sqlite 测不出来）、**级联双写**（ORM cascade vs `ondelete=CASCADE` 的分工）、**onupdate 时机**（flush 才生效）。共同点：都不是"写错代码"，是**对外部系统真实行为的假设没验证**。
反过来，"看起来专业但我判断不了"的最大一块是 **ORM cascade 与 DB CASCADE 的执行路径**（删一个 KB 发几条 DELETE、走哪套）——这块按 §七 的合法动作本该实测（SQL 计数探针），本记录没做，诚实标注：**未审，不确定**。

---

## AI 标准答案（判档总表 + 对照 + 追问链）

### 判档总表（对照你已填的部分）

| 题 | 你命中的点 | 缺/错的点 | 档 |
|---|---|---|---|
| A 契约 | 前条件①②③全对；session ⚠️ 标对了 | "data 有效"漏空 PATCH 静默 no-op；model_validate 出处归了 FastAPI；**漏 updated_at 陈旧这条最毒的后条件** | 3 |
| B 不变式 | 写出了不变式本身 | **"数据库——原子自增+行锁"归因错**：原子性保证加法不丢，保证不了"该不该加"；不变式由 create/delete 两个写点的代码维护 | 2 |
| C | 前条件对 | 后条件归"数据库"错（应为代码自己，且承诺是空的）；没回答"算不算破坏后条件" | 2 |
| 手段 1-4 / 十二问 | 未做（AI 代填） | — | — |

**综合：3 档（真懂）**——变异探测抓出真发现（`if row is None` 不可达），契约写得有模有样；差距在**归因层**：三处"谁在保证"都往外部系统推（FastAPI / 数据库），而真正在保证的是**我们自己仓库里的代码**——把保证人找错，修复时就找错门。

### 你的发现"if row is None 冗余"的完整答案

1. 单线程：不可达（get_or_403 已拦）→ 冗余成立，你是对的
2. 并发：它也防不住——identity map 返回缓存对象，分支照样不触发（断言1 实测）
3. 竞态实际结局：update → `StaleDataError` 500（ORM 校验 UPDATE 匹配行数）；delete → **静默**（ORM 不校验 DELETE 匹配行数），但端状态收敛，无害
4. 真修法：UPDATE 语句 + rowcount 检查（`incr_doc_count` 是现成范本），错误面翻译成 404/409

**追问链**：①"你说冗余，删了并发会怎样？"→ identity map + StaleDataError ②"500 合适吗？"→ 不合适，资源消失是 404/409 ③"为什么 delete 不抛？"→ ORM 只对 UPDATE 校验匹配行数，DELETE 不校验——库的未承诺行为，探针发现，文档没写

### 修复清单（进 W8 债表，今天不动代码）

1. 过期 docstring 两处清理（`doc_repo.py:14`、`kb_repo.py:17-21`）——5 分钟顺手
2. 同名重复 → 409（IntegrityError 翻译）
3. "清空 description"语义：`exclude_unset` 已区分设置与否，删掉 name 的 `if v is not None` 例外需先定产品语义
4. update/delete 竞态 → UPDATE 语句 + rowcount（与 2 一起做）
5. create 幂等性：W11 用 client-generated id；API 文档先标注"重试可能建两篇"
6. `doc_count` 不变式加一条一致性校验测试，防未来写点漂移

### 未实测声明（诚实清单）

- 并发同名 KB（手段 3 反例 5）：机制推断，未单独实测
- ORM cascade 删 KB 发几条 DELETE（站点 2 思考题）：未跑 SQL 计数探针
- 探针本身：`probes/review_probe.py`（4 断言）/ `review_probe2.py`（5 反例），全部可复跑
