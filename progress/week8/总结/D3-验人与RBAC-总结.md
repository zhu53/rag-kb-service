# W8-D3 每日总结 · 验人与 RBAC

> 本日资产：`get_current_user` 真链路落地（9 处路由改契约 + chat 漏网 1 处）+ login 堵封禁口子（用户手写）+ `require_role` 工厂 + admin 两路由 + 十端点盘点 10/10 ✅（#4/#9 实测 403）+ 清债 ④⑧ + `mutation_check.py` 两个静默失效修复
> 环境：Python 3.11.18 / MySQL 8.4.0@3307(kb_dev) / sqlite 测试隔离（conftest 赋值 DATABASE_URL）/ FastAPI 依赖缓存
> 门禁：**108 passed, 2 skipped / 覆盖率 96.70%（精确浮点）/ 变异验证 3 组（banned login、role check、updated_at）全红→绿 / ruff / mypy strict 全绿**
> 第四档 `review_NN`：任务内嵌（W8 起无独立文件）——admin 路由用户写骨架 AI 收尾 + 闭卷 8 题判卷 3/3/4/3/3/3/3/3（均 3.1，无 2 档以下）

## 一、知识地图（按面试出场率降序）

| # | 知识点 | 出场率 | 掌握要求（可验证动作） | 本日证据 |
|---|---|---|---|---|
| 1 | 验签 ≠ 验人（每请求查库） | ★★★★★ | **能讲清 JWT 为什么保证不了"人现在合法"（无状态，签名只绑票不绑持票的手）** | 交付物 0：封禁后 200 |
| 2 | 401 vs 403 判据 | ★★★★★ | **能一句话判"该 401 还是 403"并用判据复推新场景** | 判卷第 3 题 4 档；test_rbac 两条分开测 |
| 3 | 两种 owner 校验模式 + 两跳归属 | ★★★★★ | **能背 owner 契约三行 + 说出 doc 归属链为什么必须走两跳** | 十端点盘点 10/10；#9 实测 403 |
| 4 | 依赖工厂 `require_role` | ★★★★☆ | **能闭卷写 8 行工厂 + 说出两个时态（启动时调用/请求时执行）** | 用户手写一次对；判卷第 4 题 |
| 5 | 依赖缓存 | ★★★★☆ | **能说出"同请求同依赖只执行一次"及 `use_cache` 参数名** | 判卷第 5 题；router 级兜底删掉 108 全绿实测 |
| 6 | TypedDict 契约变更 | ★★★★☆ | **能说出 `Depends()` 是 mypy 的 Any 通道、类型错配只有运行时能抓** | `'dict' object has no attribute 'hex'` 实锤 6 处漏改 |
| 7 | 门禁绿 ≠ 被保护 | ★★★★☆ | **能举出"绿是因为没人测"的真实例子并说出守门测试怎么补** | banned login 测试洞：代码对但 tests 零覆盖 |
| 8 | 时序不可区分 | ★★★☆☆ | **能说出封禁判断为什么必须放 bcrypt 之后（计时探测）** | 交付物 2 三处落点核对 |

## 二、逐个知识点讲透

### 1. 验签 ≠ 验人：JWT 的第四件保证不了的事

**一句话定义**：验签保证"票是真的、没篡改、没过期"，验人是"sub 指向的人**现在**是否合法"——后者必须查库。

**为什么存在**：JWT 无状态。签名把 payload（含 sub、exp）锁死在签发那一刻，之后用户被删、被封、被改角色，票面信息一个字都不会变。没有"查库这一步"，撤销体系就只剩"等票自然过期"一条路——access 签 60 分钟，封禁一个坏人他要再横行 59 分钟。**交付物 0 就是这个洞的实锤：`is_banned=1` 的 demo1 拿旧 token 打受保护接口照样 200。**

**怎么用**（项目真实代码 `deps.py:27-44`）：

```python
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
) -> UserRow:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)   # 验签：真票/未篡改/未过期
    user_id = UUID(claims.sub)
    row = UserRepository(session).get(user_id)              # 验人：主键查库
    if row is None:
        raise UnauthorizedError("用户不存在")
    if row["is_banned"]:
        raise UnauthorizedError("账号已被封禁")
    return row
```

**底层机制**：`session.get(User, user_id)` 走主键 B+ 树单行读——全项目最便宜的查询。代价（每请求一次）换收益（状态实时生效）。D3 之前 `_bearer_scheme` 只解 token，解完就把 sub 当真——**签名成了"身份"的替身，但签名从未承诺过身份**。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 把 role/状态写进 JWT 省查库 | 封禁/降权不生效，直到旧票过期 | 票里只放 sub；状态永远查库（D2 第 6 题同判据） |
| 2 | 只在 login 时查状态 | 封禁用户拿旧票横行 | 每请求查；login 也要查（交付物 2） |
| 3 | 以为验签=验人因为"签名是服务端发的" | 概念混着讲不清 | 签名绑的是**票**，不是**持票的手**；票与人此刻的关系只有库里知道 |

**面试问法**：*"JWT 无状态，那封禁一个用户怎么立即生效？"*
**30 秒版**：封禁生效靠"每请求查库"，不是靠 token。JWT 签名只保证票没被改过，保证不了持票人现在还合法——所以验签之后必须拿 sub 查一次用户表。这是拿每请求一次主键查询，换"撤销实时生效"。想省这次查询，就得接受封禁要等票过期才生效。

**追问链**：
→ *"那次查询会不会拖垮性能？"* 主键单行读是全项目最便宜的查询，B+ 树 3-4 层；真正的开销在连接池管理。真扛不住时才上缓存，但要接受撤销延迟（TTL 内不生效）。
→ *"为什么不把 is_banned 放 token 里、封禁时把用户所有票拉黑？"* 拉黑需要维护撤销清单 = 引入有状态存储 = 那不如直接查库，复杂度白付。
→ *"项目里哪里体现的？"* `deps.py:39-43` 查库 + 封禁判断；`test_rbac.py` 封禁闭环：提权不改 token 只改库里 role，断言立刻生效。

### 2. 401 vs 403：身份问题 vs 权限问题

**一句话定义**：401 问"你是谁"（身份无效，应重登）；403 问"你是不是够格"（身份有效但被拒）。

**为什么存在**：语义混了，客户端行为就错了——把 403 当 401 处理会反复重登（没用），把 401 当 403 处理会不重登（卡死在无票状态）。状态码是给客户端的**行为指令**，不是装饰。

**怎么用**（项目里 4 处判据落点）：

| 场景 | 码 | 判据句 |
|---|---|---|
| 没票 / 票坏 / 票过期 | 401 | 身份无法确认 |
| sub 指向的人不存在 | 401 | 票指向的身份已消失，重登 |
| 用户被封禁 | **401** | 封禁 = 吊销身份，与"票过期"同类；403 留给"人是合法的但不够格" |
| member 打 admin 路由 | **403** | 人验过了，缺的是权限 |

**底层机制**：HTTP 语义层。401 携带 `WWW-Authenticate` 提示重新认证；403 表示服务器知道你是谁、且拒绝。封禁判 401 的推论：**被封禁者重新登录也必须失败**——所以 login 里也要查 `is_banned`（交付物 2），且**文案必须与"密码错"逐字一致**，否则攻击者拿文案差异探测账号是否存在/被封。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 封禁判 403 | 客户端不触发重登，卡在无效状态 | 撤销身份 = 401；角色不够 = 403 |
| 2 | 封禁文案写"账号已被封禁" | 账号状态探测通道（枚举有效邮箱） | 与"密码错"文案逐字一致 |
| 3 | 401/403 混在一条测试里 | 变异短路时红得不明确 | 分开测（test_rbac 第 1、2 条） |

**面试问法**：*"封禁用户带有效 token 请求，返回 401 还是 403？为什么？"*
**30 秒版**：401。封禁的语义是吊销身份——票虽然没过期，但它指向的身份已经不合法了，这和"票过期"同类；403 留给"身份合法但权限不够"（比如 member 打 admin 接口）。推论是 login 也要查封禁，不然封禁用户换个新票照样进。

**追问链**：
→ *"login 里怎么查？credentials 行有没有 is_banned？"* 最初没有——`UserCredentialsRow` 只有 id+hash。方案是扩行带出 `is_banned`（一次查询），否掉"再查一次"（两次查询 + 新 None 分支）。
→ *"封禁文案为什么要一样？"* 时序与文案双通道防探测：响应体一致 + bcrypt 照跑，攻击者无法区分"密码错"和"被封"。
→ *"封禁者反复重试怎么办？"* 登录接口限流（`RateLimitError` 已有异常类，W8 未接）；再往上 IP 维度封禁。

### 3. 两种 owner 校验模式 + 间接归属两跳

**一句话定义**：模式一 = owner 条件进 WHERE（默认安全）；模式二 = 取回后检查（`get_or_403`）；间接归属（doc→kb→owner）检查点必须跟着归属链走。

**为什么存在**：多租户数据的最小边界。漏一条查询 = 一条横向越权通道，且**静默**——200 加别人的数据，没有任何报错。模式一"想漏都难"（条件在 SQL 里），模式二"想对都难"（靠每个调用点自觉走检查函数）。

**怎么用**（十端点盘点，行号按 D3 收工时代码）：

| 模式 | 落点 | 特点 |
|---|---|---|
| 一（WHERE） | `kb_repo.py:48/67` 列表、计数 | 默认安全；覆盖不了按 id 直取 |
| 二（get_or_403） | `kb_service.py:35` 等 6 处 | 能区分 404/403；失效方式 = 绕过它直接 `repo.get` |
| 二·两跳 | `doc_service.py:71/78` | doc 无 owner_id，`doc.kb_id → kb.owner_id` |

**底层机制**：`get_or_403` 是唯一检查点。`doc_service.get` 必须先 `repo.get(doc_id)` 拿到 `kb_id`，再过 `get_or_403(row["kb_id"], user_id)`——**跳过这一跳 = 任何登录用户可读任何文档**。D3 实测：#9（A 的 token 打 B 的 doc）堵住时 403；走读日探针进一步实锤 `get_doc` 的路径参数 `kb_id` 未参与校验（A 用别人的 kb_id + 自己的 doc_id 拿到自己的文档——不泄漏但语义不干净，欠账在册）。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 新查询直接 `repo.get(id)` 不过检查 | 静默越权，测试全绿 | 契约第 2 条：收敛到唯一检查函数 |
| 2 | 间接归属只查一跳 | `doc.kb_id` 匹配但 kb 不是你的 | 检查点跟归属链走（第 3 条） |
| 3 | 越权测试伪造 sub 造 token | 测的是"造票对不对"，不是"拦不拦" | 造真第二用户 + 真 token |
| 4 | owner 条件能进 WHERE 却写成模式二 | 多一次往返、多一个绕过机会 | 能进 WHERE 的必须进 WHERE |

**面试问法**：*"多租户 SaaS 里，怎么保证用户 A 永远拿不到用户 B 的数据？"*
**30 秒版**：两层。能进 SQL 的场景把 owner 条件写进 WHERE——默认安全；按 id 直取、跨表间接归属这类进不了 WHERE 的，收敛到唯一一个检查函数（我项目里的 `get_or_403`），所有路由只准通过它拿数据。间接归属（文档挂在知识库下）检查点必须跟着归属链走，跳一跳就是一条越权通道。

**追问链**：
→ *"为什么不统一 404 防 IDOR 枚举？"* 产品决策：403 帮助用户理解"库存在但不是你的"；担心枚举可改 404——判据先讲清，取舍再谈。
→ *"怎么证明没漏？"* 十端点盘点 + 每端点落 `文件:行号` + 抽两条实测（#4/#9 真第二用户 403）。
→ *"check 挂在 service 还是 repo？"* service——repo 是纯数据访问（可被测试/脚本直接调用），检查是业务规则；`repo.get` 公开这一点是模式二的已知失效方式，靠"所有路由只走 service"约定压住。

### 4. 依赖工厂 `require_role`

**一句话定义**：一个"返回依赖函数"的函数——调用时记住要求哪些角色，返回的闭包进依赖图执行检查。

**为什么存在**：角色检查若靠每个路由手写 if，漏一处 = 静默越权（最阴一档：不报错、不崩、直接放行）。工厂把检查变成**结构**：进依赖图自动执行，想不执行都难；新加 admin 端点零成本。

**怎么用**（`deps.py:47-60`，用户手写判断部分一次写对）：

```python
def require_role(*roles: str) -> Callable[..., Awaitable[UserRow]]:
    async def _check(user: UserRow = Depends(get_current_user)) -> UserRow:
        if user["role"] not in roles:
            raise ForbiddenError("权限不足")
        return user
    return _check

# 用法（admin.py:28）：_admin: UserRow = Depends(require_role("admin"))
```

**底层机制**：两个时态。**启动时**：`require_role("admin")` 被调用，返回闭包登记进路由依赖；**请求时**：闭包被 FastAPI 执行，内层 `Depends(get_current_user)` 又解析出验人依赖——靠依赖缓存与路由签名共享同一次查库。返回注解 `Callable[..., Awaitable[UserRow]]` 而非 `Callable[[], ...]`：内层参数有默认值，调用方"可以不传"（mypy strict 要求）。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 写成 `Depends(require_role)`（忘传参数） | `roles` 空元组，admin 也被拒 | 工厂必须先调用再包 Depends |
| 2 | 内层抛 401 | 语义错：人是验过的 | 403（判据第 2 条） |
| 3 | TypedDict 点号访问 `user.role` | mypy `UserRow has no attribute` | 下标 `user["role"]` |
| 4 | 路由参数注解不写 | mypy 眼里 Depends 是 Any，错配静默 | `_admin: UserRow` 显式注解 |

**面试问法**：*"FastAPI 里怎么实现 RBAC？为什么用依赖工厂而不是装饰器或中间件？"*
**30 秒版**：依赖工厂。`require_role("admin")` 返回一个闭包，闭包内先 `Depends(get_current_user)` 拿到验过的人，再比角色、不够格抛 403。比装饰器好在它进依赖图、跟 OpenAPI 文档联动、能拿到依赖注入的参数；比中间件好在它**按路由粒度**声明——中间件是全局的，得自己写路径匹配。

**追问链**：
→ *"查库几次？"* 1 次——依赖缓存按 (callable, scope) 缓存，闭包内层与路由签名共用 `get_current_user`。
→ *"权限怎么动态改？"* 角色查库所以改库立即生效；不用重签票（D3 全章判据）。
→ *"admin 路由挂 router 级还是逐路由？"* 都行、语义等价、查库一样；逐路由能把 admin 行拿到手（将来"不能封自己"要用），我项目选了逐路由 + 注释写明触发条件。

### 5. 依赖缓存

**一句话定义**：同一请求内，同一个依赖函数默认只执行一次，其余位置命中缓存直接复用结果。

**为什么存在**：没有它，`get_current_user` 挂 router 兜底 + 路由签名 + `require_role` 内层 = 每请求查 3 次库。缓存让它只查 1 次——**"重复声明"才有资格成为安全冗余而不是性能事故**。

**怎么用**：默认开启（`use_cache=True`）。需要隔离时显式 `Depends(dep, use_cache=False)`——比如同一请求里要用两个不同 DB session 时。

**底层机制**：FastAPI 在解决依赖图时按 (callable, security_scopes) 维护 per-request 缓存字典；同键只执行一次，teardown（yield 依赖的收尾）也只跑一次。所以 `get_db` 即使被 5 个依赖引用，一个请求也只有一个 Session。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 以为"多处 Depends = 多次执行" | 白白绕开依赖机制自己加缓存 | 缓存默认开，别自己造 |
| 2 | `use_cache=False` 滥用 | 每请求多查库、多建 session | 只在真需要隔离的依赖上关 |
| 3 | 以为缓存跨请求 | 每个请求都重新解析 | per-request，不跨请求 |

**面试问法**：*"同一条请求里 get_current_user 被声明了三次，查几次库？"*
**30 秒版**：一次。FastAPI 的依赖缓存默认按请求缓存同一个依赖的结果，三个位置拿到的是同一个 UserRow。关掉某个依赖的缓存才例外（use_cache=False）。另外 yield 依赖的收尾（session.close）也只跑一次。

**追问链**：
→ *"缓存键是什么？"* (callable, security_scopes)——同函数不同 scope 不共享。
→ *"什么场景必须关？"* 同一请求需要两个独立事务/session 时。
→ *"怎么实测？"* 查库处打 print/log，打一次请求数打印次数；或走读日实测的镜像——把 router 级兜底删掉，108 测试全绿（缓存让"删一处"不可测，见第 8 点）。

### 6. TypedDict 契约：`Depends()` 是 mypy 的 Any 通道

**一句话定义**：依赖返回值在静态检查眼里是 `Any`——`get_current_user` 从返回 `UUID` 改成返回 `UserRow`（dict），mypy 对所有调用点**一声不吭**。

**为什么存在**：这次契约变更（D3 交付物 1）9 处路由都要跟着改，mypy 本该兜底，实际没兜。认清这条，才知道**静态检查的边界在哪**，不会因为"mypy 绿"就信代码对。

**怎么用**：

```python
# 必须显式注解，把 Any 收回来：
user: UserRow = Depends(get_current_user)   # ✅ mypy 知道是 TypedDict
user_id: UUID = Depends(get_current_user)   # ❌ mypy 不报错——Any 塞给 UUID 也行
# TypedDict 永远下标访问：
row["is_banned"]     # ✅
row.is_banned        # ❌ mypy: UserRow has no attribute
```

**底层机制**：`Depends(...)` 返回类型标注是 Any（FastAPI 无法在静态期知道依赖返回什么）。Any 与任何类型赋值兼容 = 类型检查在这条通道上失效。运行时才现形：`row["id"]` 是 str，塞给 `kb_id: UUID` 后 `dict.hex` 调用炸出 `'dict' object has no attribute 'hex'`——**traceback 实锤了 5 处漏改 + chat.py 漏网 1 处**，此前用户说"除了测试都改了"、mypy 全绿。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 依赖参数不写注解 | 错配静默通过 | 每个依赖参数显式注解 |
| 2 | TypedDict 点号访问 | mypy 红 / 运行时 AttributeError | 下标访问 |
| 3 | 信"mypy 绿 = 改完了" | 绿是 Any 通道放行的绿 | 契约变更后必须跑真请求/全测试 |
| 4 | grep 旧函数名找漏网 | 不 import 旧名的文件抓不到 | 从 traceback 顺藤摸瓜 + 全量跑测试 |

**面试问法**：*"Python 有 mypy strict，为什么还会出类型运行时错误？"*
**30 秒版**：两条通道。一是第三方库没注解，返回 Any（jose 的 jwt.encode 我得 cast 一次）；二是框架的魔法入口——FastAPI 的 `Depends()` 在静态期是 Any，类型对配错它看不见。我项目真实发生过：依赖返回类型从 UUID 换成 TypedDict，9 处调用 mypy 全绿，跑起来 6 处炸。结论：静态检查是助力不是证明，契约变更要靠测试和真请求收口。

**追问链**：
→ *"怎么堵 Any 通道？"* 显式注解每个依赖参数；strict 下未注解函数直接报错。
→ *"TypedDict 和 dataclass 怎么选？"* TypedDict 描述"形状已定的 dict"（to_row 的产物），dataclass 是真对象。边界转换在 repo 层完成。
→ *"cast 什么时候合法？"* 收敛**库的类型缺口**（文档承诺 str 只是没注解）合法；把**外部未知值**谎称成具体类型（`cast(str, row.get("name"))`）是延迟爆炸。

### 7. 门禁绿 ≠ 被保护

**一句话定义**：测试全绿只证明"跑过的路径没断"，不证明"关键路径被测过"——没人测的口子，绿得心安理得。

**为什么存在**：D3 交付物 2 的现场：用户把封禁判断写对了，门禁 100 passed，但 **tests 里没有任何封禁登录的测试**——这个洞绿着存在了一路。如果没有"补守门测试 + 故意破坏验证"的机制，它会在代码里活到出事那天。

**怎么用**：新堵的安全口子 = 新守门测试 + 变异验证。`test_banned_user_login_401_same_as_wrong_password`：注册 → 改 `is_banned=True` → 正确密码登录 → 断言 401 且**响应体与"密码错"完全相等**。变异：`if False and row["is_banned"]` → 测试红（红因正是原始漏洞形态：封禁 200 / 密码错 401）→ 还原 → 绿。

**底层机制**：判断"测试是否保护了行为 X"的唯一方法，是把行为 X 的实现破坏掉看测试红不红。红 = 有保护；不红 = 这条路径在盲区。走读日再加一例：router 级 `dependencies=[Depends(get_current_user)]` 三处全删，108 测试全绿 exit 0——兜底零覆盖，因为签名处还有一份重复保护。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | "绿了就收工" | 洞在盲区里绿着 | 新行为必须配守门测试 |
| 2 | 只补测试不做破坏验证 | 测试本身可能测错东西 | 变异：故意改坏，看红不红 |
| 3 | 重复保护让变异存活 | 误判"代码有 bug" | 人工确认是冗余而非漏洞 |

**面试问法**：*"你们怎么保证一个安全修复没有回归？"*
**30 秒版**：三件套：先有一个复现漏洞的守门测试（红）；修完变绿；再做变异验证——把修复故意改坏，测试必须重新变红。我项目里封禁登录这个修复就是这么验的：短路一行，测试立刻报出"封禁 200 / 密码错 401"，正是原始漏洞形态。

**追问链**：
→ *"变异测试和覆盖率什么关系？"* 覆盖率说"这行被跑过"，变异说"这行被**依赖着**"。跑过≠依赖——mutation_check 锚点失效时照样打印 100%。
→ *"盲区探针该杀还是该活？"* 按定义该活（盲区=没有测试保护的改动）；若被杀，先查是不是测错层（如 Schema 层变异被路由层测试意外杀死）。
→ *"项目里最值钱的一条是什么？"* admin 路由提权测试不改 token 只改库里 role——一条断言同时证明"验人查库、立即生效"。

### 8. 时序不可区分：封禁判断放 bcrypt 之后

**一句话定义**：所有失败路径的**耗时**必须一致，唯一允许的差别是响应体——否则计时本身就是信息泄漏通道。

**为什么存在**：封禁判断若放在密码验证之前，封禁用户跳过 bcrypt（几十毫秒），响应明显快于正常登录。攻击者不需要看文案，掐个表就知道"这个邮箱被封了"——文案写得再一致都白搭。

**怎么用**（`auth_service.py:27-37`）：

```python
row = self._repo.get_credentials_by_email(email)
if row is None:
    verify_password(data.password, _DUMMY_HASH)   # 用户不存在也跑一次 bcrypt
    raise UnauthorizedError("邮箱或密码错误")
if not verify_password(data.password, row["password_hash"]):
    raise UnauthorizedError("邮箱或密码错误")
if row["is_banned"]:                               # 放在 bcrypt 之后
    raise UnauthorizedError("邮箱或密码错误")       # 文案逐字一致
```

**底层机制**：三条失败路径（用户不存在 / 密码错 / 已封禁）全部跑一次 bcrypt + 同一段文案。`_DUMMY_HASH` 是模块级预计算的假哈希——不是每次现场算（那会让"用户不存在"路径多一次 gensalt，时序反而更慢更明显）。模块级 = 进程启动时算一次，运行期纯 checkpw。

**易错点**：

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 封禁判断放 verify 之前 | 计时探测通道 | 判断放 bcrypt 后 |
| 2 | `_DUMMY_HASH` 写在函数里 | 每次登录多一次 gensalt，慢且时序更怪 | 模块级常量 |
| 3 | 只对齐文案不对齐耗时 | 探测换了个通道 | 时序 + 文案双对齐 |

**面试问法**：*"登录接口怎么防用户枚举？"*
**30 秒版**：两条路：响应体和耗时都不能泄密。文案统一成"邮箱或密码错误"；用户不存在时也要跑一次 bcrypt（对着模块级假哈希），让不存在和密码错的耗时一致。封禁判断放在密码验证之后，否则封禁用户跳过 bcrypt 反而更快，掐表就能探测。

**追问链**：
→ *"为什么不直接提示'该账号被封禁'？"* 体验与安全的取舍：提示更友好但等于账号状态探测器；错误提示要按"攻击者能推断出什么"设计。
→ *"bcrypt 假哈希会不会拖慢正常登录？"* 不存在用户的路径才跑；正常用户路径不变。真库热点是 bcrypt 本身（CPU 密集），登录接口需要单独限流。
→ *"还有什么计时泄漏？"* 缓存命中差异、连接池排队——穷举不完，原则是"敏感判断的分支结构要镜像"。

## 三、30 秒答案集

1. **JWT 保证不了什么**：票真/未改/未过期，保证不了持票人现在合法——无状态，签名只绑票不绑手。
2. **封禁怎么立即生效**：每请求查库；拿每请求一次主键查询换撤销实时生效。
3. **封禁 401 还是 403**：401，吊销身份；403 留给身份合法但权限不够。
4. **为什么 login 也要查封禁**：封禁者重登必须失败，否则 401 语义等于让客户端去重登一个必然成功的口子。
5. **依赖工厂**：函数返回闭包；启动时调用登记、请求时执行检查；漏写 Depends 会被参数类型暴露。
6. **依赖缓存**：同请求同依赖只执行一次（use_cache=True 默认）；get_db 引用五次也只有一个 Session。
7. **TypedDict 访问**：永远 `row["字段"]`；点号访问 mypy 直接红。
8. **mypy 为什么没抓到契约漏改**：Depends() 是 Any 通道，类型错配静态看不见，只有真请求/测试能验。
9. **横向 vs 纵向越权**：横向=同级互访（A 打 B 的库），纵向=低打高（member 调 admin 接口）；横向发生在身份合法时。
10. **doc 归属**：无 owner 字段，`doc.kb_id → kb.owner_id` 两跳；跳一跳=任何登录用户读任何文档，静默。
11. **owner 契约三行**：能进 WHERE 的进 WHERE；做不到的收敛到唯一检查函数；间接归属检查点跟归属链走。
12. **门禁绿说明什么**：只说明跑过的路没断；没人测的路绿得心安理得——守门测试 + 变异验证补上。

## 四、白板手写靶

```python
# 靶 1：get_current_user 骨架（15 行）
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
) -> UserRow:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)
    user_id = UUID(claims.sub)
    row = UserRepository(session).get(user_id)
    if row is None:
        raise UnauthorizedError("用户不存在")
    if row["is_banned"]:
        raise UnauthorizedError("账号已被封禁")
    return row
# 要点：四步拒绝（无票/坏票/无人/被封）的顺序，封禁判 401 不判 403
```

```python
# 靶 2：require_role 工厂（7 行）
def require_role(*roles: str) -> Callable[..., Awaitable[UserRow]]:
    async def _check(user: UserRow = Depends(get_current_user)) -> UserRow:
        if user["role"] not in roles:
            raise ForbiddenError("权限不足")
        return user
    return _check
# 要点：返回注解是 Callable[..., Awaitable[UserRow]]（内层参数有默认值）；403 不是 401
```

```python
# 靶 3：get_or_403（8 行）
def get_or_403(self, kb_id: UUID, user_id: UUID) -> KBRow:
    row = self.repo.get(kb_id)
    if row is None:
        raise NotFoundError("知识库不存在")
    if row["owner_id"] != user_id:
        raise ForbiddenError("无权访问该知识库")
    return row
# 要点：404（不存在）与 403（不是你的）在这里分流；间接归属必须先查 doc 拿 kb_id 再进这个函数
```

## 五、踩坑实录

| 坑 | 现象 | 教训 |
|---|---|---|
| user_repo 同名方法定义两次 | ruff F811 抓出；Python 静默后者覆盖前者，被盖的那份还是 1.x `session.query()` | 重复定义只有静态检查能抓；新方法先 grep 同名 |
| router 挂 `/admin` 路由写 `""` | 测试打 `/api/v1/admin/users` 全 405（静态文件兜底把非 GET 翻成 405） | 405 会伪装成"路径不存在"；先看 /docs 路径清单再猜 |
| 依赖契约漏改 mypy 全绿 | "除了测试都改了"→ 15 条测试 401 + `'dict' object has no attribute 'hex'` | Depends() 是 Any 通道；契约变更靠测试收口，不靠静态检查 |
| fresh session 断言总行数 | seed 用户后总行数是 2 不是 1，断言红 | StaticPool 共享连接下按 email 精确查，不断言总数 |
| `Depends(require_role)` 忘传角色（预设坑） | roles 空元组，admin 也被拒 | 工厂必须先调用再包 Depends |

## 六、可以讲成故事的三段

**段 1：门禁全绿，漏洞活着。**
背景：交付物 2 要求堵"封禁用户还能登录"的口子。我以为是改完代码、门禁全绿就算闭环。实际是：grep 全 tests 目录发现**没有任何封禁登录的测试**——绿是因为这条路根本没人测，不是因为它被保护住了。教训：**门禁绿只说明跑过的路没断；判断"被保护"的唯一办法是把保护破坏掉看红不红。**

**段 2：mypy 全绿，15 条测试红。**
背景：把依赖返回从 UUID 改成 UserRow TypedDict，9 处路由要跟着改。我以为 mypy strict 会兜底。实际是：my py 全绿——`Depends()` 在静态期是 Any，Any 塞进 UUID 也合法；跑起来 `'dict' object has no attribute 'hex'` 一条 traceback 实锤 6 处漏改。教训：**静态检查是助力不是证明；框架魔法入口（依赖注入）是它的盲区。**

**段 3：变异得分 100%，其实一行都没测。**
背景：重构后跑变异脚本，输出"变异得分 9/9 = 100%"。我以为脚本工作正常。实际是：模板里的锚点还写着旧函数名，匹配不到就静默跳过，**空转变成了满分**；修完锚点又撞上第二层——宿主的删除钩子拦截 pytest 清理临时目录，测试全绿但退出码 1，盲区探针全被误判"杀死"。教训：**工具的输出不是判据，要能解释每个数字是怎么来的；rc 不是 0 也不等于测试红，要分清环境红和断言红。**

## 七、能力画像与下日衔接

**强项**
1. 判据迁移：D2"token 不放 role"的判据在 D3 第 3 题（封禁 401）直接复用拿 4 档——判据内化成思维而非记忆。
2. 安全直觉落代码：require_role 判断部分（TypedDict 下标 + ForbiddenError 而非 401）闭卷一次写对；login 封禁三处落点（扩行/带字段/放 bcrypt 后）全部核对通过。

**待补**
1. "机制锚点句"缺失：8 题判据全在，但"签名为什么绑不了人（无状态）""工厂为什么顺带省查询（依赖缓存）"这类**为什么成立的机制句**说不全——3 档到 4 档的台阶就在这。
2. 依赖缓存的生命周期边界：知道"同请求一次"，对 teardown 何时跑、use_cache=False 与 yield 依赖组合的行为没实测过。

**下日（D4：refresh token）预告的坑**
1. 会撞"access 里放什么"的旧判据复发：只放 sub，别把 user_id 之外的任何状态塞进去——D2 第 6 题、D3 第 1 题同一条判据第三变体。
2. 会撞"refresh token 要不要 JWT"的坑：反正每次 refresh 都要查撤销表，JWT 的无状态优势用不上——先想清楚再选 opaque random。
3. 会撞轮换的并发窗口：两个请求同时拿同一个 refresh 换新票，先想清楚"旧票已用"怎么判（这正是 D5 注入验收要打的洞之一）。
