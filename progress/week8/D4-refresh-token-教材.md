# W8-D4 教材 · Refresh Token（双 token 模型）

> 日期：2026-11-25（按实际进度，周计划里的 D4 顺延到今天）
> 前置：D2（注册登录 / bcrypt / JWT 三验）、D3（验人查库 / 401-403 / 依赖缓存）。没读过的先回读。
> 载体：全部代码锚点按今天收工时的真实文件行号写，不许凭记忆改。

## 本篇分级总表

| 节 | 主题 | 级别 |
|---|---|---|
| §一 | 痛点：安全与体验的死结 | A 必学 |
| §二 | 最小可跑示例：手动发两张"牌" | A 必学 |
| §三 | 概念逐层：双 token / 轮换 / 撤销表 | A 必学 |
| §四 | 三个机制判断：access 不入库 / opaque vs JWT / 存 hash | A 必学 |
| §五 | 易错点表 | A 必学 |
| §六 | 命令速查 | B 会用 |
| §七 | 面试问法 | A 必学 |
| §八 | 闭卷自测 8 题 | A 必学 |
| §九 | 动手任务 | A 必学 |
| §十 | 轮换并发窗口与 family 撤销 | L 了解 |

---

## §零 主线时间轴（A）

```
D2：注册登录 → 密码换一张 access 票（60 分钟，无状态）
D3：验签之后加"查库验人" → 封禁/改角色实时生效
D4（今天）：access 拆成两张票 →
    access（短命，无状态，管"这一次请求能不能放行"）
    refresh（长命，有状态入库，管"这七天还是不是你"）
    ─────────────────────────────────────────────
    在线上位置：登录/续票在 auth 边界，refresh_tokens 是第一张"有状态的安全表"。
    一句分界线：access 丢了只疼 15 分钟，refresh 丢了疼 7 天——所以 access
    可以随便放，refresh 必须像密码一样保管。
```

---

## §一 痛点：安全与体验的死结（A）

### 场景

D2-D3 之后，你的项目是这样的：登录 → 发一张 access JWT（`config.py:27`，60 分钟）→ 每个请求带票 → 服务端验签 + 查库验人。

现在问一个产品问题：**这张票该活多久？**

| 票寿命 | 安全 | 体验 |
|---|---|---|
| 60 分钟（现状） | 票丢了，攻击者横行 59 分钟（验人查库挡不住**拿票的人**，只能挡"票指向的人不合法"） | 还行，一小时输一次密码 |
| 15 分钟 | 丢了只疼 15 分钟 | **每小时被踢出去重新输密码，用户流失** |
| 7 天 | 票丢了等于账号丢了 | 舒服 |

单独调这一根旋钮，两头拧不到一起：**拧向安全就毁体验，拧向体验就毁安全。**

### 没有双 token 时，人类的土办法

1. **票签 7 天** → 泄漏=账号易主。现代 Web 的 access 泄漏渠道太多（XSS、代理日志、浏览器扩展），等不起。
2. **服务端存 session 表，票只发一个随机 ID** → 完全可撤销，但**每个请求都要查一次 session 表**（不是主键单行读那种一次，是带并发过期的活跃会话表），而且撤销粒度只有"全部下线"，不能"让旧设备下线、新设备继续"。
3. **根本不设过期** → 不讨论。

### 双 token 的解法

把"你是谁"和"你现在能不能用"拆开：

- **access**：短命（15 分钟量级）、**无状态**、每个请求都带。丢了只疼一会儿，不值得为它建基础设施。
- **refresh**：长命（7 天量级）、**有状态**（入库）、只在续票那一刻出现。正因为它有状态，撤销/轮换/审计全都能做。

> **术语首现解释（这段是新补的）**
>
> - **refresh 为什么叫 refresh**：refresh = 英文"刷新"。这张票唯一的用途就是 access 过期时，拿它去服务器"刷新"出一张新 access，所以叫 refresh token（刷新令牌）。类比：**access = 门票**（15 分钟作废，检票口扫一眼就放行）、**refresh = 会员卡**（7 天有效，门票过期了拿会员卡去售票处换新门票）。登录 = 用密码同时买到门票 + 会员卡。
> - **"线上飞"是什么**：指 token 在网络上的暴露方式。access 每发一个请求都要塞进 `Authorization` 头从浏览器传到服务器，一天"飞"几百次，每次都是一次被偷的机会。refresh 平时躺在客户端存着，7 天只在续票那一刻**传一次**——传输次数少，被偷的机会就少。后文"不在线上飞""飞一次线上"都是这个意思。
> - **"续票"是什么**：`POST /auth/refresh` 这个动作——拿 refresh 换一对新票（新 access + 新 refresh），旧 refresh 同时作废。相当于"会员卡换新门票 + 换发新会员卡"。

效果：用户 7 天无感（refresh 自动换新 access），攻击者偷到 access 只能用 15 分钟。**安全和体验从此是两个旋钮，可以分开拧，不再互相牵制。**

**判据句（背下来）**：*access 丢了疼 15 分钟，refresh 丢了疼 7 天——所以 access 可以随便放，refresh 必须当密码保管。*

---

## §二 最小可跑示例（A）

不写进项目，先在 `scratch/` 里跑一遍，5 分钟，亲手感受两张牌怎么转：

```python
# scratch/refresh_demo.py —— 概念演示，不是项目代码
import hashlib, secrets
from datetime import UTC, datetime, timedelta

def issue_pair(user_id: str) -> tuple[str, dict]:
    access = f"ACCESS::{user_id}::{int(datetime.now(UTC).timestamp())}"   # 真项目里是 JWT
    raw = secrets.token_urlsafe(32)                                       # 随机 256 bit
    stored = {"token_hash": hashlib.sha256(raw.encode()).hexdigest(),
              "user_id": user_id,
              "expires_at": datetime.now(UTC) + timedelta(days=7),
              "revoked_at": None}
    return access, {"raw": raw, **stored}

def refresh(stored: dict, presented_raw: str) -> tuple[str, dict] | None:
    if hashlib.sha256(presented_raw.encode()).hexdigest() != stored["token_hash"]:
        return None                                   # 票不对
    if stored["revoked_at"] is not None:
        return None                                   # 已被轮换/撤销 → 疑似重放
    if datetime.now(UTC) >= stored["expires_at"]:
        return None                                   # 过期
    stored["revoked_at"] = datetime.now(UTC)          # 轮换：旧票作废
    return issue_pair(stored["user_id"])

pair = issue_pair("u1")
print("登录:", pair[0])
nxt = refresh(pair[1], pair[1]["raw"]);  print("第 1 次续票:", "成功" if nxt else "失败")
old = refresh(pair[1], pair[1]["raw"]);  print("旧票再用:", "成功" if old else "失败 ← 重放被拦")
```

跑法：

```powershell
# Windows PowerShell
& .\kb-service\.venv\Scripts\python.exe scratch\refresh_demo.py
```

```bash
# Git Bash / Linux / macOS
./kb-service/.venv/Scripts/python.exe scratch/refresh_demo.py
```

**跑之前先猜**（教材规矩）：第 2 次 refresh 用**同一张旧票**，成功还是失败？
猜完再跑。跑出来的三行就是本节全部内容：登录发两张牌 → 新票能换 → **旧票再用必死**。

---

## §三 概念逐层（A）

### 3.1 两张票的分工表

| | access | refresh |
|---|---|---|
| 出现位置 | **每个**请求的 `Authorization` 头 | **只在** `POST /auth/refresh` |
| 寿命 | 短（15–60 分钟） | 长（7 天量级） |
| 形态 | JWT（自含，无状态） | **不透明随机串**（opaque，状态在库） |
| 存储 | 客户端随意（内存/localStorage） | 客户端安全存储（httpOnly cookie / 安全存储） |
| 服务端怎么验 | 验签名 + 查用户表（D3） | **查撤销表**（sha256 对一遍） |
| 丢了多严重 | 疼 15 分钟 | 疼 7 天 → 所以存 hash、可撤销、可轮换 |
| 撤销 | 做不到（无状态），靠短寿命兜底 | 一行 UPDATE `revoked_at` |

### 3.2 轮换（rotation）：refresh 每用一次就换一张

流程（今天要在项目里实现的东西）：

```
POST /auth/refresh  携带 refresh_token
  1. sha256(呈上的 token) → 查 refresh_tokens 表
  2. 查无此行                    → 401（票不对）
     查到但 revoked_at 非空      → 401（重放！见 §10）
     查到但已过期                → 401（正常过期，引导重新登录）
     user 不存在 / is_banned     → 401（D3 判据：吊销身份）
  3. 全部通过 → 同一个事务里：旧行 revoked_at=now，插新行（新 refresh + 新 access）
  4. 返回 新 access + 新 refresh
```

**为什么轮换**：refresh 理论上 7 天内每次续票都要在网络上传一次（每传一次就多一次被偷的机会）。轮换把单张票的暴露从"一张票用 7 天"压到"每次续票用完即换"——泄漏窗口从天级降到秒级。

**为什么"revoked 还被用"要特殊对待**：正常流程里旧票用一次就死，谁还会拿旧票来换？只有两种人：刚续票的正常客户端（网络抖动重试，无害）和**拿到旧票的攻击者**。所以安全规范里这是**告警级事件**——进阶做法是把同源全部撤销（§十）。

### 3.3 撤销表设计（今天要建的表）

```python
# models.py 新增（字段以交付物验收为准）
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256 hex = 64 字符
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

设计判断逐个过：

- **`token_hash` unique**：查找就是"hash 换行"，唯一索引 = 主键级查找路径。
- **为什么存 hash 不存明文**：§四·3。
- **`revoked_at` 不删行**：留着能回答"这票何时被谁用过"（审计）；定期清理过期行是后台任务（W11 再说）。
- **`expires_at` 存表里而不是只靠 JWT exp**：refresh 不是 JWT，没有自带过期；过期语义自己负责。

### 3.4 在 D3 链路上的位置

`get_current_user`（`deps.py:27-44`）**一行都不用改**——access 的验法不变。双 token 只动了 auth 边界：`login` 多发一张、新增 `/auth/refresh`、`/auth/logout`。**这就是分层的红利：续票策略换了，业务链路零感知。**

---

## §四 三个机制判断（A，本篇最值钱）

### 1. access 为什么不入库

反证法。把 access 也入库，你会得到：每个请求多一次查询（D3 那次查库是验人，这次是验票，两笔账）；撤销有了（行级 UPDATE）；然后呢？**access 的全部价值就是无状态**——为可撤销把它入库，不如直接用 refresh：短命 + refresh 层撤销，效果一样、基础设施只建一份。

**判据**：*access 用短寿命兜底安全，refresh 用数据库兜底撤销；一个状态不建两次。*

### 2. refresh 为什么不用 JWT（opaque random）

这是今天最容易答错的一题。直觉会说"token 都该是 JWT"——错。

- JWT 的核心卖点是**无状态验证**：不查库就能信 payload。
- refresh 的验证流程**反正要查库**（轮换要 UPDATE、撤销要查、封禁要查 user）——查库不可避免，JWT"免查库"的优势**用不上**。
- 用 JWT 还倒贴成本：过期管理、签名验签、payload 泄漏结构信息（攻击者能看到这是 refresh 而不是 access）。
- opaque（`secrets.token_urlsafe(32)`）一行代码，256 bit 熵，库里查到才算数。

**判据**：*要不要 JWT，看验证时要不要查库。要查库的场景，JWT 是纯负担。*

### 3. 撤销表为什么存 sha256，不存明文

和密码同理（`hash_password` 的逻辑迁移）：**这张表的内容，泄漏代价应该只是"作废全部会话"，而不是"7 天内任意登录别人账号"。** 存明文的 refresh_tokens 表 = 一张能登录所有人的票库，DB 备份、日志、误读到的每一个人都直接拿到武器。sha256 之后，泄漏者拿到的是一堆不可逆的 hash，原票仍在用户手里。

顺带一个推论：**明文 token 只在响应体里出现一次**（登录/续票的响应），服务端不留底——留底就是把 hash 白算了。

---

## §五 易错点表（A）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | refresh 也签成 JWT | 得维护第二套 exp/签名，查库照样要查 | opaque `token_urlsafe(32)` |
| 2 | 撤销表存明文 token | DB 泄漏 = 全员账号沦陷 | 存 sha256 hex（64 字符，`String(64)`） |
| 3 | 轮换"先查旧票、后插新票"不在同一事务 | 并发下旧行没 revoke 就发了新票 | revoke + insert 一个事务（D3 flush/commit 判据直接复用） |
| 4 | refresh 接口挂了 `get_current_user` | 没带 access 就续不了票——本末倒置 | refresh 靠 refresh_token 自证，自己查 user |
| 5 | 过期判断只看 `expires_at <= now` 却忘了时区 | UTC 和本地时间混用，提前/推迟 N 小时 | 全链路 `datetime.now(UTC)`（项目既有约定） |
| 6 | 封禁判断只做 login 不做 refresh | 被封用户拿着 7 天 refresh 继续换票 | refresh 里也查 `is_banned`（D3 判据第三变体） |
| 7 | `token_hash` 忘建索引/唯一约束 | 查找退化为全表扫 | `unique=True` 一行解决 |
| 8 | 轮换后忘了把**新 refresh 返回给客户端** | 客户端下次拿着已 revoke 的旧票来，401 循环 | 响应体 access + refresh 成对出现 |

## §六 命令速查（B）

```powershell
# Windows PowerShell
# 生成一个 opaque refresh token（看一眼长度和形状）
& .\kb-service\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32)); print(len(secrets.token_urlsafe(32)))"
# sha256 hex 是多少字符
& .\kb-service\.venv\Scripts\python.exe -c "import hashlib; print(len(hashlib.sha256(b'x').hexdigest()))"
# 跑 D4 相关测试
cd kb-service; & .\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_refresh.py -q --no-cov
# 门禁
cd kb-service; & .\.venv\Scripts\python.exe scripts\check.py
```

```bash
# Git Bash / Linux / macOS
./kb-service/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
./kb-service/.venv/Scripts/python.exe -c "import hashlib; print(len(hashlib.sha256(b'x').hexdigest()))"
cd kb-service && ./.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_refresh.py -q --no-cov
cd kb-service && ./.venv/Scripts/python.exe scripts/check.py
```

**两个数先跑出来记住**：`token_urlsafe(32)` ≈ 43 字符、sha256 hex = **64 字符**——`String(64)` 就是从这来的，不是拍的。

## §七 面试问法（A）

**问 1：*"JWT 过期了怎么续？为什么需要 refresh token？"***
30 秒版：access 设短命（15 分钟量级），续票靠 refresh——一张长命、有状态、入库的凭证。access 保持无状态所以不入库，安全靠短寿命兜底；refresh 反正每次都要查库做轮换和撤销，做成 opaque 随机串存 sha256。用户 7 天无感，攻击者偷到 access 只能用 15 分钟。

**问 2：*"refresh token 泄漏了怎么办？"***
30 秒版：三层兜底。轮换让单张票泄漏后只能"活一次传输"——被用过的旧票再出现就是重放；检测到重放可以把同源会话全部撤销；refresh 存的是 sha256，表泄漏也拿不到原票。再往上按设备发 refresh，能精确"踢旧设备、留新设备"。

**问 3：*"为什么 refresh 不做成 JWT，跟 access 统一多好？"***
30 秒版：JWT 的价值是无状态验证，而 refresh 的验证流程每次都要查库（轮换、撤销、查封禁），无状态优势用不上；用 JWT 还要维护第二套过期和签名，纯负担。判据：验证时要查库的场景，token 用 opaque。

**追问链预演（三层）**：
① 机制层 → 轮换在同一事务里做哪两件事？（旧行 revoke + 新行 insert）
② 边界/故障层 → 旧 refresh 被第二次使用，最可能是什么？（重放=泄漏信号；也可能是客户端网络重试，处置要区分）
③ 场景层 → 你项目里 refresh_tokens 表多久清一次？流量涨十倍这张表多大？（7 天 TTL 全量 ≈ DAU×7 行；过期清理是后台任务，W11 接）

## §八 闭卷自测 8 题（题目先看，答案折叠在最后）

> 作答方式照旧：打字闭卷，发给 AI 判卷。判据优先，机制锚点句这次要带上（D3 判卷的差距项）。

1. access 短命、refresh 长命，各自承担什么风险？把"票丢了疼多久"讲清楚。
2. refresh token 为什么用 opaque 随机串而不用 JWT？判据是什么？
3. 轮换解决什么问题？旧 refresh 被第二次使用，说明什么、服务端该怎么处置？
4. 撤销表为什么存 sha256 不存明文？泄漏这张表的最坏后果分别是什么？
5. access 为什么不入库？如果入了库，会发生什么？
6. 封禁用户的 refresh 请求返回什么码？判据从 D3 哪条来？
7. refresh 接口要不要挂 `get_current_user`？为什么？它自己怎么验"人"？
8. 轮换时"revoke 旧行"和"insert 新行"必须在同一事务里，为什么？拆开会出什么事故？

<details>
<summary>点开看答案（先全部答完再看）</summary>

1. access 丢了疼一个寿命周期（15 分钟量级），所以它可以无状态、随便放；refresh 丢了疼整个续期窗口（7 天），所以它必须入库、存 hash、可撤销可轮换。双 token 的本质是把"丢票代价"和"续票体验"拆到两张票上，各自优化。
2. 判据：**验证时要不要查库**。refresh 每次验证都要查撤销表（轮换/撤销/封禁），JWT"免查库"的优势用不上；用 JWT 反而多维护一套签名和过期，还泄漏 token 结构。opaque = `secrets.token_urlsafe(32)`，库里查到才算数。
3. 轮换把单张 refresh 的泄漏窗口从"一张票管 7 天"压到"用一次就作废换新"。旧票已被 revoke 还来使用 = 要么客户端网络重试（无害），要么**攻击者拿到了刚用过的票**（重放，泄漏信号）——安全规范里这是告警级事件，进阶处置是撤销同源全部会话；正常客户端收到 401 后重新登录即可。
4. 存 hash：表泄漏（备份/日志/误读）的代价从"7 天内任意登录别人账号"降为"作废全部会话"。明文表 = 一张能登录所有人的票库；hash 表 = 一堆不可逆的摘要，原票仍在用户手里。和密码存 bcrypt 同一个思想，只是 refresh 不需要慢哈希（原票本身就是 256 bit 随机数，不需要抗暴力猜测，快哈希足够）。
5. 入库后每请求多一次验票查询（和 D3 验人那次是两笔账），而撤销需求 refresh 层已经覆盖——**一个状态不建两次**。access 的全部价值就是无状态，入库等于把它最值钱的东西扔了，换来 refresh 已有能力。
6. 401。判据：封禁 = 吊销身份（D3 第 3 题），refresh 是"换新身份凭证"的动作，身份已被吊销的人没有资格换。且 login、access 验人、refresh 三处判 `is_banned` 是同一条判据的三个落点。
7. 不挂。refresh 请求带的不是 access，挂了它等于"必须有 access 才能换 access"，短命的 access 过期后续票就死锁了。它自己验人：sha256 查撤销表 → 查 user 存在 → 查 `is_banned`——是独立的一条验人链。
8. 拆开的并发事故：请求 A 校验旧票通过（准备 revoke），请求 B 校验同一张旧票也通过（A 还没 commit）→ 两张新票都签发，旧行可能只 revoke 一次或两次 commit 交错。"一票换一票"的守恒被破坏，重放检测也失效。同一事务里 revoke + insert（先 flush 占住写锁）保证原子性——D3 的 flush/commit 判据直接复用。

</details>

## §九 动手任务（交付物清单 + 验收标准）

> 分工照旧：核心链路你写，测试我写；AI 不直接给你能跑的成品——卡 10 分钟翻教材，再卡就喊我，一次一层提示。

**交付物 0 · 痛点实验（先亲眼看，10 分钟）**

把 `.env` 里（或环境变量）`ACCESS_TOKEN_EXPIRE_MINUTES` 改成 `1`，重启 uvicorn（**必须重启**，D2 债②：无 `--reload` 跑旧代码），登录拿票，等 65 秒后再打受保护接口。

验收：亲眼看一次 **401 凭证无效或已过期**，然后在纸上写一句：*这 65 秒里用户体验了什么、这套系统每年要多少次这种 401*。这就是 D4 要解决的东西。

**交付物 1 · 表 + 迁移**

- `models.py` 新增 `RefreshToken`（§三·3 的形状，外键指向 `users.id`）
- alembic 迁移：照 `alembic/versions/397b8b767d9c_add_users_table.py` 的形状新开一个 revision（`upgrade` 建表 / `downgrade` 删表）；测试侧不用管——conftest 的 `create_all` 会自动建

验收：`scripts/check_users_table.py` 同款思路（或直接 `alembic upgrade head` 后 mysql 里 `SHOW TABLES`）能看到 `refresh_tokens`。

**交付物 2 · 签发与哈希（security.py）**

- `create_refresh_token() -> tuple[str, str]`：返回 `(明文 token, sha256 hex)`——明文只给响应体，hash 进库
- `hash_refresh_token(raw: str) -> str`（续票时对呈上的明文做同一变换）

验收：命令速查里那两个长度数字（43 / 64）实测对上；同一条明文两次 hash 结果一致。

**交付物 3 · 双 token 登录（改 auth_service.login + TokenOut）**

- login 返回 `(access, refresh明文)`；`TokenOut` 加 `refresh_token: str`
- config 加 `refresh_token_expire_days: int = 7`

验收：注册→登录响应里有两个 token 字段；库里 `refresh_tokens` 有一行、`token_hash` 非明文。

**交付物 4 · `POST /auth/refresh`（本日核心，§三·2 的 4 步）**

验收标准（我写测试来打，你要能口头答）：
1. 正确 refresh → 200，返回**新的** access + refresh，库里旧行 `revoked_at` 非空、多一行新行
2. 旧 refresh 复用 → **401**（重放被拦）
3. 假 token / 乱串 → 401，文案与"密码错"哲学一致（不泄漏原因细节）
4. 封禁用户 refresh → 401（先做痛点实验那套封禁流程）
5. 过期 refresh（把 `expires_at` 改到过去）→ 401

**交付物 5 · `POST /auth/logout`（撤销语义）**

- 带 refresh_token 调用 → 该行 revoke → 204（或 200）
- 已 revoke 的再 logout → 204 语义上幂等，或 401——**你选一个，并能说出理由**（判卷会问）

验收：logout 后 refresh → 401。

**提交物格式**：写完喊我，我代写 `tests/test_refresh.py`（含变异验证），然后门禁 + 你闭卷答 §八 8 题。

## §九·五 业务链条三问（固定节）

1. **哪个用户可见行为**：登录一次，7 天内页面无感续票；被封禁/改密码后，正在用的客户端下一次续票被踢回登录页。
2. **不做会怎样**：要么 access 签 7 天（泄漏=账号易主，安全团队半夜找你），要么 15 分钟一踢（用户流失，产品团队半夜找你）。
3. **可复现指标**（个人项目测不出流量，标"待真实负载"）：能测的是**行为指标**——重放 401、封禁 401、轮换后旧行 `revoked_at` 非空；表规模 DAU×7 天 TTL 为上界（待真实负载）。

## §十 轮换并发窗口与 family 撤销（L 了解，不进自测）

- **并发窗口**：§八第 8 题。工业级处理是"reuse 检测"——同一张已 revoke 的 refresh 再出现，把**同一登录会话发出的所有 refresh 全部撤销**（全家桶），因为 normal 客户端不会重放，能重放说明票在外面。要支持就得给表加 `family_id`（登录时生成，同一次登录签发的 refresh 同族）。
- 我们 W8 只做"单票 revoke + 重放 401"，family 撤销记为 W9+ 可选升级——面试能讲出"知道有这个机制、知道为什么"就够了。
- 顺带一句真话：refresh token 该放 cookie 还是 localStorage，Web 圈吵了十年没有定论（httpOnly cookie 防 XSS 但有 CSRF 面，localStorage 反之）。你的项目演示页放 localStorage 就行，面试时能说出两边代价即达标。

## §十一 收尾清单

- [ ] 交付物 0–5 全部闭环，`tests/test_refresh.py` 变异验证红→绿
- [ ] §八 8 题闭卷作答 + 判卷（进 `week8/总结/`）
- [ ] 清债槽 ⑥：`doc_count` 一致性测试（计划原定 D4 槽，30 min）
- [ ] 巡检：W6 中间件-依赖-异常顺序（**当天学完内容后做**，出红不追新进度）
- [ ] 每日重写 10 min：今天从 `auth_service.login`（12 行）开始——它是你要改的函数，先重写一遍旧版再动手改新版，差距就是你今天要学的东西
