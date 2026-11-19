"""项目级 pytest 引导：在任何 kb_service 代码被 import 之前注入必需配置。

为什么这个文件放在 kb-service/ 根目录，而不是 tests/ 里：
- pytest 从 rootdir 往下加载 conftest，根上的这个最先执行；
- tests/conftest.py 第 10 行 `from kb_service.main import create_app` 会在导入时
  就执行 main.py 模块级的 `app = create_app()` → `get_settings()`，
  那一刻环境变量必须已经就位，晚一步就来不及了。

为什么必须有它（真实事故）：
`secret_key` 没有默认值（生产环境必须显式提供，fail-fast），而 .env 被 .gitignore
排除、不进仓库。于是本地有 .env 一切正常，CI 上没有这个文件，`import kb_service.main`
直接 `ValidationError: secret_key Field required`，连测试都收集不起来。

用 setdefault 而不是直接赋值：开发者本机/CI 若真提供了 SECRET_KEY，以真实值为准。
"""

import os

# 仅测试用假密钥：满足 min_length=16 即可，不涉密，也不是生产凭证。
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789")

# 测试默认不许碰真库（2026-11-19 事故后加）。
#
# 事故：`test_dev_token.py` 自己 `TestClient(create_app())`，绕过 conftest 打在
# `app` fixture 上的 `dependency_overrides[get_db]`，于是走了真 `get_db`：
#   本地 .env → MySQL kb_dev（有表）→ 200，绿；
#   CI 没有 .env → 空 sqlite 文件 → no such table → 红。
# 后果是「本地绿 ≠ CI 绿」，而且本地那条绿毫无信息量。
#
# 这里把 DATABASE_URL 钉成内存 sqlite（**赋值不是 setdefault**：.env 和环境变量
# 都可能指向真库，测试要的是确定性，不是"碰运气继承"）。这样即使某条用例再次
# 绕过 override，也会在本地立刻 `no such table` 炸出来，而不是偷偷写成 200。
#
# 唯一例外：真 MySQL 集成测试（tests/test_db_integration.py）要连真库，
# 它自己用 KB_TEST_MYSQL=1 显式声明，这时保留真实 DATABASE_URL。
if os.environ.get("KB_TEST_MYSQL") != "1":
    os.environ["DATABASE_URL"] = "sqlite://"
