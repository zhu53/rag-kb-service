# Day2 · 断点调试（PyCharm 版 · 3h）

> **今天的目标只有一个**：让程序停在你想停的地方，看着变量一个个变化。  
> 学完这一天，你会第一次有"能看见程序内部"的感觉 —— 这是从"猜 bug"到"看 bug"的分水岭。
>
> ⚠️ 今天不写新功能，只练调试。所有改动最后都要还原。

---

## 0. 前置检查（5 分钟）

### 0.1 用 PyCharm 打开**正确的目录**

```
PyCharm → File → Open → C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap
```

**打开仓库根，不是 kb-service 子目录。** 原因：

- [ ] 你的 `.idea` 配置在根目录（PyCharm 已经把 `kb-service` 识别为 Python 模块）
- [ ] 这样 `progress/`、`学习路线-24周.md` 都在项目里，随时能看
- [ ] 左侧项目树顶部显示 `python-backend-roadmap`
- [ ] 展开能看到 `kb-service`（蓝色文件夹图标 = 模块）、`progress`、`README.md`

### 0.2 确认解释器

右下角状态栏应该显示 **`Python 3.11 (.venv)`** 或类似字样。

如果不是：**File → Settings → Project → Python Interpreter → 添加 → 选 `kb-service\.venv\Scripts\python.exe`**

- [ ] 右下角显示的是 .venv 里的 Python 3.11

### 0.3 确认运行配置已就位

右上角运行下拉框里，应该有这三项（我已经帮你配好了 `.run/` 目录）：

- [ ] `FastAPI: uvicorn (debug)`
- [ ] `pytest: current file`
- [ ] `pytest: whole suite`
- [ ] 下拉框里能看到这三项

**如果看不到**：重启 PyCharm（它会加载 `.run/` 目录）。还是没有的话，手动建一个：`Run → Edit Configurations → + → Python`，参数照下面填：

| 字段                | 值                                                                             |
| ----------------- | ----------------------------------------------------------------------------- |
| Module name       | `uvicorn`（**选 module 单选按钮**，不是 Script path）                                   |
| Parameters        | `kb_service.main:app --reload --port 8000`                                    |
| Working directory | `...\python-backend-roadmap\kb-service`                                       |
| Interpreters      | 项目 venv                                                                       |
| EnvFile           | `...\python-backend-roadmap\kb-service\.env`（PyCharm 2023+ 支持，底部有 EnvFile 标签） |

### 0.4 验证测试能跑

用 `pytest: whole suite` 跑一次。底部 Run 窗口应显示 `8 passed`。

- [ ] 8 passed

---

## 1. 认识 PyCharm 调试界面（30 分钟）

### 1.1 启动调试

选 `FastAPI: uvicorn (debug)`，点 **🐞 虫子图标**（或 `Shift+F9`）。

区别：**▶️ 绿色三角是"运行"（不调试），🐞 虫子是"调试"（能打断点）**。这是 PyCharm 新手最容易搞混的一点。

等 Console 出现：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

调试启动后，PyCharm 底部会多出一个 **`Debug` 标签页**。

- [ ] 服务起来了，底部有 Debug 标签

### 1.2 六个按钮（PyCharm 的图标和位置与 VS Code 不同）

调试暂停时，**Debug 窗口左上角**有一排按钮（也可以记快捷键）：

| 按钮                 | 快捷键        | 作用                                |
| ------------------ | ---------- | --------------------------------- |
| ▶️ Resume Program  | `F9`       | 继续跑到下一个断点                         |
| ⤵️ Step Over       | `F8`       | **执行当前行**，不进入函数                   |
| ⬇️ Step Into       | `F7`       | **进入函数内部**                        |
| 🎯 Smart Step Into | `Shift+F7` | **一行里有多个调用时，让你选进哪一个** ⭐PyCharm 独有 |
| ⬆️ Step Out        | `Shift+F8` | 执行完当前函数，回到调用处                     |
| ⏹ Stop             | `Ctrl+F2`  | 停止                                |

**一句话记住**：

> **F8 = 跳过，F7 = 钻进去，Shift+F8 = 钻出来，F9 = 跑到下一个断点。**

⚠️ **和 VS Code 最大的不同**：F5 在 PyCharm 里是**重新启动调试**，不是继续！按错会导致反复重启，这是最常见的困惑。

- [ ] 我能不看表说出 F8 / F7 / F9 分别是什么

### 1.3 认识五个关键面板

**Debug 窗口**里有两个标签：**Debugger** 和 **Console**。

切到 **Debugger** 标签，左侧是三个窗口：

| 面板                | 作用        | 为什么重要           |
| ----------------- | --------- | --------------- |
| **Frames**（调用栈）   | 谁调用了当前函数  | **排查最有力的工具**    |
| **Variables**（变量） | 当前作用域所有变量 | 看值、改值、看嵌套对象     |
| **Watches**（监视）   | 手动输入表达式盯着 | 比如盯 `len(rows)` |

**PyCharm 独有的杀手功能**：

- [ ] **Inline Values**：代码行右边**直接显示变量的值**（不用展开面板看）
- [ ] **行内求值**：选中一个表达式，右键 → `Evaluate Expression`（`Alt+F8`），可以在暂停时**执行任意代码**，比如 `len(store.kbs)`
- [ ] **Set Value**（`F2`）：**临时改变量的值**，不用改代码就能测试边界情况
- [ ] 我找到了 Frames / Variables / Watches 三个面板
- [ ] 我试过 `Alt+F8` 求值

---

## 2. 第一个断点（30 分钟）

### 2.1 打第一个断点

打开 `kb-service/src/kb_service/api/v1/health.py`，**在第 12 行**点行号右边的空白处，出现**红色圆点**。

```python
10: @router.get("/health")
11: async def health() -> dict[str, str]:
12:     settings = get_settings()          # ← 断点打这里
13:     return {"status": "ok", "env": settings.env, "version": "0.1.0"}
```

> 红点 = 普通断点；**红点带对勾 = 条件断点**；灰点 = 被禁用。

### 2.2 触发断点

**用浏览器打开 <http://127.0.0.1:8000/api/v1/health>**

- [ ] 页面转圈（程序停在断点了）
- [ ] PyCharm 自动跳到 `health.py`，当前行**高亮成蓝色**
- [ ] Debugger 的 Variables 面板能看到变量
- [ ] 代码行右边出现了灰色的值提示（Inline Values）

### 2.3 观察

在 Variables 面板里找到 `settings`：

- 展开它，看 `env` 的值（`'dev'`）
- 或者把鼠标悬停在代码里的 `settings` 上，弹出浮窗

按 **`F9`**（Resume），浏览器立刻返回 JSON。

> ⚠️ 不要按 F5，那是重启。

- [ ] 页面正常返回了

---

## 3. 三个必练动作（70 分钟）

### 3.1 条件断点（15 分钟）

**场景**：接口每秒被调 100 次，我只想在某个特定 id 的请求上停。

1. 打开 `kb-service/src/kb_service/services/kb_service.py`，在**第 26 行** `row = self.repo.get(kb_id)` 打断点
2. **右键那个红点** → 在弹出的菜单里填 **Condition**
3. 输入：`str(kb_id).startswith("f")`
4. 回车

**两种触发方式**：

- 直接在代码里右键红点填条件（快）
- 或 `Ctrl+Shift+F8` 打开 **Breakpoints 总览**（能看到所有断点，也能加条件）

**验证**：去 `/docs` 调两次 `GET /api/v1/kbs/{kb_id}`：

- [ ] 传 `11111111-1111-4111-8111-111111111111` → **不停**
- [ ] 传 `ffffffff-ffff-4fff-8fff-ffffffffffff` → **停住**
- [ ] 两次行为不同，我亲眼看到条件生效
- [ ] 我能说出：红点带对勾说明是条件断点

> **面试点**：条件断点、日志断点（PyCharm 里叫 **Logging Breakpoint**，右键红点可以"只打印不暂停"）是抓偶现 bug 的利器。1/1000 概率的 bug，普通断点等不到，条件断点能精准捕获。

### 3.2 异常断点（15 分钟）

**场景**：报错栈太长，不知道异常在哪一行第一次抛出。

1. `Ctrl+Shift+F8` 打开 **Breakpoints** 总览窗口
2. 左侧列表里勾选 **`Any Exception`**（或在 "Python Exception Breakpoints" 区域勾选）
3. 可以进一步配置：勾 "On raise" 表示**抛出时立刻停**，勾 "Ignore library frames" 表示跳过第三方库的异常
4. 去 `/docs` 调 `GET /api/v1/kbs/00000000-0000-0000-0000-000000000000`（不存在的知识库）

**程序会停在 `raise NotFoundError(...)` 那一行**（而不是返回 404 的那一层）。

- [ ] 停在 `raise NotFoundError("知识库不存在")` 这行
- [ ] **Frames 面板**里能看到调用链

展开 Frames 从上往下看 —— 这是你第一次"看见"分层：

```
get_or_403      ← services 层抛的
get_kb          ← api 层调的
...
```

- [ ] 我能说出异常是在 services 层抛出的，不是 api 层

> **用完记得取消勾选** `Any Exception`，否则后面任何异常（哪怕是框架内部的正常控制流）都会停。

### 3.3 Step Into 依赖注入链（40 分钟）⭐ 今天的核心

**目标**：亲手走一遍 FastAPI 的 `Depends` 到底怎么工作。

**步骤**：

1. 打开 `kb-service/src/kb_service/api/v1/knowledge_bases.py`，在 `list_kbs` 第一行（`return KBService().list(...)`）打断点
2. 触发：`/docs` 里调 `GET /api/v1/kbs`
3. 停住后看 Variables：**`user_id` 已经有值了** —— 说明 `Depends` 在函数体执行**之前**就跑完了
4. 现在在 `kb-service/src/kb_service/api/deps.py` 的 `get_current_user_id` 函数里也打个断点
5. 重新触发（F9 继续 → 刷新请求，或者重启调试）
6. 停在 `deps.py` 后，按 **`F7`（Step Into）** 进入 `decode_access_token`
7. 在 `decode_access_token` 里，把光标放在 `jwt.decode(...)` 这一行，按 **`Shift+F7`（Smart Step Into）**
   - **PyCharm 会弹出一个小菜单让你选进入哪个调用**（`jwt.decode` 还是 `UnauthorizedError`），选 `decode`
8. 这次你会**进入 `python-jose` 第三方库的源码**

- [ ] 我成功进到了第三方库源码（能看到 `jws.py` 之类文件名）
- [ ] 我看到了 `jwt.decode` 内部在干什么（至少看懂它是先 split 再验签）

**在 `progress/week1/调试记录.md` 的"Depends 源码跟踪笔记"里写下你看到的调用顺序（3-5 行）。**

> **为什么这个练习值钱**：面试问"FastAPI 依赖注入怎么实现"，99% 的人只会背"用 Depends 声明"。你能说出"在路由函数执行前按签名递归解析依赖树，同一次请求内缓存结果" —— 这是你亲手走出来看到的，不是背的。

---

## 4. 三个 bug 狩猎（40 分钟）

> 规则：**不许用 print，只能用调试器**。每次改完记得还原（`Ctrl+Z` 或 `git checkout`）。

### Bug #1 · `split_text` 参数非法

打开 `kb-service/src/kb_service/services/doc_service.py`，把：

```python
if overlap >= chunk_size:
```

改成：

```python
if overlap > chunk_size:
```

然后上传一个文档（`/docs` 里 `POST /api/v1/kbs/{kb_id}/documents`），观察会发生什么。

**提示**：这次的坑是 `step = chunk_size - overlap` 算出 **0**，`range(0, len(text), 0)` 立刻抛 `ValueError: range() arg 3 must not be zero`。用**异常断点**抓它，比读代码快得多。

| 项            | 你的答案 |
| ------------ | ---- |
| 现象           | ？    |
| 定位过程（用了哪个手段） | ？    |
| 根因           | ？    |

- [ ] 我定位到了，并且能解释"为什么 overlap == chunk_size 会导致 step=0"

还原：`git checkout kb-service/src/kb_service/services/doc_service.py`

### Bug #2 · 删掉 SECRET_KEY

把 `kb-service/.env` 里 `SECRET_KEY=` 后面的内容删空（只留 `SECRET_KEY=`），然后**重启调试**（`Ctrl+F5` 或点重启按钮）。

- [ ] 我看到了 `ValidationError`
- [ ] 我在调试器里能定位到是哪一行代码触发校验（提示：`get_settings()` → `Settings()`）

**关键问题**：这个错误是在服务启动时抛的，还是处理请求时抛的？为什么这样设计？

答：\__________

改回来。（建议先备份：`Copy-Item .env .env.bak`）

### Bug #3 · 路由里删掉 kb_id 参数

在 `kb-service/src/kb_service/api/v1/documents.py` 里，把 `create_doc` 的 `kb_id: UUID,` 这行注释掉。

- [ ] 我看到了 422
- [ ] 我能在 `/docs` 里看到 `detail` 的结构
- [ ] 我能说出：这个 422 是 **FastAPI 框架层**拦下的，业务代码根本没执行

还原：`git checkout kb-service/src/kb_service/api/v1/documents.py`

---

## 5. PyCharm 独有的 3 个效率技巧（10 分钟，白送）

这三个比断点更省时间，学会了一辈子受用：

### 5.1 Evaluate Expression（`Alt+F8`）

程序暂停时，按 `Alt+F8`，可以**执行任意 Python 代码**看结果：

```
len(store.kbs)                    # 直接查当前有几个知识库
[row["name"] for row in store.kbs.values()]
settings.model_dump()             # 整个配置长什么样
```

**不用改代码、不用重启**就能验证猜想 —— 这是调试器最强的功能。

- [ ] 我试过至少一个表达式

### 5.2 Set Value（`F2`）

在 Variables 面板里选中一个变量，按 `F2`，**直接改变量的值**。

比如把 `chunk_size` 从 400 改成 1，然后继续执行 —— 立刻能测出边界情况，**不用改代码**。

- [ ] 我试过临时改变量值

### 5.3 断点的高级设置（右键红点）

右键断点能看到这些选项：

| 选项                                    | 用途                        |
| ------------------------------------- | ------------------------- |
| **Condition**                         | 条件表达式                     |
| **Log message to console**            | **只打印不暂停**（日志断点，生产环境常用思路） |
| **Evaluate and log**                  | 打印任意表达式的值                 |
| **Remove once hit**                   | 只停一次就自动删除                 |
| **Disable until breakpoint X is hit** | 断点 A 命中后才启用 B（跨函数追踪神器）    |

- [ ] 我看过这个菜单

---

## 6. 收尾（20 分钟）

### 6.1 填调试记录

打开 `progress/week1/调试记录.md`，把 3 个 bug + Depends 跟踪笔记填完。

### 6.2 自测（口头回答）

1. Step Over 和 Step Into 的区别？
2. PyCharm 里 F5 是什么？和 VS Code 有什么不同？
3. 什么时候该用条件断点？
4. Frames 面板解决什么问题？
5. `Evaluate Expression` 能做什么 print 做不到的事？

- [ ] 5 个都能答出来

### 6.3 提交

在 PyCharm 底部 **Commit** 面板（或 `Ctrl+K`）：

```
docs(w1): 完成 Day2 断点调试练习记录
```

然后 `Ctrl+Shift+K` push。

或者在终端：

```powershell
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap
git add -A
git commit -m "docs(w1): 完成 Day2 断点调试练习记录"
git push
```

---

## 今日验收清单（9 条）

- [ ] PyCharm 打开的是仓库根目录，解释器是 `.venv` 的 Python 3.11
- [ ] 能用 🐞 启动调试，服务正常运行
- [ ] 能在 `health.py:12` 打普通断点，浏览器请求能打中
- [ ] 能用**条件断点**（红点带对勾）让程序只在特定请求上停
- [ ] 能开启**异常断点**（Any Exception），让程序停在 `raise` 那一行
- [ ] **成功 Step Into 到第三方库源码**（python-jose）
- [ ] 能用 Frames 面板看出异常的抛出层级
- [ ] 3 个 bug 全部定位并写进调试记录
- [ ] 试过 `Alt+F8` Evaluate Expression

---

## 今天的"知识点账户"

学会了这些，面试时你可以说：

> "我习惯用调试器而不是 print 排查问题。条件断点抓偶现问题，异常断点定位第一个抛出点，Frames 还原调用链，Evaluate Expression 不改代码就能验证猜想。我读过 FastAPI 的 Depends 实现，它在路由执行前按签名递归解析依赖树，同请求内缓存结果。"
