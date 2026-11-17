-- D3 索引探针：5 组 EXPLAIN 对比实验
-- 用法（PowerShell）：
--   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
--   mysql.exe -h127.0.0.1 -P3307 -uroot -e "source .../probe_index.sql"
-- 全部在 kb_dev 库，探针表建完最后会 DROP

USE kb_dev;

-- ============ 0. 建表 + 造 5 万行数据 ============
DROP TABLE IF EXISTS probe_docs;
CREATE TABLE probe_docs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  kb_id CHAR(36) NOT NULL,
  owner_id CHAR(36) NOT NULL,
  title VARCHAR(200) NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET SESSION cte_max_recursion_depth = 100000;

INSERT INTO probe_docs (kb_id, owner_id, title, status, created_at)
WITH RECURSIVE seq AS (
  SELECT 1 AS n
  UNION ALL
  SELECT n + 1 FROM seq WHERE n < 50000
)
SELECT CONCAT('kb-', LPAD(n % 50, 3, '0')),
       CONCAT('own-', LPAD(n % 20, 3, '0')),
       CONCAT('文档标题-', n),
       ELT(1 + n % 3, 'pending', 'ready', 'failed'),
       DATE_ADD('2026-01-01 00:00:00', INTERVAL n MINUTE)
FROM seq;

SELECT COUNT(*) AS total_rows FROM probe_docs;

-- ============ 实验 A：无索引 vs 单列索引 ============
SELECT '--- A1 无索引：WHERE kb_id = ? ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE kb_id = 'kb-007';

CREATE INDEX idx_kb_id ON probe_docs (kb_id);

SELECT '--- A2 加了 idx_kb_id ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE kb_id = 'kb-007';

-- ============ 实验 B：复合索引与最左前缀 ============
CREATE INDEX idx_kb_created ON probe_docs (kb_id, created_at);

SELECT '--- B1 用到最左列 kb_id + 排序 created_at ---' AS exp;
EXPLAIN SELECT * FROM probe_docs
WHERE kb_id = 'kb-007' ORDER BY created_at DESC;

SELECT '--- B2 只有 kb_id（跳过第二列，索引仍可用） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE kb_id = 'kb-007';

SELECT '--- B3 只有 created_at（跳过最左列，索引失效） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs
WHERE created_at > '2026-02-01 00:00:00';

SELECT '--- B4 created_at 单独建索引再试 ---' AS exp;
CREATE INDEX idx_created ON probe_docs (created_at);
EXPLAIN SELECT * FROM probe_docs
WHERE created_at > '2026-02-01 00:00:00';

-- ============ 实验 C：覆盖索引 vs 回表 ============
SELECT '--- C1 只取索引列（覆盖索引，Using index） ---' AS exp;
EXPLAIN SELECT kb_id, created_at FROM probe_docs WHERE kb_id = 'kb-007';

SELECT '--- C2 取非索引列 title（要回表） ---' AS exp;
EXPLAIN SELECT kb_id, created_at, title FROM probe_docs WHERE kb_id = 'kb-007';

-- ============ 实验 D：五种索引失效写法 ============
SELECT '--- D1 对列用函数 LEFT(title,3) ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE LEFT(title, 3) = '文档标';

SELECT '--- D2 LIKE 前置通配符 ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE title LIKE '%标题-1%';

SELECT '--- D3 LIKE 后缀通配符（能走索引） ---' AS exp;
CREATE INDEX idx_title ON probe_docs (title);
EXPLAIN SELECT * FROM probe_docs WHERE title LIKE '文档标题-1%';

SELECT '--- D4 隐式类型转换：字符串列与数字比较 ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE kb_id = 7;

SELECT '--- D5 不等于 ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE status != 'ready';

SELECT '--- D6 OR 连接两个不同列 ---' AS exp;
EXPLAIN SELECT * FROM probe_docs WHERE kb_id = 'kb-007' OR status = 'ready';

-- ============ 实验 E：EXPLAIN ANALYZE 看真实耗时 ============
SELECT '--- E 无索引与有索引的真实耗时对比（先看 A2 的 rows，再看这个） ---' AS exp;
EXPLAIN ANALYZE SELECT * FROM probe_docs WHERE kb_id = 'kb-007';

-- ============ 清理 ============
DROP TABLE IF EXISTS probe_docs;
SELECT 'probe_docs 已清理' AS done;
