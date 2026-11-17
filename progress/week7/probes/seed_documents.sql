-- D3 动手任务 · 第一步：给真表灌 5000 行（不是探针表，是 documents 本体）
-- 用法（PowerShell，必须在 kb-service 目录外也能跑，走绝对路径）：
--   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
--   & F:\WorkBuddy\2026-10-20-08-44-29\tools\mysql-8.4.0\bin\mysql.exe -h 127.0.0.1 -P 3307 -uroot -e "source F:/WorkBuddy/2026-10-20-08-44-29/python-backend-roadmap/progress/week7/probes/seed_documents.sql"
--
-- 前提：三张表已经建好（见教材 §十一 提示一，先跑 create_all）
-- 三个必踩的坑，写在这里省你三次报错：
--   ① documents.id 是 CHAR(32)（SQLAlchemy Uuid 的 MySQL 映射），不是 CHAR(36)
--      → UUID 必须用 REPLACE(UUID(),'-','') 去掉横线；带横线是 36 位，严格模式直接 1406
--   ② doc_count / created_at / updated_at 在 DDL 层**没有默认值**
--      模型里的 default=0 只是 Python 侧默认，裸 SQL 灌数据不会替你填 → NOT NULL 报 1364
--   ③ documents.kb_id 有外键 → 必须先有 knowledge_bases 父行，否则 1452
--      （这条正好复习 D2 的外键拒绝孤儿）

USE kb_dev;

-- 清场：重复跑不叠加
DELETE FROM chunks;
DELETE FROM documents;
DELETE FROM knowledge_bases;

-- ① 一条父行：id 用 32 个 a，方便你后面手写 WHERE kb_id='aaaa...' 不用复制粘贴 UUID
INSERT INTO knowledge_bases (id, owner_id, name, description, doc_count, created_at, updated_at)
VALUES (REPEAT('a', 32), REPEAT('b', 32), 'seed-kb', NULL, 0, UTC_TIMESTAMP(), UTC_TIMESTAMP());

-- ② 5000 条文档
-- cte_max_recursion_depth 默认 1000，不调大会报 3636
SET SESSION cte_max_recursion_depth = 100000;

INSERT INTO documents (id, kb_id, title, status, chunk_count, created_at, updated_at)
WITH RECURSIVE seq AS (
  SELECT 1 AS n

  UNION ALL

  SELECT n + 1 FROM seq WHERE n < 5000
)
SELECT REPLACE(UUID(), '-', ''),                          -- 坑①：32 位，不带横线
       REPEAT('a', 32),                                   -- 全部挂在同一个 kb 下
       CONCAT('doc-', LPAD(n, 5, '0')),                   -- doc-00001 ... doc-05000
       -- status 故意做成偏斜分布：ready 4500 / pending 400 / failed 100
       -- 区分度只有 3/5000 → 这就是 §8 说的"低区分度列"，为交付物 4 的反例准备
       CASE WHEN n % 50 = 0 THEN 'failed'
            WHEN n % 10 = 0 THEN 'pending'
            ELSE 'ready' END,
       0,                                                 -- 坑②：显式给，DDL 无默认
       DATE_SUB(UTC_TIMESTAMP(), INTERVAL n MINUTE),      -- 时间递减，方便测 ORDER BY DESC
       UTC_TIMESTAMP()
FROM seq;

-- ③ 自检：三条 SELECT 都必须出数
SELECT COUNT(*) AS documents_total FROM documents;
SELECT status, COUNT(*) AS cnt FROM documents GROUP BY status ORDER BY cnt DESC;
SHOW INDEX FROM documents;
