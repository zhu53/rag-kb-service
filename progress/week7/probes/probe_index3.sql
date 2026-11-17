-- D3 索引探针（第三组）：回表到底贵多少（EXPLAIN ANALYZE 实测耗时）
USE kb_dev;

DROP TABLE IF EXISTS probe_docs3;
CREATE TABLE probe_docs3 (
  id BIGINT NOT NULL AUTO_INCREMENT,
  kb_id CHAR(36) NOT NULL,
  status VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET SESSION cte_max_recursion_depth = 100000;
INSERT INTO probe_docs3 (kb_id, status, title, created_at)
WITH RECURSIVE seq AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM seq WHERE n < 50000)
SELECT CONCAT('kb-', LPAD(n % 50, 3, '0')),
       ELT(1 + n % 3, 'pending', 'ready', 'failed'),
       CONCAT('文档标题-', n),
       DATE_ADD('2026-01-01 00:00:00', INTERVAL n MINUTE)
FROM seq;

CREATE INDEX idx3_kb_status ON probe_docs3 (kb_id, status);

SELECT '=== 4a 覆盖索引（只取索引列） ===' AS exp;
EXPLAIN ANALYZE SELECT kb_id, status FROM probe_docs3 WHERE kb_id = 'kb-007';

SELECT '=== 4b 回表（多取 title） ===' AS exp;
EXPLAIN ANALYZE SELECT kb_id, status, title FROM probe_docs3 WHERE kb_id = 'kb-007';

SELECT '=== 4c 全表扫（前置通配符，无索引可用） ===' AS exp;
EXPLAIN ANALYZE SELECT * FROM probe_docs3 WHERE title LIKE '%标题-499%';

DROP TABLE IF EXISTS probe_docs3;
SELECT 'probe_docs3 已清理' AS done;
