# W1 Day1 · 验收清单（10 分钟，只动手不动脑）

> 原则：**能不看笔记做出来 = 会；要翻笔记才能做 = 半会；做不出来 = 不会。**
> 别用"我感觉懂了"判断，用"我能不能做出来"判断。

---

## A. 动手题（6 题，每题 ✅/❌，不许看笔记）

### A1 · 环境可复现（2 分钟）

删掉虚拟环境，重建，跑测试。**全程只有 3 条命令。**

```powershell
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\kb-service
rm -r -Force .venv
uv sync
uv run pytest -q
```

- [ ] 最后一行是 `8 passed`
- [ ] 我知道为什么是 `uv sync` 而不是 `pip install -r requirements.txt`

> **为什么考这个**：这就是"环境可复现"。面试问"你怎么保证别人能跑起你的项目"，答案就是这两条命令。

---

### A2 · 版本锁定（1 分钟）

```powershell
cat .python-version
```

- [ ] 输出是 `3.11`
- [ ] 我能说出：这个文件是谁生成的？（`uv python pin 3.11`）
- [ ] 我能说出：它的作用是什么？（告诉 uv 和所有 clone 项目的人，这个项目必须用 3.11）

---

### A3 · 启动时校验（2 分钟）

把 `.env` 里的 `SECRET_KEY` 改成 `123`，启动服务。

```powershell
uv run uvicorn kb_service.main:app --port 8000
```

- [ ] 服务**起不来**
- [ ] 报错里有 `secret_key` 和 `at least 16 characters`
- [ ] 我能说出：校验发生在**启动时**而不是请求时，这样做的好处是——（配置错误在部署阶段就暴露，不会等线上流量来了才 500）

改回长的，服务能正常起来。

---

### A4 · 读懂一条报错（2 分钟）

不改任何代码，只看这条报错，说出三要素：

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
secret_key
  String should have at least 16 characters [type=string_too_short, input_value='123']
```

- [ ] 谁报的错：__________（`Settings` 配置类）
- [ ] 哪个字段：__________（`secret_key`）
- [ ] 为什么错：__________（字符串至少要 16 个字符，实际给了 3 个）

> **为什么考这个**：这是整个 24 周里复用次数最多的技能。会读报错 = 90% 的问题自己能解决。

---

### A5 · 测试是什么（1 分钟）

打开 `tests/test_health.py`，用**一句人话**解释第 6-10 行在干什么：

- [ ] 我的解释：____________________________________________

标准答案参考："调一下 /health 接口，断言它返回 200，且返回的 JSON 里 status 是 ok，任何一条不满足就算失败。"

---

### A6 · 改坏再修好（2 分钟）

1. 把 `src/kb_service/api/v1/health.py` 里的 `"ok"` 改成 `"healthy"`
2. `uv run pytest -q`
3. 看到 `FAILED tests/test_health.py::test_health`

- [ ] 我看到了红色 FAILED
- [ ] 我能说出：为什么失败的是 `test_health`，而 `test_requires_auth` 没失败？

改回来：

```powershell
git checkout src/kb_service/api/v1/health.py
uv run pytest -q    # 回到 8 passed
```

---

## B. 口述题（3 题，对着空气说出来，30 秒/题）

> 判断标准：**能不能连续说完 30 秒不打磕巴**。卡住的地方就是没真懂。

### B1 · "你这个项目是怎么运行的？"

期望讲出：
> "用 uv 管环境和依赖，`uv sync` 一条命令从 `pyproject.toml` + `uv.lock` 重建虚拟环境。启动用 `uvicorn kb_service.main:app`，`create_app()` 里注册中间件和路由。配置从 `.env` 读，用 pydantic-settings 校验，配置不合法服务直接起不来。"

- [ ] 说完了，没卡

### B2 · "为什么用 uv 不用 pip？"

期望讲出：**快（Rust 写的）、有锁文件保证可复现、能管 Python 版本**。三条。

- [ ] 说出 3 条

### B3 · "你怎么保证代码没被改坏？"

期望讲出：
> "写测试。现在有 8 个用例，覆盖 CRUD、参数校验、越权、SSE 流式、trace_id 透传。我要重构（比如 W7 换数据库）时先跑一遍，全绿说明行为没变。"

- [ ] 说出了"测试是重构的底气"这层意思

---

## C. 评分

| 得分 | 结论 | 下一步 |
|------|------|--------|
| A 全 ✅ 且 B 全 ✅ | **真学会了** | 明天直接开始 Day2 |
| A 有 1-2 个 ❌ | 半会 | 把那两个题再做一遍，做过就算会 |
| A 有 3 个以上 ❌ | 没过关 | 别进 Day2，回头重做一遍 Day1 的 A1-A6（40 分钟够） |
| B 卡住但 A 全过 | 会做不会说 | **正常，先放过**。嘴上的功夫靠每周复盘练，不必今天纠 |

> **重要**：B 类题今天答不流畅非常正常 —— 你连"面试话术"都还没开始练（那是 W22 的事）。今天只要求 **A 类全 ✅**，因为那才是"会不会"的硬指标。

---

## D. 记录

把结果填到 `进度看板.md`：

| 日期 | 时段 | 内容 | 时长 | 代码行数 | 卡点/疑问 |
|------|------|------|------|---------|----------|
| 2026-10-20 | | Day1 验收：A__/6，B__/3 | | | |

---

*判断"学会"的唯一标准：**给你一台干净电脑，你能不能 10 分钟内把项目跑起来。** 能，就是会了。*
