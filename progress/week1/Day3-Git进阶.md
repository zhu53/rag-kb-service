# Day3 · Git 进阶（3h）

> **今天的目标不是"记住更多命令"，而是建立三件事**：
>
> 1. **分支是你自己的实验场** —— 任何改动先在分支上做，坏了一句话丢弃
> 2. **提交历史是给别人看的** —— 一个提交只讲一件事，message 说清"为什么"
> 3. **规范靠工具强制，不靠自觉** —— pre-commit 让不合规的代码根本提交不进去
>
> 你昨天已经踩过 rebase 冲突的坑（误用 `--theirs` 导致双层重复目录），今天把那个坑拆开看清楚。

---

## 0. 先看你现在站在哪（5 分钟）

```bash
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap

git log --oneline --graph --all
git status
```

你应该看到 6-7 个提交，一条直线（没有分叉）。

**先理解一个事实**：你到现在为止**从没真正用过分支**。所有提交直接打在 `main` 上。这在小项目里能跑，但到了公司里——

- `main` 是**受保护的**，你不能直接 push，必须开分支 + 提 PR
- PR 被 review 后是 **Squash merge** 或 **Rebase merge**，你的多个零碎提交会被合并成一个干净提交
- 所以"提交历史干净"不是审美问题，是**协作要求**

> **面试点**：`main` 上的历史为什么要是线性的？因为要能用 `git bisect` 二分查找引入 bug 的提交。有 merge commit 的分叉历史会让 bisect 失效。

- [ ] 我跑过一次 `git log --oneline --graph --all`，看到了自己的提交历史

---

## 1. 分支实操（40 分钟）

### 1.1 开一个真分支，做一次真改动

今天的练习需要一个真实的功能点。我们给项目加一个**统计接口**（符合项目定位，W1 以后也用得到）。

```bash
# 从 main 开分支
git switch -c feat/stats-endpoint

# 确认切换成功（* 号在当前分支）
git branch
```

**现在写代码。** 打开 `kb-service/src/kb_service/services/kb_service.py`，在文件末尾（`class KBService` 内部，和其他方法同级）加一个方法：

```python
    def count_owned(self, user_id: UUID) -> int:
        """统计该用户拥有的知识库数量。"""
        rows, total = self.repo.list_by_owner(user_id, 0, 10_000)
        return total
```

> 先确认 `KBRepository` 有没有 `list_by_owner` 方法。如果没有，打开 `repositories/kb_repo.py` 看一眼实际方法名，按真实签名写。**这一步是故意的**——真实开发里你不会记得每个方法名，要用 IDE 的跳转（`Ctrl+B`）去查。

然后在 `api/v1/knowledge_bases.py` 加路由：

```python
@router.get("/stats/count", summary="我的知识库总数")
async def count_kbs(user_id: UUID = Depends(get_current_user_id)) -> dict[str, int]:
    return {"count": KBService().count_owned(user_id)}
```

> ⚠️ **注意路由顺序**：这个 `"/stats/count"` 必须写在 `@router.get("/{kb_id}")` **之前**。否则 FastAPI 会先匹配 `/{kb_id}`，把 `"stats"` 当成 UUID 解析，直接 422。这是个高频坑，记住。

**提交这次改动**：

```bash
git add -A
git commit -m "feat(kb): 新增统计当前用户知识库总数的接口"
```

- [ ] 分支建好了，代码写完了，提交成功了
- [ ] 我理解了路由顺序问题（`/stats/count` 必须在 `/{kb_id}` 之前）

### 1.2 amend：改掉刚提交的内容（含 message 写错）

**场景**：发现刚才的提交漏了一个文件，或者 message 打错字。

先在 `kb-service/tests/test_kb_api.py` 末尾加个测试：

```python
def test_count_kbs(client: TestClient) -> None:
    """统计接口应返回当前用户的知识库数量。"""
    for i in range(3):
        client.post("/api/v1/kbs", json={"name": f"kb-{i}"})

    resp = client.get("/api/v1/kbs/stats/count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 3
```

跑一下确认通过：

```bash
cd kb-service
./.venv/Scripts/python.exe -m pytest tests/test_kb_api.py -q
```

现在测试**还没提交**。用 amend 把它塞进上一个提交：

```bash
cd ..    # 回到仓库根
git add -A
git commit --amend --no-edit      # --no-edit 表示不改 message
git log --oneline -1              # 确认还是"一个"提交，不是两个
```

**如果是要改 message**：

```bash
git commit --amend -m "feat(kb): 新增统计当前用户知识库总数的接口（含测试）"
```

> ⚠️ **铁律**：`amend` 会改写提交历史（产生新的 commit hash）。**只能用于还没 push 的本地提交**。已经 push 到共享分支的提交再 amend，会让别人的历史和你分叉。

- [ ] 我用 `--amend` 把测试合并进了上一个提交，`git log` 里仍然只有一条
- [ ] 我知道 amend 会改变 commit hash，不能对已推送的提交用

---

## 2. rebase -i：整理提交历史（50 分钟）⭐ 今天的核心

### 2.1 制造三个"脏"提交

真实开发中你会边写边提交，历史长这样：`fix typo` → `再改一下` → `忘了加文件` → `final`。这种历史在 PR 里会被 reviewer 骂。

现在故意制造这个场景。在分支上做三次小提交：

```bash
# 提交 1：加一个 TODO 注释
echo "# TODO: 统计接口后续支持按时间范围过滤" >> kb-service/src/kb_service/api/v1/knowledge_bases.py
git add -A && git commit -m "wip: 加个注释"

# 提交 2：改一下措辞
sed -i 's/后续支持按时间范围过滤/后续支持按时间范围过滤（W8）/' kb-service/src/kb_service/api/v1/knowledge_bases.py
git add -A && git commit -m "改一下措辞"

# 提交 3：又改回来
sed -i 's/后续支持按时间范围过滤（W8）/后续支持按时间范围过滤/' kb-service/src/kb_service/api/v1/knowledge_bases.py
git add -A && git commit -m "算了改回去"
```

现在看历史：

```bash
git log --oneline -5
```

你要看到类似（从上到下是最新到最旧）：

```
xxx 算了改回去
xxx 改一下措辞
xxx wip: 加个注释
xxx feat(kb): 新增统计当前用户知识库总数的接口（含测试）
```

**三个提交讲的是同一件事：加一行注释。** 这就是要整理的。

### 2.2 交互式 rebase

```bash
git rebase -i HEAD~3
```

> **`HEAD~3` 意思是"最近 3 个提交"**。`HEAD~1` = 上一个，`HEAD~3` = 往前数 3 个。

会打开编辑器（vim 或你配置的编辑器），内容长这样：

```
pick abc1234 wip: 加个注释
pick def5678 改一下措辞
pick ghi9012 算了改回去
```

**每个 `pick` 是一个动作指令**。改成这样：

```
pick abc1234 wip: 加个注释
squash def5678 改一下措辞
squash ghi9012 算了改回去
```

`edit`（或 `e`）= 停下来让我改这个提交  
`squash`（或 `s`）= 把这个提交合并到**上一个**提交里，message 也合并  
`reword`（或 `r`）= 只改 message，不改内容  
`drop`（或 `d`）= 删掉这个提交  
`fixup`（或 `f`）= 合并到上一个，**丢弃**这个的 message

保存退出（vim 里是 `:wq`）。

接着会弹出第二个编辑器让你写合并后的 message。改成：

```
docs(kb): 加统计接口的时间范围过滤 TODO
```

**如果搞砸了想反悔**：

```bash
git rebase --abort        # 回到 rebase 之前
```

`rebase -i` 中途也可以随时 abort，这是它最安全的地方——**只要没 rebase --continue 到底，状态随时能退回来**。

- [ ] 我把 3 个提交压成了 1 个
- [ ] 我看到了 `pick` / `squash` / `reword` / `drop` / `fixup` 这几个指令
- [ ] 我知道 `git rebase --abort` 能随时反悔

### 2.3 ⭐ 重点：rebase 冲突到底怎么解

这是昨天你踩坑的地方。现在**故意制造一次冲突**，走完整流程。

**冲突是怎么来的**：`rebase` 的本质是"把当前分支的提交，一个个**重放**到目标分支的最新提交上"。重放时如果同一行代码被两边都改过，git 不知道听谁的 → 冲突。

**制造冲突**：

```bash
# 1. 在分支上改一行
sed -i 's/"""统计该用户拥有的知识库数量。"""/"""统计当前用户拥有的知识库数量（含已归档）。"""/' kb-service/src/kb_service/services/kb_service.py
git add -A && git commit -m "docs(kb): 补充计数方法说明"

# 2. 切回 main，改同一行
git switch main
sed -i 's/"""统计该用户拥有的知识库数量。"""/"""统计用户知识库数量。"""/' kb-service/src/kb_service/services/kb_service.py
git add -A && git commit -m "docs(kb): 精简计数方法说明"

# 3. 切回分支，rebase 到 main
git switch feat/stats-endpoint
git rebase main
```

**你会看到**：

```
CONFLICT (content): Merge conflict in kb-service/src/kb_service/services/kb_service.py
error: could not apply abc1234... docs(kb): 补充计数方法说明
```

打开那个文件，会看到：

```python
<<<<<<< HEAD
    """统计用户知识库数量。"""
=======
    """统计当前用户拥有的知识库数量（含已归档）。"""
>>>>>>> abc1234 (docs(kb): 补充计数方法说明)
```

**怎么读这个标记**（关键，昨天你就错在这里）：

| 部分                               | 含义                                        |
| -------------------------------- | ----------------------------------------- |
| `<<<<<<< HEAD` 到 `=======` 之间    | **当前分支（rebase 的目标，这里是 `main`）**&#x7684;内容 |
| `=======` 到 `>>>>>>> abc1234` 之间 | **正在被重放的那个提交**（你的分支改动）的内容                 |

> ⚠️ **在 rebase 里 `HEAD` 的含义和 merge 时是反的！**
>
> - **merge** 时：`HEAD` = 你当前所在的分支（比如 feat 分支）
> - **rebase** 时：`HEAD` = 你 rebase 到的目标（比如 main），因为 git 在临时检出 main 再往上叠
>
> 这就是为什么"`--theirs` / `--ours` 傻傻分不清"——**在 rebase 里它们指的对象是反的**，所以最好的做法是**手工编辑文件**，不要用 `--theirs`。

**正确做法**：手工编辑，删掉 `<<<<<<<`、`=======`、`>>>>>>>` 三行标记，留下你想要的内容。比如我想都保留：

```python
    """统计当前用户拥有的知识库数量（含已归档）。"""
```

然后：

```bash
git add kb-service/src/kb_service/services/kb_service.py
git rebase --continue
```

**如果 rebase 还有下一个冲突**，重复上面的流程。全部完成后再看历史：

```bash
git log --oneline --graph --all -10
```

你会看到分支从 main 顶端**线性生长**出来（不是分叉再合）。

**反悔重来**（如果搞乱了）：

```bash
git rebase --abort          # 完全退回 rebase 前
git reset --hard ORIG_HEAD  # 更暴力的回退（ORIG_HEAD 是 rebase 前的快照）
```

- [ ] 我亲手制造并解决了一次 rebase 冲突
- [ ] 我理解了 rebase 时 `HEAD` 指的是"目标分支"，和 merge 时相反
- [ ] 我明白了为什么冲突时**手工编辑文件**比 `--theirs` 安全

### 2.4 rebase vs merge：什么时候用哪个

|             | `git merge`             | `git rebase`            |
| ----------- | ----------------------- | ----------------------- |
| 历史形态        | 保留分叉，产生 merge commit    | 拉成一条直线                  |
| 是否改写历史      | 不改（只新增）                 | **改**（重新生成 commit hash） |
| 能不能对已推送的分支用 | 能                       | **不能**（会让别人历史混乱）        |
| 典型场景        | 合并到 main（保留"曾有一个分支"的事实） | 本地分支追平 main（把分叉抹平）      |
| 出问题怎么查      | `git log --graph` 一目了然  | 线性历史看不出"曾经并行"           |

**一句口诀**：

> **本地未推送 → rebase 让历史干净；已推送/共享 → merge 保平安。**

- [ ] 我能说出"为什么不能对已 push 的公共分支做 rebase"

---

## 3. stash：临时存一下（15 分钟）

**场景**：正在写 A 功能，写到一半，老板让你立刻去修 main 上的紧急 bug。你不想提交半成品。

```bash
# 当前有未提交改动
echo "半成品代码" >> kb-service/src/kb_service/services/kb_service.py

git stash                     # 存起来，工作区变干净
git status                    # 确认干净

git stash list                # 看到 stash@{0}

git stash pop                 # 取回到工作区（并从 stash 列表删除）
# 或者
git stash apply               # 取回但保留在 stash 列表里
```

**带 message 存**（推荐，多个 stash 时能分清）：

```bash
git stash push -m "统计接口半成品"
git stash list      # 能看到 message
```

**stash 只 stash 已跟踪文件的改动**。新增的未跟踪文件（`??` 状态）默认不 stash，要加 `-u`：

```bash
git stash push -u -m "含新文件"
```

- [ ] 我用过 `git stash` / `git stash pop`
- [ ] 我知道 `-u` 才会包含未跟踪文件

---

## 4. Conventional Commits + 三条真提交（40 分钟）

### 4.1 规范长什么样

```
<type>(<scope>): <subject>

[可选的 body：说清为什么这么改]

[可选的 footer：关联 issue / BREAKING CHANGE]
```

| type       | 用途          | 例子                                          |
| ---------- | ----------- | ------------------------------------------- |
| `feat`     | 新功能         | `feat(kb): 新增统计接口`                          |
| `fix`      | 修 bug       | `fix(auth): 修正 token 过期后返回 500`             |
| `docs`     | 只改文档        | `docs(w1): 补 Day3 教材`                       |
| `style`    | 格式/空格，不影响逻辑 | `style: ruff format 全量格式化`                  |
| `refactor` | 重构（不改外部行为）  | `refactor(repo): Repository 改为实例持有 session` |
| `test`     | 加/改测试       | `test(kb): 补 split_text 边界用例`               |
| `chore`    | 构建/工具/依赖    | `chore: 升级 ruff 到 0.17.1`                   |
| `perf`     | 性能优化        | `perf(query): 列表查询加索引`                      |

**subject 写法**：

- 用**动词原形开头**（中文就写"新增/修正/删除"），不用过去式
- **不加句号**
- **不超过 50 字**，超出说明你塞了太多事，应该拆提交

**为什么要规范**（面试能说）：

1. **工具链依赖它**：`semantic-release` / `standard-version` 按 type 自动算版本号（`feat` → minor，`fix` → patch，`BREAKING CHANGE` → major）并生成 changelog
2. **`git log --grep` 能筛**：`git log --grep="^fix"` 一秒列出所有 bug 修复
3. **code review 成本降低**：reviewer 看 type 就知道该重点看什么

### 4.2 任务：补三条符合规范的提交

现在把分支上没提交的东西整理成三条规范提交。要求**至少覆盖 `feat` / `test` / `docs` 三类**。

示例流程：

```bash
# 检查还有什么没提交
git status

# 分别提交
git add kb-service/src/kb_service/api/v1/knowledge_bases.py
git commit -m "feat(kb): 新增 /kbs/stats/count 统计接口"

git add kb-service/tests/test_kb_api.py
git commit -m "test(kb): 补统计接口的计数用例"

git add ../progress/week1/
git commit -m "docs(w1): 记录 Day3 分支与 rebase 练习"
```

> 如果上一步 rebase 已经把改动都提交了，那你已经有合规提交了。**检查 `git log --oneline` 里每条 message 是否都符合 `<type>(<scope>): <subject>` 格式**，不符合的用 `git commit --amend -m "..."` 或 `git rebase -i` 的 `reword` 改掉。

- [ ] 我的每条提交 message 都符合规范
- [ ] 我能说出 `feat` 和 `fix` 在自动生成 changelog 时的区别

---

## 5. pre-commit：让规范变成强制（40 分钟）

> 已经帮你配置好并安装了，现在**验证它真的能拦住你**。

### 5.1 看看配了什么

打开仓库根的 `.pre-commit-config.yaml`：

- `ruff --fix`：lint 并自动修（未使用变量、import 顺序、`x=1` 缺空格）
- `ruff-format`：格式化
- `trailing-whitespace` / `end-of-file-fixer`：行尾空格、文件末尾换行
- `check-yaml` / `check-toml`：配置文件语法
- `check-added-large-files`：超过 1MB 的文件拦住
- `check-merge-conflict`：**拦住没解决的 `<<<<<<<` 冲突标记**
- `detect-private-key`：拦住私钥


### 5.2 ⭐ 验收：故意提交违规代码，看它拦不拦

**打开 `kb-service/src/kb_service/services/kb_service.py`，在文件末尾加这行**：

```python
x=1
```

（缺空格 + 未使用的变量 + 变量名太短）

```bash
cd ..    # 仓库根
git add -A
git commit -m "test: 验证 pre-commit 是否拦截"
```

**你应该看到**：

```
ruff.....................................................................Failed
- hook id: ruff
- exit code: 1
- files were modified by this hook

Found 2 errors (2 fixed, 0 remaining).
```

（`ruff --fix` 会自动把它改成 `x = 1`，但 `x` 未使用这个错误修不掉，所以 commit 被中断）

**提交失败了，但这是好事。** 现在：

```bash
git diff                        # 看 ruff 自动改了什么
```


如果 ruff 把 `x=1` 改成 `x = 1` 还留着未使用变量，手动删掉那行，然后重新提交：

```bash
git checkout kb-service/src/kb_service/services/kb_service.py   # 或者手动删掉 x=1
git add -A
git commit -m "test: 验证 pre-commit 是否拦截"
```

这次应该通过。

- [ ] 我亲眼看到 ruff hook 拦截了这次提交
- [ ] 我看到了 ruff 自动修好了部分问题（`x=1` → `x = 1`）
- [ ] 我理解"自动修 + 修不了就拦"是 pre-commit 的标准行为

### 5.3 ⭐⭐ 验收 2：合并冲突标记拦截（今天最有价值的一条）

昨天你 rebase 冲突时如果留下了 `<<<<<<<` 没删干净，代码会直接语法错误、服务起不来。这条 hook 能提前挡住。

```bash
# 故意造一个冲突标记
cd kb-service
echo "<<<<<<< HEAD" >> src/kb_service/services/kb_service.py
echo "=======" >> src/kb_service/services/kb_service.py
echo ">>>>>>> abc123" >> src/kb_service/services/kb_service.py

cd ..
git add -A
git commit -m "test: 验证冲突标记拦截"
```

**你应该看到**：

```
check for merge conflicts.................................................Failed
- hook id: check-merge-conflict

src/kb_service/services/kb_service.py:78: <<<<<<< HEAD
```

提交被拦。这才是这条 hook 的价值：**在 commit 阶段拦住，而不是等 CI 阶段或运行时才发现**。

清理：

```bash
git checkout kb-service/src/kb_service/services/kb_service.py
git status
```

- [ ] 我看到了 `check-merge-conflict` 拦住了提交
- [ ] 我理解了"在 commit 阶段拦住"比"CI 阶段才发现"省多少时间

### 5.4 常见问题

**Q：pre-commit 跑得太慢？**  
只在改动的文件上跑，所以日常很快。全量跑（`--all-files`）才慢。

**Q：真的急需跳过怎么办？**

```bash
git commit --no-verify -m "..."
```

⚠️ **但公司里这么做会被 review 打回**。跳过 hook 等于绕过团队约定，应该修代码而不是绕检查。

**Q：hook 环境和项目环境是同一个吗？**  
不是。pre-commit 会给每个 hook 建**独立的隔离环境**（在 `~/.cache/pre-commit`），避免不同项目的依赖打架。这也是它首次运行慢的原因。

- [ ] 我知道 `--no-verify` 能跳过，但知道不该日常用

---

## 6. 收尾：合并回 main 并推送（20 分钟）

### 6.1 切回 main，合并分支

```bash
git switch main
git merge --no-ff feat/stats-endpoint -m "merge: 统计接口功能"
```

`--no-ff` = **禁止快进合并**，强制产生一个 merge commit。这样历史里能看到"曾经有个分支"。

> 如果想让历史线性（很多团队要求），切回分支后 `git rebase main` 然后再 `git switch main && git merge --ff-only feat/stats-endpoint`。
>
> **今天两种都试一下**，感受区别。推荐先试 `--no-ff` 看图形，再试 `--ff-only`。

```bash
git log --oneline --graph --all -10
```

- [ ] 我看到了 merge commit 形成的分叉图
- [ ] 我也试过 `--ff-only` 的线性形态（或至少理解区别）

### 6.2 删除分支

```bash
git branch -d feat/stats-endpoint      # 已合并的，安全删除
# git branch -D feat/stats-endpoint    # 强制删除（没合并时会拒绝，-D 硬删）
```

- [ ] 分支删掉了，`git branch` 只剩 main

### 6.3 推送

```bash
git push
```

⚠️ **注意**：如果前面用了 `rebase -i` 改写历史，**但那些提交还没 push 过**，那 push 是安全的。只有"改写已经 push 过的提交"才需要 `--force-with-lease`（并且会坑到别人）。

- [ ] 推送成功了

---

## 今日验收清单（8 条）

- [ ] 我创建过至少一个功能分支，并在上面工作
- [ ] 我用过 `git commit --amend` 修改最近一次提交（内容或 message）
- [ ] 我用 `git rebase -i` 把多个零碎提交压成一个（用过 `squash` 或 `fixup`）
- [ ] 我**亲手制造并解决**了一次 rebase 冲突，且是手工编辑文件而不是 `--theirs`
- [ ] 我能说出 **rebase 时 `HEAD` 指的是目标分支**，和 merge 时相反
- [ ] 我提交的消息都符合 Conventional Commits 规范
- [ ] pre-commit **真实拦截**过我的提交（lint 违规 + 冲突标记两种都试过）
- [ ] 我把分支合并回 main 并成功推送

---

## 自测 6 问（闭卷，不看上面）

1. `git merge` 和 `git rebase` 对历史的影响有什么不同？什么情况下**绝对不能**用 rebase？
2. rebase 冲突时，`<<<<<<< HEAD` 和 `>>>>>>>` 之间分别是哪边的内容？（和 merge 冲突时有什么不同？）
3. 为什么 `git commit --amend` 之后不能直接 `git push`？
4. `git reset --soft` / `--mixed` / `--hard` 的区别？
5. `git stash` 和 `git commit` 到的临时分支，在"临时存一下"这个场景下哪个更好？为什么？
6. pre-commit hook 为什么给每个 hook 建独立环境？

<details>

<summary>答案（先自己答，再看）</summary>

1. merge 保留分叉并产生 merge commit（不改历史）；rebase 把提交重放到目标分支顶端，形成直线，但**会重写 commit hash**。**绝对不能对已经 push 到共享分支的提交 rebase**——别人基于旧 hash 的工作会全部错乱。
2. rebase 时：`<<<<<<< HEAD` 到 `=======` 之间是**目标分支（你 rebase 到的那个，比如 main）**&#x7684;内容；`=======` 到 `>>>>>>>` 之间是**你正在被重放的提交（你的分支改动）**&#x7684;内容。  
   **这和 merge 时是反的**：merge 时 `HEAD` = 你当前所在的分支，`>>>>>>>` = 被合并进来的分支。  
   **实测验证（git 2.55）**：在 feat 分支上 `git rebase main` 后冲突文件显示
   ```
   <<<<<<< HEAD
   MAIN_BRANCH_CONTENT      ← HEAD 侧 = main
   =======
   FEAT_BRANCH_CONTENT      ← 重放侧 = 你的 feat 提交
   >>>>>>> 3984e9d (feat change)
   ```
   结论：**rebase 里 HEAD 指向的是"目标分支"**。所以 `git checkout --ours` 在 rebase 时保留的是 main 的版本，不是你的——这正是最容易搞反的地方。  
   **最稳的做法**：不看 `ours/theirs`，**手工编辑文件**留下想要的版本，再 `git add` + `git rebase --continue`。
3. amend 会重新生成提交（新 hash），本地和远端历史分叉。直接 push 会被拒绝（non-fast-forward），必须 force push。而 force push 到共享分支会覆盖别人的提交。
4. `--soft`：只移动 HEAD，改动留在**暂存区**（可直接 commit）；`--mixed`（默认）：移动 HEAD + 清空暂存区，改动留在**工作区**；`--hard`：移动 HEAD + 清空暂存区 + **丢弃工作区改动**（危险，数据可能找不回）。
5. 临时分支更好（`git switch -c tmp && git commit`）。因为 stash 是**匿名栈**，多个 stash 容易搞混；而临时分支有名字、能正常 `git log`/`git diff`、能随时切回来、不会因为误操作 pop 丢失。stash 适合"十几分钟的小打断"。
6. 避免不同项目的依赖版本互相污染。pre-commit 会在 `~/.cache/pre-commit` 下按 repo+rev 建独立 env，确保你在任何项目里跑同一 hook 配置，行为完全一致。

</details>

---

## 今天的"知识点账户"

面试时你可以说：

> "我习惯用功能分支开发，提交遵循 Conventional Commits，这样 CI 能按 type 自动生成 changelog。整理本地历史我用 `rebase -i` 的 squash/fixup，追平主干用 rebase 让历史保持线性，但**已经推送的共享分支绝不 rebase**。遇到 rebase 冲突我会手工编辑文件而不是用 `--theirs`，因为 rebase 时 ours/theirs 的语义和 merge 是反的，靠猜容易搞错。团队规范我用 pre-commit 强制执行——ruff 自动修，修不了的拦住，连没清理的合并冲突标记也会在 commit 阶段被挡下。"

---

## 附录：今天用到的命令速查

```bash
# 分支
git switch -c <name>              # 新建并切换
git switch <name>                 # 切换
git branch                        # 列出本地分支（* 是当前）
git branch -d <name>              # 删除已合并分支
git branch -D <name>              # 强制删除

# 提交
git commit --amend --no-edit      # 改内容不改 message
git commit --amend -m "新 message" # 改 message
git add -p                        # 交互式挑要提交的片段（强烈推荐）

# rebase
git rebase -i HEAD~3              # 交互式整理最近 3 个
git rebase main                   # 把当前分支重放到 main 上
git rebase --continue             # 解决冲突后继续
git rebase --abort                # 放弃，回到 rebase 前

# 撤销
git restore <file>                # 丢弃工作区改动（未 add）
git restore --staged <file>       # 取消暂存（已 add）
git reset --soft HEAD~1           # 撤销最近提交，改动回暂存区
git reset --hard HEAD~1           # 撤销最近提交，改动全丢（危险）

# 查看
git log --oneline --graph --all   # 图形化历史
git diff                          # 工作区 vs 暂存区
git diff --staged                 # 暂存区 vs 最近提交
git show <hash>                   # 看某次提交改了什么
git blame <file>                  # 每行是谁什么时候改的

# stash
git stash push -u -m "说明"        # 存（含未跟踪文件）
git stash list                    # 列表
git stash pop                     # 取回并删除记录
git stash apply                   # 取回但保留记录
git stash drop                    # 删除某条记录
```
