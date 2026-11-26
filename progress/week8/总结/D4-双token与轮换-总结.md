# W8-D4 总结 · 双 token：签发、轮换、撤销（2026-11-26）

> 本日资产：`refresh_tokens` 表 + alembic 迁移（四项验收全过）+ 双 token login + `/auth/refresh` 四步拒绝链 + `/auth/logout`（204 幂等）+ 清债 ⑥ doc_count 守恒测试 + W6 巡检判卷；测试 108→118，六次变异全杀
> 环境：Python 3.11.17 / SQLAlchemy 2.1.8 / MySQL 8.4（3307）/ FastAPI + Pydantic v2
> 门禁：118 passed, 4 skipped / 覆盖率 97.21%（精确浮点）/ ruff + mypy strict 全绿；变异 logout 3/3、doc_count 3/3
> 第四档：无埋坑版（用户写核心日）→ 以闭卷 8 题判卷 + W6 巡检（2/1/1，出红：三种响应形状）替代

---

## 一、知识地图（按面试出场率降序）

| # | 知识点 | 出场率 | 掌握要求 | 本日证据 |
|---|---|---|---|---|
| 1 | 双 token 模型：access 短命 / refresh 长命 | ★★★★★ | **能用数字答"为什么做 refresh token"（痛点实验读数）** | 交付物 0：EXPIRE=1 → 65 秒后 401 实录 |
| 2 | refresh 轮换与重放检测 | ★★★★★ | **能默写四步拒绝链并说出每步拦什么** | 纸笔照片全对；变异"短路 revoked_at"→ 2 红 |
| 3 | 无状态 JWT 的代价：access 不入库、logout 只管 refresh | ★★★★★ | **能说出"能记 ≠ 能改"和三个理由** | 巡检靶 3 实测：500 时 X-Trace-Id 不在 |
| 4 | opaque token vs JWT 的取舍 | ★★★★☆ | **能给出选型判据而非站队** | 闭卷 8 题第 2/3 题 |
| 5 | 凭证存储：sha256 hash 落库 | ★★★★☆ | **能答"为什么 sha256 够、密码却要 bcrypt"** | 探针 `hash(raw) 对得上 = True` |
| 6 | 条件 UPDATE + rowcount：幂等的判据 | ★★★☆☆ | **能说出 MySQL rowcount 是"改动数"不是"匹配数"** | 变异 A/B/C 三杀 |
| 7 | 滑动过期 vs 绝对上限 | ★★★☆☆ | **能说出滑动过期的语义和被盗风险** | 决策日志候选 |
| 8 | naive/aware datetime：存储层剥时区 | ★★★☆☆ | **能复现"500 的完整因果链"** | `auth_service.py:74` TypeError 500 实录 |

---

## 二、逐个知识点讲透

### 1. 双 token 模型：access 短命 / refresh 长命

**一句话定义**：登录发两张票——access 短命（分钟级、无状态、不落库），refresh 长命（天级、有状态、落库可撤销）。

**为什么存在**：没有它时只有两条路，都是死路。① 单长命 JWT：泄露后到过期前无法作废（无状态=服务端不认识它）；② 单短命凭证：用户每 15 分钟被踢一次。**痛点实验读数（面试要给数字）**：EXPIRE=1 分钟时，登录后 65 秒打受保护接口 → 401「用户凭证已过期」。日活 1000、每会话 50 请求的系统 ≈ 每天 10 万次"无故被踢"——用户没做错任何事。双 token 把"被踢"变成"无感续票"：access 死了用 refresh 换新的，用户侧零感知。

**怎么用**（本项目）：
```python
def login(self, data: LoginIn) -> tuple[str, str]:      # 元组解包，不是 list[str]
    ...
    access = create_access_token(str(row["id"]))         # 短命，JWT，不落库
    refresh = self.create_refresh_token(row["id"])       # 长命，随机串，落库
    self._commit()                                       # login 首次有写 → commit 跟着写走
    return access, refresh
```

**底层机制**：access 是 JWT——自包含（payload 带 exp/sub），服务端验签即可用，不查库；refresh 是 opaque 随机串（`secrets.token_urlsafe(32)` → 43 字符），服务端必须查表才知道它是不是自己发的。**分工的本质：把"频繁验证"和"长期身份"拆到两种介质上**——频繁验证走无状态（快），长期身份走有状态（可撤销）。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | login 返回 `list[str]` | 类型不锁长度，调用方只能 `[0]`/`[1]` 猜 | `tuple[str, str]`，解包即文档 |
| 2 | access 也落库"方便撤销" | 等于放弃了无状态，每个请求都查库 | access 靠短命自愈，不落库 |
| 3 | refresh 也做成 JWT | 轮换后旧票仍可验签通过（除非加 jti 黑名单） | refresh 用随机串，查表才有"作废" |

**面试问法**：「为什么要有 refresh token，一个 token 不行吗？」
**30 秒版**：一个 token 只能二选一——长命没法撤销，短命用户老被踢。我们把高频验证给 access（无状态、分钟级、不落库），长期身份给 refresh（随机串、落库、可撤销）。access 过期用 refresh 静默换新，用户无感；refresh 泄露可以立刻作废。我做项目实测过：把过期调到 1 分钟，65 秒后就被踢，这就是没有 refresh 时的日常。

**追问链**：
→ *"access 为什么不能也落库，这样不就能撤销了？"* 能，但代价是每个请求查一次库 + 一次 join——无状态的优势全没了，退化成 Session。正确姿势是接受"access 在 exp 前不可撤销"这个代价，用短命限制暴露窗口（本日钉死测试 `test_logout_does_not_kill_access_token`）。
→ *"refresh 泄露了怎么办？*" logout / revoke 立刻作废；轮换让旧票 401（重放拦截）。边界：**轮换不防"第一次使用前就泄露"**——偷到的活票第一跳就是合法的。所以高风险系统叠加：绑定 UA/IP 指纹、绝对上限、泄露后按 user_id 全撤。
→ *"你的项目里这套怎么落地的？流量涨十倍会不会先崩在这？"* 项目里 refresh_tokens 表按 token_hash 唯一索引查，单次索引点查，QPS 万级没问题。涨十倍先崩的不是这张表，是**轮换带来的写放大**：每次续票一次 INSERT + 一次 UPDATE。真到那天先做两件事：续票接口限流、过期行清理任务（表里 revoked 行只增不减）。

### 2. refresh 轮换与重放检测

**一句话定义**：每次续票都作废旧票、发新票——refresh token 一次性使用。

**为什么存在**：refresh 是长命票，泄露后攻击者能用 7 天。轮换把"泄露"的暴露窗口压到**一次使用**：真用户下次续票时旧票已被换掉，攻击者手里的旧票一用就 401——而且 401 本身就是"有别人在用你的票"的警报。

**怎么用**（本项目 `refresh_repo.rotate`）：
```python
def rotate(self, old: RefreshToken, new_hash: str, expires_at: datetime) -> None:
    old.revoked_at = datetime.now(UTC)        # 作废旧票
    self.session.add(RefreshToken(user_id=old.user_id, token_hash=new_hash, expires_at=expires_at))
    # 只 add 不 commit —— 和业务操作同一事务，commit 在 service 收口
```

**底层机制**：四步拒绝链（纸笔全对）——① `get_by_hash`：查无此票 → 401；② `revoked_at is not None`：重放 → 401；③ 过期比较 → 401；④ user 不存在或 `is_banned` → 401。四步**全过**才轮换。同一事务内完成"作废旧票 + 插入新票"，中途任何异常 → rollback → 旧票没作废、新票不存在 → 回到续票前状态，不会出现"旧票死了新票没生出来"的中间态。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 短路 revoked_at 判断偷懒 | 旧票无限续命 | 变异验证：`if False and ...` → 2 条测试红 |
| 2 | rotate 里自己 commit | 事务边界碎成两截，轮换不再原子 | repo 只 flush/add，commit 在 service 公开方法 |
| 3 | 四种拒绝返回不同错误信息 | 攻击者靠响应体区分"票不存在/已重放/过期" | 统一 401 + 统一 body（测试钉死） |

**面试问法**：「refresh token 轮换是什么？解决什么问题？」
**30 秒版**：每次用 refresh 换新票时，把旧票标记作废、发一张全新随机票。这样 refresh 变成一次性的——偷到旧票的人再一用就 401，而真用户续票失败恰好暴露了"有人偷票"。关键实现是作废和签发必须在同一个事务里，否则中途失败会出现"旧票死了新票没生出来"，用户被登出。

**追问链**：
→ *"轮换怎么实现原子性？"* 同一事务：UPDATE 旧行 revoked_at + INSERT 新行，一次 commit。我在 repo 层只做 flush/add，commit 收口在 service——两个会话入口各 commit 一次是事务边界碎掉的典型。
→ *"并发下同一个 refresh 发两次请求会怎样？"* 这是我项目的已知债（W9-③）：两个请求都读到活票 → 都通过检查 → 各换一张新票，**一票换两票**。唯一索引拦不住（两张新票 hash 不同、各自合法）。真正的解法是条件 UPDATE 抢占：`UPDATE ... SET revoked_at=now WHERE token_hash=? AND revoked_at IS NULL`，rowcount=0 的那个请求判定为重放。检查与写入之间有窗口，是一整类并发 bug 的共同病因。
→ *"被偷的票在第一次使用前，你完全没办法吗？"* 对，轮换只防"用过的票"。所以生产会叠加：refresh 绑定设备指纹（换 UA/IP 直接拒绝）、绝对上限（无论怎么续，72 小时必重登）、异常检测（同账号异地高频续票告警）。我项目只做了轮换 + 封禁即拒，指纹是 W9+ 的可选升级。

### 3. 无状态 JWT 的代价：access 不入库、logout 只管 refresh

**一句话定义**：JWT 验签即可用、服务端不保存 → 发出去的 access 在 exp 前收不回来。

**为什么存在**：无状态换来了水平扩展（任何实例都能验，不用共享存储），代价是**没有吊销名单**。logout 因此只能作废 refresh 票——用户"退出"后，手里的 access 仍然有效到 exp。这不是 bug 是设计，但要能说清边界。

**怎么用**（本项目 logout 的三个决策）：
```python
def logout(self, data: RefreshIn) -> None:
    self._refresh_repo.revoke_by_hash(refresh_token_hash(data.refresh_token))
    self._commit()
    # 不 raise：票不存在/已撤销都算成功 —— 幂等，且不泄漏"这张票是否存在"

@router.post("/logout", status_code=204)          # 无响应体
async def logout(body: RefreshIn, ...) -> None:   # 不挂 get_current_user
```

**底层机制**：不挂 `get_current_user` 的三个理由（判断题只答出第一个）——① **可用性**：access 过期后仍要能退出，挂了依赖就在门口 401，票永久躺在库里；② **安全性**：refresh 原文本身就是持有证明（43 字符随机串只有持有者知道），再验一次 access 是重复证明；③ **封禁语义**：`get_current_user` 查库读 `is_banned`，被封用户 access 一律 401 → **永远无法注销自己**，票永久有效，直接和封禁设计打架。形态上挂了依赖还会出现 header 里 access + body 里 refresh 双凭证耦合。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 以为 logout 能踢掉 access | 测试写"logout 后旧 access 401"永远红 | access 到 exp 前照旧 200（测试 `test_logout_does_not_kill_access_token` 钉死） |
| 2 | logout 挂鉴权依赖 | 凭证过期的用户退不了；被封用户永远退不了 | 只凭 refresh 原文认证 |
| 3 | 204 却写了 `return ApiResponse(...)` | 不报错，body 被静默丢弃，前端 `res.json()` 炸 | 204 必须 `-> None`（实测：返回 body 收到 `b''`，服务端全绿） |
| 4 | 重复 logout 返回 404 | 响应码成了"票是否存在"的探针 | 幂等：一律 204 |

**面试问法**：「用户点退出登录，后端做了什么？JWT 不是无状态吗？」
**30 秒版**：无状态 JWT 收不回已发的 access，所以 logout 作废的是 refresh 票——把撤销表里那行标 revoked，之后的续票请求 401。已发出去的 access 等它自然过期，这是无状态的固有代价，想秒踢只能上黑名单。退出接口本身不要求 access 有效——不然凭证刚过期的用户连退出都退不了，被封禁的用户更是永远退不了。

**追问链**：
→ *"想立刻把某用户的 access 全部作废怎么办？"* 三条路：token_version（用户表加版本号，JWT 带版本，验签时比对——一次改版全踢）；短期 access（分钟级，等它死）；网关黑名单（Redis 存 jti，代价是每个请求多一次查询，退化回有状态）。我的项目用"等它死 + refresh 可秒撤"兜底，秒踢是 W9 的 token_version。
→ *"logout 接口的安全边界是什么？"* 它用 refresh 原文认证——所以 refresh 请求体的传输必须 HTTPS；同时它必须幂等且恒定 204，否则重复退出/不存在的票会返回不同状态码，响应本身成了存在性探针。我的测试钉了"不存在的票也 204"。
→ *"多设备登录呢？退出手机会影响电脑吗？"* 不会——每次 login 签一张独立票，revoke 只命中 body 里那张 hash。"退出所有设备"要按 user_id 批量 revoke（`UPDATE ... WHERE user_id=? AND revoked_at IS NULL`），这也是封禁用户的配套动作。我项目的表结构天然支持（user_id 有索引）。

### 4. opaque token vs JWT：凭证选型判据

**一句话定义**：opaque = 服务端查表才认识的随机串；JWT = 自包含、验签即认识的签名串。

**为什么存在**：两者是"状态放哪"的两种答案——opaque 把状态放服务端（可撤销、每次查库），JWT 把状态放令牌里（免查库、不可中途改）。

**怎么用**（本项目的分工）：access 用 JWT（每请求验签，不查库）；refresh 用 opaque（低频使用，查一次库换撤销能力）。

**底层机制**：`secrets.token_urlsafe(32)` → 32 字节 CSPRNG → base64url → 43 字符，无填充。**为什么是 secrets 不是 uuid4/random**：uuid4 有 122 位随机但格式固定；`random` 模块是 Mersenne Twister，**可预测**，绝不能用于凭证。选型判据一句话：**凭证需要不可预测性时用 `secrets`，需要唯一性时才用 uuid4**。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 用 `random` 生成凭证 | 可预测，token 可被猜 | 只用 `secrets` |
| 2 | JWT 当 refresh 且无 jti | 轮换后旧票仍验签通过 | refresh 用 opaque 或 JWT+黑名单 |
| 3 | 说"JWT 更安全" | 站队不给判据 | 判据：**需不需要中途作废**。需要 → 服务端状态（opaque）；不需要 → 自包含（JWT） |

**面试问法**：「你们的 token 是 JWT 还是 opaque？为什么？」
**30 秒版**：分开选的。access 用 JWT，因为每请求都要验，必须免查库；refresh 用 opaque 随机串，因为它是长期凭证，必须能随时作废，作废的前提是服务端认识它。所以判据不是哪个更安全，是这个凭证的使用频率和是否需要吊销——高频不需要吊销 → JWT；低频需要吊销 → opaque。

**追问链**：
→ *"JWT 无状态，那 exp 谁保证？"* 签发时写进 payload，验签时库函数比对当前时间。注意 exp 校验是**验签库做的**，不是业务代码——我项目 `create_access_token` 里 `exp = now + timedelta(minutes)`，过期 401 由依赖链抛出。
→ *"opaque 每次查库，性能怎么办？"* hash 上有唯一索引，点查 O(1)；高频场景加 Redis 缓存（代价：缓存失效时机要和 revoke 同步，否则撤销不生效）。我项目 refresh 是低频操作（7 天一次），没这个需求。
→ *"你的 refresh 为什么要 hash 落库而不存明文？"* 见知识点 5。

### 5. 凭证存储：sha256 hash 落库

**一句话定义**：库里只存 `sha256(raw)`，明文只在签发那一刻返回给客户端，之后谁也不保存。

**为什么存在**：库泄露时攻击者拿到的只有 hash——43 字符随机串（约 256 位熵）无法像密码那样跑字典，sha256 的速度劣势在 high-entropy 输入下不成立。

**怎么用**：
```python
raw = secrets.token_urlsafe(32)                # 明文只出现这一次
row = RefreshToken(token_hash=refresh_token_hash(raw), ...)   # 库里只有 sha256
# 比对：presented = refresh_token_hash(request.refresh_token) → 当查询键
```

**底层机制**：查询键用 hash 不用明文——`get_by_hash(sha256(来的票))`。**为什么密码用 bcrypt、票用 sha256**：密码是人类选的，熵低，必须用慢哈希（bcrypt/argon2，加盐+可调 cost）抵抗离线爆破；refresh 票是 CSPRNG 的 256 位熵，字典攻击在数学上不可行，快哈希反而省 CPU。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 明文落库"方便调试" | 库泄露=会话全泄露 | 只存 hash；调试用日志里的 raw（也尽量别打） |
| 2 | 列长度没算 | hash 超长被截断或迁移报错 | sha256 hex = 64 字符，`String(64)` |
| 3 | 忘记 unique 约束 | 同一张票存两行（几率极低但语义错） | `token_hash` UNIQUE |

**面试问法**：「refresh token 在数据库里怎么存？」
**30 秒版**：只存 sha256 hash，明文只在签发那一刻返回给客户端。比对时把请求里的票做同样的 hash 当查询键。为什么不用 bcrypt——密码是人类选的低熵输入要慢哈希防字典；refresh 是 256 位随机数，字典攻击数学上不可行，快哈希足够且省 CPU。我还加了唯一约束，保证一张票只有一行。

**追问链**：
→ *"sha256 会不会被彩虹表打？"* 输入是 256 位随机数，预计算空间 2^256，物理不可行。彩虹表只对低熵输入（密码、短 ID）有效——这也是密码必须 bcrypt 的原因。
→ *"数据库泄露，攻击者能做什么？"* 什么都做不了：没有 raw 换不出有效票，hash 是查询键不是凭证。对比明文存储：库泄露=全体用户会话被盗。
→ *"你的表为什么还要 user_id 索引？"* 两个查询路径：按 hash（续票/退出）和按 user（封禁时批量撤销、"退出所有设备"）。id 用自增 int 不用 UUID——判据是这个 id 会不会暴露给外部，refresh_tokens 是纯内部表。

### 6. 条件 UPDATE + rowcount：幂等的判据

**一句话定义**：`UPDATE ... WHERE ... AND revoked_at IS NULL`，用 rowcount 判断是否真的改到了行。

**为什么存在**：logout 必须幂等（重复退出不报错），而"票是否存在"不能靠先 SELECT 再 UPDATE——那是两步，中间有窗口。

**怎么用**（本项目）：
```python
def revoke_by_hash(self, token_hash: str) -> bool:
    row = self.session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return cast(CursorResult[Any], row).rowcount > 0
```

**底层机制**：单条 SQL 内完成"检查 + 写入"，没有应用层窗口。`revoked_at IS NULL` 条件让第二次 logout 匹配 0 行 → rowcount=0 → 幂等成立。**MySQL 语义**：rowcount 是**真正改动的行数**不是匹配行数——去掉 IS NULL 条件后重复 logout 会 rowcount=1（又写了一次新时间戳），幂等语义当场丢失。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 先 SELECT 查存在再 UPDATE | 并发下两步之间行被别人改掉 | 条件写进 WHERE，一条 SQL |
| 2 | rowcount 当"匹配行数"理解 | 幂等判断永远为真 | 记住 MySQL 返回改动数 |
| 3 | `session.execute()` 返回值直接 `.rowcount` | mypy：`Result` 没有该属性 | `cast(CursorResult[Any], row)` |

**面试问法**：「怎么保证 logout 接口幂等？」
**30 秒版**：作废用条件 UPDATE——WHERE 里带上 revoked_at IS NULL，一条 SQL 同时完成检查和写入。第一次退出 rowcount=1，重复退出匹配 0 行 rowcount=0，接口恒定返回 204 不报错。这里有个 MySQL 细节：rowcount 是真正改动的行数不是匹配行数，所以这个 IS NULL 条件不能省，省了幂等就丢了。

**追问链**：
→ *"为什么不先查一下票存不存在？"* 两步之间有窗口：并发下检查和写入之间行可能被别人改。条件 UPDATE 把两步合成一步，数据库行锁保证原子。这个"检查与写入之间有窗口"和 W9 的"一票换两票"是同一个病。
→ *"rowcount=0 时接口该返回什么？"* 恒定 204。返回 404 就泄漏了"这张票不存在"，等于给攻击者一个存在性探针。返回值 bool 留给将来的审计日志。
→ *"mypy 为什么报 Result 没有 rowcount？运行时明明有。"* 见踩坑实录 2——静态注解 `Result[Any]` 是父类，`rowcount` 在子类 `CursorResult` 上。cast 是显式背书"我比类型检查器知道得多"。

### 7. 滑动过期 vs 绝对上限

**一句话定义**：每次轮换 `expires_at = now + 7 天`——活跃用户永不重登，叫滑动过期；叠加"总寿命"封顶叫绝对上限。

**为什么存在**：滑动过期解决"活跃用户被无端踢出"；但纯滑动有个漏洞——**被盗会话可以无限续命**，只要攻击者每 6 天续一次票，就能永远挂着。

**怎么用**（本项目现状）：只有滑动。`rotate(..., datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days))`，天数进 `config.refresh_token_expire_days` 不硬编码。

**底层机制**：expires_at 每次续票重写 → 语义是"**连续 7 天没用才失效**"，不是"登录后 7 天必重登"。绝对上限的实现：RefreshToken 加 `session_started_at`（首轮签发时写入、轮换时复制），续票时检查 `now - session_started_at > 72h` → 强制重登。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 硬编码 `timedelta(days=7)` | 改配置要动代码 | 进 settings |
| 2 | 只做滑动不做上限 | 被盗会话无限续命 | 叠加绝对上限（W9+） |
| 3 | 轮换时不重写 expires_at | 票越用越接近死亡，活跃用户被踢 | 每次轮换 `now + 7d` |

**面试问法**：「你们的登录态多久过期？为什么不直接 7 天有效？」
**30 秒版**：refresh 是滑动过期——每次续票重算 7 天，语义是连续 7 天不用才失效，活跃用户永不重登。但纯滑动有被盗会话无限续命的问题，所以生产要叠一个绝对上限，比如总寿命 72 小时强制重登。我的项目目前只有滑动，上限记为已知取舍。

**追问链**：
→ *"滑动过期和 Session 的 idle timeout 是不是一回事？"* 机制同源（空闲重置），差别在介质：Session 的超时在服务端内存/Redis，refresh 的在数据库行。也因此 refresh 轮换会**留痕**（revoked 行），Session 销毁即无痕——审计需求选 refresh 这类有痕设计。
→ *"轮换留下的旧行怎么办？"* 表只增不减，需要清理任务（按 expires_at 删 revoked 行）。这也是"为什么选轮换要付的存储代价"，面试说出来比背概念加分。
→ *"access 和 refresh 的过期时间怎么配比？"* access 分钟级（15–60min，暴露窗口），refresh 天级（7–30d，体验）。配比原则：access 的暴露窗口 ≤ 业务可接受的"被踢后损失"，refresh 覆盖典型会话周期。

### 8. naive/aware datetime：存储层剥时区

**一句话定义**：MySQL DATETIME 不存时区——写进去的 aware 值被剥掉 tzinfo，读回来一律是 naive。

**为什么存在**：SQLAlchemy 的 `DateTime(timezone=True)` 只是**声明愿望**；MySQL 的 DATETIME 类型物理上没有时区字段。于是 aware 的 `datetime.now(UTC)` 存进去、naive 地读出来，再和 aware 的 `now(UTC)` 比较 → `TypeError: can't compare offset-naive and offset-aware` → HTTP 500。

**怎么用**（本项目 `auth_service.refresh`）：
```python
# MySQL DATETIME 不存时区，读回来是 naive；写入时一律按 UTC 存，
# 所以这里把它当作 UTC 补上时区标记，再和 aware 的 now 比。
expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
if expires_at <= datetime.now(UTC):
    raise UnauthorizedError("用户凭证无效")
```
测试侧同样需要 `_as_utc` 归一 helper（SQLite 读回来同样 naive）。

**底层机制**：完整因果链——aware 值入库 → MySQL 剥掉 tzinfo 存裸数字 → 读回 naive → 与 `datetime.now(UTC)`（aware）比较 → Python 拒绝比较两种类型 → 未捕获 TypeError → FastAPI 500。**症状在比较行，病因在存储层，隔着一整条链路。** 约定解法：写入一律 UTC、读回一律补 UTC，全项目一个约定。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 以为 `timezone=True` 就有 时区 | 上线后偶发 500 | 它只是 SQLAlchemy 的愿望，看存储引擎 |
| 2 | 在比较行 try/except 打补丁 | 病因还在，换个路径又炸 | 在读回边界统一归一 |
| 3 | 三列 datetime 漏 `timezone=True` | PostgreSQL 上行为悄悄改变 | 列声明、读回归一双保险 |
| 4 | 测试里直接比读回值 | 测到的是"类型不匹配"不是"时间对不对" | 测试断言先 `_as_utc` 归一 |

**面试问法**：「遇到过时区相关的 bug 吗？」
**30 秒版**：遇到过。票过期判断那行抛 TypeError 500——逻辑看着全对。根因是 MySQL DATETIME 物理上不存时区，SQLAlchemy 写的 timezone=True 只是声明；aware 值入库被剥成 naive，读回来跟 aware 的 now 一比就炸。修法不是在比较行打补丁，而是全项目一个约定：写入一律 UTC，读回一律补 UTC。教训是症状和病因隔着一条链路，得顺着数据流找。

**追问链**：
→ *"为什么不用 UTC timestamp（bigint）存？"* 可以且更省心（无时区歧义、比较天然正确），代价是数据库里不可读、DBA 排查要换算。DATETIME + "一律 UTC" 的约定是折中。换成 PostgreSQL 的 `timestamptz` 则两头都不用管。
→ *"这个 bug 为什么测试没拦住？"* 测试的 SQLite 读回同样 naive，同样的 TypeError 会在测试里炸——**它拦住了**，炸的位置是我在教材示例里没归一时（真实经历：交付物 4 第一次跑 /refresh 就 500）。教训是类型不匹配的 bug 从不"偶尔出现"，只要路径覆盖到必炸。
→ *"Python 3.11 的 now() 精度问题你踩过吗？"* 踩过：3.11 下 `datetime.now()` 精度 15.6ms（Windows），`time.time` 同粒度——这就是 D2 总结里"短请求耗时全是同一个值"的原因，计时用 `perf_counter`。时间相关结论必须在实际版本上复测，不能凭记忆。

---

## 三、30 秒答案集

1. **为什么双 token**：access 短命管高频验证（无状态），refresh 长命管身份（可撤销）；实测 EXPIRE=1 分钟时 65 秒就被踢，这就是不做 refresh 的日常。
2. **轮换**：每次续票作废旧票发新票，refresh 变一次性——偷票者一用就 401，且 401 本身就是警报。
3. **轮换原子性**：作废和签发同一事务一次 commit；拆开会出现"旧票死了新票没生出来"。
4. **access 不入库**：入库=每请求查库=放弃无状态；代价是 exp 前收不回，用短命压暴露窗口。
5. **logout 只管 refresh**：无状态没有吊销名单；已发 access 等它死，秒踢上 token_version。
6. **logout 不挂鉴权**：凭证过期也要能退（可用性）；refresh 原文即持有证明；被封用户不能永远退不了。
7. **204 vs 200**：204=成功且无内容可说；实测 204 下返回 body 被静默丢弃、前端 json() 炸——"无 body"要自己守。
8. **hash 落库**：sha256 当查询键，明文只回签发那一刻；256 位熵让彩虹表物理不可行，不用 bcrypt。
9. **幂等实现**：条件 UPDATE 带 `revoked_at IS NULL`，rowcount 判真改没改；MySQL rowcount 是改动数不是匹配数。
10. **滑动过期**：每次续票重算 7 天=连续 7 天不用才失效；被盗会话可无限续命，生产叠绝对上限。
11. **timezone=True**：只是 SQLAlchemy 的愿望；MySQL DATETIME 物理无时区，读回必 naive，约定"写 UTC 读补 UTC"。
12. **一票换两票**：并发续票两张新票各自合法，唯一索引拦不住；解法是条件 UPDATE 抢占（W9 债）。

## 四、白板手写靶

### 靶 1 · 四步拒绝链（`refresh` 的骨架）

```python
def refresh(self, data: RefreshIn) -> tuple[str, str]:
    presented = refresh_token_hash(data.refresh_token)
    row = self._refresh_repo.get_by_hash(presented)
    if row is None:                                raise UnauthorizedError("用户凭证无效")
    if row.revoked_at is not None:                 raise UnauthorizedError("用户凭证无效")
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):            raise UnauthorizedError("用户凭证无效")
    user = self._repo.get(row.user_id)
    if user is None or user["is_banned"]:          raise UnauthorizedError("用户凭证无效")
    new_raw = generate_refresh_token()
    self._refresh_repo.rotate(row, refresh_token_hash(new_raw), datetime.now(UTC) + timedelta(days=7))
    self._commit()
    return create_access_token(str(user["id"])), new_raw
```
要点：四种拒绝**同一个错误信息**（防响应体探测）；归一在比较前。

### 靶 2 · 同事务轮换（`rotate`）

```python
def rotate(self, old: RefreshToken, new_hash: str, expires_at: datetime) -> None:
    old.revoked_at = datetime.now(UTC)
    self.session.add(RefreshToken(user_id=old.user_id, token_hash=new_hash, expires_at=expires_at))
```
要点：只 add 不 commit——commit 是 service 的事，事务边界在公开方法收口。

### 靶 3 · 条件 UPDATE 幂等作废（`revoke_by_hash`）

```python
def revoke_by_hash(self, token_hash: str) -> bool:
    row = self.session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return cast(CursorResult[Any], row).rowcount > 0
```
要点：`IS NULL` 条件不能省（MySQL rowcount=改动数）；cast 过 mypy。

## 五、踩坑实录

| 坑 | 现象 | 教训 |
|---|---|---|
| naive vs aware | `/auth/refresh` 一打就 500，`can't compare offset-naive and offset-aware` | 症状在比较行、病因在存储层；`timezone=True` 只是愿望 |
| mypy `Result.rowcount` | 逻辑对、跑得对，mypy 红两条：`Result has no attribute rowcount` | 静态注解是父类 `Result`，rowcount 在子类 `CursorResult`；cast 是显式背书 |
| 函数体内 import | `from sqlalchemy import CursorResult` 写进了函数体 | 函数内 import 是循环依赖逃生舱，不是顺手补 import 的地方 |
| bash 续行符进 PowerShell | `\` 结尾的 git add 被 PS 当参数，报 `Unable to create process using python.exe` | PS 续行是反引号；交互终端一条一行最稳 |
| `list[str]` 弱契约 | login 返回两个 token 用 list，调用方靠下标猜 | 两值返回用 `tuple[str, str]`，解包名字即文档 |

## 六、可以讲成故事的三段

**1. 一分钟的痛点实验**
背景：教材讲"access 要短命"，但为什么短命只是文字。→ 我以为把过期调到 1 分钟就能"看到"问题。→ 实际看到的是比预期更具体的东西：登录后干等 65 秒，401「用户凭证已过期」——**用户什么都没做错**。→ 教训：面试答"为什么需要 refresh token"要给数字（日活 1000 × 每会话 50 请求 ≈ 每天 10 万次无故被踢），不给形容词。

**2. 全绿之后的 500**
背景：轮换逻辑写完，门禁绿、探针对得上。→ 我以为接下来就是接路由收工。→ 实际一打 `/auth/refresh` 就 500：`can't compare offset-naive and offset-aware`——比较那行看着完全正确，病因在两层之外的存储层（MySQL 剥时区）。→ 教训：类型不匹配的 bug 不看逻辑对不对，要看数据的完整旅程；症状和病因隔几层，就得顺着数据流走几层。

**3. 运行时对、类型系统不认**
背景：`session.execute(update(...))` 后取 `.rowcount`，实测 1/0 全对。→ 我以为逻辑对 mypy 就该过。→ 实际 mypy 红两条：SQLAlchemy 把返回注解写成父类 `Result`，`rowcount` 只在子类 `CursorResult` 上——**类型检查器只看注解，看不到运行时真相**。→ 教训：`cast` 不是消音器，是"我比静态检查知道得多"的显式背书；写错类型它不救你。

## 七、能力画像与下日衔接

**强项 2**：
- 四步拒绝链纸笔全对（照片判：链序、同错误信息、同事务轮换全中），轮换核心题判断"每次换票都刷新 refresh 时间"✅
- 判断题核心命中率高：204 语义 / logout 可用性理由一次到位；门禁自驱（ mutation 验证后主动复绿才提交）

**待补 2**：
- 判断题的**第二层**：logout 不挂鉴权的"安全侧"理由（票本身即证明、封禁用户退不了）和 204 的"统一外壳漏口"没展开——说出第一层就停是二面止步的典型形状
- 巡检靶 2/3 栽在**异常→响应的最后一段**：以为"被 ExceptionMiddleware 包装过=统一了"，实际 404 是 `{"detail":...}`、500 是纯文本——重画洋葱图时必须标出三种响应形状

**下日预告（D5 · 注入式验收 + 债⑤）**：
- 会撞的坑 1：注入测试要求**先全红再修绿**——最容易出现"顺手把漏洞修了再跑注入"，那时全绿毫无意义（修好的≠测过的）
- 会撞的坑 2：横向越权探针（A 的 token 打 B 的 doc）要和 D3 的 `get_or_403` 缺口对齐——走读日已发现 `get_doc` 的路径参数 `kb_id` 未参与校验，D5 正好钉死它
- 会撞的坑 3：refresh 并发窗口（一票换两票）是 W9 债③，D5 若顺手测并发轮换会红——红是**已知债**不是新 bug，记录别慌
