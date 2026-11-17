-- probe_status_volume.sql —— D3 补测：低区分度索引在「小表」和「大表」上的不同命运
-- 问题：documents 只有 5000 行时，status='ready'(90%) 竟然走了索引（rows=2410）。
--      "90% 就不该走索引"这条经验在这里失效了。为什么？
-- 做法：造一张 100 万行的同构表，同样的 90/8/2 分布，看优化器怎么选。
-- 结论在最后那段 EXPLAIN ANALYZE 的实际耗时里。

DROP DATABASE IF EXISTS kb_probe_vol;
CREATE DATABASE kb_probe_vol DEFAULT CHARACTER SET utf8mb4;
USE kb_probe_vol;

SET SESSION cte_max_recursion_depth = 100000;

-- 只建 PK + status 单列索引，行宽与 documents 一致（去掉 kb_id 索引，避免干扰）
CREATE TABLE t_big (
  id          CHAR(32)     NOT NULL,
  kb_id       CHAR(32)     NOT NULL,
  title       VARCHAR(200) NOT NULL,
  status      VARCHAR(20)  NOT NULL,
  chunk_count INT          NOT NULL,
  created_at  DATETIME     NOT NULL,
  updated_at  DATETIME     NOT NULL,
  PRIMARY KEY (id),
  KEY ix_status (status)
) ENGINE = InnoDB;

-- 从 documents 复制 200 份 → 5000 × 200 = 100 万行，status 分布自然保持 90/8/2
INSERT INTO t_big (id, kb_id, title, status, chunk_count, created_at, updated_at)
SELECT
  CONCAT(LEFT(d.id, 28), LPAD(CONCAT(a.n, b.n), 4, '0')),
  d.kb_id, d.title, d.status, d.chunk_count, d.created_at, d.updated_at
FROM kb_dev.documents d
CROSS JOIN (
  SELECT 0 n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
  UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
  UNION ALL SELECT 10 UNION ALL SELECT 11 UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14
  UNION ALL SELECT 15 UNION ALL SELECT 16 UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL SELECT 19
) a
CROSS JOIN (
  SELECT 0 n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
  UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
) b;

ANALYZE TABLE t_big;

SELECT '总行数' AS item, COUNT(*) AS v FROM t_big
UNION ALL SELECT 'ready',   COUNT(*) FROM t_big WHERE status = 'ready'
UNION ALL SELECT 'pending', COUNT(*) FROM t_big WHERE status = 'pending'
UNION ALL SELECT 'failed',  COUNT(*) FROM t_big WHERE status = 'failed';

-- ── 优化器自己怎么选 ────────────────────────────────────────────────
SELECT '--- 优化器选择：ready (90%) ---' AS _;
EXPLAIN SELECT id, title FROM t_big WHERE status = 'ready';
SELECT '--- 优化器选择：failed (2%) ---' AS _;
EXPLAIN SELECT id, title FROM t_big WHERE status = 'failed';

-- ── 实测耗时三连：走索引 vs 强制全表扫 vs 覆盖索引 ───────────────────
-- EXPLAIN ANALYZE 的 actual time 是真实耗时，不是估算
SELECT '--- ANALYZE: ready 走索引 ---' AS _;
EXPLAIN ANALYZE SELECT id, title FROM t_big WHERE status = 'ready';

SELECT '--- ANALYZE: ready 强制全表扫 ---' AS _;
EXPLAIN ANALYZE SELECT id, title FROM t_big IGNORE INDEX (ix_status) WHERE status = 'ready';

SELECT '--- ANALYZE: ready 覆盖索引（只查 status,id）---' AS _;
EXPLAIN ANALYZE SELECT id, status FROM t_big WHERE status = 'ready';

SELECT '--- ANALYZE: failed 走索引 ---' AS _;
EXPLAIN ANALYZE SELECT id, title FROM t_big WHERE status = 'failed';
