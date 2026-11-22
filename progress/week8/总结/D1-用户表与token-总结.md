# W8-D1 总结 · 用户表、token、唯一约束与"验证的有效性"

> 本日资产：users 表落库（迁移 `397b8b767d9c`）+ UserRepository/UserRow + 债① IntegrityError→409 + 3 个新测试文件（test_integrity_409 / test_user_repo / check_users_table 探针）
> 环境：MySQL 8.4.0@3307（kb_dev）/ Python 3.11 / SQLAlchemy 2.0 / Windows PowerShell
> 门禁：89 passed, 2 skipped / 覆盖率 96.38%（精确浮点）/ ruff / mypy strict 全绿
> 第四档：今日无设计埋坑（债①由 AI 代写）——但出现**真事故**（双 handler）替代了埋坑环节，见第五节

## 一、知识地图（按面试出场率降序）

| # | 知识点 | 出场率 | 掌握要求 | 本日证据 |
|---|---|---|---|---|
| 1 | JWT 验签"三验三不验" | ★★★★★ | **能分开说"签名证明什么/不证明什么"，且能答"为什么验不了本人"** | 合书三问 Q1 判 4 档 + 探针读数 `(1062,...)` |
| 2 | 唯一约束 vs 先查后插+锁 | ★★★★★ | **能说清"锁方案防得住也不用"的完整判据**（行为挂隐式配置=静默失效） | 间隙锁探针：RR 3.1s 超时防得住 / RC 125ms 穿透 |
| 3 | 变异验证与测试有效性 | ★★★★★ | **能讲"测试过了≠测的是你以为的东西"的真实案例** | 双 handler 事故：变异不响→文案差两字→定位 |
| 4 | 迁移四步工序与人工审 | ★★★★☆ | **能默写四步且每步说"防什么"** | `397b8b767d9c` 人工审五项全过 |
| 5 | `default=` vs `server_default=` | ★★★☆☆ | **能说清谁进 DDL、谁不进、各自代价** | 迁移里 users 表无 DEFAULT 子句（正确） |
| 6 | 快照最小化（UserRow） | ★★★☆☆ | **能说清敏感列为什么不出快照、用"两端"表述** | test_user_repo：`"password_hash" not in row` |

## 二、逐个知识点讲透

### 1. JWT 验签：三验三不验

**一句话定义**：JWT 是服务器签名过的自描述凭据，验签只能证明"票是真的、没被改、没过期"。

**为什么存在**：HTTP 无状态，两种记忆方案——Session（服务器存，内存/存储代价+分布式粘性）vs Token（客户端带证明，服务器零存储）。签名用 `HMAC-SHA256(header.payload, secret)`：改一个字签名就崩，没有 secret 造不出新签名。

**怎么用**（项目实物）：

```python
# kb-service/src/kb_service/core/security.py（71 行，W3 就写好，D3 才有第一个调用方）
def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)  # 60
    return jwt.encode({"sub": subject, "iat": ..., "exp": expire}, key, algorithm="HS256")
```

**底层机制**：三段结构 `header.payload.signature`，前两段是 Base64（**不是加密**，任何人可读出 `sub/iat/exp`）；第三段是对前两段的 HMAC。服务器验证 = 重算 HMAC 比对 + 检查 `exp`。签名把"票"绑定到"签发者"，**不绑定持票的手**——票被偷了服务器无法区分你和小偷。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 把 Base64 当加密 | "token 里存了敏感信息也没事" | payload 明文可读，只放必要声明 |
| 2 | 验签通过就放行 | 被封禁/已删号用户拿着旧票继续用 | 验签后还要查库（D4 `get_current_user`） |
| 3 | 认为 JWT 可注销 | "下线时删掉 token" | 服务器没存它，没法删；只能等 exp 或加撤销表（D5） |
| 4 | 把 exp 校验当"验证本人" | "exp 没过所以是本人" | exp 只证明票在有效期内，不证明持有人 |

**面试问法**："JWT 为什么要签名？签名能防住什么、防不住什么？"
**30 秒版**："签名防的是伪造和篡改——没 secret 造不出合法票，改一个字签名就崩。但它防不了'票被偷'：签名只绑定票不绑定持票的手。所以登录态的完整性还需要服务端查用户是否存在、是否被封禁——这就是我们项目 D4 把 `get_current_user_id` 升级成查库的 `get_current_user` 的原因。"

**追问链**：
→ *"为什么不把用户信息全塞进 token，每次就不用查库了？"* 可以，代价是"吊销不可能"——票在有效期内永远有效。塞进去的信息越丰富，这扇窗越危险。
→ *"用户被封禁但 token 没过期，中间这 59 分钟怎么办？"* 两种：接受窗口（短 exp + refresh 轮换，我们 D5 的方案）或每请求查库（贵）。生产常见折中：关键操作查库，普通请求信 token。
→ *"流量涨十倍，每请求查库会成为瓶颈吗？"* 会。落地方案：用户状态加 Redis 缓存（TTL 秒级）或本地缓存 + 封禁时主动失效；这也是"互补方向"里可观测/成本控制的一部分。

### 2. 唯一约束 vs 先查后插+锁

**一句话定义**：防重复 email 的两路方案——唯一约束是存储引擎原子判定的**声明式**方案；先查后插是应用层两步的**过程式**方案，有竞态窗。

**为什么存在**：裸的"先 SELECT 再 INSERT"在检查和写入之间有时间窗，并发下两个请求都查空、都插入成功。唯一约束把判定下沉到存储引擎：插入那一刻原子判定，第二个 INSERT 直接报错。

**怎么用**（本项目）：

```python
__table_args__ = (UniqueConstraint("email", name="uq_user_email"),)  # 显式命名
```

**底层机制**（今天实测裁决，不是背的）：MySQL 里唯一约束的物理形态就是**唯一索引**（`SHOW INDEX` 可见，`alembic check` 把它报成 `removed index`）。`SELECT ... FOR UPDATE` 查不到行时，**RR 隔离级别**下会在该值应在的**缝隙**上加间隙锁，堵住"往缝里插"这条路；**RC 没有间隙锁**，查不到=锁不到任何东西。今天探针读数：RR 下 B 插入阻塞 3.1s → lock wait timeout（防得住）；RC 下 125ms 插入成功（防不住）。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 说"悲观锁只锁读到的行" | 判"FOR UPDATE 防不住重复"（RC 世界对，RR 世界错） | 结论带范围：RR 有间隙锁，RC 没有 |
| 2 | 认为"能防住就用锁方案" | 行为挂在隔离级别这个隐式配置上 | 防得住也不用的判据：声明式不依赖隐式配置 |
| 3 | 约束不显式命名 | downgrade 的 `drop_constraint` 引用名对不上 | `name="uq_user_email"`，与 `uq_kb_owner_name` 同风格 |
| 4 | 把 IntegrityError 全译成 409 | FK 违反也被当"输入冲突" | 看 `exc.orig` 原话缩小范围（duplicate/unique） |

**面试问法**："防止重复注册，为什么不用事务+锁，而要唯一约束？"
**30 秒版**："锁方案在 RR 下靠间隙锁其实防得住，但它防住的姿势依赖隔离级别这个隐式配置——换库、换配置就静默变样，而且 email 没索引时锁范围失控。唯一约束是声明式的：存储引擎原子保证，不依赖任何隐式配置，也不依赖每个写路径都记得走锁。所以防得住也不用。"

**追问链**：
→ *"你的项目里这个约束真的拦住过东西吗？"* 拦过：探针实测 `(1062, "Duplicate entry 'probe@test.dev' for key 'users.uq_user_email'")`，且 test_integrity_409 里同名建库第二次就是它拦的。
→ *"约束冲突现在返回什么？为什么不是 500？"* 409 Conflict——"email 已存在"是客户端输入冲突不是服务器故障。实现：exception_handler 读 `exc.orig`，MySQL 说 `Duplicate entry`、sqlite 说 `UNIQUE constraint failed`，两种方言都认，其余交回 500。
→ *"如果业务要求'同 email 同活动'才能算重复，唯一约束还能用吗？"* 不能单列了——建复合唯一约束 `(email, activity_id)`，或用应用层判重+约束兜底；判据是"冲突的语义"决定约束的形状。

### 3. 变异验证与测试有效性

**一句话定义**：改完验证代码后，故意破坏它一次，确认"测试红"的能力真的存在。

**为什么存在**：测试从 2 passed 到 2 passed，你无法区分"验证逻辑在保护我"和"验证逻辑是死代码但响应来自别处"。变异是唯一能把这两者分开的动作。

**怎么用**（今天真实案例）：债①写完后做变异——把 `if` 判断改成恒真 `raise exc`（翻译失效）→ 跑测试。**预期红，实际 2 passed**——变异不响，说明有问题。探针读数揭底：响应文案是「资源已存在**或**字段冲突」，而我写的 handler 文案是「资源已存在或**唯一**字段冲突」——差两个字 = 响应来自另一个 handler。文件里被叠加写入了两个重复的 `@app.exception_handler(IntegrityError)`，Starlette 后注册的覆盖先注册的，测试一直打的是第二个（正确的），第一个（被变异的）是死代码。

**底层机制**：Starlette 的 exception handler 按异常类型注册进字典，同类型重复注册后者覆盖前者——不报错、不警告，静默覆盖（失效三档里最阴的"静默"）。变异探测的本质：给"验证在生效"这条命题制造一个能推翻它的实验。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 跳过变异验证（"看着像好了"） | 死代码 handler 零症状永驻 | 交付前必做一次故意破坏 |
| 2 | 变异不响时怀疑测试写错 | 白改测试 | 先怀疑**执行路径**：红不到的代码可能根本没被执行 |
| 3 | 用响应判断"谁在干活"只看状态码 | 409==409 看不出来源 | 文案/trace 是识别执行路径的指纹 |
| 4 | 文件级工具改动后不 grep | 双 import、双 handler 叠加 | 改完 `grep 目标符号` 应恰好一次 |

**面试问法**："你怎么保证一个测试真的在测你想测的东西？"
**30 秒版**："做变异：把被测逻辑故意改坏一次，看测试红不红。我实际踩过一例——测试一直绿，变异却没红，最后发现文件里有重复注册的异常处理器，测试打的根本不是被变异的那个。所以我的标准变成：绿只能证明'有代码在正确响应'，变异才能证明'我改的那段在被响应'。"

**追问链**：
→ *"变异破坏应该改哪一层？"* 改**被验证的逻辑本身**（那个 if），不改测试——改测试只能证明测试会红，证明不了它红在正确的位置。
→ *"什么情况变异响了但代码还是有问题？"* 测试和实现共享同一个错误假设（比如都把 FK 违反当 409）——变异只对"独立于实现的期望"有效，所以期望必须来自规格不是来自实现。
→ *"CI 里怎么系统化？"* 真正的 mutation testing（mutmut/cosmic-ray）按存活变异体计分；个人项目退而求其次，每个关键防线配一条手工变异，成本 2 分钟。

### 4. 迁移四步工序

**一句话定义**：`autogenerate → 人工审 → upgrade head → check+current`，四步一步不省，审的是习惯。

**为什么存在**：autogenerate 只保证"生成的 op 反映模型与库的 diff"，不保证 op 顺序可执行、不保证没混入历史漂移、不保证 downgrade 对称。W7 两天三雷（1101 / 1553 / 半途状态）全是跳过"审"的代价。

**怎么用**：

```powershell
& .\.venv\Scripts\alembic.exe revision --autogenerate -m "add users table"
# 人工审：op 干净度 / 列对齐 / 命名 / down_revision / downgrade 对称
& .\.venv\Scripts\alembic.exe upgrade head
& .\.venv\Scripts\alembic.exe check    # 模型与库无漂移
& .\.venv\Scripts\alembic.exe current  # 版本真的前进了（397b8b767d9c (head)）
```

**底层机制**：DDL 隐式提交——迁移失败会留下"库结构 ≠ alembic_version"的半途状态，所以第 ④ 步的 `current` 是"版本前进"的**观察证据**（check 只证无漂移，不证 head 到位）；MySQL 的 DDL 不可回滚，downgrade 是手写的逆操作，写错顺序就是 1553（FK 索引先拆后建）。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 生成完直接 upgrade | 1101/1553/漂移混入 | 审两个函数，多出来的 op 搞清楚再执行 |
| 2 | 只跑 check 不跑 current | "以为升级了其实没升" | current 是版本前进的唯一观察证据 |
| 3 | 变异时不知道改什么 | 变异流于形式 | 注释掉 UniqueConstraint → check 必须红报 removed index |
| 4 | `default=` 期待进 DDL | 原生 SQL 插入撞 NOT NULL | default 是 Python 侧；要 DB 侧用 server_default |

**面试问法**："为什么不用 create_all？autogenerate 生成完直接跑不行吗？"
**30 秒版**："create_all 只能建不存在的表，做不了演进和回退。autogenerate 的 op 我必审——我们项目真实踩过 1101（TEXT 不许 DEFAULT）和 1553（FK 索引先拆后建）。审完 upgrade 后还要 current 确认版本前进，因为 DDL 隐式提交，失败会留下半途状态。"

**追问链**：
→ *"审的时候具体看什么？"* 五项：op 干净度（只该有本次的 op）/ 列与模型对齐 / 约束显式命名 / down_revision 接对 head / downgrade 对称可逆。
→ *"迁移失败怎么办？"* 先 `alembic current` 判断半途状态——结构变了版本没走就手工还原结构，版本走了结构没变就重跑；不许闭眼重跑 upgrade。
→ *"多人协作迁移冲突怎么办？"* down_revision 成树要 merge；团队规范：迁移文件一旦合入主干不改只加。个人项目提前养成"只加不改"的习惯。

### 5. `default=` vs `server_default=`

**一句话定义**：`default=` 是 Python 侧默认值（ORM 插入时填，不进 DDL）；`server_default=` 是数据库侧默认值（进 DDL，任何写入路径都生效）。

**为什么存在**：两种默认值的**生效半径**不同——ORM 路径 / 所有路径。今天的迁移文件里 users 表没有 DEFAULT 子句，但模型有 `default="member"`——这是**正确的**（模型怎么写 autogenerate 就怎么生成），代价是原生 SQL 绕过 ORM 插入会撞 NOT NULL。

**怎么用**（项目实物）：

```python
role: Mapped[str] = mapped_column(String(20), default="member")          # Python 侧
id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)  # 应用层生成主键
```

**底层机制**：`default=uuid4` 让主键在 Python 侧生成——这是 `create()` 里 flush 后能直接 `to_row()` 拿到 id 的前提；若改成 DB 侧生成（如 `gen_random_uuid()`），flush 后要 refresh 才能拿到。W7 的 1101 雷（TEXT 不许 DEFAULT）踩的就是 `server_default` 进 DDL 被 MySQL 拒绝。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 以为 default 会写进 DDL | 原生 SQL 撞 NOT NULL | 看迁移文件实况：没有 DEFAULT 子句=Python 侧 |
| 2 | 主键交给 DB 生成 | flush 后 id 是 None | 应用层 uuid4，flush 即可得 |
| 3 | NOT NULL 列忘设 default | 少传字段就 IntegrityError | role/is_banned 都有 default="member"/False |

**面试问法**："ORM 的 default 和数据库的 default 有什么区别？"
**30 秒版**："default 是 Python 侧，只有走 ORM 的插入才填；server_default 会进 DDL，任何写入路径都生效。我们项目 role/is_banned 用 Python 侧 default——代价是绕过 ORM 的写入会撞 NOT NULL，收益是主键也能在应用层生成，flush 后直接拿 id 不用 refresh。"

**追问链**：
→ *"什么时候必须用 server_default？"* 有非 ORM 写入路径（DBA 手工补数据、ETL）或做 NOT NULL 列的存量改造（加列必须给 server_default 否则已有行炸）。
→ *"加列时怎么避免锁表？"* MySQL 8 支持 INSTANT ADD COLUMN（须带 server_default）；这也是"加列带默认值"成为规范的技术根源。
→ *"你们项目的 created_at 为什么不用 server_default=now()？"* 统一时区语义：Python 侧 `datetime.now(UTC)` 明确 UTC，DB 的 now() 取决于会话时区——时间语义要一个权威来源。

### 6. 快照最小化（UserRow）

**一句话定义**：repo 层返回 TypedDict 快照而非 ORM 活对象，且快照字段=上层用得到的**最小集合**。

**为什么存在**：活对象改了会"以为落库了"；快照字段一多，敏感字段迟早被带进返回体。UserRow 刻意不含 `password_hash`（敏感列不出快照）和 `updated_at`（D4 用不到就不带）。

**怎么用**：

```python
def to_row(self) -> UserRow:
    return UserRow(id=self.id, email=self.email, role=self.role,
                   is_banned=self.is_banned, created_at=self.created_at)
# 测试锁死契约：assert "password_hash" not in row
```

**底层机制**：`create(email, password_hash)` 的参数名是"防明文塞进去"的闸，`to_row()` 的字段清单是"防明文带出来"的闸——同一件事的两端。名字和快照都是**类型系统层面的防线**，不靠 review 人眼。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 参数名叫 `password` | 调用方传明文进来 | `password_hash`，名字即契约 |
| 2 | 快照图省事 `model_validate(obj)` 全量转 | password_hash 进 API 返回体 | 显式字段清单 |
| 3 | 快照含活对象引用 | 改快照字段"以为改了库" | TypedDict 纯数据 |

**面试问法**："为什么 repo 层返回 TypedDict 不返回 ORM 对象？"
**30 秒版**："两个原因：活对象脱离 session 后改属性不落库，容易产生'以为改了'的假象；快照的字段清单是显式的，敏感列（password_hash）物理上进不了返回体。我们还有一条测试专门锁这个契约。"

**追问链**：
→ *"序列化时字段不够用怎么办？"* 加字段是局部改动（to_row + UserRow 同步加），比"先全量再删敏感字段"安全——默认拒绝优于默认开放。
→ *"性能上快照会多拷贝吗？"* 一次请求几个字段的对象级拷贝可忽略；真正该担心的是 N+1 查询，那是另一个问题。

## 三、30 秒答案集

1. **验签证明什么**：票是真的、没被改、没过期。不证明：用户存在、有权限、持票的是本人。
2. **为什么不验本人**：签名只绑定票不绑持票的手——票被偷了服务器无法区分。所以要查库（D4）。
3. **唯一约束 vs 锁**：锁方案 RR 下靠间隙锁防得住，但行为挂隐式配置=静默失效；唯一约束声明式、引擎原子保证。防得住也不用。
4. **间隙锁是什么**：RR 下 `FOR UPDATE` 查不到行时锁住"该值应在的缝隙"；RC 没有它，所以 RC 防不住重复。
5. **迁移为什么人工审**：autogenerate 只保证 diff 对，不保证顺序可执行、没混漂移、downgrade 对称——1101/1553 都是没审的代价。
6. **check 和 current 的分工**：check 证"模型与库无漂移"，current 证"版本真的前进了"——后者才是观察证据。
7. **default vs server_default**：前者 Python 侧只有 ORM 路径生效；后者进 DDL 所有路径生效。生效半径不同。
8. **为什么 repo 只 flush 不 commit**：一次请求多个写点要同生共死，commit 时机只有 service 层看得见。
9. **快照为什么不含 password_hash**：名字防塞明文进去（参数名），快照防带明文出来（字段清单）——类型系统层面的防线。
10. **变异验证是什么**：改坏被测逻辑一次看测试红不红；绿证明"有代码在正确响应"，变异才证明"我改的那段在被响应"。
11. **409 vs 500**：约束冲突是客户端输入冲突（409），服务器故障才是 500；判断依据是 `exc.orig` 的方言话术。
12. **Base64 是加密吗**：不是，payload 任何人可读——所以 token 里只放 sub/exp 这类非敏感声明。

## 四、白板手写靶

```sql
CREATE TABLE users (
    id            CHAR(36)     NOT NULL,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    role          VARCHAR(20)  NOT NULL,
    is_banned     BOOLEAN      NOT NULL,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_email UNIQUE (email)
);
```
要点：约束**显式命名**——回滚要引用它。

```
迁移四步：① autogenerate（只生成不执行）→ ② 人工审两函数（防 1101/1553/漂移）
        → ③ upgrade head（DDL 隐式提交，失败留半途状态）→ ④ check + current
```
要点：④ 的 current 是"版本前进"的唯一观察证据。

```python
pre, cur = None, head
while cur:
    tmp = cur.next   # ① 先存——不存就断了
    cur.next = pre   # ② 翻
    pre = cur        # ③ 前移
    cur = tmp
return pre           # cur 停在 None，新头是 pre
```
要点：三步顺序不能错；循环结束时返回 pre 不是 cur。

## 五、踩坑实录

| 坑 | 现象 | 教训 |
|---|---|---|
| Edit 叠加写入 → 双 handler | 变异（恒真 raise）下测试仍绿——测试打的是后注册的第二个 handler | 变异不响先怀疑执行路径，别急着改测试；改完文件 grep 目标符号应恰好一次 |
| 双 import 叠加 | `from sqlalchemy.exc import IntegrityError` 出现两行，ruff 才暴露 | 同上，同一事故的另一半 |
| 新代码无测试 → 覆盖率 94.08% 破线 | 门禁精确浮点比较真拦住了（旧四舍五入版本拦不住） | 96.38% 不是越高越好，是"每行新增都有归宿" |
| 变异验证差点被跳过 | 若跳过，恒真 raise 死代码 handler 零症状永驻 | 变异不是仪式，是唯一能区分"验证在保护我"和"响应来自别处"的动作 |
| 异常名手写成 Imtegrity | 探针读数 `(1062, ...)` 才想起是 Integrity（完整性） | 白板上写错不扣分但尴尬——1062 在 MySQL 层抛，Python 层接住的是翻译后的 IntegrityError |

## 六、可以讲成故事的三段

**① 变异不响的那次**
背景：债①写完，handler+测试全绿，按规矩做变异验证。→ 我以为：变异后测试必红，红绿闭环只是走个形式。→ 实际：恒真 `raise exc` 下测试**依然 2 passed**。深挖发现文件里有两个重复注册的 handler，测试打的一直是后注册的那个——被变异的是死代码。→ 教训：**绿只能证明"有代码在正确响应"，变异才能证明"我改的那段在被响应"**——而识别指纹是响应文案差的那两个字。

**② 分歧上探针**
背景：合书三问我答"先查后插 + FOR UPDATE 防不住重复 email"，教材答案说"能防住但代价大"。→ 我以为：分歧该由谁"权威"裁定。→ 实际：上探针实测——RR 下 B 插入阻塞 3.1s 超时（防得住），RC 下 125ms 穿透（防不住）。**我和教材各对一半**：我的直觉是 RC 世界的真实行为，缺的是"间隙锁"这块。→ 教训：**结论不带隔离级别限定词，就等于没说结论**；分歧不口头裁定，跑一遍就有裁决。

**③ 门禁第一次真拦我**
背景：W7 把覆盖率门禁从"四舍五入假绿"修成精确浮点比较。→ 我以为：门禁改造是防御性工程，可能永远用不上。→ 实际：D1 新增 UserRepo 没配测试，覆盖率掉到 94.08%，门禁当场红——旧版（94.75→95 不触发）对这个场景根本拦不住。→ 教训：**你修的每一个假绿，都是未来某天的真拦截**——验证体系的投资回报不在当下。

## 七、能力画像与下日衔接

**强项（带证据）**：
1. 验签三验三不验的边界感——合书 Q1 判 4 档，且能答出书上没写的"票被偷=持有即身份"（4 档标准：能教别人）。
2. 方法论内化——变异验证、探针裁决、判据来自数据这套动作已经不需要提醒（双 handler 事故是变异验证自己抓出来的）。

**待补（具体到哪句）**：
1. "间隙锁锁的是缝隙"能背，但**"为什么 RR 需要它而 RC 不需要"**（RR 要解决不可重复读所以读也要堵）这一层说不透——下次复习时先答这题。
2. `IntegrityError` 的判断只认了 duplicate/unique 两个词——**FK 违反、CHECK 违反**分别长什么样没实测过，D2 注册撞 UNIQUE 之外的其他约束时补。

**下日预告（D2，坑预告不预告内容）**：
1. 注册接口会撞**"验证 email 格式"的 schema 层 vs "email 已存在"的业务层**——两层错误码别混（422 vs 409），先想清楚哪层负责什么。
2. `verify_password` 首次真实调用，**bcrypt 校验失败和用户不存在要返回同一个错误**——不然注册接口会变成"email 枚举探测器"。
3. 删 `dev/token` 时会撞**测试依赖**——conftest 的 `auth_headers` fixture 用的是真签 token，删端点前先想测试拿什么。
