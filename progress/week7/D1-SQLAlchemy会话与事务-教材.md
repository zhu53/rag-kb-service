# W7-D1 · Engine / Session / 事务：一条 SQL 的一生

> 本周主题：MySQL + SQLAlchemy 2.0。  
> 本篇只管一件事：**一次请求里，数据库连接和事务到底是怎么被借出、用掉、还回去的。**  
> 表设计、索引、`EXPLAIN` 放在 D2、D3。今天不设计表，今天要能"看见"连接。
>
> 环境（本篇所有输出都是在这台机器实测的，不是抄文档）：  
> Python 3.11.17 · SQLAlchemy **2.1.8** · FastAPI **0.150.0** · Starlette 1.9.0 · Windows  
> 数据库：**SQLite**（演示/单测）+ **MySQL 8.4.0 LTS**（本机免安装实例，端口 **3307**，已装好，见 §十五）  
> 两条库上的结论都实测过，写法一致时我会标注"两边都验过"

---

## §零 主线：一条 SQL 的一生

如果今天只让你记住一样东西，就是这条时间轴。**下面每一节讲完，你都要能回答"这一节在线上哪个位置"。**

```
 ① 进程启动
    create_engine("sqlite:///./kb.db")        ← Engine 建好，池子建好，但一条连接都不开
                    │
 ② 请求进来（FastAPI 调 get_db 依赖）
    SessionLocal()  ──►  Session 对象出生     ← 注意：此刻【事务还没开始】，连接也还没借
                    │
 ③ handler 里第一次执行 SQL（或 flush）
    session.execute(...)  ──► 池子借出连接 + BEGIN (implicit)  ← 事务在这一刻才真正开始
                    │
 ④ handler 里写数据
    session.add(obj) / flush()  ──► INSERT 发出去了，但【别的会话看不见】
                                    （flush＝把内存改动发成 SQL，但不提交；§4.2 详解）
                    │
 ⑤ 提交
    session.commit()  ──► COMMIT，数据落库，别人终于看得见
                    │        （副作用：默认会把对象里的属性全部清空，§五）
 ⑥ 响应发出后，依赖收尾
    session.close()  ──► 没提交的自动 ROLLBACK；连接回池，池再 rollback-on-return 清一遍
```

**贯穿全篇的那条分界线：**

> **Engine 是池子（进程级，全局一个），Session 是工作台（请求级，一次请求一个）。**
>
> 池子里装的是**连接**（TCP/文件句柄，稀缺资源，要复用）；  
> 工作台上放的是**你这一个请求要改的数据**（业务状态，要隔离，用完就扔）。

搞混这两个东西，后面所有坑都会踩：把 Engine 当请求级（每次请求 create_engine → 池子爆炸）、  
把 Session 当进程级（全局共享一个 session → 一个请求未提交的数据被另一个请求看见，即越权）。

**四条时间刻度，先背下来，后面逐个验证：**

| 时刻          | 发生了什么               | 没发生什么             |
| ----------- | ------------------- | ----------------- |
| `Session()` | 对象出生                | **没开事务**、**没借连接** |
| 第一条 SQL     | 借连接 + BEGIN         | 数据还看不见            |
| `commit()`  | COMMIT，落库           | 连接**还没还**，属性被清空   |
| `close()`   | 未提交的 ROLLBACK + 还连接 | 已提交的不会回滚          |

---

## §零·五 开工前的词表（不认识这些词，后面每句都是天书）

这一节是给"从没碰过数据库"的人准备的。**你已经会写 Python 和 FastAPI，但 W1-W6 的数据一直躺在 dict 里，一次 SQL 都没写过**——  
所以先把最少的词认全。认完这一节再往下读，速度会快一倍。

### 0.5.1 数据库的五个基本词（5 分钟）

数据库在你眼里先只需要这样理解：**它就是一堆长得像 Excel 的表，但你只能用命令操作。**

| 词                   | 人话               | 类比            |
| ------------------- | ---------------- | ------------- |
| **表**（table）        | 一类数据的集合，固定几列     | 一个 sheet      |
| **行**（row / 记录）     | 一条数据             | sheet 的一行     |
| **列**（column / 字段）  | 一个属性，有类型         | sheet 的一列     |
| **主键**（primary key） | 能唯一认出这一行的列（如 id） | 学号            |
| **索引**（index）       | 为了查得快而额外建的结构     | 书末的索引页（D3 细讲） |

**四条命令就够今天用**（大小写都行，习惯大写）：

```sql
SELECT * FROM kb WHERE owner_id = 'u-1';        -- 查：从 kb 表里挑出符合条件的行
INSERT INTO kb (id, name) VALUES ('x', '我的库'); -- 增：插一行
UPDATE kb SET name = '新名字' WHERE id = 'x';     -- 改：改掉符合条件的行的某列
DELETE FROM kb WHERE id = 'x';                    -- 删：删掉符合条件的行
```

> **`WHERE` 是命门**：忘了写 `WHERE` 的 `DELETE` 会删掉整张表。这就是 §八 易错点里"删 `where` 条件"那个变异体为什么必须被测试抓住。

今天**不要求你会写复杂 SQL**（JOIN、GROUP BY 是 D2/D3 的事），只要看到 `SELECT ... FROM ... WHERE ...` 能读懂它在干嘛。

### 0.5.2 本篇的十个术语（每个都只给一句人话，展开在后面）

| 术语                  | 一句人话                                                       | 没有它会怎样                         |
| ------------------- | ---------------------------------------------------------- | ------------------------------ |
| **驱动**（driver）      | Python 和某种数据库之间的"翻译兼跑腿"：`pymysql`、`psycopg`、`sqlite3`      | 你只能自己拼字节发 TCP                  |
| **方言**（dialect）     | 每种数据库的 SQL 语法差异（占位符 `?` vs `%s`、`LIMIT` 写法）                | 换库要重写所有 SQL                    |
| **ORM**             | Object-Relational Mapping，把"表的一行"映射成"一个 Python 对象"         | 每行都是 tuple，靠下标取字段（§1.1 的痛）     |
| **连接池**（pool）       | 预先管好一批连接，用完放回而不是销毁                                         | 每次请求新建 TCP 连接，慢且会打爆数据库         |
| **事务**（transaction） | 一组"要么全成功、要么全失败"的操作                                         | 转账扣了钱没到账                       |
| **`flush`**         | 把内存里的改动**翻译成 SQL 发出去**，但不提交                                | 你以为发过了，其实还在内存里（§4.2）           |
| **`commit`**        | 让这批改动**真正生效**，别人从此看得见                                      | 数据只在你这一个连接里存在，进程一死就没           |
| **`rollback`**      | 撤销这批改动                                                     | 中途出错留下半截脏数据                    |
| **ORM 对象 / 实体**     | 一条记录对应的 Python 对象（`kb = KB(name="x")`）                     | —                              |
| **DTO**             | Data Transfer Object：**只用来传输的纯数据**（本项目的 `KBRow` TypedDict） | 把 ORM 对象直接传出层，session 一关就炸（§五） |

> **一个必须提前分清的区别**：**ORM 对象**（`KB` 类实例，绑在 session 上、能自动变 SQL）和 **DTO**（`KBRow` 字典，纯数据、跟数据库无关）不是一回事。  
> 本项目的规定是：**repo 层对外只给 DTO**，ORM 对象不出 repo 的门。理由在 §五，今天就靠这条躲开 `DetachedInstanceError`。

### 0.5.3 三问自检（答不上就先补，别硬读）

1. `SELECT * FROM kb WHERE owner_id = ?` —— 这句在干嘛？`*` 是什么意思？
2. "表的一行" 在 Python 里可以表示成什么？至少说两种（`tuple` / `dict` / 对象）。
3. 为什么"连接"需要被复用，而不是每次用完就扔？（提示：建立连接要做 TCP 握手 + 认证）

---

## §一 痛点：没有 SQLAlchemy 的时候，人是这么写的

先看"没有它会怎么做"。这是理解一切的起点——**SQLAlchemy 的每个设计，都是对下面某个具体麻烦的回应。**

> **先定义 ORM**：ORM = Object-Relational Mapping，中文"对象关系映射"。一句话：**让你用 Python 对象操作表，而不是拼 SQL 字符串**。  
> `kb = KB(name="我的库")` + `session.add(kb)` 背后会生成 `INSERT INTO kb (name) VALUES ('我的库')`。  
> 它不是"不用 SQL"，是"SQL 由它帮你写"——所以 §1.3 才说你还是得懂 SQL。

### 1.1 裸 `sqlite3` 版本（你现在也能写出来）

```python
import sqlite3, uuid
from datetime import datetime, timezone

conn = sqlite3.connect("kb.db")  # ① 连接谁管？全局？每请求一个？
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS kb (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
        name TEXT NOT NULL, doc_count INTEGER DEFAULT 0,
        created_at TEXT
    )
""")
conn.commit()  # ② 手工 commit，忘了就丢数据

kb_id = str(uuid.uuid4())
cur.execute(
    "INSERT INTO kb (id, owner_id, name, doc_count, created_at) VALUES (?, ?, ?, ?, ?)",
    (kb_id, "u-1", "我的知识库", 0, datetime.now(timezone.utc).isoformat()),
)
conn.commit()  # ③ 第二次 commit，两次之间崩了怎么办？

cur.execute("SELECT id, owner_id, name, doc_count, created_at FROM kb WHERE owner_id = ?", ("u-1",))
rows = cur.fetchall()  # ④ 拿到的是 tuple，字段顺序靠记忆
conn.close()  # ⑤ 忘了这行 → 连接泄漏，锁不释放
```

### 1.2 五个撑不住的地方（这就是 SQLAlchemy 存在的理由）

| # | 裸 driver 的麻烦        | 症状                                 | ORM 的回应                         |
| - | ------------------- | ---------------------------------- | ------------------------------- |
| ① | 连接生命周期靠人手管          | 忘了 `close()` → 连接泄漏、锁不释放（本文 §七 实测） | Engine 池 + 依赖注入自动 `close`       |
| ② | 事务边界靠人手写 `commit()` | 一个业务动作要改两张表，中间崩了只提交了一半             | `commit()` 一次提交全部（Unit of Work） |
| ③ | 行是 `tuple`，字段顺序靠记忆  | `row[3]` 是哪个字段？改表顺序就全崩             | `class KB` 有属性名，`kb.doc_count`  |
| ④ | SQL 是字符串，拼错要到运行时才知道 | 打错列名 → `no such column` 才报错        | 列名是 Python 属性，PyCharm 就能跳转      |
| ⑤ | 类型全丢                | `id` 存 TEXT，读回来是 `str` 不是 `UUID`   | `Mapped[UUID]` 自动转换（§九 实测有坑）    |

> **一句话**：driver 只解决"怎么把 SQL 发给数据库"，**不解决"谁在什么时候管连接、管事务、管对象"**。  
> SQLAlchemy 解决的是后半句。

### 1.3 那为什么还要懂 SQL？

因为 **ORM 不替你写 SQL，它只是帮你生成 SQL**。今天的动手任务里，你要做的第一件事就是  
**打开 `echo=True` 把 ORM 生成的 SQL 打出来看**——看不见 SQL 的人，调不了数据库性能（D3 的 `EXPLAIN` 就无从谈起）。

---

## §二 最小可跑示例（5 分钟，亲手跑一遍）

先跑起来，再讲概念。**跑之前先在纸上猜三件事**（写在纸笔本上，回头对答案）：

1. 建表时 `echo=True` 会打出几条 SQL？
2. 第一次 `session.execute(...)` 之前，`session.in_transaction()` 是 `True` 还是 `False`？
3. `commit()` 之后再读 `kb.name`，会再发一条 SELECT 吗？

### 2.1 建一个临时练习目录

```powershell
# Windows PowerShell（在仓库根 python-backend-roadmap 下执行）
New-Item -ItemType Directory -Force -Path scratch | Out-Null
Set-Location scratch
```

```bash
# Git Bash / Linux / macOS
mkdir -p scratch && cd scratch
```

### 2.2 文件 `scratch/d1_min.py`

```python
from sqlalchemy import String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

engine = create_engine("sqlite:///./d1.db", echo=True)  # echo=True：把每条 SQL 打出来


class Base(DeclarativeBase):  # 所有模型的基类（2.0 新写法，替代 declarative_base()）
    pass


class KB(Base):
    __tablename__ = "kb"  # 对应表名

    # Mapped[X] 是说"这个属性是列，Python 侧类型是 X"
    # mapped_column(...) 里放列级配置（主键、长度、默认值）
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


Base.metadata.create_all(engine)  # 建表（只建不存在的表，不改已有表结构 → §八 易错点 5）

session = Session(engine)  # ② 出生
print("A) 刚建好 in_transaction =", session.in_transaction())

session.execute(select(func.count()).select_from(KB))  # ③ 第一条 SQL
print("B) 发过 SQL 后 in_transaction =", session.in_transaction())

kb = KB(name="我的知识库")
session.add(kb)
session.commit()  # ⑤ 提交

print("C) 库里行数 =", session.execute(select(func.count()).select_from(KB)).scalar_one())
print("D) commit 后 kb.__dict__ 有 name 吗 =", "name" in kb.__dict__)
print("E) 读一下 kb.name =", kb.name)
print("F) 读完后 kb.__dict__ 有 name 吗 =", "name" in kb.__dict__)

session.close()  # ⑥ 收尾
```

### 2.3 跑它

```powershell
# Windows PowerShell：用项目 venv 里的解释器
& ..\kb-service\.venv\Scripts\python.exe d1_min.py
```

```bash
# Git Bash / Linux / macOS
../kb-service/.venv/Scripts/python.exe d1_min.py     # Windows 上的 Git Bash
# ../kb-service/.venv/bin/python d1_min.py           # 真 Linux / macOS
```

### 2.4 真实输出（逐行解读）

```
... INFO sqlalchemy.engine.Engine BEGIN (implicit)                 ← 建表也在事务里
... INFO sqlalchemy.engine.Engine PRAGMA main.table_info("kb")     ← 先查表存不存在
... INFO sqlalchemy.engine.Engine CREATE TABLE kb (
        id INTEGER NOT NULL,
        name VARCHAR(50) NOT NULL,
        PRIMARY KEY (id)
)
... INFO sqlalchemy.engine.Engine COMMIT                            ← create_all 自己提交了
A) 刚建好 in_transaction = False                                    ← ② 没开事务（猜对了吗）
... INFO sqlalchemy.engine.Engine BEGIN (implicit)                  ← ③ 事务在这一刻才开始
... INFO sqlalchemy.engine.Engine SELECT count(*) ...
B) 发过 SQL 后 in_transaction = True
... INFO sqlalchemy.engine.Engine INSERT INTO kb (name) VALUES (?) ('我的知识库',)
... INFO sqlalchemy.engine.Engine COMMIT                            ← ⑤
... INFO sqlalchemy.engine.Engine BEGIN (implicit)                  ← 下面这条 SELECT 又开了新事务
... INFO sqlalchemy.engine.Engine SELECT count(*) ...
C) 库里行数 = 1
D) commit 后 kb.__dict__ 有 name 吗 = False                         ← 属性被清空了！
E) 读一下 kb.name = 我的知识库
... INFO sqlalchemy.engine.Engine SELECT kb.id, kb.name FROM kb WHERE kb.id = ?   ← 为了读 name 又查了一次库
F) 读完后 kb.__dict__ 有 name 吗 = True
```

四个必须注意的点：

1. **`BEGIN (implicit)` 出现了 3 次**——不是"一个 session 一个事务"，是**一条业务动作一个事务**。  
   `commit()` 结束后事务就没了，下一条 SQL 会再开一个。这就是 §零 说的"事务的边界是 commit，不是 session 的生命"。
2. **`D) False` 是今天最反直觉的一行**：`commit()` 之后对象里的属性被**主动清空**了，再读就有了  
   `F)` 那条多余的 `SELECT`。这是 `expire_on_commit=True`（默认值）干的事，§五 专门讲。
3. `create_all` 前的 `PRAGMA main.table_info` 说明它**先查后建**——所以它幂等，跑 100 次也只建一次。
4. `CREATE TABLE` 里的 `VARCHAR(50)` 是 `String(50)` 生成的。**SQLite 根本不校验长度**（它没有真正的 VARCHAR，  
   写 200 个字符它也收），MySQL 会校验（严格模式下超长直接报错 `1406 Data too long`）。  
   **这就是"方言差异"**（§0.5.2 那个词）：同一份 Python 代码，不同数据库的真实行为不同——  
   所以 §十 的实验里凡是"行为"类的结论，都要在真 MySQL 上再验一遍。

---

## §三 四个对象，谁是谁（本篇的核心概念区）

新手最容易糊的是这四个词：Engine / Connection / Session / Transaction。  
一句话版本：

| 对象              | 是什么                                      | 生命周期                           | 类比        |
| --------------- | ---------------------------------------- | ------------------------------ | --------- |
| **Engine**      | 连接池 + 数据库方言（知道怎么把 Python 翻译成这种 DB 的 SQL） | **进程级，全局一个**                   | 自来水厂 + 管道 |
| **Connection**  | 池子里借出的一条物理连接                             | 一次借还                           | 一个水龙头     |
| **Session**     | 工作台：身份映射 + 待提交改动 + 事务句柄                  | **请求级，一次请求一个**                 | 一张办公桌     |
| **Transaction** | 一次原子操作的边界                                | 从第一条 SQL 到 `commit`/`rollback` | 桌上摊开的一叠文件 |

### 3.1 Engine 为什么必须是进程级单例

`create_engine()` 干了三件重活：

1. **建连接池**（默认 `QueuePool`：预先不建连接，用时才建，用完放回不销毁）；
2. **装载方言**（dialect）：`mysql+pymysql://`、`postgresql+psycopg://`、`sqlite:///` 各一套，负责 SQL 语法与参数占位符差异；
3. **解析 URL**。

这三件事都**不该每个请求做一次**。每请求 `create_engine` 的后果不是"慢一点"，  
而是**每请求一个池子**——池子里的连接没人回收，数据库侧连接数几分钟就顶到上限（MySQL 默认 `max_connections=151`），  
然后所有请求开始报 `Too many connections`。这是新手最常犯的线上事故之一。


> 本项目写法（D1 动手任务要你写）：`core/db.py` 里模块级 `engine = create_engine(...)`，  
> **模块只会被 import 一次**，所以它就是进程级单例。

### 3.2 Session 为什么必须是请求级

Session 里装了三样东西，全都**不能跨请求共享**：

| Session 里的东西            | 作用                                   | 跨请求共享会怎样                                              |
| ----------------------- | ------------------------------------ | ----------------------------------------------------- |
| **身份映射**（identity map）  | 同一 session 里，同一主键只对应**一个** Python 对象 | 两个请求拿到的是**同一个对象**：B 看到 A 改了一半的字段，B 再改一次就盖掉 A（详见 §3.3） |
| **待提交改动**（unit of work） | `add`/`delete` 攒着，commit 时一起发        | 请求 A 没提交的改动会被请求 B 的 commit 顺手提交掉 → **越权写入**           |
| **事务句柄**                | 一条连接 + 一个事务                          | 两个人共用一个事务，谁 commit 谁 rollback 说不清                     |

W6 你学过"依赖缓存的生命周期 = 单次请求"，那条结论在这里变成了硬需求：  
`get_db` 用 `yield` 依赖 + FastAPI 的依赖缓存，**一次请求内所有需要 DB 的地方拿到的是同一个 Session**；  
请求结束依赖收尾 `close()`，下一个请求拿新的。

### 3.3 身份映射（identity map）：为什么"1 号"在同一个 session 里只可能有一个对象

这一节是 §三 里最抽象的一个概念，所以分五步讲：**没有它会怎样 → 它是什么 → 实测 → 什么时候失效 → 错在哪**。

#### 3.3.1 先说没有它会怎样

假设 session 没有这张表。那么你写：

```python
kb = session.get(KB, 1)        # 查库，造出一个 Python 对象 A
kb.name = "新名字"              # 改 A 的属性（还没提交）
other = session.get(KB, 1)     # 又查一次库，造出对象 B —— B.name 还是旧值
```

于是同一个请求里，**1 号知识库有了两个 Python 对象**：

```
A: name = "新名字"   ← 你改过的
B: name = "旧值"     ← 数据库里那行
```

接下来任何拿到 `B` 的代码都看不到你的修改。更麻烦的是关系维护：`kb.docs` 这个集合，  
在 A 上加了文档，B 上看不见——**同一个"东西"在内存里分裂成几份，谁也不知道谁改了什么**。

这不是 SQLAlchemy 独有的问题，**所有 ORM 都必须解决它**，解法也都一样：在会话里维护一张  
"我是谁 → 我对应的那个 Python 对象"的登记表，取之前先查表。

#### 3.3.2 它是什么：一张"身份 → 对象"的表

**身份映射（identity map）= session 内部的一个字典**：

```
键：这个对象是谁          →  (类, 主键元组, identity_token)
值：对应的 Python 对象本身  →  <KB object at 0x...>
```

**类比：会议室门口的名册。**  
一次 session 就是一场会议。同一个工号的人，**在这一场会议里只有一个座位**。

- 你要见 1 号 → 前台先翻名册；
- 名册上有 → 直接把册上那个人叫来（**不发 SQL**）；
- 名册上没有 → 去数据库请人（**发 SQL**），请回来立刻在册上登记；
- 散会（`close()`）→ 名册作废，下次开会重新登记。

所以"身份映射"这个名字的意思就是：**把"数据库里的身份（主键）"映射到"内存里的那个对象"**。

#### 3.3.3 实测（跑之前先猜：第二次 `get` 会不会发 SQL？）

探针在 `progress/week7/probes/probe_identity_map.py`，直接跑：

```powershell
# Windows PowerShell（仓库根）
.\kb-service\.venv\Scripts\python.exe .\progress\week7\probes\probe_identity_map.py
```

真实输出（SQLAlchemy 2.1.8 / Python 3.11.17 / SQLite）：

```text
A) 第一次 get(KB, 1): 发了 1 条 SELECT
B) 第二次 get(KB, 1): 累计 1 条 SELECT（没增加 = 没查库）| a is b -> True
C) identity_map 类型=_WeakInstanceDict 长度=1
   key=(<class '__main__.KB'>, (1,), None)
   value is a -> True
D) 用 select() 查同一行: 发了 1 条 SELECT | c is a -> True
E) 把 a.name 改掉，再 select 一次，看拿到的是新值还是库里的旧值:
   d is a -> True | d.name = '改过的名字'
F) expunge(a) 之后再 get:
   e is a2 -> False | map 长度=1
G) 两个 Session 各 get 同一行（身份映射不跨 Session）:
   o1 is o2 -> False（同一个主键，两个对象）
   最终库里 name = 'session2 写的（基于它读到的旧值）'
   ↑ session1 的改动被静默覆盖了 —— 这就是 lost update
```

逐条读：

| 行       | 说明                                                                                                                                                            |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A→B** | 第一次 `get` 发 1 条 `SELECT` 并登记；第二次 `get` **一条 SQL 都没发**，因为查表就命中了                                                                                                |
| **C**   | `identity_map` 的实际类型是 `_WeakInstanceDict`——**就是个字典**。键 `(KB, (1,), None)` 三段分别是：**类**、**主键元组**、**identity_token**（普通映射永远是 `None`，多绑定/分片才用得上，属于支线，先不管）。值就是对象本体 |
| **D**   | `select()` 和 `get()` 不一样：**它一定会发 SQL**（1 条）。但查回来的行发现"这个人册上已经有了"，就**不拿这行数据去覆盖册上对象的属性**（除非你显式加 `populate_existing()`），直接返回册上那个对象 → `c is a` 为 True              |
| **E**   | 所以你在同一个 session 里改完属性再查，看到的是**内存里那个对象的新值**，不是库里的旧值。这也是为什么"改完想确认存进去没有"不能靠在同一个 session 再查一次                                                                     |
| **F**   | `expunge()` 是把一个人从名册上划掉。之后再 `get` 就是**新对象**（`e is a2` → False），册子长度仍是 1（旧的走了，新的进来）                                                                            |
| **G**   | 换一个 session = 换一场会议 = **另一本名册**。同一个主键必然是**两个对象**，互相不知道对方改了什么                                                                                                  |

#### 3.3.4 最容易记错的一点：`get()` 和 `select()` 的区别

|           | `session.get(KB, 1)`  | `session.scalars(select(KB).where(...))` |
| --------- | --------------------- | ---------------------------------------- |
| 先查身份映射吗   | **先查，命中就直接返回，不发 SQL** | 不查，**一定发 SQL**                           |
| 返回的是已有对象吗 | 是                     | **也是**（结果被身份映射"截胡"，丢弃行数据，返回册上那个对象）       |
| 什么时候用     | 按主键取单条（最高频）           | 条件查询、批量查询                                |

> 一句话：**`get()` 能省 SQL，`select()` 不能；但两者在"同一 session 内对象唯一"这条上一样。**

#### 3.3.5 对象什么时候"出册"（身份映射失效的四种情况）

| 动作                                             | 结果                                 | 本项目会碰到吗     |
| ---------------------------------------------- | ---------------------------------- | ----------- |
| `session.expunge(obj)`                         | 单个对象出册，再取是新对象                      | 很少用         |
| `session.close()` / 请求结束                       | **整本册子作废**，对象变 detached（§五）        | **每请求都会**   |
| `session.commit()`（默认 `expire_on_commit=True`） | 对象还在册上，但**属性被清空**，下次访问触发新 `SELECT` | **每次写操作都会** |
| 换一个 session                                    | 必然是两个对象（G 行），**身份映射不跨 session**    | **每个新请求都是** |

#### 3.3.6 所以"一次操作一个 session"到底错在哪

原教材这里我写的是"覆盖写"，不够准确。用 G 行的实测说清楚：

```text
库里初始：name = '初始'
s1 读到 '初始'，改成 'session1 写的'，commit      → 库里 = 'session1 写的'
s2 早就读到 '初始'（它不知道 s1 改过），改成 'session2 写的（基于它读到的旧值）'，commit
                                                      → 库里 = 'session2 写的...'
```

**s1 的改动静默消失了。**&#x6CA1;有任何报错、没有冲突提示——第二次 `UPDATE` 把第一次的整列覆盖掉。  
这是"读—改—写"的经典竞态（lost update），身份映射不仅救不了它，**反而是它的成因之一**：  
两个 session 各持一个对象，各自基于"自己读到的旧值"做决定。

这条正好接 D4：真要靠数据库解决，得上**版本号（乐观锁）**&#x6216; `SELECT ... FOR UPDATE`（悲观锁），  
D4 会实测。

<details>

<summary>因为 session 是**事务边界**。跨 session 共享对象意味着共享一份"待提交改动"，  
两个请求的写入会被混进同一个事务——那才是更严重的问题：请求 A 失败回滚，会把请求 B 的写入一起回滚掉。  
身份映射的边界必须和事务边界对齐，这是设计约束，不是偷懒。</summary>



</details>

<details>

<summary>`commit()` 之后这个事务结束了，库里可能已经被别人改了。为了不给你"过期数据"，  
SQLAlchemy 默认把对象上的属性全部标记为过期（`expire`），下次访问该属性就重新 `SELECT` 一次。  
对象身份还是同一个（`id()` 不变），但**数据是重新读的**——所以 §五 讲 `expire_on_commit=False`  
和 detached 时，会看到"对象还在，但读属性会炸"的另一半原因。</summary>

</details>

#### 3.3.7 面试怎么问（30 秒版）

> **问：SQLAlchemy 的 identity map 是什么？**
>
> 答：session 内部维护的一张"主键 → Python 对象"的映射表，保证同一个 session 里同一行数据  
> 只对应一个对象。所以按主键 `get()` 第二次不发 SQL；用 `select()` 仍然发 SQL，但返回的  
> 对象还是同一个。它的边界就是 session 的边界，`close()` 之后失效，跨请求必然是两个对象。

追问链（面试官往下挖）：

1. **机制**：`get()` 和 `select()` 在这件事上有区别吗？→ 有，`get()` 先查映射，`select()` 一定发 SQL 再被"截胡"。
2. **边界/故障**：两个请求同时改同一行会怎样？→ lost update，后提交覆盖先提交，且**没有报错**；要靠版本号或行锁解决（D4）。
3. **场景落地**：那"每条 SQL 一个 session"行不行？→ 不行，一是池子抖动，二是同一请求内对象会分裂成多份，改了一个另一个不知道。

#### 3.3.8 本项目落点

`get_db` 是**一次请求一个 session**，所以一次请求内 `kb_repo.get(kb_id)` 无论被调用几次，  
拿到的都是同一个 `KB` 对象。service 层改了它的字段，路由层序列化时看到的就是新值——  
**这就是为什么 DTO 转换（`KBOut`）必须发生在同一个 session 内**：一旦出了 session，  
对象 detached，连属性都读不出来（§五）。

---

## §四 事务：autobegin / commit / rollback / close

### 4.0 没有事务会怎样（先说痛点，再看机制）

假设一个业务要改两处：**建文档 → 知识库 `doc_count + 1`**。没有事务时它是两条独立 SQL：

```sql
INSERT INTO documents (...) VALUES (...);      -- ① 成功
UPDATE kb SET doc_count = doc_count + 1 WHERE id = 'x';   -- ② 服务器这时候断电
```

结果：文档建好了，计数没加。**数据库里从此有一条"多出来的文档"，而计数永远少 1。** 这种错不会报错，  
只会在某天对账时发现，而且你根本不知道是什么时候、哪个请求造成的。

**事务就是解决这个的**：把 ① ② 包成"一组"，要么全成功，要么全撤销。  
数据库保证这件事的方式是**先记日志再改数据**（redo/undo 日志），所以它能"撤销"——这不是魔法，是写日志的代价。

**四个词，一句人话**（§0.5.2 已给过 `flush`/`commit`/`rollback`，这里补最关键的那个）：

- **autobegin** = automatic begin，"**自动开事务**"。你不写 `BEGIN`，SQLAlchemy 在你**第一次执行 SQL 时**替你写。  
  这就是为什么 `Session()` 那一刻没有事务（它懒得开），而第一条 SQL 一来就有了。
- **隔离级别**（D4 细讲）：两个事务同时跑，互相能看见多少。MySQL 默认 `REPEATABLE-READ`（可重复读）。

### 4.1 一张表说清四个动作用

下面每个格子都实测过（脚本见 §十 实验一）：

| 你做的事                  | 事务状态                                 | 库里有没有数据    | 别的 Session 看得见吗 |
| --------------------- | ------------------------------------ | ---------- | --------------- |
| `Session(engine)`     | **没开** （`in_transaction() == False`） | —          | —               |
| `execute(SELECT ...)` | 开启（autobegin）                        | —          | —               |
| `add()` 只放进内存         | 没变                                   | 没有         | 没有              |
| `flush()`             | 事务进行中，**INSERT 已发出**                 | 事务内可见      | **看不见**（隔离）     |
| `commit()`            | 结束，事务销毁                              | **有**      | **看得见**         |
| `rollback()`          | 结束，改动丢弃                              | 没有         | 没有              |
| `close()`（未提交）        | 结束，**等价 rollback**                   | **没有**     | 没有              |
| `close()`（已提交）        | 无事务可回滚                               | 有（**不会丢**） | 看得见             |

实测输出（`scratch/d1_tx.py`，§十 实验一）：

```
A) 刚建好 in_transaction = False
B) 发过 SQL 后 in_transaction = True
C) flush 后 另一个 session 看到 = 0        ← 隔离：脏数据不外泄
D) close 未 commit -> 库里 = 0             ← close 即回滚
E) commit 后 库里 = 1
K) with begin() 后 库里 = 2 | 块结束后 in_transaction = False
```

### 4.2 `flush` 和 `commit` 的区别（面试必问）

- **`flush()` = 把内存改动翻译成 SQL 发给数据库，但不提交。** 此时数据在本事务内可见（自己查得到），  
  别人看不见；数据库的锁**已经加上了**（§七 的 `database is locked` 就是它引起的）。
- **`commit()` = 先自动 flush，再发 COMMIT。** 所以"我只 commit 没 flush 会不会丢" → 不会，commit 内部会 flush。

**自动 flush 还有一个隐藏触发点**：你在同一个事务里 `execute` 一条 SELECT，SQLAlchemy 会**先自动 flush 再查**，  
否则查出来的数据和你内存里的改动不一致。这条规则叫 **autoflush**，默认开。  
它是"零症状 bug"的经典来源（见 §八 易错点 3）。

### 4.3 `with session.begin():` 有什么好处

```python
with session.begin():  # 进块：开事务；正常出块：COMMIT；抛异常：ROLLBACK
    session.add(KB(name="事务块"))
```

它替你把 `try/except/rollback` 写好了。**注意**：`session.begin()` 要求"当前没有事务"，  
所以不能和"外层已经 autobegin 了"的场景混用，会报 `A transaction is already begun on this Session`。  
本项目用「依赖层 close + service 层显式 commit」的写法，不靠这个上下文管理器，原因在 §六。

---

## §五 最容易踩的一节：`expire_on_commit` 与 detached

### 5.1 现象

§二 的 `D) False` / `E) 又查了一次库` 就是这个。默认配置下：

> **`commit()` 成功后会把这个 Session 里所有对象的属性全部标记为"过期"（expire），  
> 下次访问任何属性都要重新 SELECT 一次。**

为什么这么设计？因为**你以为你提交的数据，可能已经被数据库改了**：  
触发器改了字段、`onupdate` 改了 `updated_at`、别的并发事务改了行、数据库做了类型转换（§九 的 UUID）。  
提交后一律作废重取，是"宁可多查一次，也不给你错数据"的保守选择。

### 5.2 两个后果

```python
# 后果 1：一次 commit 之后，每个对象的每次属性访问都是一条 SQL（N+1 的温床）
kb = KB(name="x")
session.add(kb)
session.commit()
print(kb.name)  # ← 这里发一条 SELECT
print(kb.id)  # ← 再发一条（同一次 refresh 通常会把整行取回，但第一次必然发）

# 后果 2：Session 关掉之后再访问 → DetachedInstanceError
session.close()
print(kb.name)  # ✗ 炸
```

实测异常原文（SQLAlchemy 2.1.8）：

```
DetachedInstanceError: Instance <KB at 0x...> is not bound to a Session;
attribute refresh operation cannot proceed (Background on this error at: https://sqlalche.me/e/21/bhk3)
```

对比实测（`expire_on_commit` 两种配置）：

| 配置                          | `commit()` 后 `kb.__dict__` 里有 `name` 吗 | `close()` 后读 `kb.name`      |
| --------------------------- | -------------------------------------- | --------------------------- |
| 默认（`expire_on_commit=True`） | **False**（被清空）                         | **`DetachedInstanceError`** |
| `expire_on_commit=False`    | **True**（保留）                           | **`'x'`**，正常读到              |

### 5.3 本项目怎么选

```python
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
```

理由（三条都要能说出来）：

1. **handler 要把 ORM 对象交给 `response_model` 序列化**，而依赖收尾的 `close()` 发生在序列化之后（§六 实测顺序），  
   如果属性全过期，序列化时每条属性再查一次库，白白多几十条 SQL；
2. **`expire_on_commit=False` 不等于"用过期的数据"**：提交后没人改这一行，内存里的值就是库里的值。  
   真怕过期，正确做法是显式 `session.refresh(obj)`，**把"我要最新数据"变成一个看得见的动作**；
3. 返回 DTO 而不是 ORM 对象时（本项目 `rows.py` 的 `KBRow` TypedDict），这条就没那么关键，  
   但**测试里断言对象字段时会舒服很多**（不会因为 session 已关而炸）。

> **易错点**：`expire_on_commit=False` **不能**解决 `DetachedInstanceError` 的另一半原因——  
> **懒加载**。**懒加载（lazy load）**＝"关系数据先不查，等你真的访问它时才查"：  
> 比如 `kb.docs` 这种"这个知识库有哪些文档"的列表，SQLAlchemy 默认**不会**在你查 `kb` 时一起查出来，  
> 而是等你写 `for d in kb.docs` 的那一刻才发一条 `SELECT * FROM documents WHERE kb_id=?`。  
> 问题是：**session 关掉之后就没法再发 SQL 了**，于是"访问一个从没加载过的关系属性"必然炸。  
> 区别记清楚：`expire_on_commit` 管的是"**加载过但作废了**"，懒加载管的是"**压根没加载过**"。

---

## §六 放进 FastAPI：`get_db` 依赖与它的两个隐藏时机

### 6.1 标准写法

```python
# core/db.py（D1 动手任务要你写的目标形态）
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from kb_service.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()  # ← 一个方案：依赖层统一提交（有争议，见 6.4）
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```


`pool_pre_ping=True` 的作用：从池子里借出的连接先发一个轻量探测（MySQL 上是 `SELECT 1` 之类），
死了就换一条。**为什么需要**：MySQL 的 `wait_timeout` 默认 8 小时，把空闲连接单方面踢掉；
池子里那条"以为活着"的连接下次用时才报 `MySQL server has gone away`。这个错误在"服务跑了一夜第二天第一个请求"时出现，
是典型的"零症状→突然全挂"。

> **为什么是 `from collections.abc import Iterator` 而不是 `from typing import Iterator`**：
> 老教程（Python 3.5 时代）都写 `typing.Iterator`。Python 3.9 起（PEP 585）`collections.abc` 里的类
> 本身就能加下标（`Iterator[Session]`），`typing` 里那些留作兼容别名，3.12+ 用起来会发 DeprecationWarning。
> 本项目 ruff 开了 `UP` 规则组（`pyproject.toml` 的 `select`），写 `typing.Iterator` 会被 **UP035** 直接拦下
> （实测：`Import from collections.abc instead: Iterator`）。**跟项目走，用 `collections.abc`。**
> 另外注意模块名是复数：`collections` 包下的 `abc`（Abstract Base Classes，抽象基类）子模块。

### 6.2 关键实测：依赖收尾到底在第几步

这是本篇最值得记住的一组数字。用一个中间件 + 一个 handler + 一个后台任务打点（`scratch/d1_timing.py`）：

```
0. 中间件进入
1. 依赖开始：拿 session
2. handler 执行
3. 中间件拿到响应（响应体已生成）
5. 后台任务执行          ← 注意 5 在 4 前面
4. 依赖收尾：关 session
```

**结论：默认情况下，`get_db` 的 `close()` 发生在「响应已生成 + 后台任务跑完」之后。**

FastAPI 0.150 的 `Depends` 有 `scope` 参数，实测三种配置：

| 配置 | 顺序 | `close()` 时机 |
|---|---|---|
| 不写（默认 `None`） | 1 → 2 → **5 → 4** | 响应发出 + 后台任务**之后** |
| `scope="request"` | 1 → 2 → **5 → 4** | 同上（默认值就是这个） |
| `scope="function"` | 1 → 2 → **4 → 5** | handler 结束、响应发出**之前** |

三个直接推论：

1. **序列化在 `close()` 之前**，所以把 ORM 对象直接交给 `response_model` 是安全的（属性还在）——
   但这也是 §五 要 `expire_on_commit=False` 的原因，否则序列化时每条属性再查一次库。
2. **后台任务跑的时候 session 还活着**。所以 `BackgroundTasks` 里能拿到 session，但**千万别用**：
   **同步**后台任务会被 Starlette 丢进 `AnyIO` 的**线程池**里执行（不是主线程、也不是事件循环），
   而 `Session` 从头到尾**没有为多线程设计**（多个线程同时用它 → 连接被两个线程抢，报
   `concurrent operations are not permitted` 之类）；更糟的是它和请求共用**同一条连接 + 同一个事务**，
   后台任务一报错，整个请求的事务跟着废掉（这就是 D6 那个"索引任务"为什么不复用请求 session 的根因）。
3. `scope="function"` 能让 session 早关，省连接占用时间——但**本项目的序列化和后台任务都需要它活着**，
   所以不改成 `function`。**知道有这个旋钮，但这次不拧**，这个判断本身就是面试可讲的东西。

### 6.3 Session 泄漏比不关文件更隐蔽

`close()` 忘了写（或者 `try/finally` 写错），后果不是马上报错，而是：
**连接回不了池 → 池子被借空 → 后续请求全部卡在"等连接"上超时。**
池子默认 `pool_size=5, max_overflow=10`，也就是第 16 个并发请求就开始等。
线上表现是"服务越跑越慢，重启就好"——这种 bug 极难查，所以**依赖注入 + `finally: close()` 是唯一正确姿势**，
不要"记得关"。

---

## §七 泄漏的实证：`database is locked` 是怎么来的

两个场景，只有一个会炸（`scratch/d1_lock.py`，§十 实验三）。实测输出：

```
场景A：泄漏的 session 只读过（SELECT）
  -> 写入成功
场景B：泄漏的 session 写过（flush 未提交）
  -> 写入失败: OperationalError (sqlite3.OperationalError) database is locked
  泄漏 session 里再 flush 一次会怎样：
    -> 没报错（连接还在，锁还在自己手里）
  -> leak.close() 后写入成功，库里 = 2 ['A', 'B-重试']
```

三条要点：

1. **只用 SELECT 的泄漏在 SQLite 上不阻塞别人**（pysqlite 驱动默认不为 SELECT 发真正的 `BEGIN`），
   但在 MySQL 的 RR 隔离级别下，长事务一样会拖住 undo log、拖慢 purge；
2. **写过就持锁**。泄漏的 session 自己还能写（锁在它手里），**别人一 `commit` 就炸**——
   这就是"我的代码明明没错，报错却在别人的请求里"的典型形态；
3. 最后 `close()` 一调，立刻写入成功，而且库里**没有**那条未提交的数据 → 再次证明 **close 即回滚**。

> **同一个实验在真 MySQL 上跑（8.4.0 / 3307 / RR 隔离级别）**，报错换了个名字，根因一模一样：
>
> ```
> J) 长事务持锁检查（另一事务 SELECT ... FOR UPDATE）
>    -> OperationalError (pymysql.err.OperationalError)
>       (1205, 'Lock wait timeout exceeded; try restarting transaction')
> ```
>
> 对照记：**SQLite 说 `database is locked`（整库一把锁），MySQL 说 `Lock wait timeout exceeded`（InnoDB 行锁 + 超时）**。
> 一个是"库被别人占了"，一个是"这一行被别人占了"——**在 MySQL 上，泄漏事务只锁住它改过的那几行，
> 所以症状更隐蔽：别的请求大部分正常，只有碰巧改同一行的那个卡住**。这就是为什么这类 bug 上线才爆。

---

## §八 易错点表

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | 每请求 `create_engine()` | 跑一阵后 `Too many connections` / 连接数曲线一路涨 | `engine` 放模块级，全局一个 |
| 2 | 全局共享一个 `Session` | 请求 A 的数据出现在请求 B；莫名越权；线程间数据错乱 | 一次请求一个 Session，靠 `get_db` yield 依赖 |
| 3 | 忘了 autoflush 会替你发 SQL | 只想查个数，`add` 的脏数据被顺手 INSERT；或反过来，查询结果包含未提交改动 | 明确知道 `session.execute` 会先 flush；需要"只看库"时用 `no_autoflush` 块 |
| 4 | `commit()` 后把对象跨请求带出去 | `DetachedInstanceError`（§五 有原文） | 返回 DTO/TypedDict，或 `expire_on_commit=False`，或提前 `refresh` |
| 5 | 以为 `create_all()` 会改表结构 | 加了字段，代码报 `no such column: kb.xxx`，库还是旧的 | `create_all` 只建**不存在**的表；改结构必须 Alembic 迁移（D5） |
| 6 | 忘了 `close()`（或 `try/finally` 写错） | 池子耗尽，全站请求卡在等连接，重启就好（§六 6.3） | `finally: session.close()`，用依赖注入兜住 |
| 7 | 在后台任务里用请求的 session | 偶发 `This session is provisioning a new connection; concurrent operations are not permitted` / 线程相关报错 | 后台任务自己开新 Session（`with SessionLocal() as s:`） |
| 8 | 把 `flush()` 当成"提交了" | 本地测没问题，另一个事务查不到数据 / 进程重启数据没了 | flush ≠ commit，只有 commit 落库 |

### 8.1 命令速查（今天会反复用到，两套写法并列）

> PowerShell 的两条注意：① 原生命令（`mysqld`/`mysql`/`python`）**不要加 `2>&1`**，否则输出被包成 ErrorRecord、`$?` 变 false；
> ② `grep`/`touch`/`rm -rf` 这些在 PowerShell 里不存在，下面已经换成 cmdlet。

**起库 / 停库（每天开工第一件事）**

```powershell
# Windows PowerShell
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\start-mysql.ps1   # 前台跑，Ctrl+C 停
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\stop-mysql.ps1    # 另开窗口停
```

```bash
# Git Bash / Linux / macOS（本机没有对应脚本时，直接起 mysqld）
"F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysqld.exe" \
  --defaults-file="F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/my.ini" --console
```

**连库 / 看库（客户端不在 PATH 里，写全路径）**

```powershell
# Windows PowerShell —— 日常用 kb（应用账号，只有 kb_dev 库的权限）
$MYSQL = "F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe"
& $MYSQL -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev -e "SHOW TABLES;"
& $MYSQL -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev -e "SELECT VERSION(), @@transaction_isolation, @@time_zone;"

# —— 诊断类命令必须用 root（观察员账号），kb 会报权限错误 ——
& $MYSQL -h 127.0.0.1 -P 3307 -u root -e "SHOW PROCESSLIST;"                    # 谁连着、在跑什么
& $MYSQL -h 127.0.0.1 -P 3307 -u root -e "SHOW ENGINE INNODB STATUS\G"          # D4 看锁/死锁用
& $MYSQL -h 127.0.0.1 -P 3307 -u root -e "SELECT * FROM performance_schema.data_locks;"  # D4 看行锁明细
```

```bash
# Git Bash / Linux / macOS
MYSQL="F:/WorkBuddy/2026-10-20-08-44-29/tools/mysql-8.4.0/bin/mysql.exe"
"$MYSQL" -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev -e "SHOW TABLES;"
"$MYSQL" -h 127.0.0.1 -P 3307 -u root -e "SHOW PROCESSLIST;"
```

> **为什么诊断命令要换 root（2026-11-12 实测踩坑）**：`kb` 的权限是
> `GRANT ALL PRIVILEGES ON kb_dev.*` —— **只在 kb_dev 这一个库里是全能的**，出了库什么都没有。
> 三类诊断命令都在它的权限之外：
>
> | 命令 | kb 的下场 | 需要什么 |
> |---|---|---|
> | `SHOW ENGINE INNODB STATUS` | `ERROR 1227: you need the PROCESS privilege` | **PROCESS 是全局权限**（`ON *.*`），没法只授给一个库 |
> | `SELECT * FROM performance_schema.data_locks` | `ERROR 1142: SELECT command denied` | performance_schema 表的 SELECT（全局） |
> | `SHOW PROCESSLIST` | **不报错，但只看到自己**（实测 kb 只有 1 行；root 能看到 event_scheduler） | 有 PROCESS 才能看到**别人**的线程 |
>
> 注意第三种最阴险：不报错、结果也"像是对的"，只是少了几行——这类权限问题**可能根本不报错**。
>
> 这不是要给 kb 补权限，而是**故意不给**：应用账号拿全局 PROCESS 意味着它能看到服务器上所有连接，
> 万一账号泄露攻击面立刻变大。**应用账号最小权限 + 诊断用管理员账号**是线上标准做法，
> 你公司里大概率也是这么分的（应用连库账号查不了 `SHOW ENGINE INNODB STATUS`）。

**跑 Python / 跑测试（务必用项目 venv，不要用系统 python）**

```powershell
# Windows PowerShell（在仓库根 python-backend-roadmap 下）
& .\kb-service\.venv\Scripts\python.exe .\scratch\d1_min.py
Set-Location kb-service
uv run pytest tests/test_db_session.py -v
uv run pytest -k "commit or rollback" -v      # 只跑名字里带这些词的用例
uv run ruff check . ; uv run mypy src
```

```bash
# Git Bash / Linux / macOS
./kb-service/.venv/Scripts/python.exe ./scratch/d1_min.py    # Windows Git Bash
# ./kb-service/.venv/bin/python ./scratch/d1_min.py          # 真 Linux / macOS
cd kb-service && uv run pytest tests/test_db_session.py -v
```

**看 ORM 到底发了什么 SQL**（今天最重要的一个开关）

```python
engine = create_engine(url, echo=True)  # 全部 SQL 打屏
engine = create_engine(url, echo=True, echo_pool="debug")  # 连"借连接/还连接"也打出来
session.execute(stmt.compile(compile_kwargs={"literal_binds": True}))  # 只编译不执行，看最终 SQL
```

**清场（练习库随便删）**

```powershell
# Windows PowerShell：连库删库，或直接删文件
& $MYSQL -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd -e "DROP DATABASE IF EXISTS kb_scratch; CREATE DATABASE kb_scratch CHARACTER SET utf8mb4;"
Remove-Item -Recurse -Force .\scratch -ErrorAction SilentlyContinue
```

```bash
# Git Bash / Linux / macOS
rm -rf ./scratch
```

---

## §九 本项目特有的两个坑（实测）

### 9.1 UUID 主键在 SQLite 里的样子

```
类型: UUID ba516574-2e45-4bb1-a969-85ad1e37c589
SQLite 里的原始值: ('ba5165742e454bb1a96985ad1e37c589', '...', 'text')
```

- 用 `mapped_column(Uuid, primary_key=True, default=uuid4)`，Python 侧拿回的是 **`uuid.UUID` 对象**（自动转换）；
- 库里存的是**去掉横线的 32 位文本**（SQLite）。MySQL 上对应 `CHAR(32)` 或 `BINARY(16)`；
  Postgres 原生有 `UUID` 类型。
- **别用 `String(36)` 凑合**：能存，但读回来是 `str`，你的 `KBRow["id"]: UUID` 类型标注就是假的（mypy 也拦不住）。

### 9.2 时区在数据库里会丢（这条会坑你到 W12）

```
created_at 读回后 tzinfo: None      ← 我存的是 datetime.now(UTC)，读回来时区没了
```

**两边都验过**：SQLite 存成字符串，MySQL 存成 `DATETIME(0)`，**读回来 `tzinfo` 都是 `None`**（实测）：

```
I) MySQL 库里的原始值 = ('aca9c3f5dde84944b47343683b2fea2a', datetime.datetime(2026, 11, 12, 5, 28, 43))
H) 读回 id 类型 = UUID | created_at tzinfo = None
```

注意第二个细节：我存的是 UTC 时间，库里存的是 `05:28`（= 13:28 北京 - 8 小时），**时区信息丢了但值是对的**——
因为连接时 `default-time-zone='+00:00'` 让服务器按 UTC 解释。如果你的 MySQL 是 `+08:00`，同一个 `datetime.now(UTC)`
会被当成本地时间写进去，**再读出来就整体偏 8 小时**。这类 bug 只在跨时区/换机器时才暴露。

所以**"存 UTC、读出来当 UTC 用"必须靠约定，不能靠类型**。本项目约定：

- 写入一律 `datetime.now(UTC)`；
- 读出时若 `tzinfo is None`，按 UTC 补上（`dt.replace(tzinfo=UTC)`），否则与"带时区的当前时间"比较会抛
  `TypeError: can't subtract offset-naive and offset-aware datetimes`；
- 需要数据库层彻底不丢时区：MySQL 用 `TIMESTAMP`（自动转 UTC 存）或 Postgres 的 `timestamptz`；
  但**不要混用**——同一列一半 `DATETIME` 一半 `TIMESTAMP` 的项目，调时区会调到崩溃；
- 这个问题在 W6-D1 你踩过一次（时区/精度），这里是它在数据库层的复现。

---

## §十 动手实验（跑之前先猜，至少猜对两个）

| # | 实验 | 猜什么 | 在哪 |
|---|---|---|---|
| 一 | 事务四动作（§四 那张表） | `close()` 不 commit，数据在不在？ | `scratch/d1_tx.py` |
| 二 | `expire_on_commit` 两种配置 | 默认配置下 `commit()` 后 `__dict__` 里有字段吗？ | `scratch/d1_expire.py` |
| 三 | 泄漏的 session | 只读泄漏会不会阻塞写入者？ | `scratch/d1_lock.py` |
| 四 | 依赖收尾时机 | `close()` 在后台任务之前还是之后？ | `scratch/d1_timing.py` |

四个脚本的**骨架**已经实测过，你需要自己敲一遍（敲比读有效 3 倍，且有错别字会被解释器抓到）。
每个实验做完，在纸笔本上写**一行结论**（不是抄代码）：

```
实验一：close 未 commit = 回滚，库里没数据
实验二：默认 commit 会清空属性 → 再读触发 SELECT
实验三：只读泄漏不锁，写过才锁（SQLite）
实验四：默认 close 在后台任务之后
```

---

## §十一 今天的动手任务（这是交付物，不是阅读）

### 任务目标

把项目从"内存 dict"往"真实数据库"挪**第一步**：只做 **连接 + 会话 + 一张表 + 一个方法**，
不碰 service 层、不碰 API 层、不碰 Alembic。

### 交付物（三个文件 + 一个测试）

**① 新建 `kb-service/src/kb_service/core/db.py`**

要求：
- 模块级 `engine`（用 `get_settings().database_url`，但**今天的默认值先临时指 SQLite**，见下）
- `SessionLocal = sessionmaker(...)`，`expire_on_commit=False`
- `get_db()`：`yield` 依赖，`try/finally` 保证 `close()`
- **不做**在依赖层自动 `commit()`（提交权留给 service 层——为什么？写一句话理由，验收时会问）

**② 新建 `kb-service/src/kb_service/repositories/models.py`**

- `Base(DeclarativeBase)`
- `class KnowledgeBase(Base)`：表名 `knowledge_bases`
- 字段对齐现有 `KBRow`（`repositories/rows.py`）：
  `id: UUID`（主键，`default=uuid4`）、`owner_id: UUID`（索引）、`name: str(100)`、
|  |  |
| --- | --- |
  `description: str | None`（`String(500)`，可空）、`doc_count: int`（默认 0）、
  `created_at` / `updated_at`（`DateTime(timezone=True)`，`default=lambda: datetime.now(UTC)`）
- 提供 `to_row(self) -> KBRow`：把 ORM 对象转成现有 TypedDict（这是 §五 的"返回 DTO"实践）

**③ 改 `kb-service/src/kb_service/repositories/kb_repo.py`**

**只改一个方法**：`create(self, owner_id, data) -> KBRow`。
- 构造函数接 `session: Session`（`def __init__(self, session: Session) -> None`）
- `create` 里 `add` + `flush()`（**不要 commit**，提交是 service 的事）+ `return obj.to_row()`
- 其余方法**原样不动**（保持内存实现，今天不追求整体切换——下一课再换）

**④ 新建 `kb-service/tests/test_db_session.py`（3 个测试）**

1. `test_commit_persists`：写入 + commit，新 Session 里查得到；
2. `test_close_without_commit_rolls_back`：写入 + flush + close，新 Session 里**查不到**；
3. `test_get_db_yields_same_session_per_request`：用 `TestClient` 打两次同一个接口？
   —— 不，今天不做接口。改成：用 `SessionLocal()` 两次，断言**是两个不同对象**（证明不是单例）。
   并在注释里写一句："一次请求一个 session，靠依赖缓存保证同一个请求内复用"。

测试用 `tmp_path` 造临时 SQLite 文件（**不要**用 `sqlite:///:memory:`，原因：`create_all` 和后续连接会拿到不同的内存库，
除非用 `StaticPool`——这是常见坑，验收会问）。

### 关于 `database_url`（这里有个必须先拆掉的雷）

`core/config.py` 里原来写的是：

```python
database_url: str = "postgresql+asyncpg://kb:kb@localhost:5432/kb"
```

**这颗雷是**：这是**异步驱动**的 URL（`asyncpg`），必须配 `create_async_engine()`；
今天我们要 `create_engine()`（同步），直接拿它去建引擎 → 启动即报错（模块没装或驱动不匹配）。
而且本机没有 Postgres，默认值指向一个不存在的东西 = 新人 clone 下来第一步就跑不起来。


**已经替你改好了**（这一条和"配置不该硬编码"不冲突，理由在下面）：

```python
# 默认值只服务"本地零配置能跑"：sqlite 不需要账号密码。
# 真库地址一律走 .env / 环境变量。W12 上 pgvector 时改成 postgresql+psycopg://...
database_url: str = "sqlite:///./kb_dev.db"
```

同时 `.env`（**不入库**，已 gitignore）里配好了真库：

```
DATABASE_URL=mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4
```

**所以现在的行为是**：不带任何环境变量 → 连 MySQL 3307（`.env` 优先于代码默认值）；
把 `.env` 里那行注释掉 → 落回 sqlite，不装任何东西也能跑。

理由（面试也能用）：**默认值的唯一职责是"本地开发零配置能跑"**，线上值一律由环境变量注入。
所以默认值该写本机能跑的东西，而不是"最终形态但本机没有"的东西。

**测试不读全局配置**——用 fixture 自己造 engine，每个测试一个临时库：

```python
@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
```

> **注意一个真实约束**：`get_settings()` 有 `@lru_cache`，**同一个进程里第一次读到的值会被缓存**。
> 如果测试想"每个测试一个临时库"，改环境变量必须配合 `get_settings.cache_clear()`，
> 或者在测试里直接构造 `Settings(database_url=...)`（**推荐后者**，别去动全局缓存）。
> 这个坑在 D1 的第三个测试里就会撞上——撞上了先自己想 5 分钟。

### 加分实验（强烈建议，5 分钟）：把 URL 换成 MySQL，其余一行不改

同一个 `models.py`、同一段 `create`/`commit`/`select` 代码，只把连接串换成
`mysql+pymysql://kb:kb_dev_pwd@127.0.0.1:3307/kb_dev?charset=utf8mb4`，跑一遍，观察三件事：

1. **业务代码零改动**——这就是 W3 学的"依赖倒置"在数据库上的兑现（repo 签名不变，实现换方言）；
2. `echo=True` 打出的 SQL **变了**：`?` 占位符变成 `%s`（`pymysql` 的 paramstyle），建表 DDL 多了 `ENGINE=InnoDB`；
3. 泄漏实验的报错**从 `database is locked` 变成 `Lock wait timeout exceeded`**（§七 末尾）。

跑完在总结里写一句："方言差异只出现在 SQL 文本和驱动层，Session/事务语义完全一致"——**这句就是面试答案**。

### 验收标准（我会按这个判档）

| 档位 | 标准 |
|---|---|
| 不及格 | 跑不起来 / 测试红 |
| 及格 | 4 个文件都对，`pytest` 3 绿，`ruff` 干净 |
| 合格 | 上面 + 能回答：为什么 `create` 里只 `flush` 不 `commit`？为什么测试不用 `:memory:`？ |
| 真懂 | 上面 + 能不看代码说出"`Session()` 之后到第一条 SQL 之间发生了什么" |
| 全对 | 上面 + 主动指出：`get_db` 里如果写 `session.commit()` 会带来什么问题 |

> 今天**不出埋坑版**——这题是你从零写，没有"AI 交付的代码"可找坑。
> 找坑的练习从 D2 开始（那天我要把 `kb_repo` 整个切到 SQLAlchemy，交付版会埋 3 个坑）。

---

## §十二 面试问法

### 12.1 三十秒版（背下来，能张口就来）

**Q1：Engine 和 Session 的区别？**
> Engine 是进程级的连接池 + 方言，全局一个，负责"怎么连、怎么翻译 SQL"；Session 是请求级的工作台，
> 负责"这一个请求里改了哪些对象、什么时候提交"，它持有事务。混用的后果：Engine 每请求建会耗尽连接，
> Session 全局共享会把一个请求未提交的数据暴露给另一个请求。

**Q2：一次请求一个 Session，为什么？**
> 三个理由：① 事务边界清晰，一个请求一次提交；② 同一请求内身份映射保证同一行是同一个对象，不会互相覆盖；
> ③ 请求结束就关闭，连接能及时还池。反过来"一次操作一个 Session"会让每行有多个副本，
> 造成 lost update，还浪费连接借还。

**Q3：`flush` 和 `commit` 什么区别？**
> flush 是把内存改动翻译成 SQL 发出去，事务没结束，别人看不见，但锁已经加了；
> commit 是先自动 flush 再发 COMMIT，数据真正落库。所以 flush ≠ 提交，进程在两者之间崩掉，数据一样丢。

**Q4：`commit()` 之后为什么还要再查一次库？**
> 因为默认 `expire_on_commit=True`：提交后所有对象属性作废，下次访问触发 SELECT。
> 设计意图是防止"数据库侧改了值（触发器、onupdate、并发写）而内存里是旧值"。
> 代价是多查、以及 session 关闭后访问报 `DetachedInstanceError`。项目里常关掉它，
> 需要最新数据时显式 `refresh()`。

### 12.2 追问链（三层递进：机制 → 边界/故障 → 场景落地）

**Q2 的追问链：**

- **第一层（机制）**：Session 里到底装了什么？
  → 身份映射、待提交改动（unit of work）、事务句柄。
- **第二层（边界/故障）**：如果两个请求共用一个 Session，最先崩的是什么？
  → 不是报错，是**静默越权**：A 的未提交改动被 B 的 commit 提交；同时线程不安全，
  并发时可能报 `concurrent operations are not permitted`。
- **第三层（场景落地）**：你的项目里怎么保证"一次请求一个"？
  → `get_db` 用 yield 依赖 + FastAPI 依赖缓存（同一请求内复用），`finally: close()` 收尾；
  **实测依赖收尾在响应发出和后台任务之后**，所以后台任务里能拿到这个 session，
  但必须自己开新 Session——否则线程池里的任务会跨线程用同一个 session。

**Q4 的追问链：**

- 第一层：`expire_on_commit` 默认值是什么？为什么？
- 第二层：关掉它有什么风险？→ 读到"提交时的值"，若提交后别人改了同一行，你手上是旧的；
  解决要么 `refresh`，要么在 SQL 层用乐观锁版本号（D4 讲）。
- 第三层：AI 应用场景里怎么落地？→ RAG 的文档入库是"先写 DB 再投递索引任务"，
  提交后要拿到 `id` 给后端任务用；如果 `expire_on_commit=True`，后台任务里访问属性会额外查库甚至 detached 报错。

**Q1 的追问链补充（场景层）**：连接池大小怎么定？
→ 不是越大越好：`pool_size` 与数据库 `max_connections`、进程数、平均持有时长共同决定；
pool 太小请求排队，太大把 DB 压死。正确做法是先量 p99 持有时长和 QPS 再算，并用 `pool_timeout` 快速失败。
（本项目还没到压测阶段，W9 会做。）

---

## §十三 闭卷自测（先自己答，再展开）

> **用法**：下面 10 题先**闭卷口答**（能说出来才算懂），再点开对应答案核对。
> 答不出 ≤2 题算读懂；≥4 题答不出就回 §零–§六 重走主线。

**题目清单**：

1. `Session(engine)` 这一行执行完，事务开了吗？连接借了吗？
2. 只 `flush()` 没 `commit()`，然后进程被 kill，数据在吗？为什么？
3. `session.close()` 会不会丢已经 commit 的数据？
4. 为什么 `expire_on_commit=False` 之后还会出现 DetachedInstanceError？
5. `create_all()` 会不会给已有表加字段？
6. 依赖 `get_db` 的 `close()` 在 FastAPI 里到底什么时候执行？
7. 为什么测试不要用 `sqlite:///:memory:`？
8. 一条时间轴上说出四个刻度：Session() / 第一条 SQL / commit / close，各发生了什么？
9. ORM 对象和 DTO（`KBRow`）有什么区别？为什么 repo 层只许把 DTO 交出去？
10. 事务到底是什么？为什么它能"撤销"已经执行过的语句？

---

**答案**：

<details><summary>答案 1</summary>

都没。Session 是惰性的：第一条 SQL（或 flush）才借连接 + `BEGIN (implicit)`。
实测 `in_transaction() == False`。
</details>

<details><summary>答案 2</summary>

不在。flush 只是把 INSERT 发出去了，事务没提交，进程一死连接断开 → 数据库回滚未提交事务。
锁在 flush 那一刻就加了，所以这段时间别的写事务会被阻塞。
</details>

<details><summary>答案 3</summary>

不会。close 只对**未结束的事务**做 rollback；已提交的数据已经在库里。
实测：commit 后 close，数据仍在。
</details>

<details><summary>答案 4</summary>

因为还有另一半原因：**懒加载**。关系属性（如 `kb.docs`）如果没被加载过，session 关闭后再访问要发 SQL，
而对象已 detached → 报错。`expire_on_commit` 只管"已加载的属性是否作废"。
</details>

<details><summary>答案 5</summary>

不会。它只对"库里不存在的表"发 `CREATE TABLE`（前面会先 `PRAGMA table_info` 查一下）。
加字段/改类型必须用 Alembic 迁移。这是"我明明加了字段为什么报 no such column"的根因。
</details>

<details><summary>答案 6</summary>

默认（`scope="request"`）在**响应生成之后 + 后台任务执行之后**。实测顺序：
中间件进入 → 依赖开始 → handler → 中间件拿到响应 → 后台任务 → 依赖收尾。
`scope="function"` 会提前到 handler 结束时、响应发出前。
</details>

<details><summary>答案 7</summary>

每条新连接都会得到一个**全新的空内存库**。`create_all` 在连接 A 上建的表，连接 B 看不见 →
表不存在。要凑合用必须配 `StaticPool` + `check_same_thread=False` 强制共用一条连接。
用 `tmp_path` 造临时文件库最省事。
</details>

<details><summary>答案 8</summary>

见 §零 的四行表。答不全就回去看——这是本篇的主线，也是明天 D2 的前提。
</details>

<details><summary>答案 9</summary>

ORM 对象（`KB` 实例）**绑在 session 上**，它的属性可能"没加载"或"已过期"，一访问就要发 SQL，
session 一关就报 `DetachedInstanceError`，还带着一堆数据库细节（连接、脏状态）。
DTO（`KBRow` 这个 TypedDict）是**纯数据**，跟数据库没关系，session 关了照样能读、能序列化、能跨层传。
所以 repo 外出只给 DTO：**上层不需要知道"你是怎么存的"，只需要知道"数据长什么样"**——
这既是分层（W3）的兑现，也是防 §五 那类炸的具体手段。
</details>

<details><summary>答案 10</summary>

事务是"一组要么全成功、要么全失败的操作"。它能撤销**不是**因为把 SQL 反着跑一遍，
而是因为数据库**先写日志再改数据**（undo 日志记录旧值），回滚时按日志把数据还原。
代价是每次写都要额外写日志——所以事务不是免费的，长事务会让日志膨胀、拖慢别人（D4 会实测）。
</details>

---

## §十四 今日纸笔靶（三行，别多写）

1. **画**：§零 那条时间轴（6 个刻度），标出"事务从哪开始、到哪结束"、"连接什么时候借、什么时候还"。
   只留最终版，页脚一行改动清单（如 `改：①close 在后台任务后 ②commit 清空属性`）。
2. **写三句**（闭卷，限定词必须写出来）：
   ① "Session 是**请求级**的工作台，Engine 是**进程级**的连接池。"
   ② "**第一条 SQL** 才借连接并开启事务，`Session()` 本身什么都不做。"
   ③ "`close()` 对未提交事务**等价于 rollback**，对已提交数据无影响。"
3. **手写骨架**（10 分钟，不看教材）：`get_db` 依赖的 `try / yield / except / finally` 四段结构。
   写完对照 §6.1，看漏了哪段。

---

## §十五 附录：本机数据库装好了（两个库，各管一件事）

开工前本机状况：**有 MySQL 8.0 服务在跑（3306）但密码不明**（别人遗留的），**没有 Docker**。
处理方式：**不碰那个 3306**，另装一个独立实例——

| 项 | 值 |
|---|---|
| 版本 | MySQL **8.4.0** LTS（zip 免安装） |
| 位置 | `F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0`（**不在仓库里**，不进 git） |
| 端口 | **3307**（避开 3306；X Protocol 已关，避免抢 33060） |
| 数据目录 | `tools\mysql-8.4.0\data`（删这个目录 = 库全清，重装一样） |
| 账号 | `root`（空密码，仅本机）/ 应用账号 `kb` / 密码 `kb_dev_pwd` |
| 库 | `kb_dev`，`utf8mb4` / `utf8mb4_0900_ai_ci` |
| 时区 | `+00:00`（跟项目"一律 UTC"对齐） |
| 隔离级别 | `REPEATABLE-READ`（MySQL 默认，D4 就是研究它） |

**每天起库（一个命令，跑着别关）**：

```powershell
# Windows PowerShell：这个窗口会被 mysqld 占住，Ctrl+C 停库
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\start-mysql.ps1

# 停库（另一个窗口，或者直接 Ctrl+C）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\stop-mysql.ps1

# 连库（客户端在 bin 下，不在 PATH 里，所以要写全路径）
& F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -h 127.0.0.1 -P 3307 -u kb -pkb_dev_pwd kb_dev
```

**两个库怎么分工（这条规矩要记到 W12）**：

| 用途 | 用什么 | 为什么 |
|---|---|---|
| 跑逻辑、单测 | **SQLite 文件库**（`tmp_path`） | 毫秒级、零清理；`pytest` 不该依赖"服务有没有起" |
| 索引 / 锁 / 隔离级别 / `EXPLAIN` | **MySQL 3307** | 只有真库有这些现象，SQLite 的 `EXPLAIN QUERY PLAN` 信息量差一个数量级 |

**方言差异表**（不影响今天的结论，D3 会逐条验证）：

| 维度 | SQLite | MySQL 8.4 | Postgres |
|---|---|---|---|
| 事务/会话 API | 完全一致（SQLAlchemy 层面，**今天全篇结论两边都验过**） | 完全一致 | 完全一致 |
| 字符串长度 | **不校验** | 严格模式校验（超长报 `1406 Data too long`） | 校验 |
| 锁粒度 | 库级（`database is locked`） | **行级**（`Lock wait timeout exceeded`） | 行级 + MVCC |
| `EXPLAIN` | `EXPLAIN QUERY PLAN`（无 `type`/`rows`/`key`） | `EXPLAIN` / `EXPLAIN ANALYZE` | `EXPLAIN (ANALYZE, BUFFERS)` |
| UUID 主键 | `CHAR(32)` 文本 | `CHAR(32)`（存的是 32 位无横线 hex，实测） | 原生 `UUID` |
| 时区 | 不存 | `DATETIME` 不存 / `TIMESTAMP` 转 UTC | `timestamptz` 保留 |

> 装库时踩到的两个真实问题，记下来免得你再踩：
> ① `my.ini` 里写 `skip-name-resolve` → 初始化只建了 `root@localhost`，用 `127.0.0.1` 连会报
> `ERROR 1130 Host '127.0.0.1' is not allowed to connect`。去掉该选项即好（或额外建 `root@'127.0.0.1'`）。
> ② 系统里已有 MySQL80 占着 3306 与 X Protocol 的 33060 → 新实例必须换端口并 `mysqlx=0`，否则起不来。
