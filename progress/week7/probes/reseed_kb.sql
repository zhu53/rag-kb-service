-- reseed_kb.sql  —— D3 动手实验前置：把 5000 篇文档重新分片到 200 个 kb
-- 为什么要做：现在只有 1 个 kb_id，按 kb 查等于全表，索引必然"看起来没用"。
-- 这不是索引的问题，是数据分布的问题。要测索引收益，必须先造出区分度。
-- 用法：mysql -h127.0.0.1 -P3307 -uroot kb_dev -e "source <绝对路径>"
-- 可重复执行：脚本先清掉旧的 kbNNN 行，再重建

USE kb_dev;

-- ── 1) 清掉上次跑残留（只删 kb 前缀的，不动 'aaaa...' 那个原始 kb） ──
DELETE FROM knowledge_bases WHERE id LIKE 'kb%';

-- ── 2) 建 200 个 kb：kb0000010...0 ~ kb0002000...0（共 32 位） ───────
INSERT INTO knowledge_bases (id, owner_id, name, description, doc_count, created_at, updated_at)
WITH RECURSIVE seq (n) AS (
  SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 200
)
SELECT
  CONCAT('kb', LPAD(n, 6, '0'), REPEAT('0', 24)),
  REPEAT('0', 32),
  CONCAT('压测知识库 ', LPAD(n, 3, '0')),
  NULL, 0, NOW(), NOW()
FROM seq;

-- ── 3) 把 5000 篇文档按 id 排序切成 200 组，每组 25 篇 ───────────────
-- 用临时表避开 MySQL 的 ERROR 1093（不能边 UPDATE 边 SELECT 同一张表）
DROP TEMPORARY TABLE IF EXISTS tmp_assign;
CREATE TEMPORARY TABLE tmp_assign (
  id    CHAR(32) NOT NULL PRIMARY KEY,
  kb_id CHAR(32) NOT NULL
);
INSERT INTO tmp_assign (id, kb_id)
SELECT
  id,
  CONCAT('kb', LPAD(NTILE(200) OVER (ORDER BY id), 6, '0'), REPEAT('0', 24))
FROM documents;

UPDATE documents d JOIN tmp_assign t ON d.id = t.id SET d.kb_id = t.kb_id;
DROP TEMPORARY TABLE tmp_assign;

-- ── 4) 回填 doc_count，让元数据和实际行数对得上 ─────────────────────
UPDATE knowledge_bases kb
JOIN (SELECT kb_id, COUNT(*) AS c FROM documents GROUP BY kb_id) s ON kb.id = s.kb_id
SET kb.doc_count = s.c;

-- ── 5) 刷新统计信息（第 3 步把 kb_id 分布全改了，账本必须重算） ─────
ANALYZE TABLE documents;
ANALYZE TABLE knowledge_bases;

-- ── 对账 ────────────────────────────────────────────────────────────
SELECT 'kb 总数'   AS item, COUNT(*) AS v FROM knowledge_bases
UNION ALL SELECT '有文档的 kb', COUNT(DISTINCT kb_id) FROM documents
UNION ALL SELECT '文档总数',   COUNT(*) FROM documents;

SELECT '每 kb 最少篇数' AS item, MIN(c) AS v FROM (SELECT COUNT(*) c FROM documents GROUP BY kb_id) x
UNION ALL SELECT '每 kb 最多篇数', MAX(c) FROM (SELECT COUNT(*) c FROM documents GROUP BY kb_id) y;

SELECT COUNT(*) AS kb_id_基数_应为200
FROM (SELECT 1 FROM documents GROUP BY kb_id) z;
