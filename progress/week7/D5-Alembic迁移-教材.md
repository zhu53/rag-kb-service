# W7-D5 Alembic 迁移：让数据库结构带上版本号（零基础版）

> 读者假设：你昨天刚学完事务、锁、索引。你知道表长什么样，也知道 `create_all()` 能把表建出来。
> 但你不知道：**表建出来之后，怎么让它在下一次改动时不把线上搞崩。**

## 本篇分级总表

| 小节 | 内容 | 级别 |
|---|---|---|
| §零 | 主线时间轴：迁移在整条链上的位置 | A 必学 |
| §一 | 痛点：没有迁移工具的团队怎么死 | A 必学 |
| §二 | 最小可跑示例（5 分钟，sqlite 隔离演练） | A 必学 |
| §三 | 三个核心概念：revision 链、版本表、autogenerate 在比较什么 | A 必学 |
| §四 | 机制：`upgrade head` 到底做了什么 | B 会用 |
| §五 | 为什么 `create_all` 不能上线（七条） | A 必学 |
| §六 | 易错点表 | A 必学 |
| §七 | 命令速查（PowerShell + bash） | B 会用 |
| §八 | 面试问法（30 秒版 + 追问链三层） | A 必学 |
| §九 | 闭卷自测（题目清单前置 + 折叠答案） | A 必学 |
| §十 | 动手任务（交付物 + 验收 + 提示阶梯） | A 必学 |
| §十一 | 业务链条三问 | A 必学 |

**L 级（了解）跳过不影响今天的任务**：Alembic 的 `branching`（多分支合并）、`--autogenerate` 的 `compare_type` 精细开关、`pyproject.toml` 配置模式。

---

## §零 主线 [A]

```
W7 之前                     W7-D1~D2            W7-D3              W7-D4              W7-D5（今天）         W7-D6            W7-D7
模型=类，表怎么来的？  →   会话与事务边界   →   索引与EXPLAIN   →   锁与死锁        →   迁移(版本化结构)   →  变异体验收   →  周总结
                            （怎么读写）        （怎么走索引）      （怎么互相阻塞）    （怎么上线演进）
                                                                    ↑                    ↑
                                                        D3 用 create_all 临时建的表   今天把它扔了，让迁移从零建
```

**一句话分界线**：

> `create_all()` 回答"**现在**把表建出来"；Alembic 回答"表是**怎么一步步变成现在这样**的"。
> 前者是一个动作，后者是一段历史。**线上环境要的是历史，不是动作。**

读每一节都要能回答："这一段在线上哪个位置？"——迁移发生在**部署流程**里，不在请求链路里；它跑在你（或 CI）敲命令的那一刻，跑完就退出。

---

## §一 痛点：没有迁移工具的团队怎么活 [A]

假设你现在要把 `documents.title` 从 `VARCHAR(200)` 改成 `VARCHAR(500)`，同时给 `status` 加一个索引。三个环境：你的笔记本、测试机、线上。

**没有迁移工具时，团队真实的做法长这样**：

1. 你手工在本地跑 `ALTER TABLE documents MODIFY title VARCHAR(500);`
2. 在群里发一句"我改了这个表，SQL 在下面"，附上语句
3. 测试机同事说"我漏跑了，刚才报 `Data too long`"
4. 线上运维晚上发版时翻聊天记录，找到一条三条消息之前的 SQL，复制粘贴
5. 两周后发现线上少一个索引——因为那条 `CREATE INDEX` 发在图片里，没人抄

这里有五个独立的失效点，每一个都真实存在：

| 做法 | 什么时候失效 |
|---|---|
| 手工敲 ALTER | 忘了在哪台机器跑过，无法核对 |
| 群里发 SQL | 消息被覆盖、顺序错、图片里的语句抄不到 |
| 写进 README 的"部署步骤" | 没人读；读了也可能跳过某一步 |
| 写个 `migrate.sql` 全量脚本 | 跑第二遍就报 `table already exists`，只能靠人肉判断"哪些已经跑过" |
| `Base.metadata.create_all()` | **只建不改**（§五 详述），加列、改类型、加索引它全都不管 |

**根子上的问题只有一个**：数据库结构的每一次变化，**没有被记录成一串可执行、可核对、可回滚的步骤**。

Alembic 干的就是这件事：把每一步结构变化写成一个 Python 文件，文件之间有先后关系，数据库里存一个"我跑到第几步了"的标记。

---

## §二 最小可跑示例：5 分钟看清 Alembic 到底生成什么 [A]

这一节**不碰你的 `kb_dev`**。用 `scratch/`（已被 `.gitignore` 忽略）里一个 sqlite 小样把流程走一遍，目的是先看见"文件长什么样"，而不是记住命令。

> **位置约定（2026-11-18 实测修正）**：demo 放在**仓库根**的 `python-backend-roadmap/scratch/alembic_demo/`，
> 目录名不要放在 `kb-service/` 下——两边都有 `scratch` 时，最容易出现"init 在一个目录、你的模型在另一个目录"的分裂现场。
> `.venv` 在 `kb-service` 里，所以命令里的可执行文件路径写成 `..\..\kb-service\.venv\Scripts\alembic.exe`。

### 2.1 准备一个隔离的小摊子

在 `python-backend-roadmap`（仓库根）下：

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force scratch\alembic_demo | Out-Null
Set-Location scratch\alembic_demo
```

```bash
# Git Bash / Linux / macOS
mkdir -p scratch/alembic_demo && cd scratch/alembic_demo
```

在 `scratch/alembic_demo/` 下建一个最小的 `models_demo.py`（手写，5 行）：

```python
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Thing(Base):
    __tablename__ = "things"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
```

### 2.2 跑 init，看它生成了什么

**在 `scratch/alembic_demo` 目录里执行**（这一步的位置很关键，见下面的方框）：

```powershell
# Windows PowerShell（当前目录 = scratch\alembic_demo）
& ..\..\kb-service\.venv\Scripts\alembic.exe init -t generic alembic
```

```bash
# Git Bash / Linux / macOS（当前目录 = scratch/alembic_demo）
../../kb-service/.venv/Scripts/alembic.exe init -t generic alembic
```

> **`init` 的两个参数容易搞混**：
> 最后一个参数 `alembic` 是**脚本目录名**（在当前位置下创建），而 `alembic.ini` **永远生成在当前工作目录**。
> 所以必须在 demo 目录里执行这条命令。如果你在 `kb-service` 里执行，ini 会落到 `kb-service/alembic.ini`，
> 而 `alembic/` 目录跑到别处去——结果就是你打开 demo 目录只看到 `models_demo.py`，以为 init 没成功。
> （**这就是 2026-11-18 我教材第一版写错的地方，实测后修正。**）

实测输出（六个产物，路径是你自己机器上的）：

```
Creating directory ...\scratch\alembic_demo\alembic ...  done
Creating directory ...\scratch\alembic_demo\alembic\versions ...  done
Generating ...\scratch\alembic_demo\alembic.ini ...  done
Generating ...\scratch\alembic_demo\alembic\README ...  done
Generating ...\scratch\alembic_demo\alembic\env.py ...  done
Generating ...\scratch\alembic_demo\alembic\script.py.mako ...  done
Please edit configuration/connection/logging settings in '...\alembic.ini' before proceeding.
```

**六个产物，各管什么**（先认识，不用背）：

| 产物 | 作用 | 你要不要动它 |
|---|---|---|
| `alembic.ini` | 配置文件：脚本目录、日志、数据库 URL | **要改**（URL 不写死，见 §三） |
| `alembic/env.py` | 迁移运行时真正执行的代码：怎么连库、拿哪份模型元数据 | **要改**（接入你的 `Base.metadata`） |
| `alembic/versions/` | 迁移文件存放处，一个文件 = 一步 | 只往里加，不手改已有文件 |
| `alembic/script.py.mako` | 新迁移文件的模板 | 基本不动 |
| `alembic/README` | 建库说明书（就是一句话） | 不动 |
| `alembic_version` 表 | **在数据库里**，不是文件，记录"跑到第几步" | 绝不用手改 |

生成的 `alembic.ini` 里有两行是好的默认值，看一眼就够：

```ini
script_location = %(here)s/alembic      # %(here)s = 这个 ini 文件所在目录
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname   # ← 占位符，必须改
```

### 2.3 改两处，让它认识你的模型

打开 `scratch/alembic_demo/alembic/env.py`，找到这两处：

```python
config = context.config          # 第 10 行附近
...
target_metadata = None           # 第 21 行附近，默认就是 None
```

改成（两处修改，用注释标出来了）：

```python
config = context.config

# ① 数据库 URL 从代码里给，不写死在 alembic.ini（写死就意味着密码进 git）
config.set_main_option("sqlalchemy.url", "sqlite:///./demo.db")

# ② 把模型所在目录放进 sys.path，并把模型元数据交给 Alembic
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # env.py 的上一层 = alembic_demo
from models_demo import Base                                    # noqa: E402

target_metadata = Base.metadata
```

> **`parents[1]` 怎么数**：`env.py` 的路径是 `.../alembic_demo/alembic/env.py`，
> `parents[0]` = `alembic/`，`parents[1]` = `alembic_demo/`（模型所在目录）。**不是 `parents[2]`**——多升一层就 import 不到。
>
> **为什么 `target_metadata` 是整件事的枢纽**：`autogenerate` 干的事就是"把这份元数据（你代码里的理想结构）和真实库（现状）做 diff"。元数据没接上，diff 的两边就有一边是 `None`——结果不是报错，而是**安静地生成一个空迁移**（`No changes detected`）。这是新手第一大坑。

### 2.4 生成第一步迁移，然后读它

```powershell
# Windows PowerShell（仍在 scratch\alembic_demo）
& ..\..\kb-service\.venv\Scripts\alembic.exe revision --autogenerate -m "create things"
```

实测输出（注意前三行是 1.20 的插件加载日志，正常现象）：

```
INFO  [alembic.runtime.plugins] setting up autogenerate plugin alembic.autogenerate.types
INFO  [alembic.runtime.plugins] setting up autogenerate plugin alembic.autogenerate.constraints
INFO  [alembic.runtime.plugins] setting up autogenerate plugin alembic.autogenerate.defaults
INFO  [alembic.runtime.plugins] setting up autogenerate plugin alembic.autogenerate.comments
INFO  [alembic.autogenerate.compare.tables] Detected added table 'things'
Generating ...\alembic\versions\9524a8d251a5_create_things.py ...  done
```

打开生成的文件（文件名 = `<revision>_<你的说明>.py`），实测内容如下——**这是你今天最该亲手读的东西**：

```python
"""create things

Revision ID: 9524a8d251a5
Revises:
Create Date: 2026-11-18 15:43:51.427830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9524a8d251a5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('things',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('things')
    # ### end Alembic commands ###
```

### 2.4 读这份文件：自问四答（先自己答，再往下看）

**问 1：`down_revision = None` 说明了什么？**

> 这个文件**不接在任何文件后面**——它是这条链的第一环。Alembic 决定执行顺序的唯一依据就是每个文件的 `down_revision`：拿到当前版本号后顺着这个字段一级级回溯，None 就是回溯的尽头。所以链的顺序写在文件内容里，跟文件名、创建时间都无关。

**问 2：`upgrade()` 里为什么是 `op.create_table(...)` 而不是一句 `CREATE TABLE` SQL？**

> 因为**迁移文件是代码，不是 SQL 文本**。`op.create_table` 是一层中间表示：你声明"要建这张表、有这些列"，Alembic 在执行时按**当前连接的数据库方言**翻译——同一份文件，在 sqlite 上生成 `CREATE TABLE things (...)`，在 MySQL 上会生成带 `ENGINE`/字符集的版本。写死 SQL 就丢掉了跨库能力和方言适配，这正是你项目里"同一套模型既要 sqlite（测试）又要 MySQL（真库）"所需要的。

**问 3：`downgrade()` 里的 `op.drop_table` 是谁写的？为什么必须写？**

> **autogenerate 自动反写的**。它的工作方式是：对"模型元数据 vs 真实库"做 diff，正向操作生成进 `upgrade()`，同时机械地生成逆向操作进 `downgrade()`（建表 ↔ 删表、加列 ↔ 删列）。
> 必须写，因为 `downgrade` 是回滚的唯一凭证——没有它，出问题只能手工逆向写 SQL。
> **但机器反写的 downgrade 只能当草稿**：它只对"结构对称"负责，不懂数据、不懂意图——`drop_column` 反写成 `add_column` 时，那一列的数据已经没了；重命名它反写成"删旧列 + 建空新列"而不是改名。所以下面的"please adjust"和它是一对提醒。

**问 4：中间那行 `# ### commands auto generated by Alembic - please adjust! ###` 在提醒什么？**

> 提醒：**上下这两条注释之间的命令是机器 diff 出来的，还没经过任何人的判断**。autogenerate 有固定盲区（重命名、数据搬迁、部分类型变更），这些场景它都会生成"能跑但语义错误"的破坏性命令。所以流程是 **生成 → 人工过一遍 → 才 upgrade**，"autogenerate 完成"不等于"迁移完成"（§六 有真实危险案例）。

### 2.5 执行并验证

```powershell
# Windows PowerShell（仍在 scratch\alembic_demo）
& ..\..\kb-service\.venv\Scripts\alembic.exe upgrade head
& ..\..\kb-service\.venv\Scripts\alembic.exe current
```

实测输出：

```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9524a8d251a5, create things
...
9524a8d251a5 (head)
```

> 注意第二行 `Will assume non-transactional DDL.`——**sqlite 上也会打印**（不是只有 MySQL 才有，§四 4.3 详细说）。

再往后撤一步，看它真能回去：

```powershell
& ..\..\kb-service\.venv\Scripts\alembic.exe downgrade -1
& ..\..\kb-service\.venv\Scripts\alembic.exe current
```

实测输出（最后一行是空的，表示"一步都没有"）：

```
INFO  [alembic.runtime.migration] Running downgrade 9524a8d251a5 -> , create things
...
```

最后直接看库里的版本表，把抽象概念变成两个查询。**不要用 `python -c "..."`**——查询里同时有单双引号，PowerShell 会把转义吃掉直接报 `SyntaxError`（实测踩过）。用一个 8 行的小脚本代替：

```powershell
# Windows PowerShell（在 scratch/alembic_demo 目录下）
& ..\..\kb-service\.venv\Scripts\python.exe inspect_demo.py
```

```bash
# Git Bash / Linux / macOS
../../kb-service/.venv/Scripts/python.exe inspect_demo.py
```

脚本内容（`inspect_demo.py`，已放在 demo 目录里）：

```python
import sqlite3

c = sqlite3.connect("demo.db")
print("表:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")])
print("alembic_version:", list(c.execute("SELECT * FROM alembic_version")))
```

> **为什么不用 `python -c`**：Python 代码里必须同时出现双引号（字符串）和单引号（SQL 里的 `'table'`），PowerShell 5.1 对嵌套引号的转义规则和 bash 不同，`\"` 会被提前截断——报 `unterminated string literal`。**嵌套引号的命令一律写成脚本文件**，一次绕开所有转义问题。

`downgrade` 之后的结果是 `['alembic_version']` 和 `version: []`——**`things` 表没了，版本记录也清空了**。再 `upgrade head` 一次，表回来、版本号回填。

**5 分钟到这里就够了**。你亲眼看见了：生成什么、改哪里、文件长什么样、跑起来什么日志、怎么退。

> 演练完可以整个删掉（它在 `scratch/` 里，本来就不进 git）：`Remove-Item -Recurse -Force ..\..\scratch\alembic_demo`。
> 但建议先留着，等 §十 动手时对照着看。


---

## §三 三个核心概念 [A]

### 3.1 revision 链：迁移是一条单链表 [A]

每个迁移文件头上有两个字段：

```python
revision = "b7d31..."        # 我是谁
down_revision = "2f1c9..."   # 我接在谁后面（None = 我是第一个）
```

`upgrade head` 执行时，Alembic 读**数据库里**的当前版本，在链上算出"从当前到 head 要经过哪几个文件"，然后**按顺序逐个执行**。

```
(None) → 2f1c9(建三表) → a83d2(加索引) → e91f4(改列) ← head
                ↑ 数据库现在记着这个            ↑ 目标
              → 要执行 a83d2、e91f4 两步
```

两条推论，都很实用：

- **顺序由 `down_revision` 决定，不由文件名或时间决定**。所以两个人同时基于同一个旧版本生成迁移，链会分叉——这时才需要 `alembic merge`（L 级，今天不碰）。
- 想回到某一步：`alembic downgrade <revision>`；想全撤：`alembic downgrade base`。`-1` 表示"往回一步"，`+1` 表示"往前一步"。

### 3.2 `alembic_version` 表：唯一真相 [A]

Alembic 在你的库里建一张极小的表：

```sql
SELECT * FROM alembic_version;
-- +--------------+
-- | version_num  |
-- +--------------+
-- | a83d2f...    |
-- +--------------+
```

**一行一列**，值就是"当前跑到哪个 revision"。这句话要记住三件事：

1. **它是判断"要不要迁移"的唯一依据**。所以 `upgrade head` 可以随便重复跑——已经在 head 上就什么都不做（幂等）。
2. **它跟着数据库走，不跟着代码走**。换台机器、换个人跑，只要连的是同一个库，读到的就是同一个状态。
3. **绝不用手改它**。手改等于改历史记录：结构没变但标记变了，下一次迁移会基于错误的假设执行，可能直接毁数据。

> 由此可以直接回答一个常见困惑："**测试库和线上库结构不一致，怎么发现？**"
> 看两张表的 `alembic_version` 是不是同一个 revision；再看 `alembic check`（1.9+）有没有待生成的变更。

### 3.3 `autogenerate` 到底在比较什么 [A]

命令是 `alembic revision --autogenerate`，但它真正做的事是：

```
diff( 模型元数据 Base.metadata , 真实数据库的当前结构 )
        ↑ 你代码里的理想           ↑ information_schema 里读出来的现状
```

然后**把差异翻译成步骤**写进迁移文件。

这个定义能推出三条必须知道的结论：

| 情形 | autogenerate 的反应 | 危险程度 |
|---|---|---|
| 模型里有、库里没有（新表/新列/新索引） | 生成 `create_*` | 安全 |
| 库里有、模型里没有（手工加的索引、别人建的表） | 生成 **`drop_*`** | **危险：会删掉线上东西** |
| 改了列名 | 生成 **`drop_column` + `add_column`** | **极度危险：等于删列重建，数据全丢** |

第 3 条是今天最重要的一个认知：**Alembic 不认识"重命名"**。它只看名字，`title` 变成 `doc_title` 在它眼里就是"少了 title、多了 doc_title"。所以**重命名必须手写迁移**（把生成的两句改成一句 `op.alter_column(..., new_column_name=...)`），或者在生成后手工改。

第 2 条直接决定了今天第一件事：**为什么要 `DROP DATABASE kb_dev` 重建**。你库里那三个索引（`ix_documents_kb_created` 等）是 D3 手工 DDL 建的，模型里没有。如果直接对着现有库跑 autogenerate，它会建议把它们**删掉**——而且这是"正确"的，因为它认为模型才是真相。

> 一句话总结这一节：**autogenerate 是 diff 工具，不是修复工具。差异的方向它不管，全都如实写出来。**

---

## §四 机制：`upgrade head` 到底做了什么 [B]

### 4.1 执行五步

```
① 读 alembic.ini → 定位 script_location（alembic 目录）
② 跑 env.py：
     - 建立连接（engine_from_config，URL 来自我们 set_main_option 的那行）
     - 把 target_metadata 交给 context
③ 查库里 alembic_version 表 → 得到 current
④ 在链上算路径：current → head 要执行哪几个文件
⑤ 逐个执行 upgrade()，每执行完一个就 UPDATE alembic_version
```

由此能解释三个现象：

- **`env.py` 报 import 错误时，连 `alembic current` 都会失败**——因为 env.py 是先跑起来的，它不通过就什么都没发生。
- **`alembic history` 不连库也能跑**（它只读文件），但 `current` 必须连库。
- **DDL 语句在 `env.py` 里的 `context.begin_transaction()` 里执行**——但这个"事务"在 MySQL 上名不副实，见 4.3。

### 4.2 offline 模式：不连库，只把 SQL 打出来 [B]

```powershell
# Windows PowerShell
& .\.venv\Scripts\alembic.exe upgrade head --sql
```

它会打印出将要执行的 DDL，**不连数据库、不执行**。两个用途：

- 提交前自查："我这条迁移到底会发什么 SQL？"（尤其在你手改过迁移文件之后）
- 交给 DBA 走审批流程（很多公司明确规定应用不能直接跑 DDL）

### 4.3 MySQL 的 DDL 不进事务——接昨天的知识 [B]

`env.py` 里有一句 `with context.begin_transaction():`，看着像"迁移整体是个事务，失败全回滚"。**在 MySQL 上不是。**

跑迁移时，日志里会出现这句（**sqlite 和 MySQL 都会打印，实测确认**）：

```
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
```

这句话的意思是"Alembic 判断这个方言的 DDL 不能靠事务保护，所以它不把整个迁移包成一个可回滚单元"。**MySQL 的 DDL 语句（`ALTER`/`CREATE`/`DROP`）会隐式提交**，你昨天在 D4 学的 `autocommit` 就是同一件事的另一面。后果很具体：

```
一个迁移里有三步：
  ① ALTER TABLE documents ADD COLUMN summary TEXT;   ✅ 成功（已隐式提交）
  ② UPDATE documents SET summary = '';               ❌ 报错（比如超时）
  ③ ALTER TABLE documents MODIFY summary TEXT NOT NULL;
→ 迁移失败，但 ① 已经生效了。库停在"一半"的状态，alembic_version 没更新。
```

所以线上迁移的铁律是三条：

1. **一个迁移只做一件事**，别把建表、改列、填数据塞进同一个文件——踩雷时损失面积小。
2. **迁移前备份**（或至少确认有 PITR/binlog）。因为失败之后 Alembic 帮不了你，只能 `forward fix`（写一个新迁移把库修回目标状态）或人工对账。
3. **先 dry-run**：`upgrade head --sql` 看一遍语句，敏感操作（`DROP`）单独确认。

### 4.4 演进一次：加索引，再撤回 [B]

真实的一次结构演进长这样（今天 §十 你会亲手做）：

```python
# 生成的迁移（或手写）
def upgrade() -> None:
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
```

跑 `upgrade head` → `SHOW INDEX FROM documents` 能看到新索引；跑 `downgrade -1` → 索引消失，版本回到上一步。

**但要注意一个反向的坑**：如果你只在数据库里加了索引、**没在模型里加 `index=True`**，那么下一次 autogenerate 会把"库里多出来的这个索引"当成垃圾，生成一条 `drop_index` 迁移。**迁移文件和模型必须同步改**，这是迁移工作里最常见的失误。

---

## §五 为什么 `create_all` 不能上线（七条） [A]

这段是 D5 的面试主菜，也是周计划里点名要"写清"的东西。

| # | 理由 | 具体后果 |
|---|---|---|
| 1 | **只建不改** | `create_all(checkfirst=True)` 只建"不存在的表"。已有表加列、改类型、加索引它**一句都不发**。线上少一列 → 代码 500 |
| 2 | **没有版本记录** | 无法回答"线上现在是哪个结构"，多环境必然漂移，且漂移无法检测 |
| 3 | **无法回滚** | 出问题只能手工逆向写 SQL，没有成对的 `downgrade` |
| 4 | **表达不了数据迁移** | 改列名、拆表、回填默认值这类"结构+数据一起动"的事，`create_all` 完全无能为力 |
| 5 | **并发启动竞态** | 多实例同时启动都跑 `create_all`，`checkfirst` 的"查一下再建"中间有窗口（TOCTOU），会撞 `table already exists` 甚至元数据锁 |
| 6 | **不可 review** | 迁移文件是 PR 里能被人读、能被人拦下的文件；`create_all` 是运行时副作用，没人看得见它要干什么 |
| 7 | **权限** | 应用账号不该有 DDL 权限（最小权限原则）。迁移应由独立账号/独立步骤执行，跑完即退 |

一句话版本：

> **`create_all` 是"在开发机上省事"，Alembic 是"对线上负责"。** 前者是给人用的，后者是给流程用的。

---

## §六 易错点表 [A]

| 认知 | 正确 |
|---|---|
| "迁移就是备份" | 迁移只改**结构**，不保数据。它和备份是两件事，都要有 |
| "`downgrade` 能把数据还回来" | 只还原结构。`drop_column` 那一列的数据，`downgrade` 里只会 `add_column` 一个空列回来 |
| "autogenerate 生成的就直接跑" | 必须人工读一遍。重命名会被写成 `drop + add`（数据全丢）；`drop_*` 必须先确认是不是自己要的 |
| "改完库就行了，模型回头再补" | 下次 autogenerate 会把你的手工改动当成垃圾删掉。**模型、迁移、库三者必须一致** |
| "`sqlalchemy.url` 写在 alembic.ini 里最省事" | 那是把密码写进 git。要从 `settings` 读（本项目同款做法） |
| "MySQL 迁移失败会自动回滚" | DDL 隐式提交，回滚不了。日志里那句 `Will assume non-transactional DDL` 就是提醒 |
| "`create_all` 留着无害，反正表都在" | 线上多实例启动时它是竞态源；而且它会"顺手"建出你不想要的表（比如某个测试用的模型忘了排除） |
| "迁移文件写完就不能改" | **还没合并且没在任何环境执行过的迁移可以改**；一旦别人跑过 / 线上跑过，就只能新增迁移来修 |
| "`alembic_version` 坏了手改一下就行" | 手改等于篡改历史，下一次迁移会基于错误假设执行 |

---

## §七 命令速查 [B]

```powershell
# Windows PowerShell（在 kb-service 目录下）
& .\.venv\Scripts\alembic.exe init -t generic alembic      # 初始化（只做一次）
& .\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
& .\.venv\Scripts\alembic.exe revision -m "hand written"    # 手写迁移（不给 --autogenerate）
& .\.venv\Scripts\alembic.exe upgrade head                  # 升到最新
& .\.venv\Scripts\alembic.exe upgrade +1                    # 只升一步
& .\.venv\Scripts\alembic.exe downgrade -1                  # 退一步
& .\.venv\Scripts\alembic.exe downgrade base                # 全撤
& .\.venv\Scripts\alembic.exe current                       # 现在在哪一步
& .\.venv\Scripts\alembic.exe history --verbose             # 链上所有步骤
& .\.venv\Scripts\alembic.exe upgrade head --sql            # 干跑，只打印 SQL
```

```bash
# Git Bash / Linux / macOS
./.venv/Scripts/alembic.exe init -t generic alembic
./.venv/Scripts/alembic.exe revision --autogenerate -m "describe change"
./.venv/Scripts/alembic.exe upgrade head
./.venv/Scripts/alembic.exe downgrade -1
./.venv/Scripts/alembic.exe current
# 真 Linux / CI 里 venv 路径是 .venv/bin/alembic
```

---

## §八 面试问法 [A]

**30 秒版**（背这一段就够应付第一层）：

> Alembic 是 SQLAlchemy 生态的迁移工具：每个结构变化写成一个带 `revision`/`down_revision` 的 Python 文件，串成一条链；数据库里用 `alembic_version` 表记录当前跑到哪一步。`upgrade head` 就是"读当前版本 → 算路径 → 按顺序执行 → 更新版本"，所以它是幂等的。`autogenerate` 是把模型元数据和真实库做 diff 后生成迁移，但它不认识重命名，生成的东西必须人工 review。`create_all` 不能上线，因为它只建不改、没有版本记录、不能回滚。

**追问链**：

- **第一层**：迁移失败怎么回滚？
  → MySQL 的 DDL 隐式提交，不能整体回滚。所以要小步迁移（一个迁移一件事）+ 迁移前备份 + 失败后 forward fix（新增迁移把结构修回目标态），而不是指望 `downgrade`。
- **第二层**：怎么保证多人协作时不冲突？
  → 迁移文件进 git、走 code review；基于最新版本的 head 生成；同时基于旧版本生成的会分叉，需要 `alembic merge` 合并成多父节点；CI 里跑一次 `upgrade head` 验证可执行性。
- **第三层**：线上零停机加索引怎么做？
  → MySQL 8 的 `CREATE INDEX` 默认 `ALGORITHM=INPLACE`、允许并发 DML，但会短暂持有元数据锁，大表上仍可能抖；生产通常用 `pt-online-schema-change` / `gh-ost` 复制表加索引再切换，或者低峰执行。迁移文件里可以手写 `op.execute("ALTER TABLE ... ALGORITHM=INPLACE, LOCK=NONE")` 明确要求。**这一步必须结合你项目里 `documents` 表 5000 行——真实规模下不用 OSS 工具，但要能说出"数据量再上一个量级就该上"的判断。**

---

## §九 闭卷自测（合上教材做）

**题目清单**（先看题，再往下翻答案）：

1. `create_all` 和 Alembic 的区别，一句话。
2. `down_revision` 是干什么的？`None` 代表什么？
3. `alembic_version` 表里有什么？为什么不能手改？
4. `autogenerate` 在比较哪两样东西？
5. 把 `title` 改名成 `doc_title`，直接 autogenerate 会发生什么？
6. `upgrade head` 为什么可以重复跑？
7. MySQL 上迁移失败为什么不能整体回滚？日志里哪句话在提醒你？
8. 三种情况下必须人工 review 生成的迁移，是哪三种？
9. 迁移文件和模型不同步，会导致什么后果？
10. 线上加索引怎么做到不停机？（答不出完整方案，能说出"在线 DDL 工具 + 低峰 + 元数据锁"也算过）

<details>
<summary>答案（做完再看）</summary>

1. `create_all` 是"现在把缺的表建出来"的动作；Alembic 是"把结构变化记录成一串可执行、可核对、可回滚的历史"。
2. 声明"我这一步接在哪一步之后"，是链表的指针；`None` 表示它是链的第一环（第一个迁移）。
3. 一行一列 `version_num`，记录当前执行的 revision。手改等于篡改历史，下一次迁移会基于错误假设执行（可能删数据或改错列）。
4. 模型元数据 `Base.metadata`（代码里的理想结构）和真实数据库的当前结构（由 `information_schema` 读出）。
5. 生成 `drop_column("title")` + `add_column("doc_title")`——等价于删列重建，**数据全丢**。必须改成 `op.alter_column(..., new_column_name=...)` 手写迁移。
6. 因为它先读 `alembic_version` 算出"当前 → head"的路径；已经在 head 上就没有路径可走，什么都不做（幂等）。
7. 因为 MySQL 的 DDL 会隐式提交，事务包不住。日志里那句 `INFO [alembic.runtime.migration] Will assume non-transactional DDL.` 就是在提醒。
8. ① 出现 `drop_*`（库里有、模型里没有）② 出现 `drop_column` + `add_column`（疑似重命名）③ 涉及 `NOT NULL`、类型收窄、唯一约束这类可能因存量数据失败的操作。
9. 下一次 autogenerate 会把库里的手工改动当成"多余"并生成删除语句；也就是**迁移工具会主动把你的结构改回去**。
10. MySQL 8 默认在线 DDL（`ALGORITHM=INPLACE`、`LOCK=NONE`）能在 DML 不停的情况下建索引，但会短暂拿元数据锁；大表用 `gh-ost` / `pt-online-schema-change` 复制表切换，安排在低峰执行。

</details>

---

## §十 动手任务 [A]

### 前置：把实验库推翻重建（周计划里定的，做之前先确认）

> ⚠️ **这一步会删掉 `kb_dev`**：D3 建的 5000 行实验数据、D4 的锁实验遗留，全部消失。
> 已有的实测结论都在 `progress/week7/*-实测记录.md` 里，库里没有不可再生的东西。
> 但**这是不可逆操作**，你自己敲，我不代手。

`kb` 账号有 `kb_dev.*` 的全部权限但没有 `CREATE DATABASE` 的全局权限，所以重建用 `root`（本机免密，前面探针一直这么连）：

```powershell
# Windows PowerShell（在 kb-service 目录下）
& .\.venv\Scripts\python.exe -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3307,user='root',password=''); cur=c.cursor(); cur.execute('DROP DATABASE IF EXISTS kb_dev'); cur.execute('CREATE DATABASE kb_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci'); print('recreated')"
```

验证：

```powershell
& .\.venv\Scripts\python.exe -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3307,user='root',password='',database='kb_dev'); cur=c.cursor(); cur.execute('SHOW TABLES'); print('tables:', cur.fetchall())"
```

应该是 `tables: ()`——**空库，一张表都没有**。这是迁移的起点。

### 交付物清单（四个）

| # | 交付物 | 验收标准（判什么，不说怎么写） |
|---|---|---|
| 1 | `alembic.ini` + `alembic/env.py` 改好 | `env.py` 里 `target_metadata` **不是 None**；数据库 URL **不在 `alembic.ini` 里出现明文密码**（从 `settings` 取） |
| 2 | 第一条迁移：建三张表 | `alembic upgrade head` 成功；`SHOW TABLES` 里有 `knowledge_bases` / `documents` / `chunks` / `alembic_version`；迁移文件里 `upgrade()` 与 `downgrade()` **成对** |
| 3 | 第二条迁移：给 `documents.status` 加索引，然后回滚 | `upgrade head` 后 `SHOW INDEX FROM documents` 出现该索引；`downgrade -1` 后索引消失、`alembic current` 退回上一版；**模型里也同步加了 `index=True`** |
| 4 | 三句话（闭卷写，写在实测记录里） | ① `create_all` 为什么不能上线（至少三条理由）② autogenerate 生成的迁移为什么必须人工读（举一个具体危险）③ 迁移失败了怎么办 |

外加：`& .\.venv\Scripts\python.exe scripts\check.py` 全绿。

> **修正（实测）**：`alembic/` 目录**不在** `check.py` 的检查范围里——它的 `TARGETS = ["src", "tests", "scripts", "conftest.py"]`。所以 `env.py` 的 import 排序不会让门禁变红（但仍建议把 import 放文件顶部，不然阅读时跳来跳去）。

### 提示阶梯（卡 10 分钟再看下一层）

<details>
<summary>第一层：init 之后 alembic 目录该放在哪</summary>

放在 `kb-service/alembic/`（项目根下、`src/` 同级）。`alembic.ini` 也在 `kb-service/` 根。这样所有 alembic 命令都在 `kb-service` 目录下跑，`prepend_sys_path = .` 能找到包。
</details>

<details>
<summary>第二层：env.py 里 import 自己的模型报 ModuleNotFoundError</summary>

`env.py` 是独立进程，不吃 pytest 的路径配置。两条路：① 确认 `kb_service` 已经装在 venv 里（`& .\.venv\Scripts\python.exe -c "import kb_service; print(kb_service.__file__)"`）；② 在 `env.py` 顶部把项目根插进 `sys.path`（和 §二 demo 里 `sys.path.insert` 同一招）。
</details>

<details>
<summary>第三层：autogenerate 说 No changes detected</summary>

按顺序排查三件事：① `target_metadata` 还是 `None` 吗（最常见）；② 模型模块真的被 import 了吗（`Base.metadata.tables` 里有没有三张表——可以在 env.py 里临时 `print(Base.metadata.tables.keys())`）；③ 库里是不是已经有表了（`SHOW TABLES`）。
</details>

<details>
<summary>第四层：迁移跑成功了，但 SHOW TABLES 里少表 / 类型不对</summary>

读生成的迁移文件，逐列和 `models.py` 对比。两个已知差异点：`DateTime(timezone=True)` 在 MySQL 上落成 `DATETIME`（**时区信息不存库**，这是 D1b 讲过的老坑）；`Uuid` 在 MySQL 上落成 `CHAR(32)`。如果迁移里出现 `sa.Uuid()` 而 MySQL 报错，说明方言不支持，需要在模型里改用显式 `String(32)` 或用 `TypeDecorator`——**先看报错原文再决定，别猜**。
</details>

<details>
<summary>第五层：第二条迁移（加索引）怎么生成</summary>

两条路都合法：① 在 `models.py` 的 `status` 列上加 `index=True`，然后 `revision --autogenerate -m "add status index"`（推荐，模型与库同步）；② `alembic revision -m "add status index"` 手写一个空迁移，自己在 `upgrade()` 里写 `op.create_index(...)`。选 ① 之后一定要打开生成的文件确认它写的是 `create_index` 而不是别的。
</details>

### 时间预估

| 段 | 内容 | 时长 |
|---|---|---|
| 第 1 段 | 重建库 + init + 改 env.py + 第一条迁移 | ~60min |
| 第 2 段 | 加索引迁移 + downgrade 回滚 + 门禁 | ~45min |
| 第 3 段 | 三句话 + 实测记录 | ~20min |

---

## §十一 业务链条三问 [A]

**① 哪个用户可见行为依赖它？**
没有直接的用户行为——迁移不服务请求。它服务的是**部署**：每一次"这个版本能上线"的动作，都依赖"库结构已经是这个版本假设的样子"。间接后果是用户可见的：少一列 → 上传文档 500；多一个索引 → 列表页从 2s 变 20ms。

**② 不做会怎样？**
把 `create_all` 留在启动代码里，或者靠手工 ALTER：三个环境结构漂移，线上某次改列忘了跑，接口在特定数据上炸；出事时无法回答"线上是哪个结构"，也无法回滚。**这是那种"平时完全无症状、在发版当晚集中爆发"的问题。**

**③ 可复现指标（个人项目可测的）**

| 指标 | 怎么测 | 今天能不能测出 |
|---|---|---|
| 迁移是否可重复执行 | 连跑两次 `alembic upgrade head`，第二次应零变更、零报错 | 能 |
| 结构是否与模型一致 | `alembic revision --autogenerate -m "should be empty"` 生成的文件 `upgrade()` 为空（然后删掉这个文件） | 能 |
| 版本是否可回退 | `downgrade -1` → `upgrade head` 一个来回，`SHOW TABLES` / `SHOW INDEX` 前后一致 | 能 |
| 迁移耗时 | 记录 `upgrade head` 在 0 行库上的耗时 | 能（但**不代表线上大表耗时**，线上要按行数放大，标"待有真实负载"） |

> 第三问不许编百分比：本项目没有真实流量，所有"性能提升 X%"的说法一律标"待有真实负载"。

---

## 页脚

`改：D5 教材初稿`
