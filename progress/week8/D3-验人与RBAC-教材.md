# W8-D3 教材 · RBAC：从验签到验人 + 多租户隔离点名

> 零基础版。默认读者没写过任何鉴权依赖，token 的三验三不验见 D1 教材 §零·五（先读那节再回来）。
> 本文所有 `文件:行号` 都对准你仓库里的真实代码（2026-11-23 版），可直接 grep。

## 本篇分级总表

| 级别 | 内容 | 要求 |
|---|---|---|
| **A 必学** | 验签≠验人、`get_current_user`、401/403 判据、封禁即时生效、横向/纵向越权、owner 两种校验模式 | 闭卷能讲 + 手写骨架 |
| **B 会用** | `require_role` 依赖工厂、依赖缓存、admin 路由、枚举攻击 403vs404 | 会写会用，不背细节 |
| **L 了解** | `use_cache=False` 场景、W14 tenant 表展望、OAuth2PasswordBearer | 一句话知道即可 |

---

## §零 主线时间轴（A）

一个带 token 的请求，在你项目里现在的完整旅程：

```
请求带 Authorization: Bearer xxx
  → ① HTTPBearer 解出头            deps.py:14
  → ② decode_access_token 验签     security.py:62   ← 验的是"票是真的、没改过、没过期"
  → ③ 取 sub 当 user_id 直接放行    deps.py:22       ← ★ 分界线在这：到这就当你是他了
  → ④ service → repo 查数据
  → ⑤ owner 校验（有的端点有，有的靠 WHERE）
  → ⑥ 数据出网
```

**一句分界线：你的系统现在在 ③ 就放行了——票真 = 人对。D3 要把分界线后移：③ 和 ④ 之间插一次查库，问三个问题——这个人还在吗？被封了吗？什么角色？**

D3 结束后的时间轴：

```
① 解头 → ② 验签 → ③' 查库验人（存在？封禁？角色？）→ ④ service
                                                    → ④' require_role（admin 端点才走）
                                                    → ⑤ owner 校验 → ⑥ 出网
```

本周收官验收（周计划原文）：**封禁一个用户后，他手里的 access token 还没过期，但下一个请求必须 401——你能说清这条链路上每一步是谁在检查。**

---

## §一 痛点：签名保证不了的第三件事（A）

### 1.1 三验三不验，漏了第四问

D1 教材讲过 token 的**三验**：验真票（签名对）、验未篡改（内容没改）、验未过期（exp 没到）。
但有个问题三验永远回答不了：

> **这个 user_id 对应的人，现在还是合法用户吗？**

三个真实场景，三验全部放行：

| 场景 | 票的状态 | 三验结论 | 现实应该 |
|---|---|---|---|
| 用户被管理员封禁 | 签名正确、内容没改、没过期 | ✅ 放行 | ❌ 拒绝 |
| 用户被删除 | 同上 | ✅ 放行 | ❌ 拒绝 |
| 攻击者拿到旧票（票本身合法） | 同上 | ✅ 放行 | 看撤销策略 |

### 1.2 为什么签名天生管不了这件事

回忆 D1 §零·五：**签名只绑票，不绑持票的手**。JWT 是无状态的——服务器验签时**不需要查任何东西**，这正是它快的原因。但"无状态"的另一面是：**服务器对票里写的任何内容都不负责任**。票写 `sub=张三`，服务器只保证"这句话确实是当初签出来的"，不保证"张三现在还是个好人"。

状态在数据库里。**要验人，必须回数据库**——这一步没有免费午餐，D3 的全部成本就是每个请求多一次主键查询。

### 1.3 你项目里的活体漏洞（实测可复现）

`deps.py:22` 的 `get_current_user_id`：

```python
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)   # 验签，到此为止
    try:
        return UUID(claims.sub)                             # 直接当真
    except ValueError as exc:
        raise UnauthorizedError("凭证 subject 不是合法用户") from exc
```

它**不 import session、不查 users 表**。所以今天在你的项目里：

1. 注册一个用户，登录拿 token；
2. 用 SQL 把他 `is_banned` 改成 1（模拟管理员封禁）；
3. 用**原来的 token** 打 `GET /api/v1/kbs` → **200，照常返回数据**。

封禁功能存在（`models.py:104` 有 `is_banned` 列），但没人检查它——这就是"验签不验人"的代价：**封禁形同虚设，攻击者手里的票在过期前（1 小时）一直好使。**

> 命令速查见 §八，这个实验 3 分钟能跑完，动手任务 0 会让你亲手打一遍。

---

## §二 最小可跑示例：15 行从"验签"到"验人"（A）

改动核心只有一个函数。改造后的 `get_current_user`（写法照抄骨架，动手时自己敲）：

```python
from kb_service.core.exceptions import ForbiddenError, UnauthorizedError
from kb_service.core.security import decode_access_token
from kb_service.core.db import get_db
from kb_service.repositories.user_repo import UserRepository
from kb_service.repositories.rows import UserRow

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
) -> UserRow:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(claims.sub)
    except ValueError as exc:
        raise UnauthorizedError("凭证 subject 不是合法用户") from exc

    row = UserRepository(session).get(user_id)      # ★ 分界线后移：查库
    if row is None:                                  # 人没了
        raise UnauthorizedError("用户不存在")
    if row.is_banned:                                # 人被封了
        raise UnauthorizedError("账号已被封禁")
    return row                                       # 把"人"（不只是 id）传下去
```

三个设计决策，每个都要能说出理由：

1. **返回 `UserRow` 而不是 UUID**。下游要角色（`require_role`）、要 id（owner 校验），一次查库都带来。`UserRow` 本来就不含 `password_hash`（D1 的最小暴露判据），出依赖层不泄密。
2. **复用 `user_repo.get()`**（`user_repo.py:16`，主键查 `session.get(User, user_id)`）——主键查询是 B+ 树最短路径，一行数据、一次树 descent，这是全项目最便宜的一次查询。
3. **封禁抛 401 不是 403**——为什么，见 §四判据表，这是 D3 最容易答错的一道面试题。

改完后，所有路由把 `Depends(get_current_user_id)` 换成 `Depends(get_current_user)`。受影响的 import 位置：`api/v1/knowledge_bases.py:9`、`api/v1/documents.py:9`（grep `get_current_user_id` 全找到）。

---

## §三 概念逐层：RBAC 与依赖工厂（A/B）

### 3.1 RBAC 是什么（术语首现，A）

**RBAC = Role-Based Access Control，基于角色的访问控制**。一句话：**权限不直接发给人，发给角色，人通过角色获得权限**。

没有 RBAC 时，你要写"如果 user_id 在这份白名单里才能删库"——权限和人绑死，换人就要改代码。RBAC 把它拆成三层：

```
用户（users 表的一行）──拥有──▶ 角色（role 字段：member / admin）──允许──▶ 操作（删任何用户、封禁人）
```

你项目里 RBAC 的载体：`users.role`（`models.py:103`，默认 `"member"`）。今天要落的是：**"操作"这一侧的检查器**。

### 3.2 为什么不直接写 `if user.role != "admin"`（B）

可以，但每个 admin 端点都要复制一遍，漏一处就是权限漏洞。**依赖工厂**把它收敛成一个可复用的依赖：

```python
def require_role(*roles: str):
    """依赖工厂：返回一个 FastAPI 依赖函数（闭包记住要求的角色）。"""
    async def _check(user: UserRow = Depends(get_current_user)) -> UserRow:
        if user.role not in roles:
            raise ForbiddenError("权限不足")
        return user
    return _check

# 用法：路由参数里
async def ban_user(
    user_id: UUID,
    _admin: UserRow = Depends(require_role("admin")),   # ← 非.admin 直接 403
    session: Session = Depends(get_db),
) -> None:
    ...
```

拆开看三层机制：

- **`require_role("admin")` 是函数调用**，调用发生在**应用启动、路由装饰器收集依赖时**，返回值 `_check` 是一个函数——这个函数"记住"了 `"admin"` 这个参数（闭包）。
- **`Depends(require_role("admin"))` 拿到的是那个函数**，FastAPI 在每个请求上执行它。回忆 mypy 那次的对照：`obj.method` 是拿机器，`obj.method()` 才是产品；这里反过来利用了"拿机器"——把**还没执行的函数**交给 FastAPI，由它在请求时执行。
- **依赖链**：`_check` 自己 `Depends(get_current_user)`，而 `get_current_user` 又 `Depends(get_db)` 和 `_bearer_scheme`——FastAPI 会递归解析整条链。**链不是白走的**，见 3.3。

### 3.3 依赖缓存：同一次请求里 get_db 只跑一次（B）

关键机制：**同一个请求内，同一个依赖函数默认只解析一次**（FastAPI 的 `use_cache=True` 默认值）。

假设一个请求同时触发 `_bearer_scheme → get_current_user → get_db` 和路由自己的 `session: Session = Depends(get_db)`：

```
get_db        → 第 1 次解析，建 Session，之后缓存命中
get_current_user → 复用同一个 Session ✓
require_role("_check") → 复用同一个 get_current_user 结果 ✓（连查库都只查一次）
```

这意味着：**一次请求哪怕五个依赖都查当前用户，users 表也只被查一次**。这就是"验人要查库"不会把性能炸掉的机制层保障。

> L 级一句话：`Depends(f, use_cache=False)` 可以强制每次重新解析，用于"故意要两个独立实例"的场景（本项目用不到，知道存在即可）。

---

## §四 401 vs 403：判据表（A，本周最易错）

两个码都表示"不行"，区别在**卡在哪一层**：

| 码 | 含义一句话 | 卡在哪 | 触发场景（你项目） | 抛的异常 |
|---|---|---|---|---|
| **401 Unauthorized** | **我不知道你是谁**（合法意义上的） | 身份层：票有问题**或人有问题** | 没带票 / 票假 / 票过期 / **用户已删除** / **用户被封禁** | `UnauthorizedError` |
| **403 Forbidden** | **我知道你是谁，但你不能动这个** | 权限层：身份合法，资源不归你 / 角色不够 | A 访问 B 的 KB（`kb_service.py:41`）/ member 调 admin 端点 | `ForbiddenError` |

**封禁为什么归 401？** 这是面试必踩的坑。两种流派都存在，但你必须给出判据而不是背答案：

- 封禁 = **身份被吊销**。"账号已被封禁"的意思是这个票不再对应一个合法身份——和"票过期"本质相同（都是"这票不能代表任何人了"），所以 401。
- 归 403 的流派理由是"身份真、权限无"。**听起来也对，但有个实际差别**：401 语义上应该触发客户端**重新认证**（重新登录），而封禁用户重新登录也登不进来（D2 的 login 没查 is_banned——注意！这也是今天的活），401 更诚实。
- **判据句**：401 = 这张票此刻失效（换张票也没用，如果人是封的）；403 = 票是好的，只是不够格。

**顺手抓一个今天发现的连带漏洞**：D2 写的 `login`（`auth_service.py`）没有检查 `is_banned`——被封用户**还能登录换新票**。查库验人修好了 API 层，登录层却是发新票的口子。动手任务里一起堵上。

---

## §五 多租户隔离：owner 校验的两种模式（A）

### 5.1 术语首现：租户 / 越权

- **租户（tenant）**：数据的归属方。本项目当前形态是**"租户=用户"**——每条 KB/doc 都属于一个 user（`owner_id`）。多组织形态（一个公司一个租户）在 W14 做。
- **越权**：访问不属于你的数据或操作。分两个方向：
  - **横向越权**：同级之间。用户 A 用自己的合法 token 访问用户 B 的 KB——身份没问题、票没问题，纯粹是"动了别人的东西"。
  - **纵向越权**：低角色拿高角色的操作。member 调 admin 端点。
- 本周 **D5 会故意把这两类漏洞注入代码再修**；今天先把"防越权的写法"显式化成契约。

### 5.2 两种 owner 校验模式（A，核心判据）

你项目里已经同时存在两种模式，先看清它们各自的失效方式：

**模式一：条件进 SQL（查询内过滤）**——`kb_repo.py:45` `list_by_owner`：

```python
.where(KnowledgeBase.owner_id == owner_id)   # 不属于我的行根本不进结果
```

- 优点：**默认安全**。忘了传 owner_id 会被 mypy 抓（参数必填）；想漏都难。
- 失效方式：**只能覆盖"能进 WHERE 的查询"**。聚合、跨表 JOIN 后再过滤的场景写起来别扭。

**模式二：取回后检查（fetch-then-check）**——`kb_service.py:35` `get_or_403`：

```python
row = self.repo.get(kb_id)          # repo.get 只有 kb_id，没有 owner 条件（kb_repo.py:41）
if row is None:
    raise NotFoundError("知识库不存在")
if row["owner_id"] != user_id:      # 取回来再比
    raise ForbiddenError("无权访问该知识库")
```

- 优点：能区分"不存在"和"无权"，报错语义准。
- 失效方式：**靠调用纪律**。`repo.get()` 是公开方法，任何人可以绕过 `get_or_403` 直接调它——漏掉检查不会报错，只会静默泄漏数据。这属于代码 review 检查单里的**静默失效**：最阴的一档。

**判据句（写进你的检查单）：能进 WHERE 的 owner 条件必须进 WHERE；做不到的场景（按 id 直取、跨表取回）必须收敛到唯一一个检查函数（这里是 `get_or_403`），并让所有路由只准通过它拿数据。检查点越少，越权面越小。**

### 5.3 全链路盘点表（今天的产出物之一）

把 KB/doc 十个端点的 owner 校验逐个点名（现状已核对，你动手任务里验证"每条真的在拦"）：

| # | 端点 | 校验位置 | 模式 | 现状 |
|---|---|---|---|---|
| 1 | `POST /kbs` | `kb_repo.py:29` 写入 owner_id | 声明 | ✅ |
| 2 | `GET /kbs`（列表） | `kb_repo.py:48` WHERE owner_id | 模式一 | ✅ |
| 3 | `GET /kbs/stats/count` | `kb_repo.py:57` WHERE | 模式一 | ✅ |
| 4 | `GET /kbs/{id}` | `kb_service.py:35` get_or_403 | 模式二 | ✅ |
| 5 | `PATCH /kbs/{id}` | `kb_service.py:55` 先 get_or_403 | 模式二 | ✅ |
| 6 | `DELETE /kbs/{id}` | `kb_service.py:63` 先 get_or_403 | 模式二 | ✅ |
| 7 | `POST /kbs/{kb_id}/documents` | `doc_service.py:46` get_or_403 | 模式二 | ✅ |
| 8 | `GET /kbs/{kb_id}/documents` | `doc_service.py:57` get_or_403 | 模式二 | ✅ |
| 9 | `GET /documents/{doc_id}` | `doc_service.py:71` 经 doc 的 kb_id 回查 | 模式二 | ✅ 但多一跳 |
| 10 | `DELETE /documents/{doc_id}` | `doc_service.py:78` 同上 | 模式二 | ✅ 但多一跳 |

**#9/#10 值得停一下**：doc 表自己没有 owner 字段，归属要经 `doc.kb_id → kb.owner_id` 两跳推出。这是**间接归属**，检查写法必须跟着走（先查 doc、再拿它的 kb_id 过 get_or_403），**不能**直接 `repo.get(doc_id)` 就返回——漏了那一跳就是横向越权。

**一个产品决策的复认**（`kb_service.py:40` 注释原文）：owner 不匹配返回 403 而非 404。代价是**资源枚举**——攻击者扫 id，403 告诉他"这个 id 存在，但不是你的"，404 则什么都不说。私密性要求高的系统（网盘）会选 404。你的项目保留 403 + 注释，判据是"知识库 id 是 UUID 随机的，枚举成本高"——**但这个权衡必须能说出来，不能只是没想过**。

---

## §六 易错点表（A）

| # | 错法 | 后果 | 正解 |
|---|---|---|---|
| 1 | 改了 `get_current_user` 但路由还 `Depends(get_current_user_id)` | 漏改的端点继续验签不验人，**静默** | 改名替换法：不留旧函数，grep 零残留 |
| 2 | `require_role` 里再查一次库 | 每请求两次 users 查询 | 复用 `Depends(get_current_user)`，靠依赖缓存只查一次 |
| 3 | 封禁用 403 | 语义混乱：客户端以为重登有用 | 封禁=身份吊销 → 401 |
| 4 | `login` 不查 `is_banned` | 封的人换新票照样进，验人白修 | 登录前查 credentials 行（含 is_banned）——注意 `get_credentials_by_email` 只有 id+hash，**别把 is_banned 塞进它**，另查或扩一个行类型 |
| 5 | 把 `is_banned`/`role` 签进 token | 封禁/降权不生效（D2 第 6 题同判据） | 状态永远查库，token 只带 sub |
| 6 | doc 端点直接 `repo.get(doc_id)` 不回查 kb | 横向越权，静默 | 间接归属必须走两跳（§5.3 #9/#10） |
| 7 | admin 接口写 `if user.role != "admin"` 散落各处 | 漏一处=漏洞；新角色要改 N 处 | `require_role` 工厂单点收敛 |
| 8 | 以为依赖链每层都重新查库 | 白白担心性能 / 或误以为没有开销 | 依赖缓存：同请求同依赖只解析一次 |
| 9 | ban 测试写完就过，没做变异 | 测试可能根本没守到查库那行 | 删掉查库段 → 测试必须红（动手任务验收） |

---

## §七 命令速查

```powershell
# Windows PowerShell —— 均在 kb-service 目录下

# 0. 痛点实验：封禁后旧 token 是否还好使（预期 200 = 漏洞实锤）
& .\.venv\Scripts\python.exe -m uvicorn kb_service.main:app --host 127.0.0.1 --port 8000
# 另开终端：
$tok = curl.exe -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"demo1@example.com","password":"correct-horse-9"}'
# 取 token 后打 kbs，再执行封禁 SQL，再打一次对比
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev -e "UPDATE users SET is_banned=1 WHERE email='demo1@example.com';"

# 1. 找出所有待换的旧依赖引用
Select-String -Path src\kb_service\**\*.py -Pattern "get_current_user_id"

# 2. 给自己造一个 admin（dev 手段，别进生产思维）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev -e "UPDATE users SET role='admin' WHERE email='demo1@example.com';"

# 3. 门禁
& .\.venv\Scripts\python.exe scripts\check.py
```

```bash
# Git Bash / Linux / macOS —— 真机上 .venv/bin/python，Windows 的 Git Bash 用 .venv/Scripts/python.exe
grep -rn "get_current_user_id" src/
./.venv/Scripts/python.exe scripts/check.py
```

---

## §八 面试问法

**30 秒版（背这段）**：

> "我的鉴权分两层。第一层验签：JWT 验签名、篡改、过期——这只证明票是真的，不证明持票的人还是合法用户。第二层验人：`get_current_user` 依赖拿 sub 查库，验存在、验封禁、取角色，封禁用户旧 token 下一个请求就 401。代价是每请求一次主键查询，换来的是撤销能力——状态放 token 里封禁就不生效，这是设计上想清楚的取舍。资源层再加 owner 校验防横向越权：能进 WHERE 的进 WHERE，不能的收敛到 get_or_403 单点检查。"

**追问链三层**：

1. **机制层**：401 和 403 怎么分？→ 身份层/权限层；封禁为什么 401（身份吊销）；JWT 无状态为什么还要查库。
2. **边界故障层**：每请求多一次查询，QPS 高了怎么办？→ 主键查走 B+ 树 O(1) 页读，可承受；再往上谈缓存 + 短 TTL（注意 TTL 内封禁不生效的窗口，又是撤销 vs 性能的同一权衡）；长事务里 ban check 已过、事务中途被封怎么办（窗口存在，接受并说清）。
3. **场景落地层**：多节点部署，节点 A 封禁、节点 B 的本地缓存还有旧角色？→ 我项目是每请求查库天然一致；引入缓存后要谈失效策略；横向越权怎么系统防？→ owner 条件契约 + 注入式验收（D5 实测）。

---

## §九 闭卷自测（题目清单先看，答案折叠在最后）

1. 验签保证了哪三件事？第四件它保证不了的是什么？
2. `get_current_user` 相比 `get_current_user_id` 多了哪一步？这一步的代价和收益各一句话？
3. 封禁用户的旧 token 打接口，返回 401 还是 403？说判据。
4. `require_role("admin")` 为什么做成"函数返回函数"？直接写个 `check_admin(user)` 每个路由手动调用行不行？差在哪？
5. 同一个请求里 `get_db` 被 3 个依赖用到，Session 建几次？靠什么机制？
6. `list_by_owner` 和 `get_or_403` 各是什么模式？各自的失效方式？
7. 横向越权和纵向越权各一句定义，各举你项目里的一例。
8. doc 详情接口为什么必须"先查 doc、再拿 kb_id 过 get_or_403"，不能直接返回？

<details>
<summary>参考答案（点开前先在纸上写）</summary>

1. 真票（签名对）、未篡改、未过期；保证不了"sub 指向的人现在是否合法"——签名只绑票不绑持票的手，状态在库里。
2. 多一次主键查询（`session.get(User, id)`）；代价 = 每请求一次 B+ 树单行读（最便宜的查询），收益 = 撤销能力（封禁/删号即时生效）。
3. 401。判据：封禁=身份吊销，票不再对应合法身份，与"票过期"同类；403 留给"身份合法但不够格"。补充：401 语义上触发重登，封禁者重登也应失败（login 也要查 is_banned）。
4. 依赖工厂让 FastAPI 在请求时自动执行检查、把"检查"变成依赖图的一部分（漏写 `Depends` 会被类型/参数缺失暴露）；手动调用靠人记得，漏一处静默越权。另外工厂能进依赖缓存，与 get_current_user 共享一次查库。
5. 一次。FastAPI 同请求内依赖结果默认缓存（use_cache=True），同函数只解析一次。
6. `list_by_owner` = 查询内过滤（条件进 WHERE，默认安全，失效方式是"覆盖不了不能进 WHERE 的查询"）；`get_or_403` = 取回后检查（能区分不存在/无权，失效方式是"靠调用纪律，绕过它直接调 repo.get 不报错"）。
7. 横向：同级用户之间访问彼此资源（A 的 token 打 B 的 KB，应 403）。纵向：低角色做高角色操作（member 调 admin 端点，应 403）。
8. doc 表没有 owner 字段，归属是间接的（doc.kb_id → kb.owner_id）。直接返回 = 跳过归属推算 = 任何登录用户可读任何 doc（横向越权）。

</details>

---

## §十 动手任务（交付物清单 + 验收标准）

> 老规矩：判什么不给怎么写。卡 10 分钟 → 翻教材对应节 → 合上凭记忆写 → 才允许抄并标记。§九 自测过 6 题以上才开工。

### 交付物 0 · 痛点实验（30 min，先红后改）

封禁 demo1 用户 → 旧 token 打 `GET /api/v1/kbs` → **记录 200 这个读数**（截图进实测记录）。这是今天的"变异验证前置"：先亲眼看到漏洞，再修。

### 交付物 1 · `get_current_user` 替换（核心，A）

- **动作**：`deps.py` 新增 `get_current_user`（骨架 §二），**删除** `get_current_user_id`，全链路引用替换（grep 零残留）。
- **验收**：封禁用户旧 token → **401**；删除场景（SQL 删行后旧 token）→ 401；正常用户不受影响。
- **变异验证（必做）**：注释掉查库那三行 → 你写的封禁测试必须红；恢复 → 复绿。这就是周计划那句"删掉查库那步，封禁就静默失效 = 真落了"。

### 交付物 2 · `login` 堵口子（§六易错点 4）

- **验收**：封禁用户登录 → 401，文案与"密码错"**不区分**（不给封禁状态探测口）；未封禁登录不受影响。

### 交付物 3 · `require_role` + admin 路由（B）

- **动作**：`deps.py` 加 `require_role` 工厂；新增 admin 路由（建议 `api/v1/admin.py`）：
  - `GET /api/v1/admin/users`：用户列表（复用/扩展 `UserOut`，admin 视角可含 `is_banned`）
  - `PATCH /api/v1/admin/users/{user_id}`：改 `is_banned`（封禁/解封，这是封禁功能的真实入口，替代交付物 0 里的 SQL 手改）
- **验收**：member 调这两个端点 → **403**；admin → 200；封禁后**用被封者的旧 token** 立刻打 kbs → 401（全链路闭环，不再用 SQL 模拟）。
- **落点核销预告**：admin 路由就是本周 `require_role` 的 `文件:行号` 证据。

### 交付物 4 · 测试（`tests/test_rbac.py`，代写可喊我）

至少 5 条：封禁→旧 token 401 / login 封禁 401 / member 调 admin 403 / admin 改 ban 200 / 横向：A 的 token 打 B 的 KB → 403（这条是 D5 注入验收的预演，先立一个绿的）。

### 交付物 5 · 多租户盘点落档（A）

- **动作**：把 §5.3 盘点表核对一遍（每行亲手 curl 一遍不现实的，挑 #4/#9 两条实测 403），写进 `progress/week8/D3-实测记录.md`；加一节"owner 条件契约"三行判据（§5.2 判据句照抄即可）。
- **验收**：实测记录里 #9 的探针读数 = 403；契约三行在档。

### 清债槽（45 min：④ + ⑧）

- **④ `updated_at` 返回旧值**（20 min）：`kb_repo.py` update 分支，PATCH 成功后返回的行里 `updated_at` 是旧值——原因与 flush/expire 有关，验收 = PATCH 响应里的 `updated_at` 与 MySQL 直查一致。
- **⑧ 过期 docstring 清理**（15 min）：`deps.py:32` 的 "W8 TODO：换成 OAuth2PasswordBearer" 今天就过期了——顺手清掉；grep `TODO` 找出已经做完的，全部销账。
- 详细验收标准见 `D1-清债作战单.md`。

### 纸笔巡检（内容学完再做，10 min）

**W4 测试骨架**：合上一切，画出 conftest 三件套（DATABASE_URL 钉死 sqlite / client fixture / db fixture 清表）+ 一条典型测试的依赖链。写不出画 `?`，对照 `tests/conftest.py` 补。

---

## §十·五 业务链条三问（固定节）

1. **哪个用户可见行为**：管理员封禁某账号 → 该账号**下一个请求**就被拒（不等 token 过期）；member 永远进不了 admin 页面；A 永远看不到 B 的知识库。
2. **不做会怎样**：封禁功能等于没有（1 小时票据横行）；admin 端点裸奔（任何登录用户可封禁别人——这是纵向越权事故）；用户之间互相翻数据（横向越权，知识库产品直接不可用）。
3. **可复现指标**（不许编百分比）：封禁后旧 token 请求状态码 401（前后对比 200→401）；member 打 admin 端点 = 403；每请求新增 SQL 恰好 1 条主键 SELECT（可开 echo 实数）；横向探针 403。

---

## §十一 收尾清单

- [ ] 交付物 0–5 + 清债槽 ④⑧ 全部有读数
- [ ] 变异验证做过一次（删查库 → 红 → 复绿）
- [ ] 三类比例（自写 / 翻看后写对 / 照抄）报数
- [ ] 实测记录写 `D3-实测记录.md`（含痛点实验的 200 读数截图）
- [ ] 总结写 `总结/D3-验人与RBAC-总结.md`（总结先行，别重蹈 D5/D6 覆辙）
- [ ] 生成当日 commit + push 命令块
- [ ] 关后台任务（MySQL 3307 / uvicorn）
