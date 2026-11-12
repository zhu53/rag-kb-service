# W7-D1b MySQL 配置态解剖 —— 你手上这个实例是怎么"配"出来的

> **前置**：D1 已读（Engine / Session / 事务）。D1 讲的是**客户端视角**：代码里怎么用 session。
> 这一篇讲**服务端视角**：这个库本身是怎么被"配"出来的，每个参数管什么，改错了会怎样。
>
> **全部结论实测于 2026-11-12**，环境：MySQL 8.4.0 LTS @ 127.0.0.1:3307，
> `F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0`。凡是标了「实测」的地方，输出都是真跑的。
>
> **为什么单独写这一篇**：周计划里我原本写的是"装库细节、字符集配置这类配置态我给现成命令不展开"。
> 后来改主意了，但理由要说准：**配置参数本身不是面试题，配置错了产生的故障才是**。utf8 存不了 emoji、
> 时区差 8 小时、`MySQL server has gone away`、大小写表名换台机器报表不存在……
> 每个故障背后都是一个"**为什么必须这么配**"。而你现在手上有一个真实实例，拆它比背文档强一百倍。
>
> ⚠️ **不要逐行读，也不要背参数**。这篇是"手册 + 六条因果链"，读法见下。

---

## §0.1 读法：这篇里哪些是面试重点（2026-11-12 校准）

面试官**不会**问"`collation-server` 那一行怎么写"。他们问的是"你的库为什么用 utf8mb4"、
"为什么接口偶发 500 报 `gone away`"。所以判据只有一条：

> **能说出"不这么配会发生什么故障"的，是面试重点；只能说出"应该这么配"的，不是。**

| 级别 | 内容 | 怎么处置 |
|---|---|---|
| **A 级** | 下面 6 条因果链 + 2 个时间数字 | **背因果链，不背参数名** |
| **B 级** | §二~§八 其余配置项、`SET PERSIST`、`performance_schema.variables_info` 排查手法 | 扫一遍留印象，出事回来搜 |
| **C 级** | `[mysqld]` 那 8 行的具体写法、端口、路径、启动脚本 | 照抄，永远不用记 |

**A 级 6 条**（格式统一为：故障现象 → 根因 → 配置/机制）：

| # | 故障现象 | 根因 | 配置 / 机制 |
|---|---|---|---|
| 1 | 昵称带 emoji 报 `Incorrect string value: '\xF0\x9F...'` | MySQL 的 `utf8` 是 `utf8mb3`，最多 **3 字节**，存不了 4 字节字符 | `character_set_server=utf8mb4`；建库建表显式 `COLLATE utf8mb4_0900_ai_ci` |
| 2 | 两个 `Alice` / `alice` 同时存在，唯一索引没拦住 | `_ai_ci` 不区分大小写、不区分重音，`'Alice' = 'alice'` 为真 | 用户名/邮箱列用 `utf8mb4_0900_as_cs` 或 `utf8mb4_bin` |
| 3 | 时间差 8 小时；比较时抛 `can't subtract offset-naive and offset-aware` | `DATETIME` 不带时区（原样存原样读）；`TIMESTAMP` 按**会话**时区换算 | `time_zone='+00:00'`；应用侧一律 `datetime.now(UTC)`，读出 `tzinfo is None` 就按 UTC 补 |
| 4 | 数据莫名少了一截，日志一条异常都没有 | 非严格 `sql_mode` 下超长**静默截断**（本篇实例默认是严格的，只在 `SET SESSION sql_mode=''` 后复现） | 保持 `STRICT_TRANS_TABLES`；别为了"少报错"关掉它 |
| 5 | 接口偶发 `MySQL server has gone away` / `Lost connection` | `wait_timeout=28800`（8h）到期服务端单方面断，池里仍留着这条死连接 | `pool_pre_ping=True`（每次借出先探活）+ `pool_recycle` 设成**小于** `wait_timeout` |
| 6 | 一个请求卡住，别的请求全超时 | 漏 `close()` 的 session 拿着行锁不放 | `innodb_lock_wait_timeout=50`（秒）；`get_db` 的 `finally: close()` |

**A 级 2 个数字**（本篇实测值，记这两个就够）：

```
wait_timeout            = 28800 秒（8 小时）   ← "gone away" 的倒计时
innodb_lock_wait_timeout = 50   秒            ← "卡住"到报错的忍耐上限
```

> **顺带记住 SQLAlchemy 的两个默认值也是 None（=不启用）**：`pool_pre_ping=None`、`pool_recycle=None`。
> 也就是说"连接池自动处理死连接"这件事**默认并不成立**，得你自己开。

剩下的内容当手册用：想不起某个参数干什么，`Ctrl+F` 搜变量名回来看。**不要为了"读完整"而通读 1800 行。**

---

## §零 主线：一条装配线，八个刻度

把"MySQL 能用了"这件事拆成一条时间线。**配置不是一堆静态的键值对，是在这条线上的不同时刻"生效"的。**

> **先别怕这里出现的词**（实例、端口、数据目录、字符集、collation（排序规则）、认证插件、连接池、落盘……）。
> 这一节只要求"混个脸熟 + 记住分界线"，**每个词的准确含义在 §0.5 逐个定义**。
> 读第一遍时不认识的词直接跳过，读完 §0.5 再回来读一遍这一节——这是刻意设计的顺序。

```
━━━ 服务端一生只做一次的事（改配置 = 重启） ━━━
① mysqld.exe 被双击
   找配置文件：--defaults-file 指定 / 否则按默认顺序搜
   找不到 → 全部用编译默认值（我们的 608 个变量就是这么来的）

② 解析 [mysqld] 段
   basedir、datadir、port、字符集、时区、连接上限……全部在内存里定下来
   ← 从这一刻起，"这个实例是什么环境"就定了

③ 第一次初始化（--initialize-insecure，只跑一次）
   data 目录被创建，系统库 mysql 的表结构 + 字符集 + collation 写进磁盘
   ← 【本篇最重要的一条】从这里开始，字符集脱离了配置文件，改成 utf8mb4 也改不动已建的东西

④ 监听端口，开始接客
   TCP 3307 进入 LISTENING

━━━ 每一次连接都要重做的事 ━━━
⑤ 客户端找 [client] 段 → 决定"往哪连、用什么字符集谈"

⑥ 握手第一问：你是谁？
   服务端拿 user + 连上来的 host，去 mysql.user 表里匹配
   匹配到 → 看这一行的 plugin 字段决定用什么认证方式

⑦ 认证通过 → 协商字符集（client/connection/results 三件套）→ 继承一堆会话变量
   time_zone、sql_mode、transaction_isolation 在这一刻"复制"给这个会话

⑧ 会话开始跑 SQL
   这个会话里 SET 的东西（SET NAMES / SET time_zone）只影响自己，不影响别人
```

**贯穿全篇的那条分界线**：

> **`[mysqld]` 决定"这个库是什么环境"——改一次，所有连接都变，要重启。**
> **`[client]` / 连接串决定"这一次连接怎么谈"——改一次，只影响这一次会话。**
> **而已经落盘的东西（字符集、表结构、数据），配置文件说什么都没用了。**

记住这三句话，本篇后面所有细节都挂在这条线上。

---

## §0.5 开工前的词表

### 0.5.1 五个基础设施词（不懂这些，后面全是天书）

| 词 | 一句人话 | 没有它会怎样 | 在我们这对应什么 |
|---|---|---|---|
| **实例**（instance） | 一个跑起来的 `mysqld.exe` 进程 + 它管的一堆文件 | 你只有一堆文件，没有任何东西在响应 | PID 48536 那个进程 |
| **端口**（port） | 一台机器上区分"不同服务"的号码；MySQL 默认 3306 | 两个 MySQL 抢同一个门牌号，后起的起不来 | 我们用 **3307** |
| **数据目录**（datadir） | 所有库、表、日志、事务日志都在这一个目录里 | 数据不知道往哪存 | `tools\mysql-8.4.0\data` |
| **配置文件** | 一个文本文件，写"启动时用什么参数" | 每次启动都要手打几十个参数，且记不住 | `tools\mysql-8.4.0\my.ini` |
| **参数/变量**（variable） | 一个名字 + 一个值，控制某个行为 | 行为全靠硬编码，改不了 | `port=3307` 里的 `port` |

> **"参数"和"变量"是同一个东西的两个名字**：写在配置文件里叫**参数（option）**，
> 在运行时用 `SHOW VARIABLES` 看到叫**变量（variable）**。而且名字可能还不一样（§4.4 有个真实例子）。

### 0.5.2 十个配置词

| 词 | 一句人话 | 没有它会怎样 | 在我们这对应什么 |
|---|---|---|---|
| **动态参数 / 静态参数** | 动态的能在线改（`SET GLOBAL`），静态的只能改文件重启 | 你以为改了就生效，实际没变 | `max_connections` 动态、`port` 静态 |
| **全局变量 / 会话变量** | 全局的给所有新连接当模板；会话的只属于当前连接 | 你在一个窗口 `SET` 了，另一个窗口没变，以为见鬼了 | `@@global.time_zone` / `@@session.time_zone` |
| **字符集**（character set） | 字符 ↔ 字节的翻译规则 | 中文变 `???`，emoji 存不进去 | `utf8mb4` |
| **排序规则**（collation） | 在某个字符集下，"谁大谁小、什么算相等" | `WHERE name='alice'` 查不到 `Alice`，或者查到了不该查到的 | `utf8mb4_0900_ai_ci` |
| **认证插件**（auth plugin） | 密码怎么加密、怎么校验的一套算法 | 客户端和服务端算法对不上，连不上 | `caching_sha2_password` |
| **连接串 / DSN** | 一行字符串，把"驱动+账号+密码+地址+库+参数"全写进去 | 要写 6 个参数到处传 | `mysql+pymysql://kb:...@127.0.0.1:3307/kb_dev?charset=utf8mb4` |
| **连接池**（pool） | 客户端预先留几条连接反复用，省掉"每次连一次"的开销 | 每个请求都握手一次，QPS 上不去 | `pool_size=5`、`max_overflow=10` |
| **严格模式**（strict mode） | 数据不合规时**报错**，而不是偷偷改一改塞进去 | 存进去的是被截断的假数据，你还以为成功了 | `sql_mode` 里的 `STRICT_TRANS_TABLES` |
| **落盘** | 写到磁盘文件，进程重启还在 | 你以为配置改了，重启后全回去了 | §3.10、§8.2 |
| **静默失效** | 配错了不报错，就是不生效 | 排查半天才发现 `[mysqld]` 拼成了 `[mysqldd]` | §2.6 |

### 0.5.3 三问自检

读这篇之前，你至少要能回答：

1. **"3306 和 3307 是什么关系？"** —— 同一台机器上两个独立的 MySQL 实例，各管各的数据目录，互不知道对方存在。
2. **"配置文件改了，为什么重启才生效？"** —— 大部分参数是"启动时读一次、写进内存"的，改了文件内存里那份不会自己变。
3. **"为什么数据库里存的是 UTC，页面上显示的是北京时间？"** —— 库里统一存 UTC，显示时按用户时区转换。**存和显示是两件事**（§4 详讲）。

答不上来就先读这一篇，别去读 D2。

---

## §一 痛点：没有配置文件的世界

先看"没有它会怎么做"，这是理解一切的起点。

### 1.1 手工启动一个 MySQL 要打多少参数

假设没有配置文件，你得这样启动（这些参数都是真实存在的）：

```bat
mysqld.exe --basedir=D:\mysql --datadir=D:\mysql\data --port=3307 ^
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci ^
  --default-time-zone=+00:00 --max_connections=100 ^
  --innodb_buffer_pool_size=256M --log-error=D:\mysql\data\error.log
```

十一个参数。**三个具体的麻烦**立刻出现：

| 麻烦 | 具体表现 | 后果 |
|---|---|---|
| **记不住** | 少写 `--datadir` → 它可能去 `C:\Program Files\MySQL\data` 找个空目录，起来是个空库 | 你以为数据丢了，其实是连错了实例 |
| **复制不了** | 换台机器/换个人，得重新问"你那台是怎么起的" | 环境永远不一致，bug 只在一台机器上出现 |
| **没法回滚** | 改坏了不知道改之前是什么 | 只能靠记忆恢复，或者重装 |

### 1.2 配置文件解决的正是这三件事

| 需求 | 配置文件的回答 |
|---|---|
| 记不住 | 写一次，永久生效 |
| 复制不了 | 一个文本文件，拷过去就是同一个环境 |
| 没法回滚 | 进 git / 手动备份，能 diff、能回滚 |

**所以"配置文件"的本质不是"方便"，是"环境即代码"**。这也是为什么本项目连 `ruff.toml`、`pyproject.toml`、`.pre-commit-config.yaml` 都要进 git——同一套思路。

> 一个诚实的补充：面试里不会问你"配置文件有什么用"，但会问
> "**你怎么保证开发/测试/生产环境一致**"——这就是这道题的底层答案。

---

## §二 `my.ini` 逐行解剖

### 2.1 全文（就是你现在跑着的这份）

```ini
[mysqld]
basedir=F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0
datadir=F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/data
port=3307
# 关掉 X Protocol（默认 33060 会和已有的 MySQL80 抢端口）
mysqlx=0
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
# 统一按 UTC 存时间：项目里一律 datetime.now(UTC)，库也跟着 UTC，避免"差 8 小时"扯皮
default-time-zone='+00:00'
# skip-name-resolve  ← 8.4 初始化只建 root@'localhost'，加了它 127.0.0.1 会被判 Host not allowed
max_connections=100
innodb_buffer_pool_size=256M
log-error=F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/data/error.log

[client]
port=3307
default-character-set=utf8mb4
```

一共 **13 行有效配置**。13 行就能决定一个数据库的全部"性格"。下面逐行拆。

### 2.2 逐行表格

| 行 | 参数 | 管什么 | 我们为什么这么写 | 写错的症状 |
|---|---|---|---|---|
| `[mysqld]` | 段名 | 这一段只给**服务端**进程读 | 服务端参数必须放这里 | 写进 `[client]` → 服务端看不见，静默失效 |
| `basedir` | 安装根目录 | 去哪找 `share/`（错误信息模板、字符集定义）、`lib/` | 免安装版必须显式指定，否则它按编译时的路径找 | 起不来：`Can't find error-message file` |
| `datadir` | 数据目录 | 库、表、binlog、redo log 全在这 | 独立目录 = 删掉整个实例不伤别人 | 指到已有目录 → 可能覆盖别人的库 |
| `port` | 监听端口 | 门牌号 | 3306 被一个遗留的 MySQL 8.0 占着，我们走 **3307** | 起不来：`Do you already have another mysqld server running on port` |
| `mysqlx=0` | 关 X Protocol | 一个给 NoSQL/文档式访问用的新协议，默认 33060 | 33060 也被那个 8.0 占着，不关就抢端口 | 起不来（端口冲突），或者白占一个端口 |
| `character-set-server` | 服务端默认字符集 | 新建库/表**没显式指定时**的默认值 | `utf8mb4` 才是完整的 UTF-8（见 §3.5） | 用 `utf8` → emoji 存不进去（1366） |
| `collation-server` | 服务端默认排序规则 | 字符串怎么比大小、什么算相等 | `0900_ai_ci` 是 8.0 起的新标准（见 §3.7） | 大小写敏感/不敏感和预期不符 → 查询结果集变化 |
| `default-time-zone` | 默认时区 | 新会话继承的 `time_zone` | `'+00:00'` = UTC，和代码里 `datetime.now(UTC)` 一致 | 库里存北京时间、代码按 UTC 读 → **差 8 小时** |
| `max_connections` | 最大连接数 | 服务端最多同时接多少条连接 | 学习机 100 够用（生产要按池子算，见 §7.5） | 打满 → `Too many connections`，全站 500 |
| `innodb_buffer_pool_size` | InnoDB 缓冲池 | 缓存热数据和索引的内存区，**MySQL 最重要的参数** | 学习机 256M（实测 `268435456` 字节） | 太小 → 疯狂读盘，慢十倍 |
| `log-error` | 错误日志路径 | 启动失败、崩溃、死锁的信息都写这 | 出问题第一眼看它 | 路径写错 → 启动就失败，而且**你没日志可看** |
| `[client]` | 段名 | 这一段给**所有客户端工具**读（`mysql.exe`、`mysqldump.exe`…） | 这样不用每次敲 `-P 3307` | 忘写 → 每次都要手打端口 |
| `port` | 客户端默认端口 | 连哪个门牌号 | 与服务端一致 | 连到 3306 那个遗留实例上，看到的是别人的库 |
| `default-character-set` | 客户端默认字符集 | 客户端发 SQL 时用什么编码 | `utf8mb4` | 中文变问号（乱码，见 §3.4） |

### 2.3 五个值得单独说的

#### 2.3.1 `datadir` 里到底有什么（看一眼就懂为什么它不能乱指）

```
data/
├── #ib_16384_0.dblwr       ← doublewrite buffer（防页损坏）
├── #innodb_redo/           ← redo log（崩溃恢复用）
├── #innodb_temp/           ← 临时表空间
├── ACER.pid                ← 当前进程号，mysqld 靠它判断"我是不是已经在跑"
├── auto.cnf                ← 实例唯一 ID（主从复制用：从库靠它认主库，同 ID 会被拒绝）
├── binlog.000001 / .000002 ← 二进制日志（记下所有改数据的操作，主从复制靠它重放，也可用来做数据恢复）
├── mysql/                  ← 系统库（账号、权限、表定义）
├── kb_dev/                 ← 我们的业务库
└── sys/ performance_schema/ information_schema/
```

**`ACER.pid` 值得一提**：机器名 + `.pid`。MySQL 启动时会检查这个文件，发现里面的进程还活着就拒绝启动（"另一个实例在跑"）。所以有时"端口明明空着却起不来"，是这个文件在拦。

#### 2.3.2 `port`：为什么要 3307，以及"端口能证明你在连谁"

我们机器上其实有**两个** MySQL：

| 实例 | 端口 | 谁装的 | 我们用它吗 |
|---|---|---|---|
| MySQL 8.0（Windows 服务 `MySQL80`） | 3306 | 不知道（可能是遗留） | **不用**，不碰 |
| MySQL 8.4.0（我们解压的 zip） | **3307** | 我解的 | **就用它**，学完删目录即走 |

实测证据——`--no-defaults` 不读配置时，客户端默认去 3306，直接撞上那个遗留实例：

```
$ mysql.exe --no-defaults -u root -e "SELECT @@port;"
ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: NO)
```

**这条错误不是"密码错"那么简单**：它证明"不读配置文件 → 连到了另一个实例"。排查连接问题时，**第一件事永远是确认端口**，因为"连错库"和"数据丢了"在症状上几乎一样。

#### 2.3.3 `mysqlx=0`：一个你可能永远用不上但会害你的协议

MySQL 8.0 起自带 **X Protocol**，默认端口 **33060**，用于文档式/NoSQL 风格访问（MySQL Shell、Connector/X）。我们完全用不到，但它：
- 默认开启 → 白占一个端口
- 33060 已被那个 8.0 实例占用 → 我们起不来

所以显式关掉。**这类参数的特点：你没配它，它也在工作。** 配置文件的价值一半来自"我打开了什么"，另一半来自"我明确关掉了什么"。

#### 2.3.4 `log-error` 配了，但文件不在（真实踩坑）

看这个矛盾：

```
$ ls data/error.log
head: cannot open 'data/error.log' for reading: No such file or directory
```

配置里明明写了 `log-error=.../data/error.log`，实例也在跑，**文件却不存在**。

原因：我们用 `--console` 启动。

```
$ mysqld.exe --defaults-file=...\my.ini --console
```

`--console` 在 Windows 上的语义是"**把错误日志写到标准错误（stderr），不写文件**"。它**覆盖** `log-error`。

所以：
- **学习期用 `--console`**：错误直接打在终端里，起不来立刻看见 → 这是对的
- **生产用服务方式启动**（不带 `--console`）：才会真的写 `error.log`

> **这条测试题很经典**：「配了 log-error 但日志文件不存在」，99% 是 `--console` / `--log-error=stderr` 覆盖了。
> 你不是配错了，你是被另一条优先级更高的设置盖住了。

#### 2.3.5 `innodb_buffer_pool_size`：唯一的"性能参数"

其它参数管"对不对"，这一个管"快不快"。

它的作用：InnoDB 在内存里开一块区域，缓存**数据页和索引页**。查询要的数据在池里 → 直接内存返回；不在 → 从磁盘读。

| 场景 | 建议值 | 理由 |
|---|---|---|
| 学习机（我们） | 256M | 内存是共享的，别占太多 |
| 专用数据库服务器 | 物理内存的 **50%–75%** | 剩下的留给 OS 文件缓存和每个连接的会话内存 |
| 云上小规格（1G 内存） | 128M–256M | 开太大反而被 OOM 杀掉 |

**面试常问**："buffer pool 设多大？" 标准答法不是背百分比，是：
> "先看数据总量，如果热数据能全放进内存，就按热数据量给；放不进去就给到物理内存的 60–70%，
> 然后看 `Innodb_buffer_pool_read_requests` 和 `Innodb_buffer_pool_reads` 的比值（命中率），
> 低于 99% 说明池子不够。"

（这两个状态变量 `SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%'` 就能看，D3 讲索引时会用到。）

### 2.4 配置文件是怎么被找到的

`mysqld.exe` 启动时按顺序找，**找到第一个就用，不合并**（这是 MySQL 的规则，和有些软件"层层覆盖"不同）：

**Windows 上的默认搜索顺序**：

```
%WINDIR%\my.ini  →  %WINDIR%\my.cnf  →  C:\my.ini  →  C:\my.cnf
→  basedir\my.ini  →  basedir\my.cnf
→  还有 --defaults-extra-file 指定的
```

**Linux 上**：`/etc/my.cnf` → `/etc/mysql/my.cnf` → `SYSCONFDIR/my.cnf` → `~/.my.cnf` …

我们用 `--defaults-file` 强制指定，绕开这套搜索。**两个必须知道的规则**：

**规则一：`--defaults-file` 必须是第一个参数。**

```
$ mysql.exe -u root --defaults-file="...\my.ini" -e "SELECT @@port;"
mysql: [ERROR] unknown variable 'defaults-file=F:/.../my.ini'.
```

它被当成"一个叫 defaults-file 的变量"了——因为配置文件还没读，它不知道这是个"文件路径参数"。**错误信息很误导**：不是"位置错了"，是"不认识的变量"。这条坑我在启动脚本里已经替你避开了（`mysqld.exe --defaults-file=... --console`）。

**规则二：配置文件的选项名用连字符，不用下划线。**

```ini
default-time-zone='+00:00'    ✅ 正确
default_time_zone='+00:00'    ❌ 不认
```

但 `SHOW VARIABLES` 查的时候是**下划线**：

```sql
SHOW VARIABLES LIKE 'time_zone';      -- 变量名（下划线）
```

**配置文件用连字符，变量名用下划线**——这是两个命名体系，别混。

### 2.5 段名 = 程序名（实测）

`my.ini` 里的 `[xxx]` 不是"逻辑分组"，是**"给哪个程序读"**。

用 `--print-defaults` 能直接看到解析结果（**这是排查"配置到底生效没有"的第一把刀**）：

```
$ mysqld.exe --defaults-file="...\my.ini" --print-defaults
mysqld.exe would have been started with the following arguments:
--basedir=F:/.../mysql-8.4.0 --datadir=F:/.../mysql-8.4.0/data --port=3307
--mysqlx=0 --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci
--default-time-zone=+00:00 --max_connections=100 --innodb_buffer_pool_size=256M
--log-error=F:/.../data/error.log

$ mysql.exe --print-defaults
mysql.exe would have been started with the following arguments:
--port=3307 --default-character-set=utf8mb4
```

两件事一眼看清：

1. **`mysqld` 只读到 `[mysqld]` 那一段，`mysql` 只读到 `[client]` 那一段。** 互不干扰。
2. **`[client]` 段里没有 `host` 和 `user`** —— 所以 `mysql.exe -u root` 不带 `-h` 时，它连的是……本机（默认），端口却自动是 3307。实测：

```
$ mysql.exe -u root -e "SELECT @@port, @@character_set_client;"
连到哪个端口  客户端字符集
3307          utf8mb4
```

**不用 `-P 3307` 就能连对**，全靠 `[client]` 段。这就是配置文件的"一次配置、处处受益"。

### 2.6 段名拼错 = 静默失效（最容易浪费一整天的那种坑）

MySQL **不会**因为配置文件里有不认识的段名或参数名就拒绝启动。它要么忽略，要么在错误日志里写一行警告然后继续。

| 你写的 | 结果 | 症状 |
|---|---|---|
| `[mysqld]` | ✅ 正常 | — |
| `[mysqldd]` | ❌ 整个段被忽略 | 所有参数都没生效，但**零报错** |
| `[mysql]` 里写 `port=3307` | ⚠️ 只有 `mysql.exe` 读到 | 服务端还是 3306，客户端却连 3307 → 连不上 |
| `[mysqld]` 里写 `character_set_server=utf8mb4`（下划线） | ❌ 不认 | 字符集没变，你以为是 MySQL 的问题 |
| `datadir = F:/path`（等号两边有空格） | ✅ 空格会被裁掉 | — 这个反而没问题 |

**排查口诀**：配置没生效 → 先 `--print-defaults` 看有没有被解析出来。没解析出来 = 名字/段名写错；解析出来了但行为不对 = 优先级问题（§2.7）或被 `--console` 之类覆盖（§2.3.4）。

### 2.7 两个配置源：`my.ini` 和 `mysqld-auto.cnf`

除了 `my.ini`，`datadir` 里还有个**自动生成**的配置文件：

```
data/mysqld-auto.cnf
```

它是 `SET PERSIST` 命令的产物（§8.2 实测）。**加载顺序：`my.ini` 先，`mysqld-auto.cnf` 后** → 所以后者**会覆盖**前者。

这意味着：

> 你改了 `my.ini` 但重启后没生效，很可能是 `mysqld-auto.cnf` 里有个更晚加载的值把它盖住了。
> 排查方法：`cat data/mysqld-auto.cnf`，或者 `RESET PERSIST` 清空它。

我们现在这份是干净的（清理过实测痕迹）：

```json
{"Version": 2}
```

---

## §三 字符集与 collation —— 本篇最重的一节

### 3.1 两个概念，各一句话

| 概念 | 一句话 | 类比 |
|---|---|---|
| **字符集**（charset） | 字符 ↔ 字节的**翻译表**：`'中'` = 哪个字节序列？ | 密码本。同一段文字，用不同密码本翻出来字节完全不同 |
| **排序规则**（collation） | 在这个字符集下，**谁大谁小、什么算相等** | 字典的排序习惯。同样的字，按拼音排还是按笔画排 |

**两个必须分开的问题**：

- **存不进去**（字符集问题）→ 报错 1366，或者变成 `???`
- **查不出来 / 查出多余的**（collation 问题）→ 不报错，结果集悄悄不对

第二类比第一类危险得多，因为**没有错误**。

### 3.2 四级继承链（实测）

字符集不是"一个值"，是**四级继承**，逐级可覆盖：

```
server（my.ini 的 character-set-server）
  └─ database（CREATE DATABASE ... CHARACTER SET ...，不写就继承 server）
       └─ table（CREATE TABLE ... CHARACTER SET ...，不写就继承 database）
            └─ column（col VARCHAR(20) CHARACTER SET ...，不写就继承 table）
```

实测我们的系统库：

```
$ SHOW CREATE DATABASE mysql;
CREATE DATABASE `mysql` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */
                 /*!80016 DEFAULT ENCRYPTION='N' */

$ SHOW CREATE DATABASE kb_dev;
CREATE DATABASE `kb_dev` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */
```

**`mysql` 系统库（存账号、权限、表定义的那个库）也是 utf8mb4** —— 这不是巧合，是 §3.10 要讲的"初始化即落盘"。

建库时我们写的是：

```sql
CREATE DATABASE kb_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

其实 `my.ini` 里已经设了默认值，**显式再写一遍是刻意的**：让"这个库要 utf8mb4"这件事写在建库语句里，而不是藏在某台机器的配置文件里。**依赖默认值 = 依赖那台机器的配置。**

**本节最重要的一句**：

> **继承只发生在"创建"的那一刻。** 后来改 server 默认值，已存在的库/表/列**一个都不会变**。
> 想让老表变 utf8mb4，得 `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4`（而且有索引长度、数据量、锁表三个坑）。

### 3.3 三件套 + `SET NAMES`（实测）

客户端和服务端之间**不是"一个字符集"，是三个**：

| 变量 | 管什么方向 | 搞错的表现 |
|---|---|---|
| `character_set_client` | 客户端**发**出去的 SQL 是什么编码 | 服务端把你的中文按 latin1 解读 → 存进去就是乱的 |
| `character_set_connection` | 服务端拿到的 SQL 在**转换/比较**时用什么编码 | `WHERE` 比较结果不对 |
| `character_set_results` | 服务端**返回**结果用什么编码 | 你在终端看到 `???` 或乱码 |

实测 `SET NAMES latin1` 一次改了哪几个：

```
$ SHOW VARIABLES LIKE 'character_set_connection';
character_set_connection    utf8mb4

$ SET NAMES latin1;
$ SHOW VARIABLES LIKE 'character_set_%';
character_set_client        latin1      ← 变了
character_set_connection    latin1      ← 变了
character_set_database      utf8mb4     ← 没变（这是库的默认值）
character_set_filesystem    binary      ← 无关
character_set_results       latin1      ← 变了
character_set_server        utf8mb4     ← 没变（服务端默认值）
character_set_system        utf8mb3     ← 永远 utf8mb3（元数据内部用，不可改）
character_sets_dir          F:\...\share\charsets\
```

**结论：`SET NAMES x` 等价于同时设 `character_set_client` / `connection` / `results` 三个。只影响当前会话，不影响别人。**

> `character_set_system` 恒为 `utf8mb3` 这一条很反直觉，但它管的是"表名、列名这些元数据内部怎么存"，
> 和你的数据无关，**不要试图改它**（改了也白改）。

### 3.4 乱码的根因公式（背下来，一辈子够用）

```
乱码 = 写入时声明的编码  ≠  读出时声明的编码
```

**注意：不是"数据坏了"，是"两次声明不一致"。** 所以：

| 现象 | 说明 |
|---|---|
| 存进去是 `??` 或 `???` | **写的时候就丢了**（目标字符集没有这个字符），不可恢复 |
| 存进去是 `ä¸æ–‡` 这种鬼画符 | **数据是好的**，只是被当 latin1 读了。改对连接字符集就能显示 |
| `Incorrect string value: '\xF0\x9F\x98\x80'` | 目标列是 3 字节字符集，塞了 4 字节字符 → **被拒绝**（严格模式下） |

第三种的报错原文（下面 §3.5 实测）。

### 3.5 `utf8` 是个假 utf8（面试最高频的一道）

MySQL 的 `utf8` **不是** UTF-8，是 **`utf8mb3`**：最多 3 字节，只能覆盖 BMP（Basic Multilingual Plane，基本多文种平面，即码位 U+0000–U+FFFF 这一区，涵盖了世界上绝大多数常用文字）。

UTF-8 里 **4 字节**的那些字符（emoji、部分生僻汉字、部分音乐符号）：`utf8mb3` 存不了。

实测：

```sql
CREATE TABLE t_utf8mb3 (name VARCHAR(20)) CHARACTER SET utf8mb3;
CREATE TABLE t_utf8mb4 (name VARCHAR(20)) CHARACTER SET utf8mb4;

INSERT INTO t_utf8mb3 (name) VALUES ('😀');   -- 4 字节，U+1F600
```

```
ERROR 1366 (HY000): Incorrect string value: '\xF0\x9F\x98\x80' for column 'name' at row 1
```

**报错里的 `\xF0\x9F\x98\x80` 就是 😀 的 4 字节 UTF-8 编码**——MySQL 把原始字节打给你了，这就是"我收到的字节我没法用我这个 3 字节字符集表示"。

换 `utf8mb4` 表：

```sql
INSERT INTO t_utf8mb4 (name) VALUES ('😀');
SELECT name, CHAR_LENGTH(name) AS 字符数, LENGTH(name) AS 字节数 FROM t_utf8mb4;
```

```
name   字符数  字节数
😀      1      4
```

**1 个字符、4 个字节**——这两个数字后面（§3.9）还有用。

> **面试标准答案（30 秒版）**：
> "MySQL 的 `utf8` 是 `utf8mb3` 的别名，最多 3 字节，存不了 emoji 和部分生僻字，插入会报 1366。
> `utf8mb4` 才是完整的 UTF-8，最多 4 字节。所以建库建表一律 `utf8mb4`，
> 8.0 起默认值也已经是 utf8mb4 了，只有老库需要手动迁移。"

**追问一层**（为什么当年会这样）：MySQL 4.1 引入 UTF-8 支持时（2003 年），Unicode 还认为"21 位够用、3 字节能覆盖常用字符"，4 字节区被当作罕见。后来 emoji 普及，4 字节成了刚需，但改默认值会破坏兼容性，于是只能新增 `utf8mb4`，`utf8` 保持原义直到 8.0 才把默认值改掉。

**追问二层**（怎么迁移）：`ALTER TABLE t CONVERT TO CHARACTER SET utf8mb4`，注意三件事：① 索引前缀长度（`VARCHAR(255)` 从 765 字节变 1020 字节，可能超 `innodb_large_prefix` 限制，8.0 已解决）② 大表会锁/耗时长，要 `pt-online-schema-change` 或 `ALGORITHM=INPLACE` ③ 连接串和客户端也要一起改 `charset=utf8mb4`，否则"库里对了、读出来还是乱"。

### 3.6 collation 名字怎么读：`utf8mb4_0900_ai_ci`

拆成四段：

| 段 | 含义 | 我们这份 |
|---|---|---|
| `utf8mb4` | 属于哪个字符集 | 完整 UTF-8 |
| `0900` | 按 **Unicode 9.0.0** 的排序规则（UCA，Unicode Collation Algorithm，即"Unicode 官方规定的字符串比较算法"） | 8.0 的新标准 |
| `ai` | **accent insensitive**：重音不敏感，`a` = `á` | 不敏感 |
| `ci` | **case insensitive**：大小写不敏感，`a` = `A` | 不敏感 |

对应的反义：`as`（accent sensitive）、`cs`（case sensitive）、`bin`（按字节比，最严格）。

**实测四种组合**：

```sql
SELECT 'a' = 'A' COLLATE utf8mb4_0900_ai_ci,   -- 1（ci：大小写算同一个）
       'a' = 'A' COLLATE utf8mb4_0900_as_cs,   -- 0（cs：不同）
       'a' = 'á' COLLATE utf8mb4_0900_ai_ci,   -- 1（ai：重音算同一个）
       'a' = 'á' COLLATE utf8mb4_0900_as_cs,   -- 0（as：不同）
       'a' < 'B' COLLATE utf8mb4_0900_ai_ci,   -- 1
       'a' < 'B' COLLATE utf8mb4_0900_as_cs;   -- 1
```

```
1  0  1  0  1  1
```

**最后一列值得想一下**：`as_cs` 下 `'a' < 'B'` 也是 **1**。如果按字节比，`a`=0x61 > `B`=0x42，应该是 0。为什么是 1？

因为 `0900_*` 系列**按 Unicode 排序权重（UCA）比，不是按字节比**：`a` 和 `b` 的首权重 `a < b`，大小写只是次要权重。所以 `a < B` 成立。

**真正按字节比的是 `_bin`**：

```sql
SELECT 'a' < 'B' COLLATE utf8mb4_bin,        -- 0（0x61 > 0x42）
       'A' < 'a' COLLATE utf8mb4_bin,        -- 1（0x41 < 0x61）
       'A' < 'a' COLLATE utf8mb4_0900_as_cs; -- 0（权重相同，靠 case 级别比较）
```

```
0  1  0
```

> **一句话记法**：`_bin` = 比字节；`_ci/_cs` = 比 Unicode 权重，只是大小写算不算一样。

### 3.7 `general_ci` vs `0900_ai_ci`：换 collation 会改变查询结果（实测）

老代码/老教程里常见 `utf8mb4_general_ci`。它和 `0900_ai_ci` 的差别不只是"新旧"：

```sql
SELECT 'ß' = 'ss' COLLATE utf8mb4_general_ci,   -- 0
       'ß' = 'ss' COLLATE utf8mb4_0900_ai_ci,   -- 1
       '①' = '1' COLLATE utf8mb4_general_ci,    -- 0
       '①' = '1' COLLATE utf8mb4_0900_ai_ci;    -- 1
```

```
0  1  0  1
```

**这意味着什么**：在 `0900_ai_ci` 下，`WHERE name = '1'` 会**查出 `①`**；在 `general_ci` 下不会。同一句 SQL，换个 collation 结果集就变了。

- `general_ci` 的算法粗糙、覆盖范围窄（2000 年代初的实现）
- `0900_ai_ci` 严格遵循 Unicode 9.0 的 UCA，覆盖更准

**我们的选择**：`utf8mb4_0900_ai_ci`（8.0+ 默认）。理由：正确性优先，且是默认值——依赖默认值不如显式写（§3.2）。

> 一个真实的业务权衡：如果做**用户名查重**、**邮箱查重**，`ci` 是好事（`Alice` 和 `alice` 视为同一人，防重）；
> 如果做**密码哈希**、**token 比较**、**文件名**，`ci` 是灾难（两个不同的串被当成相等）。所以这些列应显式用 `_bin` 或 `_as_cs`。

### 3.8 collation 影响唯一索引（这条能造成生产事故，实测）

```sql
CREATE TABLE t_uniq_ci  (name VARCHAR(20) COLLATE utf8mb4_0900_ai_ci UNIQUE);
CREATE TABLE t_uniq_bin (name VARCHAR(20) COLLATE utf8mb4_bin UNIQUE);

INSERT INTO t_uniq_ci  VALUES ('Alice');
INSERT INTO t_uniq_bin VALUES ('Alice');

INSERT INTO t_uniq_ci  VALUES ('alice');   -- 只改了大小写
INSERT INTO t_uniq_bin VALUES ('alice');   -- 同样的操作
```

```
-- ci 表：
ERROR 1062 (23000): Duplicate entry 'alice' for key 't_uniq_ci.name'

-- bin 表：
+-------+
| name  |
+-------+
| Alice |
| alice |
+-------+
```

**同一个唯一索引，`ci` 下冲突、`bin` 下共存。**

这条的实战意义：

| 场景 | 该用 | 否则 |
|---|---|---|
| 用户昵称/邮箱唯一 | `_ci` | 有人能注册 `Admin` 冒充 `admin` |
| 邀请码/优惠码/token | `_bin` | `AbC123` 和 `abc123` 被判重复，发不出去 |
| 文件名/路径 | `_bin` | Linux 允许两个大小写不同的文件，MySQL 拦你 |

**注意报错里的 `Duplicate entry 'alice'`——你插的是 `alice`，它告诉你和已有的冲突，但没告诉你"和 `Alice` 冲突"**。第一次遇到会怀疑人生。

### 3.9 `VARCHAR(N)` 的 N 是**字符数**，不是字节数（实测）

这是 `utf8mb4` 迁移时最常见的误解。

```sql
CREATE TABLE t_len (name VARCHAR(5)) CHARACTER SET utf8mb4;
```

三次插入，看结果：

| 插什么 | 字符数 | 字节数 | 结果 |
|---|---|---|---|
| `'abcde'`（5 个 ASCII） | 5 | 5 | ✅ 成功 |
| `'abcdef'`（6 个 ASCII） | 6 | 6 | ❌ `ERROR 1406 Data too long for column 'name'` |
| `'中文中文中'`（5 个汉字） | 5 | **15** | ✅ 成功 |
| `'😀😀😀😀😀'`（5 个 emoji） | 5 | **20** | ✅ 成功 |
| `'😀😀😀😀😀😀'`（6 个 emoji） | 6 | 24 | ❌ 1406 |

实测输出：

```
name        字符数  字节数
中文中文中     5     15
😀😀😀😀😀     5     20
```

**所以 `VARCHAR(5)` 的 5 是"5 个字符"，能存 5 个汉字或 5 个 emoji。** 内存/磁盘占用按字节算（最长 5×4=20 字节）。

> 一个连带影响：`VARCHAR(255)` 在 utf8mb4 下最长占 255×4 = **1020 字节**，
> 早期 InnoDB 索引前缀限制 767 字节时，`VARCHAR(255)` 建索引会失败（`Specified key was too long`）。
> 8.0 已把这个限制提到 3072 字节，所以现在不会再报——**但这也是"老教程说不行、新版本可以"的典型例子**。

### 3.10 初始化即落盘（本篇最重要的一条）

`--initialize-insecure` 那一刻，**字符集和 collation 就写进了系统表**：

```
$ SHOW CREATE DATABASE mysql;
CREATE DATABASE `mysql` ... DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
```

`mysql` 这个库的表结构、账号表、权限表，全都是用**当时的**字符集建的。

**推论（记住这个因果链）**：

```
初始化时的 character-set-server
  → 决定 mysql 系统库的字符集
    → 决定账号名、库名、表名、列名这些元数据怎么存
      → 之后改 my.ini 的 character-set-server，这些"老东西"一个都不变
```

**所以"改配置让字符集变成 utf8mb4"是一个错觉**。真正要做的分两种情况：

| 情况 | 怎么办 |
|---|---|
| 库刚建、还没数据 | `DROP DATABASE` 重建成 utf8mb4，最干净 |
| 已有数据 | `ALTER DATABASE ... CHARACTER SET utf8mb4` + 逐表 `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4`，并一起改连接串 |

**实测补充一条**：我们的实例初始化时就带了 `--character-set-server=utf8mb4`，所以 `mysql` 库本来就是 utf8mb4。如果哪天你重装忘了带这个参数，`mysql` 库可能是 utf8mb3，那时会出现"账号密码里有中文/emoji 就登不上"这种离谱现象。

---

## §四 时区：`DATETIME` vs `TIMESTAMP`（实测差 8 小时）

### 4.1 两个类型，行为完全不同

| | `DATETIME` | `TIMESTAMP` |
|---|---|---|
| 存什么 | **字面值**，原样存原样取 | 转成 **UTC 时间戳**存，读时按会话时区转回 |
| 时区转换 | ❌ 不做 | ✅ 写入转 UTC、读出转本地 |
| 范围 | 1000-01-01 ~ 9999-12-31 | 1970-01-01 ~ 2038-01-19（**32 位限制**） |
| 占字节 | 5 字节 | 4 字节 |
| 自动更新 | 需显式 `ON UPDATE` | `DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

**实测：同一条记录，两个字段填同一个 `NOW()`，然后在不同会话时区下读**

```sql
CREATE TABLE t_time (d DATETIME, ts TIMESTAMP NULL);

SET time_zone = '+08:00';              -- 假装客户端在东八区
INSERT INTO t_time VALUES (NOW(), NOW());
SELECT @@session.time_zone AS tz, d, ts FROM t_time;
```

```
tz       d                     ts
+08:00   2026-11-12 16:38:24   2026-11-12 16:38:24    ← 写入时两个一样
```

```sql
SET time_zone = '+00:00';              -- 换到 UTC 会话
SELECT @@session.time_zone AS tz, d, ts, TIMESTAMPDIFF(HOUR, d, ts) AS 差几小时 FROM t_time;
```

```
tz       d                     ts                     差几小时
+00:00   2026-11-12 16:38:24   2026-11-12 08:38:24    -8
```

**同一条记录：`DATETIME` 纹丝不动（16:38:24），`TIMESTAMP` 少了 8 小时（08:38:24）。**

因为：
- `DATETIME` 存的就是字符串 `2026-11-12 16:38:24`，读写都不转换
- `TIMESTAMP` 写入时把 `16:38:24(+08:00)` 转成 UTC `08:38:24` 存起来；读到 UTC 会话时直接给你 UTC 值

**所以 TIMESTAMP 的"值"取决于你看它的时区，DATETIME 的"值"是死的。**

### 4.2 为什么本项目统一 UTC

我们 `my.ini` 里写了：

```ini
default-time-zone='+00:00'
```

配合代码里 `datetime.now(UTC)`，形成一条闭环：

```
代码写 datetime.now(UTC)  →  序列化成 +00:00 的时间  →  存进库（库时区也是 +00:00，不做转换）
     ↑                                                              ↓
页面显示时按用户时区转换  ←  读出 +00:00  →  比较/计算永远在 UTC 下进行
```

**好处**：跨时区部署（服务器在 UTC、用户在东八区、另一个用户在美西）不需要任何"加 8 小时"的魔法，转换只发生在**展示层**这一个地方。

**坏处**：用 `mysql.exe` 直接看数据时会觉得"时间不对"（比北京时间少 8 小时）。这不是 bug，是设计。

> **面试常问**："你们数据库时间用什么类型？" 
> 好答案："统一 `DATETIME` 存 UTC，应用层用带时区的 `datetime`（Python 的 `datetime.now(UTC)`），
> 展示层按用户时区转换。不用 `TIMESTAMP`，因为 2038 年问题，而且它的值随时区浮动，
> 排查问题时容易看错。"

### 4.3 三层时区，改哪一层影响谁

| 层 | 变量/参数 | 影响范围 | 怎么改 |
|---|---|---|---|
| 服务端默认 | `default-time-zone`（配置）/ `@@global.time_zone` | **新建立**的连接 | 改 my.ini 重启，或 `SET GLOBAL time_zone='+00:00'` |
| 会话 | `@@session.time_zone` | 当前连接 | `SET time_zone='+08:00'` |
| 客户端（Python） | 连接串 / 驱动参数 | 时间对象怎么序列化 | SQLAlchemy URL 的 `connect_args={"init_command": "SET time_zone='+00:00'"}` |

**注意 `SET GLOBAL` 对已存在的连接无效**——它们已经继承了旧值。这是"配置改了但看起来没生效"的常见原因（和 §8 呼应）。

### 4.4 选项名 ≠ 变量名（一个真实的坑）

配置里写的是 **`default-time-zone`**，但 `SHOW VARIABLES` 里**没有这个名字**：

```sql
SHOW VARIABLES LIKE 'default_time_zone';   -- 空结果！
SHOW VARIABLES LIKE 'time_zone';           -- 有
```

```
time_zone    +00:00
```

**`default-time-zone` 这个参数的作用是"设置 `time_zone` 的初始值"，它自己不是一个可查询的变量。**

同类例子：
- `character-set-server`（参数） → `character_set_server`（变量）
- `innodb-buffer-pool-size`（参数） → `innodb_buffer_pool_size`（变量）

**规律：参数名用连字符，变量名用下划线，且个别参数名和变量名根本不同名。** 查不到某个变量时，先怀疑"我查的是参数名还是变量名"。

### 4.5 `@@system_time_zone` 是空的（实测，反直觉）

```
$ SHOW VARIABLES LIKE 'system_time_zone';
system_time_zone    （空字符串）
```

`system_time_zone` 表示"操作系统报告的时区名"（比如 `China Standard Time`）。我们这台机器上它是**空**的。

含义：**MySQL 不知道操作系统在哪个时区**。如果这时你没有显式设 `default-time-zone`，新会话的 `time_zone` 会是 `SYSTEM`，而 `SYSTEM` 又解析不出具体偏移 → 行为不可预期。

**所以 `default-time-zone='+00:00'` 不是"锦上添花"，是"必须显式写"**。这条实测正好解释了为什么很多 Windows 上的 MySQL 会出现"时间差 8 小时"——它靠不住操作系统的时区。

> 顺带一个排查技巧：`SELECT NOW(), UTC_TIMESTAMP(), @@session.time_zone` 一行就能看出当前会话的时区对不对。

---

## §五 `sql_mode`：报错，还是偷偷改数据

### 5.1 严格模式：6 个字符塞进 `VARCHAR(5)` 会发生什么

同一个插入，两种 `sql_mode`：

**严格模式（我们现在的默认）：**

```sql
INSERT INTO t_len (name) VALUES ('abcdef');
```
```
ERROR 1406 (22001): Data too long for column 'name' at row 1
```

**非严格模式：**

```sql
SET SESSION sql_mode='';
INSERT INTO t_len (name) VALUES ('abcdef');
SELECT name, CHAR_LENGTH(name) AS 存了几个字符 FROM t_len WHERE name LIKE 'abc%';
```

```
name     存了几个字符
abcde    5
```

**`abcdef` 被静默截断成 `abcde`，而且 `SHOW WARNINGS` 是空的——连警告都没有。**

这就是严格模式存在的全部理由：

> **宁可让请求 500，也不要让数据库里悄悄躺着一半的数据。**

想想这个场景：用户昵称超长 → 非严格模式下存成被砍一半的昵称 → 用户看到自己叫"张三分"（原本"张三分明很生气"）。**没有人报错，没有人收到告警，数据已经错了。**

### 5.2 我们实例的完整 `sql_mode`（实测）

```
ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,
ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
```

六个，逐个说：

| 项 | 管什么 | 关掉会怎样 |
|---|---|---|
| `STRICT_TRANS_TABLES` | 写入不合规就报错（不是截断） | 超长截断、`NULL` 塞进 `NOT NULL` 变默认值（§5.1） |
| `ONLY_FULL_GROUP_BY` | `GROUP BY` 里没出现、又没聚合的列，不许查 | `SELECT name, COUNT(*) FROM t GROUP BY id` 能跑，但 `name` 是**随机一行**的值 |
| `NO_ZERO_IN_DATE` | 不许 `2026-00-15` 这种 | 存进一个不存在的日期 |
| `NO_ZERO_DATE` | 不许 `0000-00-00` | 存进一个"零日期"，读出来 Python 直接解析失败 |
| `ERROR_FOR_DIVISION_BY_ZERO` | 除零报错 | `1/0` 静默变 `NULL` |
| `NO_ENGINE_SUBSTITUTION` | 引擎不存在就报错，不偷偷换 | 你要 InnoDB，它给你 MyISAM，然后**事务失效** |

**`ONLY_FULL_GROUP_BY` 值得单独说**——它是 MySQL 5.7 起才默认开启的，是无数老项目升级时炸掉的原因。它拦的是这种 SQL：

```sql
SELECT department, name, COUNT(*) FROM employee GROUP BY department;
```

`department` 分组后，每组有多行，`name` 该取哪一行？MySQL 老版本"随便给你一个"，PostgreSQL / 标准 SQL 直接报错。开启后 MySQL 也报错，逼你写清楚（`ANY_VALUE(name)` 或把 `name` 加进 `GROUP BY`）。

> **面试点**：`ONLY_FULL_GROUP_BY` 是 MySQL 向标准 SQL 靠拢的一步。被问到"MySQL 和 Postgres 的差异"，
> 这是排前三的答案（其它是：默认隔离级别 RR vs RC、`utf8` 问题、`RETURNING` 支持、`UPDATE ... LIMIT`）。

### 5.3 为什么不建议关严格模式

网上有大量"报错就 `SET sql_mode=''`"的帖子。那是把问题从"看得见"改成"看不见"：

| 你遇到的报错 | 关掉严格模式后 | 真实该做的 |
|---|---|---|
| 1406 `Data too long` | 数据被截断 | 加长字段，或在应用层校验长度 |
| 1366 `Incorrect string value` | 变成 `???` | 换 utf8mb4 |
| 1048 `Column cannot be null` | 塞个默认值（0 / ''） | 补 `NOT NULL` 的默认值，或修业务逻辑 |
| 1292 `Incorrect datetime value` | 存 `0000-00-00` | 校验输入 |

**四条都是"关掉就消停，但数据全烂"**。

---

## §六 账号、host 匹配、认证插件

### 6.1 `user@host` 是一个整体

MySQL 的账号不是"用户名"，是 **`用户名@来源主机`** 一对：

```
$ SELECT user, host, plugin FROM mysql.user ORDER BY user, host;
user              host         plugin
kb                127.0.0.1    caching_sha2_password
kb                localhost    caching_sha2_password
mysql.infoschema  localhost    caching_sha2_password
mysql.session     localhost    caching_sha2_password
mysql.sys         localhost    caching_sha2_password
root              localhost    caching_sha2_password
```

**我们为什么建了两个 `kb`**：一个 `kb@localhost`，一个 `kb@127.0.0.1`。因为它们**不是同一个账号**。

### 6.2 `localhost` 和 `127.0.0.1` 不是一回事

| 你写 | MySQL 怎么理解 |
|---|---|
| `-h localhost` | 在 Windows 上走 **命名管道 / 共享内存**（不走 TCP！）；在 Linux 上走 unix socket |
| `-h 127.0.0.1` | 走 **TCP**，连到 `port` 指定的端口 |

因为走的是两条不同的路，"来源主机"被识别成两个不同的字符串 → 匹配到两条不同的账号记录。

**这就是为什么"我本地明明能连，Python 里却连不上"**：命令行默认 `localhost`，连接串里写的是 `127.0.0.1`，而只建了其中一个账号。

### 6.3 `skip-name-resolve` 的坑（我们亲自踩过）

这条配置在被注释掉之前是开着的：

```ini
# skip-name-resolve  ← 8.4 初始化只建 root@'localhost'，加了它 127.0.0.1 会被判 Host not allowed
```

`skip-name-resolve` 的作用：**不做反向 DNS 解析**（把 IP 反查成主机名），只按 IP 匹配账号。好处是连得快（省一次 DNS 查询）。

**但**：MySQL 8.4 初始化时只建 `root@localhost`。开了 `skip-name-resolve` 后，`127.0.0.1` 不再被解析成 `localhost`，于是：

```
ERROR 1130 (HY000): Host '127.0.0.1' is not allowed to connect to this MySQL server
```

**现象极具迷惑性**：`mysql -u root`（走 localhost）能连，`mysql -h 127.0.0.1 -u root` 连不上。你会以为是密码问题、防火墙问题，其实是账号匹配问题。

**解法二选一**：① 不开 `skip-name-resolve`（我们现在的做法）② 建 `root@'127.0.0.1'`。

> 生产上通常两条都做：开 `skip-name-resolve`（省 DNS），同时把所有账号按 IP 段建齐（`'app'@'10.0.%.%'`）。

### 6.4 匹配优先级：精确 > 通配 > 通配符

有多个账号都能匹配时，MySQL 按 **host 的"具体程度"** 选，不是按创建顺序：

```
'kb'@'127.0.0.1'      ← 最具体，优先
'kb'@'localhost'
'kb'@'127.0.0.%'
'kb'@'%'              ← 最宽，最后
```

**`%` 匹配任意字符（含空）**。所以 `'kb'@'%'` 能从任何 IP 登录——**这是安全事故的经典形态**：为了"先让它能连"，建了个 `%` 账号，然后忘了删。

> 我们的 `kb` 账号只授了 `kb_dev.*` 的权限，且只有 `localhost` / `127.0.0.1` 两个来源，**没有 `%`**。
> 这是有意的：学习机也别养成"图省事建 `%`"的习惯。

### 6.5 `caching_sha2_password`：为什么装 pymysql 还要装 cryptography

8.0 起默认认证插件从 `mysql_native_password` 换成了 `caching_sha2_password`（SHA-256，更安全）。

它的认证过程有个细节：**首次连接（缓存未命中）时，密码要先用服务端的 RSA 公钥加密再传**（否则密码等于明文过网）。RSA 加密需要 `cryptography` 库。

pymysql 源码里写得很清楚（`.venv/Lib/site-packages/pymysql/_auth.py:141`）：

```python
if not _have_cryptography:
    raise RuntimeError(
        "'cryptography' package is required for sha256_password or"
        + " caching_sha2_password auth methods"
    )
```

**所以我们 `uv add pymysql cryptography` 装了两个**——不是"顺手"，是必需。少了它，连接时报：

```
RuntimeError: 'cryptography' package is required for sha256_password or caching_sha2_password auth methods
```

> **面试点**：MySQL 8 默认 `caching_sha2_password`，老客户端（比如旧版 Navicat、旧 JDBC、旧 pymysql）可能连不上，
> 报 `Authentication plugin 'caching_sha2_password' cannot be loaded`。
> 正确解法是**升级客户端/装依赖**，不是把账号改回 `mysql_native_password`（那是降级安全性）。

### 6.6 8.4 里 `mysql_native_password` 已经**移除**了（实测，重要）

如果你照着老教程写：

```sql
CREATE USER 'x'@'localhost' IDENTIFIED WITH mysql_native_password BY 'pwd';
```

在 8.4 上会失败：

```
$ SELECT PLUGIN_NAME, PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME LIKE '%password%';
PLUGIN_NAME             PLUGIN_STATUS
sha256_password         ACTIVE
caching_sha2_password   ACTIVE
mysql_native_password   DISABLED        ← 注意这个

$ CREATE USER 'nat_test'@'localhost' IDENTIFIED WITH mysql_native_password BY 'x';
ERROR 1524 (HY000): Plugin 'mysql_native_password' is not loaded
```

**状态是 `DISABLED`，不是 `ACTIVE`。** 8.4 把它从"默认禁用但可加载"变成了"默认不加载"（要 `--mysql-native-password=ON` 才启用），并在未来版本彻底删除。

**这条的意义**：网上 90% 的"MySQL 8 连不上怎么办"教程都写着"改成 `mysql_native_password`"。**在 8.4 上这条路已经走不通了。** 遇到连接问题，正确方向是解决客户端依赖，而不是降级插件。

> 这也是"技术断言必须看版本"的最好例子。同一句话在 8.0 上对，在 8.4 上就是错的。

### 6.7 密码写在哪（一条工程纪律）

| 位置 | 能写吗 | 为什么 |
|---|---|---|
| 代码里 | ❌ | 一旦进 git，永久留在历史里，删也删不干净 |
| `config.py` 默认值 | ❌ | 同上（我们默认值是 sqlite，本来就不需要密码） |
| `.env` | ✅ | 已在 `.gitignore` 里，本机私有 |
| `.env.example` | ✅ 但只能是**占位符** | 它是提交进仓库的模板，`kb:密码@...` 这种不算泄露 |
| 环境变量 / 密钥管理服务 | ✅ | 生产标准做法 |

我们 `.env` 里：

```
DATABASE_URL=mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4
```

`.env.example` 里：

```
# DATABASE_URL=mysql+pymysql://kb:密码@127.0.0.1:3307/kb_dev?charset=utf8mb4
```

**注意 `.env.example` 里是中文"密码"两个字**——它一眼就能看出"这是占位符，不是真密码"。

> 顺带一句：`kb_dev_pwd` 这种弱密码在学习机无所谓，但**别把这种习惯带到任何会被别人访问的环境**。

---

## §七 连接池：客户端的配置，但和服务端是一对

### 7.1 池子的容量到底是多少（实测）

D1 讲过 `Engine` 是进程级连接池。具体数字：

```python
engine = create_engine(URL, pool_size=5, max_overflow=10)
```

实测——逐个借连接（借了不还），看服务端真实连接数：

```
借出  1 个 → 服务端 kb 连接数 = 2
借出  2 个 → 服务端 kb 连接数 = 3
...
借出  8 个 → 服务端 kb 连接数 = 9

pool.status(): Pool size: 5  Connections in pool: 1  Current Overflow: 4  Current Checked out connections: 8
全部归还后 → pool.status(): Pool size: 5  Connections in pool: 5  Current Overflow: 0  Current Checked out connections: 0
```

读这张表：

| 概念 | 值 | 含义 |
|---|---|---|
| `pool_size` | 5 | **常驻**连接数。池子里永远留着这么多（归还后 `Connections in pool: 5`） |
| `max_overflow` | 10 | 高峰期允许**临时超出** pool_size 的数量 |
| 容量上限 | **5 + 10 = 15** | 同一个 Engine 最多同时借出 15 条 |
| 超了会怎样 | — | 第 16 个请求**阻塞等待** `pool_timeout`（默认 30 秒），超时报 `QueuePool limit of size 5 overflow 10 reached` |
| `pool_timeout` | 30.0 | 等不到空闲连接就报错 |
| 池类型 | `QueuePool` | 同步引擎的默认池 |

**注意服务端连接数（9）总比借出数多 1** —— 那 1 条是探测查询自己用的连接。

### 7.2 `wait_timeout` 8 小时：为什么会有 `MySQL server has gone away`

```
$ SHOW VARIABLES LIKE 'wait_timeout';
wait_timeout    28800        ← 28800 秒 = 8 小时
```

**含义**：一条连接**空闲超过 8 小时**，服务端会主动关掉它（省资源）。

**问题**：服务端关连接时**不会通知客户端**。客户端池子里还留着这条"看起来还活着"的连接，下次借出去一用：

```
(2006, 'MySQL server has gone away')
```

或者

```
(2013, 'Lost connection to MySQL server during query')
```

**这个 bug 的经典特征**：

| 特征 | 说明 |
|---|---|
| 只在**低峰期**出现 | 夜里没人访问，连接空闲 8 小时 → 被关 |
| 早上第一个请求必挂 | 后面就正常了（池子重新建连） |
| 本地开发永远复现不了 | 你一天重启八次服务 |
| 日志里只有一条孤零零的 2006 | 没有任何前置错误 |

### 7.3 `pool_pre_ping`：专治这个（实测）

`pool_pre_ping=True` 的作用：**每次从池里取连接，先发一个极轻量的探测（`SELECT 1`），失败就丢弃重连。**

实测对比（用 `KILL` 从另一个连接杀掉池里的连接，精确模拟"服务端已断开"）：

```
pre_ping=False -> OperationalError: (2013, 'Lost connection to MySQL server during query')
pre_ping=True  -> 复用后查询成功: 1
```

**开关的差别就是"挂一次"和"无感重连"。**

| 配置 | 代价 | 收益 |
|---|---|---|
| `pool_pre_ping=True` | 每次借出多一次 `SELECT 1`（约 0.1ms，同机） | 死连接自动恢复，2006 基本消失 |
| 不开 | 零额外开销 | 低峰后首次请求偶发 500 |

**生产标配就是开**。学习机也开着——省得你半夜被"明明昨天还好好的"困扰：

```python
create_engine(url, pool_pre_ping=True)
```

### 7.4 `pool_recycle` 必须小于 `wait_timeout`

另一种解法是**主动**在连接变老之前扔掉重建：

```python
create_engine(url, pool_recycle=3600)  # 连接超过 3600 秒就重建
```

**硬规则**：`pool_recycle < wait_timeout`。

`wait_timeout` 是 28800，`pool_recycle=3600` 是安全的。如果你把它设成 40000（大于 28800），**等于没设**——连接早在 28800 就被服务端杀了，你还在池子里养着它。

| 方案 | 原理 | 缺点 |
|---|---|---|
| `pool_pre_ping` | 用之前验一下 | 每次多一次往返 |
| `pool_recycle` | 用之前先看年龄 | 年龄卡得不准（网络抖动、服务端重启不受控） |
| 两个都开 | 双保险 | 都没副作用，**推荐** |

### 7.5 容量规划：`max_connections` 够不够（这道算术题面试会问）

服务端 `max_connections=100`。客户端每个进程最多开 `pool_size + max_overflow = 15` 条。

**如果你用 8 个 worker 进程跑 FastAPI**：

```
8 worker × 15 = 120  >  100        ← 打满，第 101 条连接被拒
```

报错：

```
ERROR 1040 (HY000): Too many connections
```

**正确的算式**：

```
worker 数 × (pool_size + max_overflow) + 管理连接（监控/运维/你手动连的） < max_connections
```

学习机（单进程 + 你自己手动连）用 `5 + 10 = 15` 对 100，绰绰有余。但**这个算式要记住**，它是"为什么上线后数据库连接数爆了"的标准答案。

> 反过来也要注意：`max_connections` 不是越大越好。每条连接在服务端都要占内存（排序缓冲、临时表等），
> 1000 条连接可能吃掉几个 G。**"连接数过多"的正确解法是加连接池/减 worker，不是调大上限。**

### 7.6 本项目现在怎么配（对照 D1 的 `core/db.py`）

```python
# D1 的写法（学习版，参数都用默认）
engine = create_engine(settings.database_url, pool_pre_ping=True)

# 生产级写法（知道有这些旋钮即可，今天不改）
engine = create_engine(
    settings.database_url,
    pool_size=5,  # 常驻 5 条
    max_overflow=10,  # 高峰最多再开 10 条
    pool_timeout=30,  # 等连接最多 30 秒
    pool_recycle=3600,  # 1 小时重建，远小于 wait_timeout 8 小时
    pool_pre_ping=True,  # 借出前验活
    echo=False,  # 生产关掉 SQL 日志（性能 + 日志量）
)
```

**连接串里的参数 vs `create_engine` 的参数，作用不同**：

| 位置 | 管什么 |
|---|---|
| URL 的 `?charset=utf8mb4` | 传给 **pymysql 驱动**的（连接级字符集） |
| `create_engine(...)` 的关键字 | 传给 **SQLAlchemy 池**的（池行为） |
| `connect_args={...}` | 透传给驱动的其它参数（如 `init_command`） |

> **一个诚实的实测发现**：pymysql 2.2.8 的默认字符集**已经是 `utf8mb4`**
> （`connections.py:65: DEFAULT_CHARSET = "utf8mb4"`），所以 URL 里的 `?charset=utf8mb4` 在当前版本是
> **冗余的**。实测两种情况的结果完全一样：
>
> ```
> 不带 charset 参数     client=utf8mb4  conn=utf8mb4  results=utf8mb4
> 带 charset=utf8mb4    client=utf8mb4  conn=utf8mb4  results=utf8mb4
> ```
>
> **但仍然建议显式写**：① 老版本 pymysql 默认是 `utf8`（= utf8mb3）② 换驱动（mysqlclient/aiomysql）默认值不一定一样
> ③ 读代码的人不用去查驱动的默认值。**"依赖默认值"和"显式声明"之间，配置项永远选后者。**

---

## §八 参数改了，怎么才生效

### 8.1 三种改法，三种寿命

| 改法 | 立即生效？ | 重启后还在？ | 影响范围 | 适用 |
|---|---|---|---|---|
| `SET SESSION x=y` | ✅ | ❌ | 当前连接 | 临时调试（如 `SET time_zone`） |
| `SET GLOBAL x=y` | ✅（**仅对新连接**） | ❌ | 整个实例 | 临时救火（如临时调大 `max_connections`） |
| `SET PERSIST x=y` | ✅ | ✅ | 整个实例 | 需要保留的动态参数 |
| 改 `my.ini` + 重启 | ❌ 要重启 | ✅ | 整个实例 | 静态参数（`port`/`datadir`） |

**两个反直觉的点**：

1. **`SET GLOBAL` 对已存在的连接无效**。老连接用的是它建立时"复制"的那份会话变量。所以你 `SET GLOBAL` 之后，只有新连接看到新值——**你会以为没生效**。
2. **静态参数根本不能 `SET`**。`port`、`datadir`、`character-set-server` 这类只能改文件 + 重启。硬 `SET` 会报 `Variable 'port' is a read only variable`。

### 8.2 `SET PERSIST` 写到哪里了（实测）

```sql
SET PERSIST max_connections=100;
```

生成/更新了 `data/mysqld-auto.cnf`：

```json
{"Version": 2, "mysql_dynamic_parse_early_variables": {
  "max_connections": {"Value": "100", "Metadata": {"Host": "localhost", "User": "root", "Timestamp": 1794472769344950}}
}}
```

**注意它记了三样东西**：值、谁改的（`User`）、什么时候（`Timestamp`）。这是审计线索。

**加载顺序：`my.ini` → `mysqld-auto.cnf`（后者覆盖前者）。** 所以：

> 改了 `my.ini` 不生效 → 先看 `mysqld-auto.cnf` 里有没有同名项。
> 清理：`RESET PERSIST;`（实测执行后文件变成 `{"Version": 2}`）。

### 8.3 哪些参数必须重启

| 参数 | 要重启？ | 备注 |
|---|---|---|
| `port` / `datadir` / `basedir` | ✅ 必须 | 进程启动时就要用 |
| `character-set-server` / `collation-server` | ✅ 必须 | 而且改了也不影响已建的库（§3.10） |
| `lower_case_table_names` | ✅ 必须，且**初始化后不能改** | 见 §8.4 |
| `max_connections` | ❌ 动态 | 可以 `SET GLOBAL` / `SET PERSIST` |
| `innodb_buffer_pool_size` | ❌ 8.0 起可在线调 | 但调整过程有开销，缩小时更慢 |
| `sql_mode` | ❌ 动态 | `SET GLOBAL` / `SET SESSION` |
| `wait_timeout` | ❌ 动态 | `SET GLOBAL` |

**判断方法**：`SHOW VARIABLES` 查不到"是否动态"，但 `SET GLOBAL` 试一下就知道（报 read only 就是静态）。或者查 `performance_schema.variables_info`（§8.4）。

### 8.4 排查神器：每个变量"是从哪来的"（实测）

这是本篇最实用的一招。`performance_schema.variables_info` 会告诉你**每个变量的值是从哪来的**：

```sql
SELECT VARIABLE_NAME, VARIABLE_SOURCE, VARIABLE_PATH, SET_TIME, SET_USER
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN ('port','basedir','datadir','innodb_buffer_pool_size',
                        'character_set_server','lower_case_table_names','max_connections','sql_mode');
```

实测输出：

```
VARIABLE_NAME             VARIABLE_SOURCE  VARIABLE_PATH                                  SET_TIME                    SET_USER
basedir                   EXPLICIT         F:\...\mysql-8.4.0\my.ini                      NULL                        NULL
character_set_server      COMPILED         NULL                                           NULL                        NULL
collation_server          COMPILED         NULL                                           NULL                        NULL
datadir                   EXPLICIT         F:\...\mysql-8.4.0\my.ini                      NULL                        NULL
innodb_buffer_pool_size   EXPLICIT         F:\...\mysql-8.4.0\my.ini                      NULL                        NULL
lower_case_table_names    COMPILED         NULL                                           NULL                        NULL
max_connections           DYNAMIC          NULL                                           2026-11-12 08:39:29.345018  root
port                      EXPLICIT         F:\...\mysql-8.4.0\my.ini                      NULL                        NULL
sql_mode                  DYNAMIC          NULL                                           2026-11-12 08:39:48.472206  root
```

**`VARIABLE_SOURCE` 的四种值**：

| 值 | 含义 | 怎么变成这样的 |
|---|---|---|
| `COMPILED` | 用了**编译时的默认值** | 配置文件里没写，也没人 `SET` |
| `EXPLICIT` | 从**配置文件**读到的 | `VARIABLE_PATH` 告诉你具体是哪个文件 |
| `DYNAMIC` | 被 **`SET` 改过** | `SET_TIME` / `SET_USER` 告诉你谁在什么时候改的 |
| `PERSISTED` | 被 **`SET PERSIST`** 改过（写进 `mysqld-auto.cnf`） | 重启还在 |

**这张表直接回答"我的配置到底生效了吗"**：

- `port` / `basedir` / `datadir` / `innodb_buffer_pool_size` 都是 `EXPLICIT` + 路径指向 `my.ini` → **配置确实被读到了**
- `character_set_server` 是 `COMPILED` → **不是"配置没生效"**，而是我们配的 `utf8mb4` **恰好等于 8.0 的编译默认值**，所以 MySQL 认为是"默认值"
- `max_connections` / `sql_mode` 是 `DYNAMIC`，`SET_USER=root` → **被我用 SQL 改过**（就是 §8.2 那次实测）

**这条"`COMPILED` 不代表配置没生效"极其重要**。我第一次看到时也以为 `character_set_server` 没读到，差点去改 my.ini。真实原因是：**值和默认值相同时，来源显示为默认值。**

全实例的分布（实测）：

```
VARIABLE_SOURCE  n
COMPILED         608      ← 608 个变量都在用默认值
DYNAMIC          6        ← 6 个被人 SET 过
EXPLICIT         5        ← 5 个来自 my.ini（正好是我们配的那 5 个"与默认不同"的）
```

619 个变量，**你只需要配 5 个**。这个比例本身就说明：**默认值是被精心设计过的，不要瞎调。**

### 8.5 `lower_case_table_names`：初始化后不能改（换系统就炸的那种）

实测值：**1**

| 值 | 行为 | 哪个系统默认 |
|---|---|---|
| `0` | 表名**区分**大小写，按你写的存 | **Linux** |
| `1` | 表名**存成小写**，比较不区分 | **Windows**、macOS |
| `2` | 存成你写的，比较不区分 | 很少用 |

实测创建 `CREATE TABLE CaseTest`：

```
$ SELECT table_name FROM information_schema.tables WHERE table_schema='cfg_lab' AND table_name LIKE '%asetest%';
TABLE_NAME
casetest        ← 存成小写了
```

**这条的实战意义**（真实事故模板）：

> 开发在 Windows 上写 `SELECT * FROM UserAccount`，一切正常（存的是 `useraccount`，比较也不区分）。
> 部署到 Linux（`lower_case_table_names=0`），**表名区分大小写** → `Table 'db.UserAccount' doesn't exist`。

**而且它不能改**：`lower_case_table_names` 只在初始化时生效，之后改配置文件也没用（8.0 起直接禁止改，防止元数据损坏）。

**工程纪律**：**表名一律小写 + 下划线**（`user_account`）。这样三个平台都一样，永远不踩这个坑。我们的 `kb_dev` 里将来建表也照这个规矩。

---

## §九 易错点表（15 条，其中 14 条本篇实测过）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 用 `utf8` 建表 | 插 emoji 报 `ERROR 1366 Incorrect string value` | 建库建表一律 `utf8mb4` |
| 2 | 以为 `VARCHAR(255)` 的 255 是字节 | 以为存不了 100 个汉字 | 255 是**字符数**；utf8mb4 下最长占 1020 字节 |
| 3 | 改了 `character-set-server` 以为老表会变 | `SHOW CREATE TABLE` 还是 utf8mb3 | 字符集在建表时落盘，要 `ALTER TABLE ... CONVERT TO` |
| 4 | 客户端/服务端字符集不一致 | 库里是 `ä¸æ–‡`，或读出 `???` | 查三件套（client/connection/results），统一 utf8mb4 |
| 5 | `[mysqld]` 拼错 / 参数用下划线 | 配置全不生效，**零报错** | `--print-defaults` 验证；参数用连字符 |
| 6 | 以为 `--defaults-file` 放哪都行 | `unknown variable 'defaults-file=...'` | 必须是**第一个**参数 |
| 7 | 配了 `log-error` 但找不到日志 | `data/error.log` 不存在 | 用了 `--console`，它把日志导到 stderr，覆盖了 `log-error` |
| 8 | `localhost` 能连，`127.0.0.1` 不能 | `ERROR 1130 Host '127.0.0.1' is not allowed` | 两者是不同账号；别开 `skip-name-resolve` 或建齐账号 |
| 9 | 照老教程改 `mysql_native_password` | 8.4 上 `ERROR 1524 Plugin ... is not loaded` | 8.4 已移除；升级客户端/装 `cryptography`，别降级 |
| 10 | 只装 `pymysql` 不装 `cryptography` | `RuntimeError: 'cryptography' package is required...` | `caching_sha2_password` 需要 RSA，必须装 |
| 11 | 不开 `pool_pre_ping` | 低峰后首个请求 `(2006) MySQL server has gone away` | `pool_pre_ping=True`；或 `pool_recycle < wait_timeout` |
| 12 | `SET GLOBAL` 后老连接没变 | 以为改配置没生效 | `SET GLOBAL` 只对新连接生效；要全生效得重启 |
| 13 | 看到 `VARIABLE_SOURCE=COMPILED` 以为配置没读到 | 白改一遍 my.ini | 值和编译默认值相同时就显示 `COMPILED` |
| 14 | Windows 上开发用 `UserAccount` 表名 | 部署到 Linux 报 `Table doesn't exist` | 表名一律小写下划线；`lower_case_table_names` 初始化后不能改 |
| 15 | 在 PowerShell 里用 `< file.sql`，或改用 `Get-Content -Raw \| mysql.exe` | 前者 `The '<' operator is reserved`；后者**中文变 `???` 报 1064**（管道按 GBK 转码） | 用 `mysql.exe -e "source file.sql"`（§10.7 实测三种写法） |

---

## §十 命令速查

### 10.1 起停库

```powershell
# Windows PowerShell（这个窗口会被占住，Ctrl+C 就是停库）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\start-mysql.ps1

# 停库（另开一个窗口）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\stop-mysql.ps1

# 看是不是在跑
Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue
```

```bash
# Git Bash / Linux / macOS
/f/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysqld.exe \
  --defaults-file="F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/my.ini" --console

netstat -ano | grep ":3307"
```

> **PowerShell 两个注意**：① 原生命令不要加 `2>&1`（会把每行包成 ErrorRecord 且让 `$?` 变 false）
> ② `grep` / `rm -rf` 不存在，用 `Select-String` / `Remove-Item -Recurse -Force`。

### 10.2 连库

```powershell
# Windows PowerShell（[client] 段已带 port，所以不用 -P）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -u kb -pkb_dev_pwd kb_dev

# root（空密码）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -u root kb_dev
```

```bash
# Git Bash / Linux / macOS
/f/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysql.exe -u kb -pkb_dev_pwd kb_dev
```

### 10.3 看配置 / 变量

```sql
-- 看是不是真的读到了配置文件
-- （命令行跑：mysqld.exe --defaults-file="...\my.ini" --print-defaults）

SHOW VARIABLES LIKE 'character_set_%';       -- 字符集全家
SHOW VARIABLES LIKE 'collation_%';           -- 排序规则
SHOW VARIABLES LIKE '%time_zone%';           -- 时区（注意没有 default_time_zone）
SHOW VARIABLES LIKE 'sql_mode';              -- 严格模式
SHOW VARIABLES LIKE 'wait_timeout';           -- 空闲多久被断开
SHOW VARIABLES LIKE 'max_connections';        -- 连接上限
SHOW VARIABLES LIKE 'lower_case_table_names'; -- 表名大小写
SHOW VARIABLES LIKE 'transaction_isolation';  -- 隔离级别（D4 的主角）
SHOW VARIABLES LIKE 'datadir';                -- 数据目录

-- 看某个库/表/列的字符集
SHOW CREATE DATABASE kb_dev;
SHOW CREATE TABLE kb.knowledge_bases;
SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='kb_dev' AND CHARACTER_SET_NAME IS NOT NULL;

-- 看"这个值从哪来的"（最强排查工具）
SELECT VARIABLE_NAME, VARIABLE_SOURCE, VARIABLE_PATH, SET_TIME, SET_USER
FROM performance_schema.variables_info
WHERE VARIABLE_SOURCE <> 'COMPILED';

-- 看谁连着（连接池占了几条）
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, LEFT(INFO,60) AS sql_head
FROM information_schema.PROCESSLIST
WHERE USER = 'kb' ORDER BY TIME DESC;
SHOW PROCESSLIST;
```

### 10.4 会话级实验

```sql
SELECT NOW(), UTC_TIMESTAMP(), @@session.time_zone;    -- 时区对不对
SET time_zone = '+08:00';                              -- 只影响本会话
SET NAMES utf8mb4;                                     -- 三件套一起设
SET SESSION sql_mode='';                               -- 临时关严格模式（危险，只用于实验）
SET GLOBAL max_connections=200;                        -- 只对新连接生效，重启丢失
SET PERSIST max_connections=200;                       -- 写进 mysqld-auto.cnf，重启还在
RESET PERSIST;                                         -- 清空 mysqld-auto.cnf 里的动态配置
```

### 10.5 看日志 / 连接诊断

```powershell
# 起不来时先看这个（注意：--console 模式下不写文件）
Get-Content F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\data\*.err -Tail 30 -ErrorAction SilentlyContinue
Get-Content F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\data\error.log -Tail 30 -ErrorAction SilentlyContinue

# 存活探测 + 一句话状态
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysqladmin.exe -u root ping
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysqladmin.exe -u root status
```

```bash
# Git Bash / Linux / macOS
tail -30 /f/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/data/error.log
```

实测 `mysqladmin status` 输出：

```
Uptime: 11515  Threads: 2  Questions: 399  Slow queries: 0  Opens: 295
Flush tables: 3  Open tables: 215  Queries per second avg: 0.034
```

### 10.6 跑测试（应用侧）

```powershell
# Windows PowerShell（在 kb-service 目录）
uv run pytest -q
uv run pytest tests/test_db_session.py -v
```

```bash
# Git Bash / Linux / macOS（在 kb-service 目录）
uv run pytest -q
```

### 10.7 跑一个 `.sql` 文件（PowerShell 有个硬坑，实测过三种写法）

bash 里这样跑（`<` 是输入重定向）：

```bash
# Git Bash / Linux / macOS
/f/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysql.exe -h 127.0.0.1 -P 3307 -u root \
  --default-character-set=utf8mb4 < progress/week7/probes/probe_config.sql
```

**PowerShell 里不能这么写**——`<` 是保留符号：

```
The '<' operator is reserved for future use.
```

下面三种替代写法我都实测了，**只有第三种是对的**：

| 写法 | 结果 |
|---|---|
| `mysql.exe ... < file.sql` | ❌ PowerShell 语法错误 |
| `Get-Content file.sql -Raw -Encoding utf8 \| mysql.exe ...` | ❌ **SQL 里的中文变成 `???`**，报 `ERROR 1064` |
| `mysql.exe ... -e "source file.sql"` | ✅ 正确 |

第二种为什么会坏？PowerShell 5.1 把**字符串管道给原生命令**时，用的是 `[Console]::OutputEncoding`（默认 GBK/代码页 936），不是文件本身的 UTF-8。于是中文被转成 GBK 字节喂给 mysql，mysql 按 utf8mb4 解 → 乱码 → SQL 语法错。**加 `-Encoding utf8` 也救不回来**（实测）。

**正确写法**（`source` 是 mysql 客户端的内置命令，文件由 mysql 自己按 `--default-character-set` 读，绕开 PowerShell 的编码转换）：

```powershell
# Windows PowerShell（仓库根）。第一行让中文列名正常显示，只需要设一次
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& "F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe" `
  -h 127.0.0.1 -P 3307 -u root --default-character-set=utf8mb4 `
  -e "source progress/week7/probes/probe_config.sql"
```

三个细节：
- `source` 后面的路径**用正斜杠**（`progress/week7/...`），反斜杠在 mysql 客户端里有转义含义
- `-e "source xxx.sql"` 是"执行这条命令"，不是"执行这个文件"——`source` 才是读文件
- **不要加 `2>&1`**：PowerShell 里给原生命令加它会把每行包成 ErrorRecord 并让 `$?` 变 `false`

> 这条和之前 `grep` / `rm -rf` 一样，属于**"bash 能跑、PowerShell 不能跑"**。
> 你终端是 PowerShell，所以以后我给你涉及重定向或中文内容的命令，都会给实测过的 PowerShell 版。

---

## §十一 动手实验（**跑之前先猜，猜完再跑**）

> 规则：每个实验先在纸上写你猜的结果，跑完对。**猜错的那个才是最值得记的。**

### 实验 1：配置文件到底被解析成了什么
```powershell
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysqld.exe `
  --defaults-file="F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\my.ini" --print-defaults
```
**先猜**：输出里会不会出现 `[client]` 段的 `port`？会不会出现 `--mysqlx=0`？

### 实验 2：系统库是谁定的字符集
```sql
SHOW CREATE DATABASE mysql;
```
**先猜**：如果我把 `my.ini` 的 `character-set-server` 改成 `latin1` 并重启，这个输出会变吗？

### 实验 3：`utf8` 存 emoji
```sql
CREATE DATABASE lab2 CHARACTER SET utf8mb4;
USE lab2;
CREATE TABLE t3 (name VARCHAR(20)) CHARACTER SET utf8mb3;
INSERT INTO t3 VALUES ('😀');
```
**先猜**：报错？截断？还是成功？错误码是多少？

### 实验 4：`SET NAMES` 改了哪几个
```sql
SET NAMES latin1;
SHOW VARIABLES LIKE 'character_set_%';
```
**先猜**：`character_set_server` 会变吗？`character_set_database` 会变吗？

### 实验 5：唯一索引遇大小写
```sql
USE lab2;
CREATE TABLE u1 (name VARCHAR(20) COLLATE utf8mb4_0900_ai_ci UNIQUE);
INSERT INTO u1 VALUES ('Alice');
INSERT INTO u1 VALUES ('alice');
```
**先猜**：报 1062 还是插进去两条？

### 实验 6：切时区读 `TIMESTAMP`
```sql
CREATE TABLE t6 (d DATETIME, ts TIMESTAMP NULL);
SET time_zone='+08:00'; INSERT INTO t6 VALUES (NOW(), NOW());
SET time_zone='+00:00'; SELECT d, ts FROM t6;
```
**先猜**：`d` 和 `ts` 会一样吗？差几个小时？

### 实验 7：`SET GLOBAL` 的寿命
```sql
SET GLOBAL max_connections=200;
SELECT @@max_connections;
-- 然后重启 MySQL，再查一次
```
**先猜**：重启后是 100 还是 200？换成 `SET PERSIST` 呢？

**做完清理**（别把实验表留在 `kb_dev` 里）：
```sql
DROP DATABASE IF EXISTS lab2;
```

---

## §十二 面试问法

### Q1 `utf8` 和 `utf8mb4` 的区别（出现率最高，几乎必问）

**30 秒版**：
> "MySQL 的 `utf8` 是 `utf8mb3` 的别名，最多 3 字节，只能存 BMP，emoji 和部分生僻字存不了，插入报 1366。
> `utf8mb4` 是完整 UTF-8，最多 4 字节。所以建库建表一律 utf8mb4。8.0 起默认值已经是 utf8mb4 了。"

**追问一层（机制）**：为什么当年会这样？——MySQL 4.1（2003）引入 UTF-8 时，Unicode 只用到 3 字节范围，4 字节区被当作罕见；后来 emoji 普及，改成 4 字节会破坏兼容性，只能新增 `utf8mb4` 这个名字，`utf8` 保持原义。

**追问二层（边界/故障）**：老库怎么迁？——`ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4`，注意三件事：索引前缀长度（8.0 前 767 字节限制）、大表锁表时间、**连接串也要一起改**（否则库里对了读出来还乱）。

**追问三层（场景落地）**：我们项目里怎么保证不出这个问题？——建库语句显式写 `CHARACTER SET utf8mb4`，`my.ini` 设 `character-set-server=utf8mb4`，连接串带 `?charset=utf8mb4`，三处都写（不依赖任何一处的默认值）。

### Q2 线上出现乱码，你怎么排查（场景题）

**30 秒版**：
> "先分清是'存的时候就丢了'还是'读的时候才乱'。存的时候丢，库里是 `???` 或 `?`，不可恢复；
> 读的时候乱，库里是好数据，只是连接字符集不对。排查看两端：`SHOW VARIABLES LIKE 'character_set_%'`
> 看 client/connection/results 三件套，以及表和列的字符集。"

**追问一层（机制）**：三件套分别管什么？——client 管客户端发出的 SQL 编码，connection 管服务端收到的 SQL 在转换/比较时的编码，results 管返回结果的编码。`SET NAMES x` 一次改这三个。

**追问二层（边界）**：如果三件套都是 utf8mb4，表也是 utf8mb4，还是乱，可能是什么？——① 客户端程序本身用了错的编码发请求（比如 Java 的 `useUnicode=false`）② 数据是历史遗留的坏数据（以前用 latin1 存进去的，改字符集也救不回来，需要导出重建）③ 终端显示编码不对（数据是好的，只是你看到的乱）。

**追问三层（场景）**：怎么预防？——统一 utf8mb4（库/表/列/连接四层）、CI 里加一条"新表必须有显式字符集"的检查、`information_schema.COLUMNS` 定期扫描非 utf8mb4 的列。

### Q3 `DATETIME` 和 `TIMESTAMP` 的区别（必问）

**30 秒版**：
> "`DATETIME` 存字面值，读写都不做时区转换，范围到 9999 年，占 5 字节；
> `TIMESTAMP` 存 UTC 时间戳，读写按会话时区转换，范围到 2038 年，占 4 字节。
> 我们统一用 `DATETIME` 存 UTC，应用层保证带时区，展示层转换。"

**追问一层（机制）**：为什么 `TIMESTAMP` 会随会话时区变？——写入时把本地时间转成 UTC 存，读出时再按当前会话的 `time_zone` 转回来。`DATETIME` 两个方向都不转。

**追问二层（边界）**：`TIMESTAMP` 的 2038 问题怎么来的？——内部是 32 位有符号整数存 Unix 时间戳，2038-01-19 03:14:07 后溢出。`DATETIME` 用 5 字节分别存年月日时分秒，没有这个问题。

**追问三层（场景）**：你们项目怎么处理跨时区？——库里全部 UTC（`my.ini` 的 `default-time-zone='+00:00'` + 代码 `datetime.now(UTC)`），API 返回 ISO 8601 带偏移量（`2026-11-12T08:38:24+00:00`），前端按用户时区渲染。转换只发生在展示层的**一个地方**。

### Q4 连接池怎么配，为什么要有 `pool_pre_ping`

**30 秒版**：
> "`pool_size` 是常驻连接数，`max_overflow` 是高峰期允许临时超出的数量，容量上限是两者之和。
> `pool_pre_ping=True` 是每次借出连接前先发个轻量探测，因为服务端的 `wait_timeout`（默认 8 小时）
> 会主动断开空闲连接而不通知客户端，不探测就会在低峰后第一个请求报 `MySQL server has gone away`。"

**追问一层（机制）**：`pre_ping` 的开销是多少？——一次 `SELECT 1` 往返，同机约 0.1ms，可忽略；跨机房就值得权衡，那时更常用 `pool_recycle`（按年龄淘汰，零往返）。

**追问二层（边界）**：`pool_recycle` 设多少合适？——必须**小于** `wait_timeout`。28800 的 `wait_timeout` 配 3600 的 `recycle` 是安全组合；配 40000 等于没配。

**追问三层（场景）**：8 个 worker 怎么算 `max_connections`？——`worker × (pool_size + max_overflow) + 管理连接 < max_connections`。8×15=120 对 100 就会打满，报 `1040 Too many connections`。

### Q5 MySQL 默认隔离级别为什么是 RR，Postgres 为什么是 RC

（这题是 D4 的主角，这里只给"配置角度"的答法）

**30 秒版**：
> "MySQL 默认 `REPEATABLE-READ`，Postgres/Oracle 默认 `READ-COMMITTED`。
> 历史原因是 MySQL 早期只有 statement-based binlog，RC 下主从复制会不一致，所以默认 RR 保证复制安全；
> 5.1 引入 row-based binlog 后这个限制没了，但默认值为了兼容一直没改。
> PG 是 MVCC 实现得更彻底，RC 就够用，而且 RC 减少锁冲突。"

**追问一层（机制）**：RR 在 MySQL 下有什么"额外行为"？——普通 `SELECT`（叫**快照读**）靠 **MVCC**（Multi-Version Concurrency Control，多版本并发控制：每行保留多个版本，读的时候按事务开始时刻挑一个版本看，所以不加锁也能读到一致的数据）不加锁；但 `UPDATE`/`DELETE`/`SELECT ... FOR UPDATE`（叫**当前读**，读最新版本）会加**间隙锁（gap lock）**——它锁的不是某一行，而是"两条索引记录之间的空隙"，目的是防止别人往这个空隙里插入新行（也就是防幻读）。这是 MySQL 特有的，容易死锁。

**追问二层（边界）**：RR 能防幻读吗？——分两种读法：**快照读**下天然防住了（全程看同一份快照，别人插的行你看不见）；**当前读**下靠间隙锁防（你锁住的空隙别人插不进去）。所以答案是"能，但靠两套不同机制"，只在快照读下不加锁。

**追问三层**：你们项目用哪个？——（D4 会给答案，我提前说：业务用 RC 更常见，因为死锁少、`UPDATE` 不锁间隙；但这是团队决策，要写进文档。）

### Q6 生产环境字符集怎么定（工程题）

**30 秒版**：
> "库、表、连接三处统一 utf8mb4，collation 用 `utf8mb4_0900_ai_ci`（8.0 默认）。
> 例外是唯一性要求严格的列——邀请码、token、文件名——单独指定 `_bin` 或 `_as_cs`，
> 否则大小写不敏感会让两个不同的值被判重复。"

**追问一层**：`_bin` 和 `_as_cs` 怎么选？——`_bin` 是纯字节比较，最快最死板；`_as_cs` 走 Unicode 权重，`a < B` 成立（因为按字母序），适合"要区分大小写但排序要符合语言习惯"的场景。**做唯一约束时 `_bin` 更可预测。**

**追问二层**：改了 collation 会影响什么？——① 唯一索引的判定（§3.8 实测）② `ORDER BY` 的顺序 ③ `WHERE`/`JOIN` 的结果集（§3.7 实测 `①`=`1`）④ 已有的索引可能需要重建（collation 变了索引的排序就变了）。

**追问三层**：怎么发现线上的表字符集不统一？——
```sql
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA NOT IN ('mysql','information_schema','performance_schema','sys')
  AND CHARACTER_SET_NAME IS NOT NULL
  AND CHARACTER_SET_NAME <> 'utf8mb4';
```

---

## §十三 闭卷自测（10 题，先写答案再展开）

<details><summary>1. `my.ini` 里的 `[mysqld]` 和 `[client]` 分给谁读？举一个"写错段名"的后果。</summary>

`[mysqld]` 只给服务端 `mysqld.exe` 读，`[client]` 给所有客户端工具（`mysql.exe`、`mysqldump.exe`）读，且客户端程序还会读与自己同名的段（`[mysql]`）。

写错段名（如 `[mysqldd]`）→ 整段被忽略，**零报错**，所有参数都不生效。用 `--print-defaults` 可以立刻看出配置有没有被解析。
</details>

<details><summary>2. `--defaults-file` 为什么必须是第一个参数？不这么做报什么错？</summary>

因为它是"告诉程序去哪找配置文件"的引导参数，必须在读配置之前就处理。放到后面，程序还没读配置，不认识这个选项名 → `mysql: [ERROR] unknown variable 'defaults-file=...'`。

这个错误信息很有迷惑性：它说的是"不认识这个变量"，不是"位置错了"。
</details>

<details><summary>3. 我配了 `log-error`，但 `data/error.log` 不存在，实例却在正常跑。为什么？</summary>

因为启动用了 `--console`。Windows 上 `--console` 把错误日志写到 stderr，**覆盖** `log-error`。

学习期用 `--console` 是好的（错误直接打屏）；生产要以服务方式启动（不带 `--console`）才会真的写文件。
</details>

<details><summary>4. `SET NAMES latin1` 会改哪几个变量？`character_set_server` 会变吗？</summary>

改三个：`character_set_client`、`character_set_connection`、`character_set_results`。

`character_set_server` **不变**（那是服务端默认值，供新建库继承），`character_set_database` 也不变（那是当前库的默认值）。`SET NAMES` 只影响当前会话。
</details>

<details><summary>5. `VARCHAR(5)` 能存几个 emoji？为什么？</summary>

5 个。`VARCHAR(N)` 的 N 是**字符数**不是字节数，emoji 算 1 个字符、占 4 字节，所以 `VARCHAR(5)` 在 utf8mb4 下最长占 20 字节。

实测：`'😀😀😀😀😀'` 成功（5 字符 / 20 字节），6 个报 `ERROR 1406 Data too long`。
</details>

<details><summary>6. 为什么改了 `character-set-server` 之后，已有的表还是老字符集？</summary>

因为字符集在**创建时**就写进了表的元数据（`information_schema.TABLES` / `COLUMNS`），继承只发生在创建那一刻。改服务端默认值只影响"之后新建的"库和表。

要改老表必须 `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4`，而且有索引长度、锁表、数据量三个坑。
</details>

<details><summary>7. `VARIABLE_SOURCE` 显示 `COMPILED`，是不是说明我的配置文件没被读到？</summary>

**不是**。`COMPILED` 只表示"当前值等于编译默认值"。如果你配的值恰好就是默认值（比如 `character_set_server=utf8mb4`，而 8.0 的编译默认值就是 utf8mb4），它仍显示 `COMPILED`。

判断"配置读没读到"看 `EXPLICIT` + `VARIABLE_PATH` 是否指向你的文件；我们实例上 `port`/`basedir`/`datadir`/`innodb_buffer_pool_size` 是 `EXPLICIT`。
</details>

<details><summary>8. 唯一索引在 `utf8mb4_0900_ai_ci` 下，`Alice` 和 `alice` 会冲突吗？换个 collation 呢？</summary>

**会冲突**，报 `ERROR 1062 Duplicate entry 'alice'`（因为 `ci` = case insensitive，两者算相等）。

换成 `utf8mb4_bin` 就可以共存（纯字节比较）。所以邀请码/token/文件名这类列必须显式用 `_bin` 或 `_as_cs`。
</details>

<details><summary>9. `wait_timeout=28800` 和 `pool_pre_ping=True` 是什么关系？</summary>

`wait_timeout=28800`（8 小时）是服务端主动断开空闲连接的阈值，且**不通知客户端**。客户端池子里会留着"看起来活着"的死连接，下次借出一用就报 `(2006) MySQL server has gone away`。

`pool_pre_ping=True` 在每次借出前发个 `SELECT 1` 验活，失败就丢弃重连——正好治这个。另一种解法是 `pool_recycle`，但它必须**小于** `wait_timeout` 才有效。
</details>

<details><summary>10. 8.4 上还能用 `IDENTIFIED WITH mysql_native_password` 建账号吗？为什么老教程都说可以？</summary>

**不能**。实测报 `ERROR 1524 (HY000): Plugin 'mysql_native_password' is not loaded`，查 `information_schema.PLUGINS` 显示它的状态是 `DISABLED`。

老教程在 8.0 上是对的（8.0 里它是 deprecated 但仍可用），8.4 把它改成默认不加载。**这就是"技术结论必须带版本"的典型例子**：同一句话在 8.0 对、8.4 错。

正解是升级客户端 + 装 `cryptography`（`caching_sha2_password` 需要 RSA），不是降级认证插件。
</details>

---

## §十四 这篇东西怎么用

| 场景 | 看哪节 |
|---|---|
| 明天要建表了，先把库配好 | §二（逐行）、§3.2（四级继承） |
| 突然出现乱码 | §3.3（三件套）、§3.4（根因公式）、§3.5（utf8 是假的） |
| 时间差 8 小时 | §四（整节） |
| 连不上数据库 | §6.2（localhost vs 127.0.0.1）、§6.5（认证插件）、§6.6（8.4 移除 native） |
| 上线后连接数爆了 / 2006 错误 | §7.1（容量）、§7.2–7.3（pre_ping） |
| 改了配置不生效 | §2.5（`--print-defaults`）、§2.7（两个配置源）、§8.4（`variables_info`） |
| 面试前一天复习 | §十二（6 题 × 四层）、§九（14 条易错点） |

**和 D2 的衔接**：下一篇要建三张表（`knowledge_bases` / `documents` / `chunks`）。建表时会用到本篇的：

- `utf8mb4` + `utf8mb4_0900_ai_ci`（每张表都显式写）
- `DATETIME` 而不是 `TIMESTAMP`（统一 UTC）
- 表名全小写下划线（避开 `lower_case_table_names` 坑）
- `VARCHAR(N)` 的 N 是字符数（估长度时别按字节算）

**最后一句话**：配置文件的每一行，都是一次"我和默认值不同"的决定。**配了 619 个变量中的 5 个，是因为那 5 个必须和默认不一样。** 剩下的 608 个用默认值，是相信 MySQL 的默认值是经过千万次部署验证的——**除了 `utf8` 那个历史包袱，其它都别瞎调。**
