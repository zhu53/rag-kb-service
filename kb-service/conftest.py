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
