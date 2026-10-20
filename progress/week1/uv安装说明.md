# W1 Day1 · uv 安装说明（Windows）

> 一句话结论：**默认装在 C 盘用户目录，装就装，别纠结。**
> 你在 C 盘还有 90GB 可用，uv 本体只有约 30-40MB。

---

## 1. 默认装在哪

官方脚本 `irm https://astral.sh/uv/install.ps1 | iex` 的默认路径：

| 内容 | 默认路径 |
|------|---------|
| uv / uvx 可执行文件 | `C:\Users\acer-pc\.local\bin\` |
| uv 下载的 Python 解释器 | `C:\Users\acer-pc\AppData\Roaming\uv\python\` |
| 全局缓存（包、wheel） | `C:\Users\acer-pc\AppData\Local\uv\cache\` |

**真正占空间的不是 uv 本体，是缓存**（几百 MB，长期可清）。项目虚拟环境 `.venv` 默认跟着每个项目走 —— 如果项目放在 C 盘，`.venv` 也在 C 盘。

你现在的项目在 `C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\`，所以 `.venv` 也会在 C 盘。一个 venv 约 200-400MB，20 周下来十几个项目也就 5-8GB，你 90GB 完全够。

---

## 2. 方案 A：直接默认安装（推荐，别折腾）

PowerShell 里执行：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

装完**必须重开一个终端**（PATH 才生效），然后验证：

```powershell
uv --version
# 期望输出类似：uv 0.9.x (...)
```

如果提示 `uv 不是内部或外部命令`，手动加 PATH：把 `C:\Users\acer-pc\.local\bin` 加进用户环境变量 PATH。

---

## 3. 方案 B：想省 C 盘空间（把缓存和 Python 挪到 D 盘）

只有当你打算装很多 Python 版本、跑很多项目时才值得。PowerShell：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
[Environment]::SetEnvironmentVariable("UV_CACHE_DIR", "D:\uv\cache", "User")
[Environment]::SetEnvironmentVariable("UV_PYTHON_INSTALL_DIR", "D:\uv\python", "User")
[Environment]::SetEnvironmentVariable("UV_TOOL_DIR", "D:\uv\tools", "User")
```

三个变量的作用：

| 变量 | 作用 | 建议 |
|------|------|------|
| `UV_CACHE_DIR` | 包/轮子缓存，**最占空间**，可以随时删 | 放 D 盘很划算 |
| `UV_PYTHON_INSTALL_DIR` | `uv python install` 装的解释器 | 如果你已有系统 Python，可不动 |
| `UV_TOOL_DIR` | `uv tool install` 装的 CLI 工具（ruff、httpie 等） | 可放 D 盘 |

设完要**重开终端**。验证：

```powershell
uv cache dir
# 应输出 D:\uv\cache
```

> 注意：`uv venv` 建的项目虚拟环境路径由 `VIRTUAL_ENV` / 项目位置决定，**不受上面变量控制** —— `.venv` 永远在项目根目录，这是设计如此，别试图改。

---

## 4. 常见坑（Windows 专属）

### 坑 1：`无法加载文件 ... 因为在此系统上禁止运行脚本`
执行策略拦住了脚本。开一个 **管理员** PowerShell：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 坑 2：装完立刻用报 `uv 不是内部或外部命令`
PATH 只在**新开的终端**生效。重开 PowerShell / VS Code（VS Code 要重启整个进程，不是重开终端标签）。

### 坑 3：VS Code 终端里找不到 uv，但 PowerShell 里有
VS Code 是装 uv 之前就开着的，它继承的是旧环境变量。**完全退出 VS Code 再打开**。

### 坑 4：`uv sync` 报找不到 Python 3.11
uv 不会自动装解释器（除非 `--python-preference` 配置允许）。手动：

```powershell
uv python install 3.11
```

---

## 5. 装完做这三件事就算 Day1 第 1 步完成

```powershell
# ① 版本确认
uv --version

# ② 进项目建环境（在 kb-service 目录下）
cd C:\Users\acer-pc\WorkBuddy\2026-10-20-08-44-29\python-backend-roadmap\kb-service
uv sync --group dev

# ③ 跑测试（期望：8 passed）
uv run pytest -q
```

**注意 `.env` 要先建好**，否则 `pydantic-settings` 读取配置会异常：

```powershell
copy .env.example .env
```

然后打开 `.env`，把 `SECRET_KEY` 改成一个长随机串（至少 16 位，这是 `config.py` 里 `min_length=16` 的硬校验）：

```powershell
# 生成一个
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 6. 面试会问的一句话总结

> "我用 uv 替代 pip/conda：uv 是 Rust 写的，依赖解析快一个数量级；它能锁 `uv.lock` 保证环境可复现；还能直接管理 Python 解释器版本。缓存和环境路径都可通过 `UV_CACHE_DIR` 等环境变量重定向。项目虚拟环境放在项目根目录 `.venv`，用 `uv sync` 一条命令从零重建。"
