# reviews/ · 第四档验收题

每次交付后的一道附加题：给你一份**能跑、输出正常、lint 全过、docstring 齐全**的代码，里面埋了 3–4 个坑，让你自己定位。

> 判定标准：**能找出来，才说明真懂了**。跑一遍就能发现的坑没有价值，所以每题至少有一个坑**运行时零症状**，只能靠读代码想到。

## 为什么放在仓库根，不在 `kb-service/` 或 `progress/weekN/`

第四档题面原本散在三处：`kb-service/`、`progress/week1/…`、`progress/week2-3/…`。问题有三个：

1. **目录变脏**：`src/ tests/ scripts/` 里突然多出 `review_*.py`，看不出哪个是项目文件
2. **指标失真**：如果被 pytest 收集会抬高或降低覆盖率；如果被 mypy 检查，题面里"故意写宽的类型"会变成"项目报错"
3. **找不回来**：想复习某道题时，得记得它在哪一周的哪个子目录

所以独立成一层，与 `progress/`（学习记录）、`kb-service/`（项目）平级：

```
python-backend-roadmap/
├── kb-service/     项目代码（受完整门禁：ruff + pytest + 覆盖率 + 变异 + mypy）
├── progress/       周计划 / 教材 / 总结
├── reviews/        第四档题面（只做 ruff 检查）
├── ruff.toml       让 reviews 继承项目规则，两套标准一致
└── 进度看板.md
```

> **历史遗留已清理（2026-11-01）**：原先编号在 W3 内部重启过——W3 有 4 次第四档，
> 文件却叫 `review_01…04`，导致 `04` 实际是第 7 次、`01/02/03` 各出现两份。
> 现已按**实际顺序统一重排为 01–11**，文件名编号 = 第四档次数。对照关系见下方清单的「原名」列。

## 命名规则

```
review_<序号>_<主题>.py
        │        └─ 给人看的线索，但**不能泄露坑的位置**
        └─ 第几次第四档（全局连续，当前到 11）
```

- 序号**连续递增且全局唯一**，与周次、天数无关
- **文件里不写"这行有问题"之类的字样**，要像真实交付物——否则做题就退化成"找注释"
- 答案**不写进文件**，放对话里用 `<details>` 折叠

## 怎么跑

每个文件都**自包含**（只依赖标准库 + `httpx`/`respx`/`pytest`），不 import 项目代码，所以不装包也能跑。

```powershell
# Windows PowerShell（用 kb-service 的 venv，因为 respx/httpx 装在里面）
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap
& .\kb-service\.venv\Scripts\python.exe reviews\review_11_typing.py
```

```bash
# Git Bash / Linux / macOS（Windows 上的 venv 是 Scripts，真 Linux 是 bin）
cd /c/Users/acer-pc/WorkBuddy/2026-10-20-08-44-29/python-backend-roadmap
./kb-service/.venv/Scripts/python.exe reviews/review_11_typing.py
```

有的题自带自检（文件末尾 `if __name__ == "__main__"`），直接跑会打印 `PASS/FAIL` 清单；有的题只提供类/函数，需要你自己写几行调用去戳它。

## 出题规范（写新题必须满足）

1. **坑数 3–4 个**，不多不少
2. **至少 2 个是近期踩过或写对过的**——用来检验"真记住"还是"照改"
3. **至少 1 个运行时零症状**，否则整题会退化成"跑一遍就找到"
4. **出题前自己必须跑一遍**：能跑通、输出好看、`ruff check` + `ruff format --check` 干净、（涉及类型时）`mypy --strict` 零错误
5. 答案放对话折叠区，**给分层提示阶梯**：先说"坑在哪几层" → 再说症状 → 最后才点具体行

## 判定分档

| 找到 | 判定 |
|---|---|
| 1 个 | 及格 |
| 2 个 | 合格 |
| 3 个 | 真懂 |
| 全部 | 全对 |

## 现有清单（11 题）

| # | 文件 | 主题 | 出自 | 原名 | 得分 |
|---|---|---|---|---|---|
| 01 | `review_01_logging.py` | 项目统一的 JSON 日志配置 + trace_id | W1-D6 抄改 | 同名 | 3/4 |
| 02 | `review_02_api.py` | docstore 原型（上传/统计/查询） | W2 | 同名 | **4/4** |
| 03 | `review_03_stream.py` | ingest 批处理读取工具集（重构版） | W2 | 同名 | 3/4 |
| 04 | `review_04_notes.py` | 笔记工具分层：NoteStore / NoteService | W3 分层练习 | `review_01_notes` | 2/4 |
| 05 | `review_05_audit.py` | 审计日志：trace_id 盖章 + 按操作人检索 | W3 分层练习 | `review_02_audit` | **4/4** |
| 06 | `review_06_stats.py` | 词频统计 + 命中率缓存包装 | W3 kbcli | `review_03_stats` | 3/4 |
| 07 | `review_07_lexicon.py` | 词表统计 + 6 个单元测试（全是假测试） | W3 收尾 | `review_04_lexicon` | 3/4 |
| 08 | `review_08_notes.py` | service 层 + fake repo + 交互断言 | W4-D3 | `review_05_notes` | 2/4 |
| 09 | `review_09_cache.py` | 会话 TTL 缓存 + 异步自检（慢与脆） | W4-D4 | `review_06_cache` | 2.5/4 |
| 10 | `review_10_gateway.py` | LLM 网关：缓存 + 时间 + 外部 HTTP | W4-D5 | `review_07_gateway` | 1/4 |
| 11 | `review_11_typing.py` | 文档视图装配：返回值 / 参数 / `cast` | W5-D1 | `review_08_typing` | **3/3** |

> `04` 和 `08` 都叫 notes，但完全不同：04 考**分层**（存取与业务规则分离），08 考**测试替身**（fake repo 与交互断言）。

## 检查

`reviews/` 和 `kb-service/` 用**同一套** ruff 规则：仓库根 `ruff.toml` 里 `extend = "kb-service/pyproject.toml"`，避免两套标准。

- 只检查 ruff，**不进** pytest / 覆盖率 / mypy（练习题不能抬高门禁指标）
- 门禁命令（在 `kb-service/` 下）会自动带上 `reviews/`：

```powershell
& .\.venv\Scripts\python.exe scripts\check.py
```

```bash
./.venv/Scripts/python.exe scripts/check.py
```
