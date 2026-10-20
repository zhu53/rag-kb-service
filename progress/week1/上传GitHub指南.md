# 上传到 GitHub 指南（W1）

> 结论先说：**现在就该上传，不要等。** 原因见下面"为什么现在传"。
> 你的 SSH 已经配好（`~/.ssh/id_ed25519.pub`，GitHub 认你为 `zhu53`），所以不用配 token。

---

## 一、为什么现在传（不是等做完再传）

| 理由 | 说明 |
|------|------|
| **提交历史本身就是作品** | 面试官看仓库第一眼看的不是代码多牛，是**你有没有持续提交的习惯**。24 周 100+ 次提交的绿格子，比一个完美的"最后一天上传的项目"说服力强十倍 |
| **倒逼你用 Git 工作流** | 上传后才敢开分支、做实验、rebase —— 本地没有远端时，你永远只会在 main 上瞎改 |
| **防止丢代码** | 你的笔记本丢了/硬盘坏了，本地 git 什么都没了。远端才是备份 |
| **早暴露隐私问题** | `.env` 里的密钥一旦上传过一次（即使后来删除），GitHub 的公开历史里仍能找到。趁现在项目还没密钥，先把 `.gitignore` 验证到位 |
| **简历要放链接** | 秋招填简历时，一个"从 W1 起有完整 commit 记录"的仓库，比"上传于 2027-06"的仓库可信得多 |

---

## 二、上传前的三个检查（必做）

### 检查 1：`.env` 绝不能被提交

```powershell
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\kb-service
git status --ignored --short | Select-String "\.env"
```

- [ ] 输出里可以看到 `.env`（说明被忽略），**看不到 `.env.example` 被忽略**（说明示例文件会被提交，这是对的）

如果 `.env` 出现在"未跟踪"列表里（不是 ignored），**先停**，检查 `.gitignore` 里有没有 `.env` 这一行。

> ⚠️ 硬规则：**一旦密钥被提交并推到公开仓库，视为已泄露，必须立刻去服务商后台轮换密钥。** 删 commit 也没用，GitHub 的 fork 和缓存可能已经存了。

### 检查 2：确认要提交的改动是"有意为之"

```powershell
git status --short
git diff
```

逐行看一遍 diff。**如果你不知道自己改了什么，就不要提交。** 这是最基本的提交纪律。

### 检查 3：测试全绿

```powershell
uv run pytest -q
```

- [ ] `8 passed`

**永远不要提交红的测试。** 宁可少一个功能，也不要一个有已知 bug 的仓库。

---

## 三、创建仓库（网页操作，2 分钟）

1. 打开 https://github.com/new
2. **Repository name**：`kb-service`（或 `rag-kb-service`，稍正式）
3. **Description**：`企业级 RAG 知识库服务 · Python 后端工程能力练习（FastAPI + pgvector）`
4. 选 **Private** 还是 **Public**？

| | 建议 | 理由 |
|---|---|---|
| **Public** | ✅ **推荐** | 秋招简历能贴链接；绿格子是公开背书。这是学习项目，没有商业机密 |
| Private | 也行 | 但简历上贴不了链接，价值减半。等 W21 上线后再转 public 也可以 |

5. **不要**勾选 "Add a README" / ".gitignore" / "license"（你本地已经有了，勾了会产生冲突）
6. 点 **Create repository**

---

## 四、关联远端并推送（3 条命令）

创建后 GitHub 会显示一堆命令，**只用这两条**：

```powershell
git remote add origin git@github.com:zhu53/kb-service.git
git branch -M main
git push -u origin main
```

> 注意用 **SSH 地址**（`git@github.com:` 开头），不是 `https://` —— 你的 SSH key 已配好，SSH 不用输密码。
> 如果仓库名不是 `kb-service`，把 URL 换成你实际的名字。

推送成功后浏览器刷新仓库页面，应该能看到代码和那条 `chore(w1): ...` 提交。

---

## 五、你还得先提交那几个"没提交的改动"

我刚看了你的工作区，有 4 个文件改了但没提交：

```
M src/kb_service/core/logging.py       ← 格式化（ruff 干的）
M src/kb_service/repositories/kb_repo.py
M src/kb_service/services/rag_service.py  ← import 排序（ruff 干的）
M tests/test_health.py                 ← 你自己加的一行注释
```

前三个是 **ruff 自动格式化/排序**的结果（因为你按了保存或跑了 lint），属于正常的代码风格统一；第四个是你自己加的注释（注释掉的那行断言，正好是你在做 A6 实验）。

**建议这样提交**（体现"一个提交做一件事"的原则）：

```powershell
# 第一个提交：纯格式化，无行为变化
git add src/kb_service/core/logging.py src/kb_service/repositories/kb_repo.py src/kb_service/services/rag_service.py
git commit -m "style(w1): 应用 ruff 格式化与 import 排序"

# 第二个提交：测试注释（如果你打算保留这个学习痕迹就提交，不想留就 git checkout 掉）
git add tests/test_health.py
git commit -m "test(w1): 保留 A6 改坏实验的注释痕迹"
```

> **为什么拆成两个提交**：代码评审时，一个"只改格式"的提交可以放心略过，混着逻辑改动就得逐行看。这是团队协作的基本礼仪，面试会问。

---

## 六、以后每周的推送节奏

```powershell
# 每天结束时（哪怕只改了 10 行）
git add -A
git commit -m "feat(w2): 手写 LRU 缓存"
git push

# 每周结束时打 tag（重要！）
git tag w02-done
git push --tags
```

**规则**：
- 一天至少一次提交，别攒到周末
- 提交信息必须 `type(scope): subject` 格式
- 每周一个 tag，方便回看"第 2 周结束时项目长什么样"

---

## 七、顺手做的两件事（提升仓库专业度）

### 7.1 加 LICENSE

学习项目建议 **MIT**（最宽松，别人能自由参考）。GitHub 仓库页面 → Add file → Create new file → 输入 `LICENSE` → 右侧会出现 "Choose a license template"。

### 7.2 加一个仓库徽章（README 开头）

```markdown
![tests](https://github.com/zhu53/kb-service/actions/workflows/ci.yml/badge.svg)
```

前提是 W19 配了 CI。**现在加了是坏图**，所以放到 W19 再加 —— 记住这件事就行。

---

## 八、隐私自查清单（公开仓库必看）

- [ ] `.env` 没有提交（有 `.env.example` 就够）
- [ ] 没有硬编码的 API Key / 数据库密码
- [ ] 没有个人隐私信息（学号、身份证、手机号）
- [ ] `uv.lock` **应该**提交（保证依赖可复现），不要忽略它
- [ ] `.venv/` 已忽略（它体积大且平台相关，绝对不能提交）

---

*检查完把 `git remote -v` 和 `git log --oneline` 的输出发我，我确认一下就带你把 commit 推上去。*
