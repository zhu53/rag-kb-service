-- D3 索引探针（第二组）：补对照，分离"写法失效"与"选择性太差"
-- 用途：第一组里 D3（后缀 LIKE）与 D5（!=）都退化成 ALL，不能直接断言"写法失效"

USE kb_dev;

DROP TABLE IF EXISTS probe_docs2;
CREATE TABLE probe_docs2 (
  id BIGINT NOT NULL AUTO_INCREMENT,
  kb_id CHAR(36) NOT NULL,
  status VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET SESSION cte_max_recursion_depth = 100000;

INSERT INTO probe_docs2 (kb_id, status, title, created_at)
WITH RECURSIVE seq AS (
  SELECT 1 AS n UNION ALL SELECT n + 1 FROM seq WHERE n < 50000
)
SELECT CONCAT('kb-', LPAD(n % 50, 3, '0')),
       ELT(1 + n % 3, 'pending', 'ready', 'failed'),
       CONCAT('文档标题-', n),
       DATE_ADD('2026-01-01 00:00:00', INTERVAL n MINUTE)
FROM seq;

CREATE INDEX idx2_kb ON probe_docs2 (kb_id);
CREATE INDEX idx2_status ON probe_docs2 (status);
CREATE INDEX idx2_title ON probe_docs2 (title);

-- ===== 1. 后缀通配符：换高选择性前缀 =====
SELECT '--- 1a LIKE 高选择性前缀（约 11 行） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE title LIKE '文档标题-499%';

SELECT '--- 1b LIKE 低选择性前缀（约 2 万行） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE title LIKE '文档标题-1%';

-- ===== 2. != 在「有索引但区分度低」的列上 =====
SELECT '--- 2a status != ready（status 有索引，命中约 67%） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE status != 'ready';

SELECT '--- 2b status = ready（等值，但仍约 33%） ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE status = 'ready';

-- ===== 3. 本项目真实查询：kb_id + status 双条件 =====
SELECT '--- 3a 只有单列索引 idx2_kb ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE kb_id = 'kb-007' AND status = 'ready';

CREATE INDEX idx2_kb_status ON probe_docs2 (kb_id, status);

SELECT '--- 3b 加复合索引 (kb_id, status) ---' AS exp;
EXPLAIN SELECT * FROM probe_docs2 WHERE kb_id = 'kb-007' AND status = 'ready';

-- ===== 4. 回表到底贵多少：EXPLAIN ANALYZE 实测 =====
SELECT '--- 4a 覆盖索引：只取索引列 ---' AS exp;
EXPLAIN ANALYZE SELECT kb_id, status FROM probe_docs2 WHERE kb_id = 'kb-007';

SELECT '--- 4b 要回表：多取 title ---' AS exp;
EXPLAIN ANALYZE SELECT kb_id, status, title FROM probe_docs2 WHERE kb_id = 'kb-007';

SELECT '--- 4c 全表扫：无可用索引 ---' AS exp;
EXPLAIN ANALYZE SELECT * FROM probe_docs2 WHERE title LIKE '%标题-499%';

DROP TABLE IF EXISTS probe_docs2;
SELECT 'probe_docs2 已清理' AS done;
