# RAG 知识库服务 · Python 后端工程能力训练

> 一个从零开始的后端工程能力成长仓库：**代码 + 学习记录**放在一起，每一周的进展都可以回溯。
> 目标岗位：2027 届秋招 · Python 后端 / AI 应用开发。

---

## 这个仓库是什么

不是一份"做完就完事"的作业，而是一条 **24 周的学习轨迹**：

| 目录 | 内容 |
|------|------|
| `kb-service/` | 主线练手项目：企业级 RAG 知识库服务（FastAPI + 分层架构 + SSE 流式） |
| `progress/` | 每周的周计划、练习代码、验收清单、调试记录 |
| `学习路线-24周.md` | 完整的 24 周路线设计（六阶段 + 验收硬指标） |
| `进度看板.md` | 逐周进度、每日打卡、里程碑 |
| `八股题库.md` | 面试知识点（从 W6 起填充） |

**为什么把学习记录也放进仓库**：一个真实的、持续提交的技术成长记录，比一份包装精美的单次作业更能说明问题。

---

## 项目：kb-service

企业级 RAG 知识库服务的渐进式实现。**同一条主线贯穿 24 周**，每个阶段往上加一层工程能力，而不是做 5 个互不相关的 demo。

### 分层架构

```
api/          ← HTTP 层：路由、参数校验、鉴权依赖、状态码
services/     ← 业务层：业务规则、编排。不 import fastapi / sqlalchemy
repositories/ ← 数据层：SQL / 缓存操作
schemas/      ← Pydantic：对外契约
core/         ← 配置、日志、异常、安全等横切能力
```

依赖方向单向向下：`api → services → repositories`。业务异常在 service 层 raise，由 API 层统一翻译成 HTTP 响应 —— **业务代码与 Web 框架解耦**。

### 快速开始

```bash
cd kb-service

# 环境（uv 会自动读取 .python-version 使用 Python 3.11）
uv sync --group dev

# 配置
cp .env.example .env
# 编辑 .env，把 SECRET_KEY 换成长随机串（至少 16 位）
# 生成：uv run python -c "import secrets; print(secrets.token_urlsafe(48))"

# 启动
uv run uvicorn kb_service.main:app --reload --port 8000
# 打开 http://127.0.0.1:8000/docs
```

### 开发命令

```bash
uv run pytest -q                     # 测试
uv run pytest --cov=src/kb_service   # 覆盖率
uv run ruff check . --fix            # lint
uv run ruff format .                 # 格式化
uv run mypy src                      # 类型检查
```

### 已完成（v0.1 · W1）

- `uv` + `pyproject.toml`（Ruff / mypy strict / pytest / coverage）
- 分层骨架 + 内存 Repository
- 统一错误响应 `{code, message, detail}` + 业务异常体系
- JSON 结构化日志 + `trace_id` 贯穿请求（ContextVar）
- 知识库 CRUD（分页、JWT 鉴权、越权 403）
- 文档入库 + 文本切分
- `/chat` 问答：同步 JSON + SSE 流式双模式
- **8 个测试全绿**

### 路线图（按周解锁）

| 周次 | 加什么 |
|------|--------|
| W7 | 内存存储 → SQLAlchemy 2.0 + Alembic 迁移 |
| W8 | 用户表 + RBAC + 多租户隔离 |
| W10 | Redis 缓存 + 滑动窗口限流 |
| W11 | 文档解析改 Celery 异步 + 进度查询 |
| W12 | embedding + pgvector 混合检索 + RRF |
| W13 | Prometheus 指标 + Grafana |
| W14 | `/chat` 接真实 LLM 流式 |
| W15-16 | 多轮会话记忆、Agent 工具编排、RAG 评测集 |
| W18-21 | Docker 多阶段构建、CI/CD、部署、压测调优 |

### 已知的"故意留的坑"（练手点）

1. 鉴权只校验了 JWT 签名，没有用户表 —— W8 补
2. `split_text` 是字符窗口切分，会切断句子 —— W12 用真实语料验证
3. `_retrieve` 是关键词命中，召回质量差 —— W12 换向量检索并做评测对比
4. 内存存储无并发安全、无持久化 —— W7 换数据库
5. `/chat` 未做限流和 token 预算控制 —— W15/W17 补

---

## 提交规范

```
<type>(<scope>): <subject>

type: feat | fix | docs | style | refactor | test | chore | perf
```

示例：
```
feat(w7): 用 SQLAlchemy 替换内存仓储
fix(w10): 修复缓存击穿导致的重复穿透查询
test(w12): 补充混合检索召回率测试
```

每周结束打 tag：`git tag w07-done && git push --tags`

---

## License

MIT
