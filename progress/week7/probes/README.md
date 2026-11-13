# W7 实测探针（AI 用）

这一组脚本是**教材里那些数字的来源**，不是练习题。

- 用法：先在 `scratch/` 里**自己敲** §十 的四个实验，猜完、跑完、写下结论，
  再来这里跑一遍对答案。
- 跑法（在仓库根 `python-backend-roadmap` 下）：

```powershell
# Windows PowerShell
& .\kb-service\.venv\Scripts\python.exe .\progress\week7\probes\probe_tx.py
```

```bash
# Git Bash / Linux / macOS
./kb-service/.venv/Scripts/python.exe ./progress/week7/probes/probe_tx.py
```

| 脚本 | 对应教材 | 验证什么 |
|---|---|---|
| `probe_tx.py` | §四 | autobegin 时机 / flush 的隔离 / close 即回滚 / `with begin()` |
| `probe_expire.py` | §五 | `expire_on_commit` 两种配置下 `__dict__` 与 `DetachedInstanceError` |
| `probe_lock.py` | §七 | 只读泄漏不锁、写泄漏 `database is locked` |
| `probe_timing.py` | §六 | 依赖收尾 vs 中间件 vs 后台任务的顺序（0→1→2→3→5→4） |
| `probe_autoflush.py` | §4.2 / §4.3 | autoflush 触发条件 + `no_autoflush` + `begin()` 重复调用的报错原文 |
| `probe_identity_map.py` | **§3.3** | 身份映射内部结构（`_WeakInstanceDict`，键是 `(类, 主键元组, token)`）/ `get` 第二次不发 SQL / `select` 发 SQL 但返回同一对象 / 改动后同 session 查看到内存新值 / `expunge` 出新对象 / 跨 session 的 **lost update** |
| `probe_config.sql` | **D1b §三~§八** | 字符集四级链 / `SET NAMES` 只改三件套 / `VARCHAR(5)` 是字符数 / collation 影响相等与唯一索引 / `DATETIME` vs `TIMESTAMP` 差 8 小时 / 严格模式 vs 静默截断 / 表名小写 / `variables_info` 变量来源 |
| `probe_pool.py` | **D1b §七** | `pool_pre_ping` 对 `KILL` 掉死连接的自动重连 / `pool_size + max_overflow` 扩容与归还 / `wait_timeout` 阈值 |

> **D1b 的两条特殊跑法**（都实测过）：
>
> ```powershell
> # Windows PowerShell（仓库根）
> # 1) SQL 探针。别用 `<`（PowerShell 不支持），也别用管道（中文会变 ???），要用 mysql 内置的 source
> [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
> & "F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe" `
>   -h 127.0.0.1 -P 3307 -u root --default-character-set=utf8mb4 `
>   -e "source progress/week7/probes/probe_config.sql"
> # 2) 池探针
> & .\kb-service\.venv\Scripts\python.exe .\progress\week7\probes\probe_pool.py
> ```
>
> ```bash
> # Git Bash（bash 支持 `<`，可以直接用；注意用正斜杠）
> /f/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysql.exe -h 127.0.0.1 -P 3307 -u root \
>   --default-character-set=utf8mb4 < progress/week7/probes/probe_config.sql
> ./kb-service/.venv/Scripts/python.exe ./progress/week7/probes/probe_pool.py
> ```
>
> `probe_config.sql` 会建/删一个 `cfg_lab` 库，**不碰 `kb_dev`**；跑完自己清理干净。
> 两个探针都需要 MySQL 在 3307 上跑着。

实测环境：Python 3.11.17 · SQLAlchemy 2.1.8 · FastAPI 0.150.0 · Windows。
换版本数字可能变（尤其 `in_transaction()` 的时机），改动前先重跑。
