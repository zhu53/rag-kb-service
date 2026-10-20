# kb-service · RAG 知识库服务（学习脚手架）

渐进式练手项目：**同一个项目贯穿 24 周路线**，每个阶段往上加一层工程能力。
路线文档见上一级目录 `../学习路线-24周.md`。

## 快速开始

```bash
# 1. 安装 uv（一次性）
#    Windows PowerShell: irm https://astral.sh/uv/install.ps1 | iex

# 2. 建虚拟环境 + 装依赖
uv sync --group dev

# 3. 准备环境变量
cp .env.example .env      # 然后修改 SECRET_KEY

# 4. 起服务
uv run uvicorn kb_service.main:app --reload --port 8000

# 5. 打开交互文档
#    http://127.0.0.1:8000/docs
```

```bash
uv run pytest -q                     # 跑测试
uv run pytest --cov=src/kb_service   # 覆盖率
uv run ruff check . --fix            # lint
uv run ruff format .                 # 格式化
uv run mypy src                      # 类型检查
```

## 分层约定（面试会问，务必能讲清）

```
api/         ← HTTP 层：路由、参数校验、鉴权依赖、返回码。不写业务规则
services/    ← 业务层：事务边界、业务规则、编排。不 import fastapi / sqlalchemy
repositories/← 数据层：SQL / 缓存操作。只做数据存取，不写业务判断
schemas/     ← Pydantic：对外契约（请求/响应）
models/      ← ORM 实体（W7 出现）
core/        ← 配置、日志、异常、安全等横切能力
```

**依赖方向单向向下**：`api → services → repositories`。反向 import 一律视为设计错误。
`AppError` 在 service 层 raise，由 `main.py` 的异常处理器翻译成 HTTP 响应 —— 这就是"业务代码与 Web 框架解耦"。

## 已完成（v0.1，对应路线 W1–W5 起手）

- `uv` + `pyproject.toml`（Ruff / mypy strict / pytest / coverage 全配好）
- 8 个测试全绿（CRUD、参数校验、越权、SSE 流式、trace_id）
- 分层骨架 + 内存 Repository（先跑通逻辑，W7 换数据库）
- 统一错误响应体 `{code, message, detail}` + 业务异常体系
- JSON 结构化日志 + `trace_id` 贯穿请求（`ContextVar`）+ 耗时记录
- 知识库 CRUD（分页、JWT 鉴权依赖、越权 403 判定）
- 文档入库 + 简单切分（`split_text`）
- `/chat` 问答：同步 JSON + SSE 流式两种模式（检索为朴素关键词版）

## TODO 清单（按路线周次解锁，不要跳着做）

| 周次 | 任务 | 改动点 |
|------|------|--------|
| W5 | 覆盖率补到 80%+，mypy 0 error | `tests/` |
| W7 | 内存仓储换 SQLAlchemy 2.0 + Alembic 迁移 | `repositories/` |
| W7 | 设计 kb / doc / chunk 三表（索引、外键、软删除） | `models/`、`alembic/` |
| W8 | 用户表 + RBAC + refresh token（JWT 已就位） | `api/deps.py`、`core/security.py` |
| W10 | 热点接口加 Redis 缓存 + 滑动窗口限流 | `repositories/`、`core/` |
| W11 | 文档解析改 Celery 异步 + 进度查询 | `services/doc_service.py` |
| W12 | `split_text` 升级按段落切；接 embedding + pgvector；混合检索 + RRF | `services/`、`repositories/` |
| W13 | Prometheus 指标 + Grafana 面板 | `main.py` |
| W14 | `/chat` 流式改真 LLM；超时与断连处理（`CancelledError`） | `services/rag_service.py` |
| W15 | 多轮会话记忆 + 工具调用编排 + 租户配额 | `services/` |
| W16 | 评测集（50 条 golden QA）+ 指标脚本 | `scripts/eval.py` |
| W18 | 多阶段 Dockerfile + `docker compose`（API + PG + Redis） | `docker-compose.yml` |
| W19 | GitHub Actions：lint → mypy → test → build | `.github/workflows/ci.yml` |
| W20 | 部署上云 + Nginx + HTTPS | 部署脚本 |
| W21 | locust 压测 + 瓶颈分析与优化记录 | `scripts/loadtest.py` |

## 已知的"故意留的坑"（练手点）

1. 鉴权只校验了 JWT 签名，没有用户表 —— token 里的 user_id 不存在的也能通过，W8 补用户表校验与封禁逻辑。
2. `split_text` 是字符窗口切分，会把句子切断 —— W12 用真实语料验证效果。
3. `RagService._retrieve` 是关键词命中，召回质量很差 —— W12 换成向量检索并做评测对比。
4. 内存存储无并发安全、无持久化 —— W7 换数据库解决。
5. `/chat` 未做限流和 token 预算控制 —— W15/W17 补。

## 提交规范

```
feat(w7): 用 SQLAlchemy 替换内存仓储
fix(w10): 修复缓存击穿导致的重复穿透查询
test(w12): 补充混合检索召回率测试
```

每完成一周打一个 tag：`git tag w07-db && git push --tags`。
