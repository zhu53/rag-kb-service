# W6-D5a 教材 · OpenAPI 文档定制（只讲一件事）

> 本篇只有一个主语：**`/openapi.json` 这份 JSON**。它怎么出生、存在哪、被谁看、你怎么改它。
> 全部断言本机实测（FastAPI 0.150.0 / Python 3.11）。读法：§一 先动手跑，看见东西再往回读。

## 零、主线：这份 JSON 的一生（三站）

```
① 构建     应用启动后第一次需要它时，把"路由表"翻译成 JSON
              ↓
② 缓存     存进 app.openapi_schema（印好一次，放柜台）
              ↓
③ 送出     GET /openapi.json 把它发出去；GET /docs 是浏览器拿它渲染成网页
```

**定制 = 在 ① 的时候改内容**（改构造参数、改路由装饰器、替换构建函数），或者在 ③ 的时候决定"要不要让人拿到"。

一句话记住：**你从来没在写文档，你一直在改这份 JSON。**

## 一、先看见它（3 分钟，三步）

**第 1 步**：看真实项目的这份 JSON 长什么样（不要打开 `/docs`，先看原始数据）。

```powershell
# Windows PowerShell，kb-service 目录
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; s = app.openapi(); print(list(s)); print(json.dumps(s['info'], ensure_ascii=False, indent=2)); print(list(s['paths']))"
```

你会看到顶层只有几个键：`openapi` / `info` / `paths` / `components`，可能还有 `tags`。`paths` 是全部接口路径。

**第 2 步**：看某一个接口的完整"说明书"。

```powershell
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; print(json.dumps(app.openapi()['paths']['/api/v1/kbs'], ensure_ascii=False, indent=2)[:1200])"
```

**第 3 步**：起服务，浏览器打开 `http://127.0.0.1:8000/docs`。

```powershell
& .\.venv\Scripts\python.exe -m uvicorn kb_service.main:app --reload --port 8000
```

对着看：网页上每一个分组、每一条接口说明、每一个参数字段，**都能在第 1、2 步的 JSON 里找到对应物**。`/docs` 里没有一处是"额外手写"的。

> 跑到这里你应该已经明白：`/docs` 不是文档，是**渲染器**。所以要定制文档，只有一条路——改 JSON。

## 二、菜谱类比：5 个键分别是什么

把 JSON 想成一家餐馆的**菜单**：

| JSON 键 | 类比 | 里面放什么 |
|---|---|---|
| `info` | 菜单封面 | 店名（title）、版本（version）、一句话介绍（description） |
| `paths` | 菜单正文 | 每道菜（接口）：叫什么（summary）、怎么点（参数）、端上来什么样（responses） |
| `components.schemas` | 菜单末尾的**配料附录** | 所有数据模型的定义；正文用 `$ref` 指向附录，避免每道菜重复写一遍配料 |
| `tags` | 菜单的**章节** | 前菜 / 主菜 / 甜点，每章配一句说明；也决定章节顺序 |
| `servers` | 封底的**门店地址** | 测试环境 / 生产环境的 base URL |

三个立刻能用的翻译：

- `$ref: '#/components/schemas/ApiResponse'` = "配料见附录第 3 条"，**不是**"这里复制一份"。
- `openapi_tags` = 只写章节名和章节说明；**它不决定哪道菜放哪章**，那是每道菜自己标的 `tags`。
- `responses` 的每个状态码 = "这道菜如果端不出来，我们怎么答复"。

## 三、改法四种（按"改哪一层"排）

### 3.1 改封面：`FastAPI(...)` 构造参数

```python
app = FastAPI(
    title=settings.app_name,      # 菜单封面店名
    version="0.1.0",              # 版本
    description="知识库检索服务：文档上传、切块、向量检索。",   # 一句话介绍，支持 Markdown
)
```

只影响 `info` 段。**这是投入产出比最高的一处**：前端打开 `/docs` 第一眼看的就是它。

### 3.2 改正文：路由装饰器上的五个字段

```python
@router.post(
    "",
    tags=["knowledge-bases"],
    summary="创建知识库",                       # 一行，列表页显示
    description="创建一个新的知识库。\n\n- 名称不可重复\n- 描述可为空",   # 多行，详情页显示，支持 Markdown
    response_description="创建成功，返回知识库本体",   # 只改"成功响应"那一行的说明
    deprecated=False,                          # True 时 /docs 里划灰线
    responses={401: {"model": ApiResponse, "description": "未认证（code=40100）"}},
    status_code=201,
)
```

实测进 JSON 的样子：

```
summary: 创建知识库
description: 创建一个新的知识库。
responses: {'201': {'description': '创建成功，返回知识库本体', ...},
            '401': {'description': '未认证（code=40100）', 'content': {'application/json': {'schema': {'$ref': ...}}}}}
```

两个要点：

1. **`responses=` 只写文档，不改行为**。写上 401 不代表接口真会返 401——那是 D4 的 handler 干的事。**文档和实现是两条独立的路，写歪了不会有任何报错**，这是 OpenAPI 最容易骗自己的地方。
2. `deprecated=False` 时 JSON 里**不出现**这个键；只有 `True` 才写（实测）。

### 3.3 改章节：`openapi_tags` + 一个必须的纪律

```python
TAG_KBS = "knowledge-bases"
TAG_DOCS = "documents"
TAG_CHAT = "chat"

app = FastAPI(
    openapi_tags=[
        {"name": TAG_KBS, "description": "知识库的增删改查"},
        {"name": TAG_DOCS, "description": "文档上传、切块、解析状态"},
        {"name": TAG_CHAT, "description": "基于知识库的问答（含流式）"},
    ],
)
```

**为什么必须用常量**（今天第一个坑，实测）：

```
tags 段：name='share'    desc=分享（故意写错：真实 tag 是 shares）
路由：  GET /shares      tags=['shares']
```

- 声明了 `share` 但没路由用 → `/docs` 里出现**一个没有任何接口的空章节**；
- 路由用了 `shares` 但没声明 → 自动出现，**没有说明，排在最后**。

**两侧都不报错、测试也不挂**。这就是为什么 tag 名要定义成常量、路由和 tags 表引用同一份——靠肉眼对齐迟早错一次，而错了没人告诉你。

### 3.4 改结构：替换 `app.openapi`

当你要加"菜单上没有的东西"——比如公司统一的 `x-team` 字段、多个 `servers`、全局安全声明：

```python
base_openapi = app.openapi          # ① 先把原方法存成变量，绝对不能省

def custom_openapi() -> dict:
    if app.openapi_schema:           # ② 命中缓存直接返回
        return app.openapi_schema
    schema = base_openapi()          # ③ 用存下来的原方法（不是 app.openapi()）
    schema.setdefault("servers", []).append({"url": "https://api.example.com", "description": "生产"})
    app.openapi_schema = schema      # ④ 写回缓存
    return schema

app.openapi = custom_openapi
```

**①③ 是今天最凶的坑**：`app.openapi = custom_openapi` 之后，`app.openapi` 已经指向**你自己**。函数体里再写 `app.openapi()` 就是自己调自己。本机实测：

```
RecursionError: maximum recursion depth exceeded
  File "...", line 130, in custom_openapi
    schema = app2.openapi()
  [Previous line repeated 966 more times]
```

它不会说"命名冲突"，只说 966 层递归——第一次遇到根本联想不到原因。**规则一句话：替换方法之前，先把原方法存成变量。**

**缓存语义**（实测，别记错）：

```
custom 函数被调用 3 次（3 次请求）
schema 真正构建 1 次
```

- 你的函数**每次请求 `/openapi.json` 都被调用**（它就是那个路由的处理函数）；
- 真正的"翻译路由表"**只发生 1 次**，之后走 `app.openapi_schema` 缓存。

**推论**：同一进程里动态加了路由，旧文档不会自己更新——得先 `app.openapi_schema = None`。（`--reload` 重启进程时自然清掉，所以开发时感觉不到。）

### 3.5 最后一个开关：从菜单里藏一道菜

```python
@router.get("/internal/stats", include_in_schema=False)
```

实测：`paths` 里没有它，但请求照样 200。**它不是权限控制**——只是从菜单上消失，猜得到路径的人都能点。

## 四、关掉它：生产环境要关三个门

```python
app = FastAPI(
    docs_url="/docs" if settings.env != "prod" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.env != "prod" else None,
)
```

实测三个全 `None`：`/docs` → 404，`/openapi.json` → 404。

**只关 `/docs` 是假关门**：JSON 还在，任何人 `curl /openapi.json` 就拿到全量接口清单。要关就三个一起，或者干脆在网络层挡。

## 五、易错点表

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | tag 名拼错 | **零症状**，`/docs` 出现空章节 + 无说明章节 | tag 名定义成常量，两处引用同一份 |
| 2 | 函数体里 `app.openapi()` | `RecursionError` 966 层 | 先 `base = app.openapi` 存原方法 |
| 3 | 以为改了路由文档会立刻生效 | 同一进程里文档不变 | `app.openapi_schema = None` 清缓存 |
| 4 | 只关 `docs_url` | `/openapi.json` 泄露全量接口 | 三个入口一起关 |
| 5 | 以为 `responses=` 会改行为 | 文档写 401，实际不返 401 | 它只写文档；行为在 handler |
| 6 | 在 `paths` 里手改 | 下次构建就被覆盖（缓存清了就没了） | 改源头（装饰器）或替换 `openapi()` |
| 7 | 用 `/docs` 验证改动 | 页面像缓存、看不出差异 | 一律以 `app.openapi()` 的 JSON 为准 |

## 六、命令速查

```powershell
# Windows PowerShell，kb-service 目录 ==================================
# 顶层键
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; print(list(app.openapi()))"

# tags 与说明
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; print(json.dumps(app.openapi().get('tags'), ensure_ascii=False, indent=2))"

# 某个接口的文档
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; import json; print(json.dumps(app.openapi()['paths']['/api/v1/kbs'], ensure_ascii=False, indent=2)[:1500])"

# 全部路径
& .\.venv\Scripts\python.exe -c "from kb_service.main import app; print(list(app.openapi()['paths']))"
```

```bash
# Git Bash / Linux =====================================================
# Windows 上的 Git Bash 用 ./.venv/Scripts/python.exe；真 Linux 用 .venv/bin/python
./.venv/Scripts/python.exe -c "from kb_service.main import app; print(list(app.openapi()['paths']))"
```

## 七、闭卷自测（先答，再展开）

<details>
<summary>1. `/docs` 和 `/openapi.json` 是什么关系？</summary>

`/openapi.json` 是框架自动生成的接口说明书（JSON）；`/docs` 是浏览器加载这份 JSON 后用 Swagger UI 渲染的网页。**没有 JSON 就没有页面**，页面上的每一个字都来自 JSON。

</details>

<details>
<summary>2. 定制文档，本质上在改什么？</summary>

改那份 JSON。三种入口：构造参数（`info` 段）、路由装饰器（`paths` 段）、替换 `app.openapi`（整份）。`/docs` 里没有一处是手写的。

</details>

<details>
<summary>3. tag 名写错了会怎样？</summary>

零报错。声明了没用 → 空章节；用了没声明 → 无说明章节、排最后。只有人打开 `/docs` 才看得出。所以 tag 名要用常量。

</details>

<details>
<summary>4. 为什么自定义 `openapi()` 必须先存原方法？</summary>

赋值后 `app.openapi` 已指向你的函数，函数体里再调 `app.openapi()` 就是自己调自己——实测 966 层 `RecursionError`。必须先 `base = app.openapi`。

</details>

<details>
<summary>5. 缓存的是"函数调用"还是"构建结果"？</summary>

构建结果。你的函数每次请求都被调用（3 次请求 = 3 次调用），但"翻译路由表"只做 1 次（`app.openapi_schema`）。所以动态加路由不会自动出现在文档里。

</details>

<details>
<summary>6. 生产环境怎么算"真关掉文档"？</summary>

`docs_url` / `redoc_url` / `openapi_url` 三个都设 `None`。只关 `/docs` 的话 `/openapi.json` 仍然泄露全量接口。

</details>

<details>
<summary>7. `responses={401: {"model": ApiResponse}}` 会改变接口行为吗？</summary>

不会。它只把"401 长什么样"写进文档（`model` 还会被注册进 `components.schemas`，用 `$ref` 复用）。真正的 401 由 D4 的 handler 产生。**文档与实现是两条路，写歪了不报错。**

</details>

## 八、今天上午的任务单（约 45 分钟）

按顺序做，每步都用 `app.openapi()` 的 JSON 验证，不看 `/docs`。

1. **加 `openapi_tags`**：三个分组 `knowledge-bases` / `documents` / `chat`，各写一句说明。tag 名在 `main.py` 里定义成常量（或放 `core/constants.py`），路由里的 `tags=["knowledge-bases"]` 换成常量引用。
   *验收*：`app.openapi()["tags"]` 有三条、顺序正确，且每个 tag 都至少有一个路由在用（不出现空章节）。
2. **补封面**：`FastAPI(description=...)` 写一句"这个服务是干什么的"。
3. **prod 真关**：现在只关了 `redoc_url`；把 `openapi_url` 也按 `env` 条件关掉。
   *验收*：把 `settings.env` 临时设成 `prod`（或直接改条件）看三个 URL 是否都 404，改回来。
4. **给 `create_kb` 补文档**：`summary` / `description` / `response_description` / `responses={401: {"model": ApiResponse, "description": "未认证（code=40100）"}}`。
   *验收*：JSON 里这个接口的 `responses` 同时有 `201` 和 `401`，401 的 schema 是 `$ref` 到 `ApiResponse`。

做完跑 `check.py`（应该 64 passed，文档改动不影响测试），然后把 `app.openapi()["tags"]` 和一个接口的 `responses` 片段贴给我。
