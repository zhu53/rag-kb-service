-- probe_pk_order.sql  —— D3 补测：随机 UUID 主键 vs 自增主键，页填充率差多少
-- 结论先不放，跑完自己看 information_schema 的 data_length
-- 用法：mysql -h127.0.0.1 -P3307 -uroot -e "source <绝对路径>"
-- 全程在独立库 kb_probe 里做，跑完自己 DROP，不碰 kb_dev

DROP DATABASE IF EXISTS kb_probe;
CREATE DATABASE kb_probe DEFAULT CHARACTER SET utf8mb4;
USE kb_probe;

SET SESSION cte_max_recursion_depth = 1000000;

-- ── 表 A：随机 UUID 主键（等价项目的 char(32) 主键） ──────────────
CREATE TABLE t_uuid (
  id  CHAR(32) NOT NULL,
  pad CHAR(60) NOT NULL,
  PRIMARY KEY (id)
) ENGINE = InnoDB;

INSERT INTO t_uuid (id, pad)
WITH RECURSIVE seq (n) AS (
  SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 40000
)
SELECT REPLACE(UUID(), '-', ''), REPEAT('x', 60) FROM seq;

-- ── 表 B：自增 BIGINT 主键（行宽完全相同，只换主键） ──────────────
CREATE TABLE t_seq (
  id  BIGINT NOT NULL AUTO_INCREMENT,
  pad CHAR(60) NOT NULL,
  PRIMARY KEY (id)
) ENGINE = InnoDB;

INSERT INTO t_seq (pad)
WITH RECURSIVE seq (n) AS (
  SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 40000
)
SELECT REPEAT('x', 60) FROM seq;

ANALYZE TABLE t_uuid;
ANALYZE TABLE t_seq;

-- ── 对账 1：两边行数一致、UUID 真的互不相同 ────────────────────────
SELECT 't_uuid' AS t, COUNT(*) AS rows_, COUNT(DISTINCT id) AS distinct_id FROM t_uuid
UNION ALL
SELECT 't_seq',  COUNT(*), COUNT(DISTINCT id) FROM t_seq;

-- ── 对账 2：页数 / 碎片 / 平均每页行数 ─────────────────────────────
-- data_length 单位是字节，除以 16384 才是页数
SELECT
  table_name,
  table_rows                                   AS est_rows,
  data_length                                  AS data_bytes,
  data_length / 16384                          AS data_pages,
  ROUND(data_length / 16384 * 16 / 1024, 2)    AS data_MB,
  ROUND(table_rows / (data_length / 16384), 1) AS rows_per_page,
  data_free                                    AS free_bytes,
  index_length                                 AS index_bytes
FROM information_schema.tables
WHERE table_schema = 'kb_probe'
ORDER BY table_name DESC;

-- ── 对账 3：聚簇索引到底占多少页（这个数是权威的） ─────────────────
-- CLUST_INDEX_SIZE = 主键那棵 B+ 树的页数
SELECT
  NAME                     AS table_name,
  NUM_ROWS                 AS rows_,
  CLUST_INDEX_SIZE         AS clust_pages,
  OTHER_INDEX_SIZE         AS secondary_pages,
  ROUND(CLUST_INDEX_SIZE * 16384 / 1024.0 / 1024, 2) AS clust_MB
FROM information_schema.INNODB_TABLESTATS
WHERE NAME LIKE 'kb_probe/t_%';

-- ── 对账 4：反推行宽，核对「32 字节 vs 8 字节」这 24 字节去哪了 ────
-- 期望：t_uuid 每行比 t_seq 正好多 24 字节左右
SELECT
  table_name,
  ROUND(data_length / table_rows, 1)               AS bytes_per_row,
  ROUND(data_length / 16384 / table_rows * 100, 2) AS page_usage_pct
FROM information_schema.tables
WHERE table_schema = 'kb_probe'
ORDER BY table_name DESC;

-- 收摊：想留证据就先别跑下面这行
-- DROP DATABASE kb_probe;
